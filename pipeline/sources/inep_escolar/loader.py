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

INEP_ESCOLAR_YEAR = 2024
INEP_ESCOLAR_URL = (
    f"https://download.inep.gov.br/dados_abertos/microdados_censo_escolar_{INEP_ESCOLAR_YEAR}.zip"
)
INEP_ESCOLAR_FILENAME = f"microdados_censo_escolar_{INEP_ESCOLAR_YEAR}.zip"


@dataclass(frozen=True, slots=True)
class EscolarRecord:
    cd_mun: CdMun
    escolas: int
    matriculas_basica: int


def _parse_escolar_stream(
    handle: TextIO,
    uf: UfCode,
    valid_cd_muns: set[CdMun],
) -> dict[CdMun, EscolarRecord]:
    first_line = handle.readline()
    if not first_line:
        raise ValueError("CSV do Censo Escolar vazio")
    delimiter = ";" if first_line.count(";") >= first_line.count(",") else ","
    headers = [
        h.strip().strip('"').upper() for h in next(csv.reader([first_line], delimiter=delimiter))
    ]

    if "CO_MUNICIPIO" not in headers or "QT_MAT_BAS" not in headers:
        raise ValueError(f"Colunas esperadas ausentes no Censo Escolar: {headers[:15]}")

    mun_idx = headers.index("CO_MUNICIPIO")
    mat_idx = headers.index("QT_MAT_BAS")
    sit_idx = (
        headers.index("TP_SITUACAO_FUNCIONAMENTO") if "TP_SITUACAO_FUNCIONAMENTO" in headers else -1
    )

    uf_prefix = UF_IBGE_CODES[uf]
    escolas: dict[CdMun, int] = defaultdict(int)
    matriculas: dict[CdMun, int] = defaultdict(int)

    for row in csv.reader(handle, delimiter=delimiter):
        if len(row) <= max(mun_idx, mat_idx, sit_idx):
            continue
        raw_mun = "".join(ch for ch in row[mun_idx] if ch.isdigit())
        if not raw_mun.startswith(uf_prefix):
            continue
        cd = CdMun(raw_mun)
        if cd not in valid_cd_muns:
            continue
        if sit_idx >= 0 and row[sit_idx].strip() not in {"1", ""}:
            continue
        raw_mat = row[mat_idx].strip().replace(",", ".")
        try:
            mat = int(float(raw_mat)) if raw_mat else 0
        except ValueError:
            mat = 0
        escolas[cd] += 1
        matriculas[cd] += max(0, mat)

    return {
        cd: EscolarRecord(
            cd_mun=cd,
            escolas=escolas.get(cd, 0),
            matriculas_basica=matriculas.get(cd, 0),
        )
        for cd in sorted(valid_cd_muns)
    }


def load_inep_escolar_from_file(
    path: Path,
    uf: UfCode,
    valid_cd_muns: set[CdMun],
) -> dict[CdMun, EscolarRecord]:
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path, "r") as zf:
            csv_members = [
                name
                for name in zf.namelist()
                if name.lower().endswith(".csv")
                and "ed_basica" in Path(name).name.lower()
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
                return _parse_escolar_stream(text_fp, uf=uf, valid_cd_muns=valid_cd_muns)

    with path.open("r", encoding="latin-1", errors="replace", newline="") as handle:
        return _parse_escolar_stream(handle, uf=uf, valid_cd_muns=valid_cd_muns)


def ensure_inep_escolar_raw_file(
    raw_root: Path | None = None,
    manifest_path: Path | None = None,
) -> ArtifactSync:
    downloader = make_http_stream_downloader(ssl_context=build_inep_ssl_context(raw_root))
    sync = ensure_raw_artifact_stream(
        source_id="inep_escolar",
        filename=INEP_ESCOLAR_FILENAME,
        url=INEP_ESCOLAR_URL,
        downloader=downloader,
        raw_root=raw_root,
        manifest_path=manifest_path,
    )
    upsert_manifest_entry(
        manifest_path,
        sync,
        {
            "orgao": "INEP / MEC",
            "ano_ref": INEP_ESCOLAR_YEAR,
            "licenca": "CC BY-ND 3.0 / Dados Abertos INEP",
            "cobertura": "BR",
        },
    )
    return sync
