from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from pathlib import Path

import openpyxl

from pipeline.sources._common import (
    ArtifactSync,
    build_inep_ssl_context,
    ensure_raw_artifact_stream,
    make_http_stream_downloader,
    normalize_pt_name,
    upsert_manifest_entry,
)
from pipeline.types import UF_IBGE_CODES, CdMun, UfCode

INEP_IDEB_YEAR = 2025
INEP_IDEB_AI_URL = (
    f"https://download.inep.gov.br/ideb/resultados/"
    f"divulgacao_anos_iniciais_municipios_{INEP_IDEB_YEAR}.zip"
)
INEP_IDEB_AF_URL = (
    f"https://download.inep.gov.br/ideb/resultados/"
    f"divulgacao_anos_finais_municipios_{INEP_IDEB_YEAR}.zip"
)
INEP_IDEB_EM_URL = (
    f"https://download.inep.gov.br/ideb/resultados/"
    f"divulgacao_ensino_medio_municipios_{INEP_IDEB_YEAR}.zip"
)


@dataclass(frozen=True, slots=True)
class IdebRecord:
    cd_mun: CdMun
    ideb_ai: float | None
    ideb_af: float | None
    ideb_em: float | None
    ideb_medio: float | None


def _parse_ideb_value(raw: object) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        val = float(raw)
        return round(val, 2) if 0.0 <= val <= 10.0 else None
    text = str(raw).strip().replace(",", ".")
    if not text or text in {"-", "ND", "nd", "...", "NA", "N/A"}:
        return None
    try:
        val = float(text)
    except ValueError:
        return None
    return round(val, 2) if 0.0 <= val <= 10.0 else None


def _read_ideb_stage_xlsx(
    path: Path,
    uf: UfCode | None,
    valid_cd_muns: set[CdMun],
) -> dict[CdMun, float | None]:
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path, "r") as zf:
            xlsx_members = [
                n for n in zf.namelist() if n.lower().endswith(".xlsx") and not n.startswith("__")
            ]
            if not xlsx_members:
                raise ValueError(f"Nenhuma planilha .xlsx encontrada em {path}")
            wb = openpyxl.load_workbook(
                io.BytesIO(zf.read(xlsx_members[0])),
                read_only=True,
                data_only=True,
            )
    else:
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)

    try:
        ws = wb.active
        if ws is None:
            raise ValueError(f"Planilha IDEB sem aba ativa: {path}")

        mun_idx = -1
        rede_idx = -1
        val_idx = -1
        header_found = False

        uf_prefix = UF_IBGE_CODES[uf] if uf is not None else ""
        scores: dict[CdMun, float | None] = {}

        for row in ws.iter_rows(values_only=True):
            if not header_found:
                cells = [str(c).strip().upper() if c is not None else "" for c in row]
                if "CO_MUNICIPIO" in cells and "REDE" in cells:
                    mun_idx = cells.index("CO_MUNICIPIO")
                    rede_idx = cells.index("REDE")
                    obs_cols = [
                        (i, c) for i, c in enumerate(cells) if c.startswith("VL_OBSERVADO_")
                    ]
                    if not obs_cols:
                        raise ValueError(f"Coluna VL_OBSERVADO_* ausente em {path}")
                    # Prefer latest observed year (e.g., VL_OBSERVADO_2025)
                    obs_cols.sort(key=lambda item: item[1])
                    val_idx = obs_cols[-1][0]
                    header_found = True
                continue

            if len(row) <= max(mun_idx, rede_idx, val_idx):
                continue
            raw_mun = row[mun_idx]
            if raw_mun is None:
                continue
            mun_str = "".join(ch for ch in str(raw_mun).split(".")[0] if ch.isdigit())
            if uf_prefix and not mun_str.startswith(uf_prefix):
                continue
            cd = CdMun(mun_str)
            if cd not in valid_cd_muns:
                continue
            rede = normalize_pt_name(str(row[rede_idx] or ""))
            if rede != "publica":
                continue
            scores[cd] = _parse_ideb_value(row[val_idx])

        if not header_found:
            raise ValueError(f"Cabeçalho CO_MUNICIPIO/REDE não encontrado em {path}")
        return scores
    finally:
        wb.close()


def load_inep_ideb_from_files(
    ai_path: Path,
    af_path: Path,
    em_path: Path,
    uf: UfCode | None,
    valid_cd_muns: set[CdMun],
) -> dict[CdMun, IdebRecord]:
    ai = _read_ideb_stage_xlsx(ai_path, uf=uf, valid_cd_muns=valid_cd_muns)
    af = _read_ideb_stage_xlsx(af_path, uf=uf, valid_cd_muns=valid_cd_muns)
    em = _read_ideb_stage_xlsx(em_path, uf=uf, valid_cd_muns=valid_cd_muns)

    result: dict[CdMun, IdebRecord] = {}
    for cd in sorted(valid_cd_muns):
        v_ai = ai.get(cd)
        v_af = af.get(cd)
        v_em = em.get(cd)
        present = [v for v in (v_ai, v_af, v_em) if v is not None]
        medio = round(sum(present) / len(present), 2) if present else None
        result[cd] = IdebRecord(
            cd_mun=cd,
            ideb_ai=v_ai,
            ideb_af=v_af,
            ideb_em=v_em,
            ideb_medio=medio,
        )
    return result


def ensure_inep_ideb_raw_files(
    raw_root: Path | None = None,
    manifest_path: Path | None = None,
) -> tuple[ArtifactSync, ArtifactSync, ArtifactSync]:
    downloader = make_http_stream_downloader(ssl_context=build_inep_ssl_context(raw_root))
    specs = [
        (f"ideb_ai_municipios_{INEP_IDEB_YEAR}.zip", INEP_IDEB_AI_URL),
        (f"ideb_af_municipios_{INEP_IDEB_YEAR}.zip", INEP_IDEB_AF_URL),
        (f"ideb_em_municipios_{INEP_IDEB_YEAR}.zip", INEP_IDEB_EM_URL),
    ]
    syncs: list[ArtifactSync] = []
    for filename, url in specs:
        sync = ensure_raw_artifact_stream(
            source_id="inep_ideb",
            filename=filename,
            url=url,
            downloader=downloader,
            raw_root=raw_root,
            manifest_path=manifest_path,
        )
        upsert_manifest_entry(
            manifest_path,
            sync,
            {
                "orgao": "INEP / MEC",
                "ano_ref": INEP_IDEB_YEAR,
                "licenca": "CC BY-ND 3.0 / Dados Abertos INEP",
                "cobertura": "BR",
            },
        )
        syncs.append(sync)
    return syncs[0], syncs[1], syncs[2]
