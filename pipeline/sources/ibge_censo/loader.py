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
from pipeline.types import UF_IBGE_CODES, CdMun, UfCode, parse_cd_mun, parse_sidra_number

CENSO_YEAR = 2022


@dataclass(frozen=True, slots=True)
class MunicipioPop:
    cd_mun: CdMun
    pop: int
    ano_ref: int


def censo_url_for_uf(uf: UfCode) -> str:
    uf_num = UF_IBGE_CODES[uf]
    return f"https://apisidra.ibge.gov.br/values/t/4714/n6/in%20n3%20{uf_num}/v/93/p/{CENSO_YEAR}"


def censo_filename_for_uf(uf: UfCode) -> str:
    return f"{uf.lower()}_pop_{CENSO_YEAR}.json"


def load_censo_from_file(path: Path) -> dict[CdMun, MunicipioPop]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or len(raw) < 2:
        raise ValueError(f"Arquivo SIDRA Censo inválido ou vazio: {path}")

    records: dict[CdMun, MunicipioPop] = {}
    for row in raw[1:]:
        if not isinstance(row, dict):
            raise ValueError("Registro SIDRA Censo inválido")
        cd_mun = parse_cd_mun(row.get("D1C"))
        val = parse_sidra_number(row.get("V"))
        if val is None:
            raise ValueError(f"População ausente no SIDRA Censo para {cd_mun}: {row.get('V')!r}")
        if val < 0:
            raise ValueError(f"População negativa para {cd_mun}: {val}")
        pop_int = int(round(val))
        ano_raw = str(row.get("D3C", "")).strip()
        if not ano_raw.isdigit():
            raise ValueError(f"Ano inválido no SIDRA Censo para {cd_mun}: {ano_raw!r}")
        if cd_mun in records:
            raise ValueError(f"Município duplicado no Censo: {cd_mun}")
        records[cd_mun] = MunicipioPop(cd_mun=cd_mun, pop=pop_int, ano_ref=int(ano_raw))
    return records


def ensure_censo_raw_file(
    uf: UfCode,
    raw_root: Path | None = None,
    manifest_path: Path | None = None,
    fetcher: Fetcher | None = None,
) -> tuple[ArtifactSync, dict[CdMun, MunicipioPop]]:
    resolved_manifest = manifest_path if manifest_path is not None else MANIFEST_PATH
    sync = ensure_raw_artifact(
        source_id="ibge_censo",
        filename=censo_filename_for_uf(uf),
        url=censo_url_for_uf(uf),
        raw_root=raw_root,
        manifest_path=resolved_manifest,
        fetcher=fetcher,
    )
    records = load_censo_from_file(sync.path)
    ano_ref = next(iter(records.values())).ano_ref
    sources = read_manifest(resolved_manifest)
    sources[sync.source_key] = {
        "ano_ref": ano_ref,
        "feature_count": len(records),
        "fetched_at": sync.fetched_at,
        "sha256": sync.sha256,
        "url": sync.url,
    }
    write_manifest(resolved_manifest, sources)
    return sync, records
