from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import openpyxl

from pipeline.sources._common import (
    MANIFEST_PATH,
    ArtifactSync,
    Fetcher,
    ensure_raw_artifact,
    read_manifest,
    write_manifest,
)
from pipeline.types import CdMun, parse_cd_mun

ARRANJOS_YEAR = 2015
ARRANJOS_FILENAME = "tab01.xlsx"
ARRANJOS_URL = (
    "https://geoftp.ibge.gov.br/organizacao_do_territorio/"
    "tipologias_do_territorio/arranjos_populacionais/tabelas_xls_2ed/tab01.xlsx"
)

_SKIP_PREFIXES = ("tabela", "arranjos populacionais", "fonte", "nota", "obs")


@dataclass(frozen=True, slots=True)
class ArranjoMunicipio:
    cd_mun: CdMun
    nome_arranjo: str
    is_nucleo: bool
    indice_integracao: float | None


def _parse_optional_float(raw: object) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    text = str(raw).strip().replace(",", ".")
    if not text or text in {"-", "..", "..."}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def load_arranjos_from_file(path: Path) -> dict[CdMun, ArranjoMunicipio]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb[wb.sheetnames[0]]
        current_arranjo: str | None = None
        records: dict[CdMun, ArranjoMunicipio] = {}

        for row in ws.iter_rows(values_only=True):
            if not row or len(row) < 2:
                continue
            col0 = row[0]
            col1 = row[1]

            if col1 is None:
                if col0 is not None:
                    text = str(col0).strip()
                    lower = text.lower()
                    if text and not any(lower.startswith(p) for p in _SKIP_PREFIXES):
                        current_arranjo = text
                continue

            code_str = str(col1).strip()
            if code_str.endswith(".0"):
                code_str = code_str[:-2]
            if len(code_str) != 7 or not code_str.isdigit():
                continue
            if current_arranjo is None:
                raise ValueError(f"Município {code_str} sem cabeçalho de arranjo em {path}")

            cd_mun = parse_cd_mun(code_str)
            nucleo_raw = str(row[3]).strip().lower() if len(row) > 3 and row[3] is not None else ""
            is_nucleo = nucleo_raw == "sim"
            indice = _parse_optional_float(row[5]) if len(row) > 5 else None
            records[cd_mun] = ArranjoMunicipio(
                cd_mun=cd_mun,
                nome_arranjo=current_arranjo,
                is_nucleo=is_nucleo,
                indice_integracao=indice,
            )
    finally:
        wb.close()

    if not records:
        raise ValueError(f"Nenhum município em arranjo populacional lido de {path}")
    return records


def ensure_arranjos_raw_file(
    raw_root: Path | None = None,
    manifest_path: Path | None = None,
    fetcher: Fetcher | None = None,
) -> tuple[ArtifactSync, dict[CdMun, ArranjoMunicipio]]:
    resolved_manifest = manifest_path if manifest_path is not None else MANIFEST_PATH
    sync = ensure_raw_artifact(
        source_id="ibge_arranjos",
        filename=ARRANJOS_FILENAME,
        url=ARRANJOS_URL,
        raw_root=raw_root,
        manifest_path=resolved_manifest,
        fetcher=fetcher,
    )
    records = load_arranjos_from_file(sync.path)
    sources = read_manifest(resolved_manifest)
    sources[sync.source_key] = {
        "ano_ref": ARRANJOS_YEAR,
        "feature_count": len(records),
        "fetched_at": sync.fetched_at,
        "sha256": sync.sha256,
        "url": sync.url,
    }
    write_manifest(resolved_manifest, sources)
    return sync, records
