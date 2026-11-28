from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from pipeline.sources._common import (
    MANIFEST_PATH,
    ArtifactSync,
    Fetcher,
    ensure_raw_artifact,
    read_manifest,
    write_manifest,
)
from pipeline.types import CdMun, parse_cd_mun

FAM_PBF_FILENAME = "fam_pbf.json"
VAL_PBF_FILENAME = "val_pbf.json"
FAM_PBF_URL = "https://www.ipeadata.gov.br/api/odata4/ValoresSerie(SERCODIGO='FAM_PBF')"
VAL_PBF_URL = "https://www.ipeadata.gov.br/api/odata4/ValoresSerie(SERCODIGO='VAL_PBF')"


@dataclass(frozen=True, slots=True)
class MunicipioBolsaFamilia:
    cd_mun: CdMun
    familias: int
    valor_mil_reais: float | None
    ano_ref: int


def _parse_latest_municipal_series(path: Path) -> dict[CdMun, tuple[str, float]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("value"), list):
        raise ValueError(f"JSON IPEA/MDS Bolsa Família inválido: {path}")

    best: dict[CdMun, tuple[str, float]] = {}
    for row in raw["value"]:
        if not isinstance(row, dict) or row.get("NIVNOME") != "Municípios":
            continue
        ter_code = str(row.get("TERCODIGO", "")).strip()
        if len(ter_code) != 7 or not ter_code.isdigit():
            continue
        val_raw = row.get("VALVALOR")
        if val_raw is None:
            continue
        val_f = float(val_raw)
        if not math.isfinite(val_f) or val_f < 0.0:
            continue
        date_str = str(row.get("VALDATA", "")).strip()
        if len(date_str) < 10 or not date_str[:4].isdigit():
            continue
        date_key = date_str[:10]
        cd_mun = parse_cd_mun(ter_code)
        prev = best.get(cd_mun)
        if prev is None or date_key > prev[0]:
            best[cd_mun] = (date_key, val_f)
    return best


def load_bolsa_familia_from_files(
    fam_path: Path,
    val_path: Path,
) -> dict[CdMun, MunicipioBolsaFamilia]:
    fam_by_mun = _parse_latest_municipal_series(fam_path)
    val_by_mun = _parse_latest_municipal_series(val_path)
    if not fam_by_mun:
        raise ValueError(f"Nenhum registro municipal de famílias PBF em {fam_path}")

    records: dict[CdMun, MunicipioBolsaFamilia] = {}
    for cd_mun in sorted(fam_by_mun):
        fam_date, fam_val = fam_by_mun[cd_mun]
        val_entry = val_by_mun.get(cd_mun)
        val_mil = val_entry[1] if val_entry is not None and val_entry[0] == fam_date else None
        records[cd_mun] = MunicipioBolsaFamilia(
            cd_mun=cd_mun,
            familias=int(round(fam_val)),
            valor_mil_reais=val_mil,
            ano_ref=int(fam_date[:4]),
        )
    return records


def ensure_bolsa_familia_raw_files(
    raw_root: Path | None = None,
    manifest_path: Path | None = None,
    fetcher: Fetcher | None = None,
) -> tuple[ArtifactSync, ArtifactSync, dict[CdMun, MunicipioBolsaFamilia]]:
    resolved_manifest = manifest_path if manifest_path is not None else MANIFEST_PATH
    fam_sync = ensure_raw_artifact(
        source_id="mds_bolsa",
        filename=FAM_PBF_FILENAME,
        url=FAM_PBF_URL,
        raw_root=raw_root,
        manifest_path=resolved_manifest,
        fetcher=fetcher,
    )
    val_sync = ensure_raw_artifact(
        source_id="mds_bolsa",
        filename=VAL_PBF_FILENAME,
        url=VAL_PBF_URL,
        raw_root=raw_root,
        manifest_path=resolved_manifest,
        fetcher=fetcher,
    )
    records = load_bolsa_familia_from_files(fam_sync.path, val_sync.path)
    latest_year = max(r.ano_ref for r in records.values())
    sources = read_manifest(resolved_manifest)
    for sync in (fam_sync, val_sync):
        sources[sync.source_key] = {
            "ano_ref": latest_year,
            "cobertura": "BR",
            "feature_count": len(records),
            "fetched_at": sync.fetched_at,
            "licenca": "Dados Abertos MDS / IPEA Data",
            "orgao": "MDS / IPEA Data (Bolsa Família)",
            "sha256": sync.sha256,
            "url": sync.url,
        }
    write_manifest(resolved_manifest, sources)
    return fam_sync, val_sync, records
