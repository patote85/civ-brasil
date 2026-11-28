from __future__ import annotations

import json
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
from pipeline.types import CdMun, parse_cd_mun, parse_sidra_number

SANEAMENTO_YEAR = 2022
SANEAMENTO_FILENAME = "br_esgoto_adequado_2022.json"
SANEAMENTO_URL = (
    "https://apisidra.ibge.gov.br/values/t/6805/n6/all/v/1000381/p/2022/c11558/46290"
)


@dataclass(frozen=True, slots=True)
class MunicipioSaneamento:
    cd_mun: CdMun
    esgoto_adequado_pct: float | None
    ano_ref: int


def load_saneamento_from_file(path: Path) -> dict[CdMun, MunicipioSaneamento]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or len(raw) < 2:
        raise ValueError(f"Arquivo SIDRA Saneamento inválido ou vazio: {path}")

    records: dict[CdMun, MunicipioSaneamento] = {}
    for row in raw[1:]:
        if not isinstance(row, dict):
            continue
        cd_mun = parse_cd_mun(row.get("D1C"))
        val = parse_sidra_number(row.get("V"))
        if val is not None and not (0.0 <= val <= 100.0):
            raise ValueError(f"Percentual de saneamento fora de [0, 100] para {cd_mun}: {val}")
        ano_raw = str(row.get("D3C", str(SANEAMENTO_YEAR))).strip()
        ano_int = int(ano_raw) if ano_raw.isdigit() else SANEAMENTO_YEAR
        records[cd_mun] = MunicipioSaneamento(
            cd_mun=cd_mun,
            esgoto_adequado_pct=val,
            ano_ref=ano_int,
        )
    if not records:
        raise ValueError(f"Nenhum registro de saneamento lido de {path}")
    return records


def ensure_saneamento_raw_file(
    raw_root: Path | None = None,
    manifest_path: Path | None = None,
    fetcher: Fetcher | None = None,
) -> tuple[ArtifactSync, dict[CdMun, MunicipioSaneamento]]:
    resolved_manifest = manifest_path if manifest_path is not None else MANIFEST_PATH
    sync = ensure_raw_artifact(
        source_id="ibge_saneamento",
        filename=SANEAMENTO_FILENAME,
        url=SANEAMENTO_URL,
        raw_root=raw_root,
        manifest_path=resolved_manifest,
        fetcher=fetcher,
    )
    records = load_saneamento_from_file(sync.path)
    sources = read_manifest(resolved_manifest)
    sources[sync.source_key] = {
        "ano_ref": SANEAMENTO_YEAR,
        "feature_count": len(records),
        "fetched_at": sync.fetched_at,
        "sha256": sync.sha256,
        "url": sync.url,
    }
    write_manifest(resolved_manifest, sources)
    return sync, records
