from __future__ import annotations

import csv
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path

import pyogrio.raw
from shapely import from_wkb

from pipeline.sources._common import (
    ArtifactSync,
    ensure_raw_artifact_stream,
    make_http_stream_downloader,
    normalize_pt_name,
    upsert_manifest_entry,
)
from pipeline.types import CdMun, UfCode

ANTAQ_YEAR = 2026
INFRASA_PORTOS_URL = (
    "https://geoportal.infrasa.gov.br/wp-content/uploads/2026/10/Instalacoes_portuarias-1.zip"
)
INFRASA_PORTOS_FILENAME = "Instalacoes_portuarias_2026.zip"


@dataclass(frozen=True, slots=True)
class PortPoint:
    nome: str
    tipo: str
    municipio: str
    cd_mun: CdMun | None
    hidrovia: str
    lat: float
    lon: float
    carga_toneladas: float


def _load_optional_cargo_by_port(cargo_path: Path | None) -> dict[str, float]:
    if cargo_path is None or not cargo_path.is_file():
        return {}
    result: dict[str, float] = {}
    with cargo_path.open("r", encoding="latin-1", errors="replace", newline="") as handle:
        first_line = handle.readline()
        if not first_line:
            return {}
        delimiter = ";" if first_line.count(";") >= first_line.count(",") else ","
        handle.seek(0)
        for row in csv.DictReader(handle, delimiter=delimiter):
            port_name = str(
                row.get("Porto Atracação") or row.get("Instalacao") or row.get("nome") or ""
            ).strip()
            raw_val = (
                str(
                    row.get("VLPesoCargaBruta")
                    or row.get("carga_toneladas")
                    or row.get("toneladas")
                    or "0"
                )
                .strip()
                .replace(",", ".")
            )
            if not port_name:
                continue
            try:
                tons = float(raw_val)
            except ValueError:
                continue
            key = normalize_pt_name(port_name)
            result[key] = result.get(key, 0.0) + max(0.0, tons)
    return result


def load_antaq_from_files(
    ports_path: Path,
    uf: UfCode,
    mun_name_to_cd: dict[str, CdMun],
    cargo_path: Path | None = None,
) -> tuple[list[PortPoint], list[dict[str, str]]]:
    norm_mun_map = {normalize_pt_name(k): v for k, v in mun_name_to_cd.items()}
    cargo_map = _load_optional_cargo_by_port(cargo_path)
    ports: list[PortPoint] = []
    rejected: list[dict[str, str]] = []

    raw_records: list[tuple[str, str, str, str, str, float | None, float | None]] = []
    if ports_path.suffix.lower() == ".zip":
        with zipfile.ZipFile(ports_path, "r") as zf:
            shp_names = [n for n in zf.namelist() if n.lower().endswith(".shp")]
            if not shp_names:
                raise ValueError(f"Shapefile não encontrado em {ports_path}")
            shp_member = shp_names[0]
        meta, _fids, geoms, fields = pyogrio.raw.read(f"/vsizip/{ports_path}/{shp_member}")
        field_names = [str(f).lower() for f in meta["fields"]]
        for idx, geom_wkb in enumerate(geoms):
            row = {field_names[j]: fields[j][idx] for j in range(len(field_names))}
            geom = from_wkb(geom_wkb) if geom_wkb is not None else None
            pt = geom.centroid if geom is not None and not geom.is_empty else None
            raw_records.append(
                (
                    str(row.get("nome") or "").strip(),
                    str(row.get("tipo") or "").strip(),
                    str(row.get("uf") or "").strip().upper(),
                    str(row.get("municipio") or "").strip(),
                    str(row.get("hidrovia") or "").strip(),
                    float(pt.y) if pt is not None else None,
                    float(pt.x) if pt is not None else None,
                )
            )
    else:
        payload = json.loads(ports_path.read_text(encoding="utf-8"))
        for feat in payload.get("features", []):
            props = feat.get("properties") or {}
            geom = feat.get("geometry") or {}
            coords = geom.get("coordinates") if isinstance(geom, dict) else None
            lon = float(coords[0]) if isinstance(coords, list) and len(coords) >= 2 else None
            lat = float(coords[1]) if isinstance(coords, list) and len(coords) >= 2 else None
            raw_records.append(
                (
                    str(props.get("nome") or "").strip(),
                    str(props.get("tipo") or "").strip(),
                    str(props.get("uf") or "").strip().upper(),
                    str(props.get("municipio") or "").strip(),
                    str(props.get("hidrovia") or "").strip(),
                    lat,
                    lon,
                )
            )

    for nome, tipo, row_uf, municipio, hidrovia, lat, lon in raw_records:
        if row_uf != uf:
            continue
        if lat is None or lon is None or not (-35.0 <= lat <= 6.0 and -75.0 <= lon <= -32.0):
            rejected.append(
                {
                    "source": "antaq",
                    "name": nome,
                    "reason": "coordenada_invalida",
                    "raw_lat": str(lat),
                    "raw_lon": str(lon),
                }
            )
            continue
        cd_mun = norm_mun_map.get(normalize_pt_name(municipio))
        tons = cargo_map.get(normalize_pt_name(nome), 0.0)
        ports.append(
            PortPoint(
                nome=nome,
                tipo=tipo or "Instalação Portuária",
                municipio=municipio,
                cd_mun=cd_mun,
                hidrovia=hidrovia,
                lat=lat,
                lon=lon,
                carga_toneladas=round(tons, 2),
            )
        )

    ports.sort(key=lambda p: (p.tipo != "Porto Organizado", -p.carga_toneladas, p.nome))
    return ports, rejected


def ensure_antaq_raw_file(
    raw_root: Path | None = None,
    manifest_path: Path | None = None,
) -> ArtifactSync:
    sync = ensure_raw_artifact_stream(
        source_id="antaq",
        filename=INFRASA_PORTOS_FILENAME,
        url=INFRASA_PORTOS_URL,
        downloader=make_http_stream_downloader(),
        raw_root=raw_root,
        manifest_path=manifest_path,
    )
    upsert_manifest_entry(
        manifest_path,
        sync,
        {
            "orgao": "InfraSA / ONTL / ANTAQ",
            "ano_ref": ANTAQ_YEAR,
            "licenca": "Dados Abertos Gov.br",
            "cobertura": "BR",
        },
    )
    return sync
