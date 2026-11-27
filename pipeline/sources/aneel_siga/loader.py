from __future__ import annotations

import csv
import json
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pipeline.sources._common import (
    ArtifactSync,
    default_fetcher,
    ensure_raw_artifact,
    upsert_manifest_entry,
)
from pipeline.types import UfCode

ANEEL_YEAR = 2026
EPE_WEBMAP_BASE = "https://gisepeprd2.epe.gov.br/arcgis/rest/services/WMS_Webmap_EPE_Data/MapServer"
EPE_LAYERS: tuple[tuple[int, str], ...] = (
    (14, "Eólica (EOL)"),
    (15, "Solar (UFV)"),
    (16, "Hidrelétrica (UHE)"),
    (17, "PCH"),
    (18, "CGH"),
    (19, "Térmica Biomassa (UTE)"),
    (20, "Térmica Fóssil (UTE)"),
    (21, "Nuclear (UTN)"),
)
ANEEL_FILENAME = "epe_aneel_usinas_operacao.json"


@dataclass(frozen=True, slots=True)
class PowerPlantPoint:
    ceg: str
    nome: str
    fonte: str
    potencia_mw: float
    lat: float
    lon: float
    uf: str


def _fetch_epe_power_plants_bundle(_url: str) -> bytes:
    all_features: list[dict[str, Any]] = []
    for layer_id, fonte_label in EPE_LAYERS:
        offset = 0
        while True:
            params = urllib.parse.urlencode(
                {
                    "where": "1=1",
                    "outFields": "*",
                    "resultOffset": offset,
                    "resultRecordCount": 1000,
                    "f": "geojson",
                }
            )
            layer_url = f"{EPE_WEBMAP_BASE}/{layer_id}/query?{params}"
            payload = json.loads(default_fetcher(layer_url).decode("utf-8"))
            features = payload.get("features", [])
            if not isinstance(features, list) or not features:
                break
            for feat in features:
                if not isinstance(feat, dict):
                    continue
                props = dict(feat.get("properties") or {})
                props["fonte"] = fonte_label
                all_features.append(
                    {
                        "type": "Feature",
                        "properties": props,
                        "geometry": feat.get("geometry"),
                    }
                )
            if len(features) < 1000:
                break
            offset += len(features)
    return json.dumps(
        {"type": "FeatureCollection", "features": all_features},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _extract_uf_from_ceg(ceg: str) -> str:
    parts = ceg.strip().upper().split(".")
    if len(parts) >= 3 and len(parts[2]) == 2 and parts[2].isalpha():
        return parts[2]
    return ""


def _parse_float(raw: object) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    cleaned = str(raw).strip().replace(",", ".")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _validate_coord(
    name: str,
    lat: float | None,
    lon: float | None,
) -> tuple[bool, str]:
    if lat is None or lon is None:
        return False, "coordenada_ausente"
    if -75.0 <= lat <= -32.0 and -35.0 <= lon <= 6.0:
        return False, "lat_lon_trocados"
    if not (-35.0 <= lat <= 6.0 and -75.0 <= lon <= -32.0):
        return False, "fora_dos_limites_do_brasil"
    return True, ""


def load_aneel_siga_from_file(
    path: Path,
    uf: UfCode,
) -> tuple[list[PowerPlantPoint], list[dict[str, str]]]:
    plants: list[PowerPlantPoint] = []
    rejected: list[dict[str, str]] = []

    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="latin-1", errors="replace", newline="") as handle:
            reader = csv.DictReader(handle, delimiter=";")
            for row in reader:
                row_uf = str(row.get("SigUFPrincipal") or row.get("UF") or "").strip().upper()
                if row_uf and row_uf != uf:
                    continue
                fase = str(row.get("DscFaseUsina") or "Operação").strip().lower()
                if "opera" not in fase:
                    continue
                nome = str(row.get("NomEmpreendimento") or row.get("Nome") or "").strip()
                ceg = str(row.get("CodCEG") or "").strip()
                fonte = str(
                    row.get("SigTipoGeracao") or row.get("DscOrigemCombustivel") or "Usina"
                ).strip()
                kw = _parse_float(
                    row.get("MdaPotenciaFiscalizadaKw") or row.get("MdaPotenciaOutorgadaKw")
                )
                lat = _parse_float(row.get("NumCoordNEmpreendimento") or row.get("Latitude"))
                lon = _parse_float(row.get("NumCoordEEmpreendimento") or row.get("Longitude"))
                ok, reason = _validate_coord(nome, lat, lon)
                if not ok or lat is None or lon is None:
                    rejected.append(
                        {
                            "source": "aneel_siga",
                            "name": nome or ceg,
                            "reason": reason,
                            "raw_lat": str(lat),
                            "raw_lon": str(lon),
                        }
                    )
                    continue
                mw = max(0.0, (kw or 0.0) / 1000.0)
                plants.append(
                    PowerPlantPoint(
                        ceg=ceg,
                        nome=nome or ceg,
                        fonte=fonte,
                        potencia_mw=round(mw, 4),
                        lat=lat,
                        lon=lon,
                        uf=row_uf or _extract_uf_from_ceg(ceg),
                    )
                )
        return plants, rejected

    payload = json.loads(path.read_text(encoding="utf-8"))
    features = payload.get("features", [])
    for feat in features:
        if not isinstance(feat, dict):
            continue
        props = feat.get("properties") or {}
        geom = feat.get("geometry") or {}
        ceg = str(props.get("ceg") or props.get("CEG") or "").strip()
        row_uf = (
            str(props.get("uf") or props.get("UF") or _extract_uf_from_ceg(ceg)).strip().upper()
        )
        if row_uf and row_uf != uf:
            continue
        nome = str(
            props.get("nome") or props.get("Nome") or props.get("NOME") or ceg or "Usina"
        ).strip()
        fonte = str(props.get("fonte") or props.get("combust") or "Usina").strip()
        kw = _parse_float(props.get("potencia") or props.get("Potencia") or props.get("POTENCIA"))
        coords = geom.get("coordinates") if isinstance(geom, dict) else None
        lon = _parse_float(coords[0]) if isinstance(coords, list) and len(coords) >= 2 else None
        lat = _parse_float(coords[1]) if isinstance(coords, list) and len(coords) >= 2 else None
        ok, reason = _validate_coord(nome, lat, lon)
        if not ok or lat is None or lon is None:
            rejected.append(
                {
                    "source": "aneel_siga",
                    "name": nome,
                    "reason": reason,
                    "raw_lat": str(lat),
                    "raw_lon": str(lon),
                }
            )
            continue
        mw = max(0.0, (kw or 0.0) / 1000.0)
        plants.append(
            PowerPlantPoint(
                ceg=ceg,
                nome=nome,
                fonte=fonte,
                potencia_mw=round(mw, 4),
                lat=lat,
                lon=lon,
                uf=row_uf,
            )
        )

    plants.sort(key=lambda p: (-p.potencia_mw, p.nome))
    return plants, rejected


def ensure_aneel_siga_raw_file(
    raw_root: Path | None = None,
    manifest_path: Path | None = None,
) -> ArtifactSync:
    sync = ensure_raw_artifact(
        source_id="aneel_siga",
        filename=ANEEL_FILENAME,
        url=f"{EPE_WEBMAP_BASE}/14..21",
        raw_root=raw_root,
        manifest_path=manifest_path,
        fetcher=_fetch_epe_power_plants_bundle,
    )
    upsert_manifest_entry(
        manifest_path,
        sync,
        {
            "orgao": "ANEEL / EPE (WebMap MME)",
            "ano_ref": ANEEL_YEAR,
            "licenca": "Dados Abertos Gov.br",
            "cobertura": "BR",
        },
    )
    return sync
