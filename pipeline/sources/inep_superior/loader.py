from __future__ import annotations

import csv
import io
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from pipeline.sources._common import (
    ArtifactSync,
    build_inep_ssl_context,
    ensure_raw_artifact_stream,
    make_http_stream_downloader,
    upsert_manifest_entry,
)
from pipeline.types import UF_IBGE_CODES, CdMun, UfCode

INEP_SUPERIOR_YEAR = 2025
INEP_SUPERIOR_URL = (
    "https://download.inep.gov.br/microdados/"
    f"microdados_censo_educacao_superior_{INEP_SUPERIOR_YEAR}.zip"
)
INEP_SUPERIOR_FILENAME = f"microdados_censo_educacao_superior_{INEP_SUPERIOR_YEAR}.zip"


@dataclass(frozen=True, slots=True)
class SuperiorRecord:
    cd_mun: CdMun
    ies: int
    matriculas_superior: int


def _parse_superior_stream(
    handle: TextIO,
    uf: UfCode,
    valid_cd_muns: set[CdMun],
) -> dict[CdMun, SuperiorRecord]:
    first_line = handle.readline()
    if not first_line:
        raise ValueError("CSV do Censo da Educação Superior vazio")
    delimiter = ";" if first_line.count(";") >= first_line.count(",") else ","
    headers = [
        h.strip().strip('"').upper() for h in next(csv.reader([first_line], delimiter=delimiter))
    ]

    mun_col = next(
        (c for c in ("CO_MUNICIPIO", "CO_MUNICIPIO_LO", "CO_MUNICIPIO_IES") if c in headers),
        None,
    )
    mat_col = next(
        (c for c in ("QT_MAT", "QT_MATRICULA_TOTAL", "QT_MAT_TOTAL") if c in headers),
        None,
    )
    ies_col = "CO_IES" if "CO_IES" in headers else None
    if mun_col is None or mat_col is None:
        raise ValueError(f"Colunas esperadas ausentes no Censo Superior: {headers[:15]}")

    mun_idx = headers.index(mun_col)
    mat_idx = headers.index(mat_col)
    ies_idx = headers.index(ies_col) if ies_col is not None else -1

    uf_prefix = UF_IBGE_CODES[uf]
    ies_by_mun: dict[CdMun, set[str]] = defaultdict(set)
    mat_by_mun: dict[CdMun, int] = defaultdict(int)

    for row in csv.reader(handle, delimiter=delimiter):
        if len(row) <= max(mun_idx, mat_idx, ies_idx):
            continue
        raw_mun = "".join(ch for ch in row[mun_idx] if ch.isdigit())
        if not raw_mun.startswith(uf_prefix):
            continue
        cd = CdMun(raw_mun)
        if cd not in valid_cd_muns:
            continue
        raw_mat = row[mat_idx].strip().replace(",", ".")
        try:
            mat = int(float(raw_mat)) if raw_mat else 0
        except ValueError:
            mat = 0
        mat_by_mun[cd] += max(0, mat)
        if ies_idx >= 0:
            ies_id = row[ies_idx].strip()
            if ies_id:
                ies_by_mun[cd].add(ies_id)

    return {
        cd: SuperiorRecord(
            cd_mun=cd,
            ies=len(ies_by_mun.get(cd, set())),
            matriculas_superior=mat_by_mun.get(cd, 0),
        )
        for cd in sorted(valid_cd_muns)
    }


def load_inep_superior_from_file(
    path: Path,
    uf: UfCode,
    valid_cd_muns: set[CdMun],
) -> dict[CdMun, SuperiorRecord]:
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path, "r") as zf:
            csv_members = [
                name
                for name in zf.namelist()
                if name.lower().endswith(".csv")
                and "curso" in Path(name).name.lower()
                and not name.startswith("__MACOSX")
            ]
            if not csv_members:
                csv_members = [
                    name
                    for name in zf.namelist()
                    if name.lower().endswith(".csv") and not name.startswith("__MACOSX")
                ]
            if not csv_members:
                raise ValueError(f"Nenhum CSV encontrado em {path}")
            target = max(csv_members, key=lambda m: zf.getinfo(m).file_size)
            with zf.open(target, "r") as raw_fp:
                text_fp = io.TextIOWrapper(raw_fp, encoding="latin-1", errors="replace", newline="")
                return _parse_superior_stream(text_fp, uf=uf, valid_cd_muns=valid_cd_muns)

    with path.open("r", encoding="latin-1", errors="replace", newline="") as handle:
        return _parse_superior_stream(handle, uf=uf, valid_cd_muns=valid_cd_muns)


def ensure_inep_superior_raw_file(
    raw_root: Path | None = None,
    manifest_path: Path | None = None,
) -> ArtifactSync:
    downloader = make_http_stream_downloader(ssl_context=build_inep_ssl_context(raw_root))
    sync = ensure_raw_artifact_stream(
        source_id="inep_superior",
        filename=INEP_SUPERIOR_FILENAME,
        url=INEP_SUPERIOR_URL,
        downloader=downloader,
        raw_root=raw_root,
        manifest_path=manifest_path,
    )
    upsert_manifest_entry(
        manifest_path,
        sync,
        {
            "orgao": "INEP / MEC",
            "ano_ref": INEP_SUPERIOR_YEAR,
            "licenca": "CC BY-ND 3.0 / Dados Abertos INEP",
            "cobertura": "BR",
        },
    )
    return sync
