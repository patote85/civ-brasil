from __future__ import annotations

import csv
import io
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

import py7zr

from pipeline.sources._common import (
    ArtifactSync,
    build_mun_prefix6_map,
    ensure_raw_artifact_stream,
    ftp_stream_downloader,
    normalize_pt_name,
    upsert_manifest_entry,
)
from pipeline.types import UF_IBGE_CODES, CdMun, UfCode

RAIS_YEAR = 2025
RAIS_URL = f"ftp://ftp.mtps.gov.br/pdet/microdados/RAIS/{RAIS_YEAR}/RAIS_ESTAB_PUB.7z"
RAIS_FILENAME = f"RAIS_ESTAB_PUB_{RAIS_YEAR}.7z"


@dataclass(frozen=True, slots=True)
class RaisDivisionRecord:
    cd_mun: CdMun
    cnae_div: str
    cnae_secao: str
    vinculos: int
    estabelecimentos: int


def cnae_division_to_section(div: str) -> str:
    if len(div) != 2 or not div.isdigit():
        return "Z"
    n = int(div)
    if 1 <= n <= 3:
        return "A"
    if 5 <= n <= 9:
        return "B"
    if 10 <= n <= 33:
        return "C"
    if n == 35:
        return "D"
    if 36 <= n <= 39:
        return "E"
    if 41 <= n <= 43:
        return "F"
    if 45 <= n <= 47:
        return "G"
    if 49 <= n <= 53:
        return "H"
    if 55 <= n <= 56:
        return "I"
    if 58 <= n <= 63:
        return "J"
    if 64 <= n <= 66:
        return "K"
    if n == 68:
        return "L"
    if 69 <= n <= 75:
        return "M"
    if 77 <= n <= 82:
        return "N"
    if n == 84:
        return "O"
    if n == 85:
        return "P"
    if 86 <= n <= 88:
        return "Q"
    if 90 <= n <= 93:
        return "R"
    if 94 <= n <= 96:
        return "S"
    if n == 97:
        return "T"
    if n == 99:
        return "U"
    return "Z"


def _find_col(headers: list[str], candidates: tuple[str, ...]) -> int:
    norm = [normalize_pt_name(h) for h in headers]
    for cand in candidates:
        for idx, name in enumerate(norm):
            if cand in name:
                return idx
    raise ValueError(f"Coluna RAIS não encontrada ({candidates}) em cabeçalho: {headers[:12]}")


def _parse_rais_stream(
    handle: TextIO,
    uf: UfCode,
    valid_cd_muns: set[CdMun],
) -> tuple[list[RaisDivisionRecord], dict[str, int]]:
    first_line = handle.readline()
    if not first_line:
        raise ValueError("Arquivo RAIS vazio")
    delimiter = ";" if first_line.count(";") >= first_line.count(",") else ","
    headers = next(csv.reader([first_line], delimiter=delimiter))

    mun_idx = _find_col(headers, ("municipio", "munic"))
    cnae_idx = _find_col(headers, ("cnae 2.0 classe", "cnae classe", "cnae_2", "cnae"))
    vinc_idx = _find_col(headers, ("qtd vinculos ativos", "vinculos ativos", "vinculos"))

    uf_prefix = UF_IBGE_CODES[uf]
    mun_lookup = build_mun_prefix6_map(valid_cd_muns)

    agg_vinc: dict[tuple[CdMun, str], int] = defaultdict(int)
    agg_estab: dict[tuple[CdMun, str], int] = defaultdict(int)
    rows_sp = 0
    rows_skipped = 0
    missing_cnae = 0

    reader = csv.reader(handle, delimiter=delimiter)
    for row in reader:
        if len(row) <= max(mun_idx, cnae_idx, vinc_idx):
            rows_skipped += 1
            continue
        raw_mun = row[mun_idx].strip().strip('"')
        digits_mun = "".join(ch for ch in raw_mun if ch.isdigit())
        if not digits_mun.startswith(uf_prefix):
            continue
        cd_mun = mun_lookup.get(digits_mun) or mun_lookup.get(digits_mun[:6])
        if cd_mun is None:
            rows_skipped += 1
            continue

        raw_vinc = row[vinc_idx].strip().strip('"').replace(".", "").replace(",", ".")
        try:
            vinc = int(float(raw_vinc)) if raw_vinc else 0
        except ValueError:
            vinc = 0
        if vinc < 0:
            vinc = 0

        raw_cnae = "".join(ch for ch in row[cnae_idx] if ch.isdigit())
        if len(raw_cnae) >= 2:
            cnae_div = raw_cnae.zfill(5)[:2] if len(raw_cnae) <= 5 else raw_cnae[:2]
        else:
            cnae_div = "00"
            missing_cnae += 1

        key = (cd_mun, cnae_div)
        agg_vinc[key] += vinc
        agg_estab[key] += 1
        rows_sp += 1

    records = [
        RaisDivisionRecord(
            cd_mun=cd,
            cnae_div=div,
            cnae_secao=cnae_division_to_section(div),
            vinculos=agg_vinc[(cd, div)],
            estabelecimentos=agg_estab[(cd, div)],
        )
        for cd, div in sorted(agg_vinc.keys())
    ]
    stats = {
        "rows_sp": rows_sp,
        "rows_skipped": rows_skipped,
        "missing_cnae": missing_cnae,
        "vinculos_sp": sum(r.vinculos for r in records),
        "estabelecimentos_sp": sum(r.estabelecimentos for r in records),
    }
    return records, stats


def load_rais_from_file(
    path: Path,
    uf: UfCode,
    valid_cd_muns: set[CdMun],
) -> tuple[list[RaisDivisionRecord], dict[str, int]]:
    if path.suffix.lower() == ".7z":
        with tempfile.TemporaryDirectory(prefix="civbr_rais_") as tmp_dir:
            tmp_root = Path(tmp_dir)
            with py7zr.SevenZipFile(path, mode="r") as archive:
                archive.extractall(path=tmp_root)
            candidates = sorted(
                p
                for p in tmp_root.rglob("*")
                if p.is_file() and p.suffix.lower() in {".txt", ".csv"}
            )
            if not candidates:
                candidates = sorted(p for p in tmp_root.rglob("*") if p.is_file())
            if not candidates:
                raise ValueError(f"Nenhum arquivo de dados encontrado em {path}")
            with candidates[0].open(
                "r", encoding="latin-1", errors="replace", newline=""
            ) as handle:
                return _parse_rais_stream(handle, uf=uf, valid_cd_muns=valid_cd_muns)

    raw_bytes = path.read_bytes()
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        text = raw_bytes.decode("latin-1", errors="replace")
    return _parse_rais_stream(io.StringIO(text), uf=uf, valid_cd_muns=valid_cd_muns)


def ensure_rais_raw_file(
    raw_root: Path | None = None,
    manifest_path: Path | None = None,
) -> ArtifactSync:
    sync = ensure_raw_artifact_stream(
        source_id="rais",
        filename=RAIS_FILENAME,
        url=RAIS_URL,
        downloader=ftp_stream_downloader,
        raw_root=raw_root,
        manifest_path=manifest_path,
    )
    upsert_manifest_entry(
        manifest_path,
        sync,
        {
            "orgao": "MTE / PDET",
            "ano_ref": RAIS_YEAR,
            "licenca": "Dados Abertos Gov.br",
            "cobertura": "BR",
        },
    )
    return sync
