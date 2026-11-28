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

ATLAS_VIOLENCIA_FILENAME = "aviol12_thomic.json"
ATLAS_VIOLENCIA_URL = (
    "https://www.ipeadata.gov.br/api/odata4/ValoresSerie(SERCODIGO='AVIOL12_THOMIC')"
)


@dataclass(frozen=True, slots=True)
class MunicipioAtlasViolencia:
    cd_mun: CdMun
    taxa_homic_100k: float
    ano_ref: int


def load_atlas_violencia_from_file(path: Path) -> dict[CdMun, MunicipioAtlasViolencia]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("value"), list):
        raise ValueError(f"JSON IPEA Atlas da Violência inválido: {path}")

    best_by_mun: dict[CdMun, tuple[str, float]] = {}
    for row in raw["value"]:
        if not isinstance(row, dict):
            continue
        if row.get("NIVNOME") != "Municípios":
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
        prev = best_by_mun.get(cd_mun)
        if prev is None or date_key > prev[0]:
            best_by_mun[cd_mun] = (date_key, val_f)

    if not best_by_mun:
        raise ValueError(f"Nenhum registro municipal lido de {path}")

    return {
        cd: MunicipioAtlasViolencia(cd_mun=cd, taxa_homic_100k=val, ano_ref=int(date_key[:4]))
        for cd, (date_key, val) in sorted(best_by_mun.items())
    }


def ensure_atlas_violencia_raw_file(
    raw_root: Path | None = None,
    manifest_path: Path | None = None,
    fetcher: Fetcher | None = None,
) -> tuple[ArtifactSync, dict[CdMun, MunicipioAtlasViolencia]]:
    resolved_manifest = manifest_path if manifest_path is not None else MANIFEST_PATH
    sync = ensure_raw_artifact(
        source_id="ipea_atlas_violencia",
        filename=ATLAS_VIOLENCIA_FILENAME,
        url=ATLAS_VIOLENCIA_URL,
        raw_root=raw_root,
        manifest_path=resolved_manifest,
        fetcher=fetcher,
    )
    records = load_atlas_violencia_from_file(sync.path)
    latest_year = max(r.ano_ref for r in records.values())
    sources = read_manifest(resolved_manifest)
    sources[sync.source_key] = {
        "ano_ref": latest_year,
        "cobertura": "BR",
        "feature_count": len(records),
        "fetched_at": sync.fetched_at,
        "licenca": "Dados Abertos IPEA / FBSP",
        "orgao": "IPEA / FBSP (Atlas da Violência)",
        "sha256": sync.sha256,
        "url": sync.url,
    }
    write_manifest(resolved_manifest, sources)
    return sync, records
