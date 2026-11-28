from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pipeline.sources._common import (
    ArtifactSync,
    Fetcher,
    default_fetcher,
    ensure_raw_artifact,
)
from pipeline.types import CdMun

IPEA_IDHM_URL = "https://www.ipeadata.gov.br/api/odata4/ValoresSerie(SERCODIGO='ADH_IDHM')"
IPEA_GINI_URL = "https://www.ipeadata.gov.br/api/odata4/ValoresSerie(SERCODIGO='ADH_GINI')"


@dataclass(frozen=True, slots=True)
class IpeaIdhmRecord:
    cd_mun: CdMun
    idhm: float | None
    gini: float | None


def _extract_2010_map(path: Path, valid_cd_muns: set[CdMun], label: str) -> dict[CdMun, float]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("value", [])
    if not isinstance(rows, list):
        raise ValueError(f"Formato inválido em {path}")
    out: dict[CdMun, float] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        val_data = str(row.get("VALDATA") or "")
        if not val_data.startswith("2010"):
            continue
        ter_code = "".join(ch for ch in str(row.get("TERCODIGO") or "") if ch.isdigit())
        if len(ter_code) != 7:
            continue
        cd = CdMun(ter_code)
        if cd not in valid_cd_muns:
            continue
        raw_val = row.get("VALVALOR")
        if raw_val is None:
            continue
        val = float(raw_val)
        if not (0.0 <= val <= 1.0):
            raise ValueError(f"{label} fora de [0,1] para {cd}: {val}")
        out[cd] = round(val, 4)
    return out


def load_ipea_idhm_from_files(
    idhm_path: Path,
    gini_path: Path,
    valid_cd_muns: set[CdMun],
) -> dict[CdMun, IpeaIdhmRecord]:
    idhm_map = _extract_2010_map(idhm_path, valid_cd_muns, "IDHM")
    gini_map = _extract_2010_map(gini_path, valid_cd_muns, "Gini")
    return {
        cd: IpeaIdhmRecord(
            cd_mun=cd,
            idhm=idhm_map.get(cd),
            gini=gini_map.get(cd),
        )
        for cd in sorted(valid_cd_muns)
    }


def ensure_ipea_idhm_raw_files(
    raw_root: Path | None = None,
    manifest_path: Path | None = None,
    fetcher: Fetcher = default_fetcher,
) -> tuple[ArtifactSync, ArtifactSync]:
    from pipeline.sources._common import upsert_manifest_entry

    idhm_sync = ensure_raw_artifact(
        source_id="ipea_idhm",
        filename="adh_idhm.json",
        url=IPEA_IDHM_URL,
        raw_root=raw_root,
        manifest_path=manifest_path,
        fetcher=fetcher,
    )
    gini_sync = ensure_raw_artifact(
        source_id="ipea_idhm",
        filename="adh_gini.json",
        url=IPEA_GINI_URL,
        raw_root=raw_root,
        manifest_path=manifest_path,
        fetcher=fetcher,
    )
    upsert_manifest_entry(
        manifest_path,
        idhm_sync,
        {
            "orgao": "IPEA / PNUD / FJP (Atlas Brasil)",
            "ano_ref": 2010,
            "licenca": "Dados Abertos IPEA",
            "cobertura": "BR",
        },
    )
    upsert_manifest_entry(
        manifest_path,
        gini_sync,
        {
            "orgao": "IPEA / PNUD / FJP (Atlas Brasil)",
            "ano_ref": 2010,
            "licenca": "Dados Abertos IPEA",
            "cobertura": "BR",
        },
    )
    return idhm_sync, gini_sync
