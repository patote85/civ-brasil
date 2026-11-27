from __future__ import annotations

import json
import os
import tempfile
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import h3
import numpy as np
import numpy.typing as npt
import pyarrow as pa
import pyarrow.parquet as pq
from pyproj import Transformer
from shapely import transform as shapely_transform
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry

from pipeline.sources.ibge_malhas import Municipio

EQUAL_AREA_PROJ = "+proj=aea +lat_0=-32 +lon_0=-60 +lat_1=-5 +lat_2=-42 +ellps=GRS80 +units=m"
H3_RESOLUTION = 5
SP_OFFICIAL_AREA_KM2 = 248_219.0
SQ_METERS_PER_SQ_KM = 1_000_000.0

_TO_EQUAL_AREA = Transformer.from_crs("EPSG:4326", EQUAL_AREA_PROJ, always_xy=True)


@dataclass(frozen=True, slots=True)
class MunicipioHexRow:
    cd_mun: str
    h3: str
    area_km2: float
    frac: float


@dataclass(frozen=True, slots=True)
class HexSummary:
    h3: str
    municipios: tuple[str, ...]
    cd_muns: tuple[str, ...]
    area_km2: float
    municipio_count: int


def _project_coords(coords: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    xs, ys = _TO_EQUAL_AREA.transform(coords[:, 0], coords[:, 1])
    return np.column_stack((xs, ys)).astype(np.float64)


def _project_geometry(geom: BaseGeometry) -> BaseGeometry:
    return shapely_transform(geom, _project_coords)


def _iter_polygons(geom: BaseGeometry) -> Sequence[Polygon]:
    if isinstance(geom, Polygon):
        return (geom,)
    if isinstance(geom, MultiPolygon):
        return tuple(geom.geoms)
    raise ValueError(f"Geometria inesperada: {geom.geom_type}")


def _candidate_cells(geom: BaseGeometry, resolution: int) -> set[str]:
    h3_shape = h3.geo_to_h3shape(geom.__geo_interface__)
    seed_cells = set(
        h3.h3shape_to_cells_experimental(h3_shape, resolution, contain="overlap")
    )
    for poly in _iter_polygons(geom):
        rep = poly.representative_point()
        seed_cells.add(h3.latlng_to_cell(rep.y, rep.x, resolution))
        for lon, lat in poly.exterior.coords:
            seed_cells.add(h3.latlng_to_cell(lat, lon, resolution))

    candidates: set[str] = set(seed_cells)
    for cell in seed_cells:
        candidates.update(h3.grid_disk(cell, 1))
    return candidates


def _projected_cell_polygon(cell: str, cache: dict[str, BaseGeometry]) -> BaseGeometry:
    cached = cache.get(cell)
    if cached is not None:
        return cached
    boundary_latlng = h3.cell_to_boundary(cell)
    ring_lonlat = [(lon, lat) for lat, lon in boundary_latlng]
    poly_proj = _project_geometry(Polygon(ring_lonlat))
    cache[cell] = poly_proj
    return poly_proj


def compute_equal_area_km2(municipios: Sequence[Municipio]) -> float:
    total_m2 = sum(_project_geometry(m.geometry).area for m in municipios)
    return total_m2 / SQ_METERS_PER_SQ_KM


def build_municipio_hex_table(
    municipios: Sequence[Municipio],
    resolution: int = H3_RESOLUTION,
) -> list[MunicipioHexRow]:
    cell_cache: dict[str, BaseGeometry] = {}
    rows: list[MunicipioHexRow] = []

    for municipio in sorted(municipios, key=lambda item: item.cd_mun):
        mun_proj = _project_geometry(municipio.geometry)
        mun_area_m2 = mun_proj.area
        if mun_area_m2 <= 0.0:
            raise ValueError(f"Área não positiva para município {municipio.cd_mun}")

        candidates = sorted(_candidate_cells(municipio.geometry, resolution))
        for cell in candidates:
            hex_proj = _projected_cell_polygon(cell, cell_cache)
            inter_area_m2 = mun_proj.intersection(hex_proj).area
            if inter_area_m2 <= 0.0:
                continue
            rows.append(
                MunicipioHexRow(
                    cd_mun=municipio.cd_mun,
                    h3=cell,
                    area_km2=inter_area_m2 / SQ_METERS_PER_SQ_KM,
                    frac=inter_area_m2 / mun_area_m2,
                )
            )

    rows.sort(key=lambda item: (item.cd_mun, item.h3))
    return rows


def build_hex_summaries(
    rows: Sequence[MunicipioHexRow],
    nomes_por_cd_mun: Mapping[str, str],
) -> list[HexSummary]:
    grouped: dict[str, list[MunicipioHexRow]] = defaultdict(list)
    for row in rows:
        grouped[row.h3].append(row)

    summaries: list[HexSummary] = []
    for cell in sorted(grouped):
        ordered = sorted(grouped[cell], key=lambda item: item.cd_mun)
        cd_muns = tuple(item.cd_mun for item in ordered)
        municipios = tuple(nomes_por_cd_mun[cd] for cd in cd_muns)
        area_km2 = round(sum(item.area_km2 for item in ordered), 6)
        summaries.append(
            HexSummary(
                h3=cell,
                municipios=municipios,
                cd_muns=cd_muns,
                area_km2=area_km2,
                municipio_count=len(ordered),
            )
        )
    return summaries


def write_municipio_hex_parquet(
    rows: Sequence[MunicipioHexRow],
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    schema = pa.schema(
        [
            ("cd_mun", pa.string()),
            ("h3", pa.string()),
            ("area_km2", pa.float64()),
            ("frac", pa.float64()),
        ]
    )
    table = pa.table(
        {
            "cd_mun": [row.cd_mun for row in rows],
            "h3": [row.h3 for row in rows],
            "area_km2": [row.area_km2 for row in rows],
            "frac": [row.frac for row in rows],
        },
        schema=schema,
    )
    fd, tmp_name = tempfile.mkstemp(
        dir=output_path.parent,
        prefix=f".{output_path.name}.",
        suffix=".tmp",
    )
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        pq.write_table(table, tmp_path)
        os.replace(tmp_path, output_path)
    except BaseException:
        if tmp_path.exists():
            tmp_path.unlink()
        raise


def write_sp_hex_json(
    summaries: Sequence[HexSummary],
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "resolution": H3_RESOLUTION,
        "state": "SP",
        "hex_count": len(summaries),
        "total_area_km2": round(sum(item.area_km2 for item in summaries), 6),
        "hexes": [
            {
                "h3": item.h3,
                "municipios": list(item.municipios),
                "cd_muns": list(item.cd_muns),
                "municipio_count": item.municipio_count,
                "area_km2": item.area_km2,
            }
            for item in summaries
        ],
    }
    serialized = (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    fd, tmp_name = tempfile.mkstemp(
        dir=output_path.parent,
        prefix=f".{output_path.name}.",
        suffix=".tmp",
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, output_path)
    except BaseException:
        if tmp_path.exists():
            tmp_path.unlink()
        raise
