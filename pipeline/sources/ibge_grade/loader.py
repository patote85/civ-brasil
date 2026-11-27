from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pyogrio.raw
from shapely import from_wkb, make_valid
from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.geometry.base import BaseGeometry

from pipeline.sources._common import (
    MANIFEST_PATH,
    ArtifactSync,
    Fetcher,
    ensure_raw_artifact,
    read_manifest,
    write_manifest,
)

GRADE_1KM_YEAR = 2022
GRADE_1KM_FILENAME = "BR1KM_20251002.zip"
GRADE_1KM_SHP_MEMBER = "BR1KM.shp"
GRADE_1KM_URL = (
    "https://geoftp.ibge.gov.br/recortes_para_fins_estatisticos/"
    "grade_estatistica/censo_2022/grade_1km/BR1KM_20251002.zip"
)


@dataclass(frozen=True, slots=True)
class GradeCell:
    pop: float
    geometry: BaseGeometry


def load_grade_cells_from_file(
    path: Path,
    bbox: tuple[float, float, float, float] | None = None,
) -> list[GradeCell]:
    if path.suffix.lower() in {".geojson", ".json"}:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or raw.get("type") != "FeatureCollection":
            raise ValueError(f"Grade GeoJSON inválida: {path}")
        features = raw.get("features")
        if not isinstance(features, list):
            raise ValueError(f"Features ausentes em {path}")
        cells: list[GradeCell] = []
        for feat in features:
            if not isinstance(feat, dict):
                continue
            props = feat.get("properties")
            if not isinstance(props, dict):
                continue
            raw_pop = props.get("TOTAL", props.get("POP", 0))
            pop_val = float(raw_pop) if raw_pop is not None else 0.0
            if pop_val <= 0.0:
                continue
            geom = shape(feat["geometry"])
            if not geom.is_valid:
                geom = make_valid(geom)
            if isinstance(geom, (Polygon, MultiPolygon)) and not geom.is_empty:
                cells.append(GradeCell(pop=pop_val, geometry=geom))
        return cells

    vsi_path = (
        f"/vsizip/{path.resolve()}/{GRADE_1KM_SHP_MEMBER}"
        if path.suffix.lower() == ".zip"
        else str(path)
    )
    _meta, _fids, wkb_array, fields = pyogrio.raw.read(
        vsi_path,
        columns=["TOTAL"],
        bbox=bbox,
        where="TOTAL > 0",
    )
    if wkb_array is None or len(wkb_array) == 0:
        return []
    geoms = from_wkb(wkb_array)
    pops = fields[0]
    result: list[GradeCell] = []
    for geom, pop_val in zip(geoms, pops, strict=True):
        pop_f = float(pop_val)
        if pop_f <= 0.0 or geom is None or geom.is_empty:
            continue
        result.append(GradeCell(pop=pop_f, geometry=geom))
    return result


def ensure_grade_raw_file(
    raw_root: Path | None = None,
    manifest_path: Path | None = None,
    fetcher: Fetcher | None = None,
) -> ArtifactSync:
    resolved_manifest = manifest_path if manifest_path is not None else MANIFEST_PATH
    sync = ensure_raw_artifact(
        source_id="ibge_grade",
        filename=GRADE_1KM_FILENAME,
        url=GRADE_1KM_URL,
        raw_root=raw_root,
        manifest_path=resolved_manifest,
        fetcher=fetcher,
    )
    sources = read_manifest(resolved_manifest)
    sources[sync.source_key] = {
        "ano_ref": GRADE_1KM_YEAR,
        "fetched_at": sync.fetched_at,
        "resolution": "1km",
        "sha256": sync.sha256,
        "url": sync.url,
    }
    write_manifest(resolved_manifest, sources)
    return sync
