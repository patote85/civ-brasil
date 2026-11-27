from __future__ import annotations

import os
import tempfile
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import h3
import numpy as np
import numpy.typing as npt
import pyarrow as pa
import pyarrow.parquet as pq
from pyproj import Transformer
from shapely import STRtree
from shapely import transform as shapely_transform
from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry

from pipeline.grid.h3_grid import EQUAL_AREA_PROJ, MunicipioHexRow
from pipeline.sources.ibge_grade import GradeCell
from pipeline.sources.ibge_malhas import Municipio
from pipeline.types import CdMun, H3Index

WeightMethod = Literal["grade_1km", "area_fallback"]

_TO_EQUAL_AREA = Transformer.from_crs("EPSG:4326", EQUAL_AREA_PROJ, always_xy=True)


@dataclass(frozen=True, slots=True)
class DasymetricWeightRow:
    cd_mun: CdMun
    h3: H3Index
    weight: float
    method: WeightMethod


def _project_coords(coords: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    xs, ys = _TO_EQUAL_AREA.transform(coords[:, 0], coords[:, 1])
    return np.column_stack((xs, ys)).astype(np.float64)


def _project_geometry(geom: BaseGeometry) -> BaseGeometry:
    return shapely_transform(geom, _project_coords)


def _projected_hex_polygon(cell: str, cache: dict[str, BaseGeometry]) -> BaseGeometry:
    cached = cache.get(cell)
    if cached is not None:
        return cached
    boundary_latlng = h3.cell_to_boundary(cell)
    ring_lonlat = [(lon, lat) for lat, lon in boundary_latlng]
    poly = _project_geometry(Polygon(ring_lonlat))
    cache[cell] = poly
    return poly


def build_dasymetric_weights(
    municipios: Sequence[Municipio],
    mun_hex_rows: Sequence[MunicipioHexRow],
    grade_cells: Sequence[GradeCell],
) -> list[DasymetricWeightRow]:
    rows_by_mun: dict[str, list[MunicipioHexRow]] = defaultdict(list)
    for row in mun_hex_rows:
        rows_by_mun[row.cd_mun].append(row)

    grade_geoms_proj: list[BaseGeometry] = []
    grade_pops: list[float] = []
    grade_areas: list[float] = []
    for cell in grade_cells:
        if cell.pop <= 0.0:
            continue
        proj = _project_geometry(cell.geometry)
        area = proj.area
        if area > 0.0:
            grade_geoms_proj.append(proj)
            grade_pops.append(cell.pop)
            grade_areas.append(area)

    tree = STRtree(grade_geoms_proj) if grade_geoms_proj else None
    hex_cache: dict[str, BaseGeometry] = {}
    output: list[DasymetricWeightRow] = []

    for municipio in sorted(municipios, key=lambda item: item.cd_mun):
        cd_mun = CdMun(municipio.cd_mun)
        m_rows = sorted(rows_by_mun.get(municipio.cd_mun, []), key=lambda r: r.h3)
        if not m_rows:
            raise ValueError(f"Município sem hexágonos na grade: {cd_mun}")

        if len(m_rows) == 1:
            output.append(
                DasymetricWeightRow(
                    cd_mun=cd_mun,
                    h3=H3Index(m_rows[0].h3),
                    weight=1.0,
                    method="grade_1km" if tree is not None else "area_fallback",
                )
            )
            continue

        mun_proj = _project_geometry(municipio.geometry)
        pop_by_hex: dict[str, float] = {row.h3: 0.0 for row in m_rows}

        if tree is not None:
            candidate_idxs = tree.query(mun_proj, predicate="intersects")
            if len(candidate_idxs) > 0:
                mun_hex_geoms: list[tuple[str, BaseGeometry]] = []
                for row in m_rows:
                    hex_proj = _projected_hex_polygon(row.h3, hex_cache)
                    piece = mun_proj.intersection(hex_proj)
                    if not piece.is_empty and piece.area > 0.0:
                        mun_hex_geoms.append((row.h3, piece))

                piece_tree = STRtree([g for _, g in mun_hex_geoms]) if mun_hex_geoms else None
                if piece_tree is not None:
                    for idx_val in candidate_idxs:
                        idx = int(idx_val)
                        g_geom = grade_geoms_proj[idx]
                        g_pop = grade_pops[idx]
                        g_area = grade_areas[idx]
                        hit_pieces = piece_tree.query(g_geom, predicate="intersects")
                        for p_idx_val in hit_pieces:
                            p_idx = int(p_idx_val)
                            h3_cell, piece_geom = mun_hex_geoms[p_idx]
                            inter_area = piece_geom.intersection(g_geom).area
                            if inter_area > 0.0:
                                pop_by_hex[h3_cell] += g_pop * (inter_area / g_area)

        total_grade_pop = sum(pop_by_hex.values())
        if total_grade_pop > 0.0:
            for row in m_rows:
                output.append(
                    DasymetricWeightRow(
                        cd_mun=cd_mun,
                        h3=H3Index(row.h3),
                        weight=pop_by_hex[row.h3] / total_grade_pop,
                        method="grade_1km",
                    )
                )
        else:
            frac_sum = sum(row.frac for row in m_rows)
            for row in m_rows:
                output.append(
                    DasymetricWeightRow(
                        cd_mun=cd_mun,
                        h3=H3Index(row.h3),
                        weight=row.frac / frac_sum,
                        method="area_fallback",
                    )
                )

    output.sort(key=lambda item: (item.cd_mun, item.h3))
    return output


def reconcile_sum(
    mun_values: Mapping[CdMun, float],
    weights: Sequence[DasymetricWeightRow],
) -> dict[H3Index, float]:
    totals: dict[H3Index, float] = {}
    for row in weights:
        if row.cd_mun not in mun_values:
            raise ValueError(f"Município ausente nos valores de soma: {row.cd_mun}")
        val = mun_values[row.cd_mun]
        totals[row.h3] = totals.get(row.h3, 0.0) + val * row.weight
    return dict(sorted(totals.items()))


def reconcile_rate(
    mun_rates: Mapping[CdMun, float | None],
    weights: Sequence[DasymetricWeightRow],
    mun_pop: Mapping[CdMun, float],
) -> dict[H3Index, float | None]:
    weighted_sum: dict[H3Index, float] = defaultdict(float)
    pop_sum: dict[H3Index, float] = defaultdict(float)
    all_hexes: set[H3Index] = set()

    for row in weights:
        all_hexes.add(row.h3)
        rate = mun_rates.get(row.cd_mun)
        if rate is None:
            continue
        pop = mun_pop.get(row.cd_mun, 0.0)
        hex_pop = pop * row.weight
        if hex_pop <= 0.0:
            continue
        weighted_sum[row.h3] += rate * hex_pop
        pop_sum[row.h3] += hex_pop

    result: dict[H3Index, float | None] = {}
    for cell in sorted(all_hexes):
        denom = pop_sum.get(cell, 0.0)
        result[cell] = (weighted_sum[cell] / denom) if denom > 0.0 else None
    return result


def write_parquet_atomic(table: pa.Table, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=output_path.parent,
        prefix=f".{output_path.name}.",
        suffix=".tmp",
    )
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        pq.write_table(table, tmp_path)
        with tmp_path.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(tmp_path, output_path)
    except BaseException:
        if tmp_path.exists():
            tmp_path.unlink()
        raise
