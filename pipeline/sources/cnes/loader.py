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
    build_mun_prefix6_map,
    ensure_raw_artifact_stream,
    make_http_stream_downloader,
    upsert_manifest_entry,
)
from pipeline.types import UF_IBGE_CODES, CdMun, UfCode

CNES_YEAR = 2025
CNES_ESTAB_URL = (
    "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/CNES/cnes_estabelecimentos_csv.zip"
)
CNES_LEITOS_URL = (
    "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/saes/drac/CNES_Leito/csv/"
    f"cnes_leitos_cadastrados_{CNES_YEAR}_csv.zip"
)
CNES_ESTAB_FILENAME = "cnes_estabelecimentos_csv.zip"
CNES_LEITOS_FILENAME = f"cnes_leitos_cadastrados_{CNES_YEAR}_csv.zip"

HOSPITAL_TYPES = {"05", "5", "07", "7", "62"}


@dataclass(frozen=True, slots=True)
class CnesMunRecord:
    cd_mun: CdMun
    estabelecimentos: int
    hospitais: int
    leitos: int


@dataclass(frozen=True, slots=True)
class CnesPoint:
    cnes_id: str
    nome: str
    cd_mun: CdMun
    lat: float
    lon: float
    tipo_unidade: str
    leitos: int


def _open_csv_text(path: Path) -> TextIO:
    if path.suffix.lower() == ".zip":
        zf = zipfile.ZipFile(path, "r")
        members = [
            n for n in zf.namelist() if n.lower().endswith(".csv") and not n.startswith("__MACOSX")
        ]
        if not members:
            zf.close()
            raise ValueError(f"Nenhum CSV encontrado em {path}")
        target = max(members, key=lambda m: zf.getinfo(m).file_size)
        raw_bytes = zf.read(target)
        zf.close()
        return io.StringIO(raw_bytes.decode("latin-1", errors="replace"))
    return path.open("r", encoding="latin-1", errors="replace", newline="")


def _find_header_index(headers: list[str], candidates: tuple[str, ...]) -> int:
    for cand in candidates:
        if cand in headers:
            return headers.index(cand)
    return -1


def _parse_float(raw: str) -> float | None:
    cleaned = raw.strip().strip('"').replace(",", ".")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_int(raw: str) -> int:
    val = _parse_float(raw)
    if val is None or val < 0:
        return 0
    return int(round(val))


def _load_leitos_by_cnes(
    leitos_path: Path,
    uf_prefix: str,
    mun_lookup: dict[str, CdMun],
) -> tuple[dict[str, int], dict[CdMun, int]]:
    handle = _open_csv_text(leitos_path)
    try:
        first_line = handle.readline()
        if not first_line:
            return {}, {}
        delimiter = ";" if first_line.count(";") >= first_line.count(",") else ","
        headers = [
            h.strip().strip('"').upper().lstrip("\ufeff")
            for h in next(csv.reader([first_line], delimiter=delimiter))
        ]
        cnes_idx = _find_header_index(headers, ("CO_CNES", "CNES"))
        mun_idx = _find_header_index(
            headers,
            ("CO_MUNICIPIO", "CO_IBGE", "IBGE", "CO_MUNICIPIO_GESTOR", "CODUFMUN", "CO_MUNIC"),
        )
        exist_idx = _find_header_index(
            headers,
            ("QT_EXIST", "QT_EXISTENTE", "QTDE_EXISTENTE", "LEITOS_EXISTENTES", "LEITOS_EXISTENTE"),
        )
        comp_idx = _find_header_index(headers, ("COMP", "CO_COMPETENCIA", "COMPETENCIA", "ANOMES"))
        if exist_idx < 0:
            raise ValueError(
                f"Coluna de leitos existentes ausente em {leitos_path}: {headers[:15]}"
            )

        # Keep latest competence month per CNES (if monthly rows exist)
        rows_by_comp: dict[str, list[tuple[str, CdMun | None, int]]] = defaultdict(list)
        for row in csv.reader(handle, delimiter=delimiter):
            if len(row) <= max(cnes_idx, mun_idx, exist_idx, comp_idx):
                continue
            cd_mun: CdMun | None = None
            if mun_idx >= 0:
                raw_mun = "".join(ch for ch in row[mun_idx] if ch.isdigit())
                if raw_mun and not raw_mun.startswith(uf_prefix):
                    continue
                cd_mun = mun_lookup.get(raw_mun) or mun_lookup.get(raw_mun[:6])
            raw_cnes = row[cnes_idx].strip().strip('"') if cnes_idx >= 0 else ""
            cnes_id = raw_cnes.zfill(7) if raw_cnes.isdigit() else raw_cnes
            qty = _parse_int(row[exist_idx])
            if qty <= 0:
                continue
            comp = row[comp_idx].strip().strip('"') if comp_idx >= 0 else "latest"
            rows_by_comp[comp].append((cnes_id, cd_mun, qty))

        if not rows_by_comp:
            return {}, {}
        latest_comp = sorted(rows_by_comp.keys())[-1]
        by_cnes: dict[str, int] = defaultdict(int)
        by_mun: dict[CdMun, int] = defaultdict(int)
        for cnes_id, cd_mun, qty in rows_by_comp[latest_comp]:
            if cnes_id:
                by_cnes[cnes_id] += qty
            if cd_mun is not None:
                by_mun[cd_mun] += qty
        return dict(by_cnes), dict(by_mun)
    finally:
        handle.close()


def load_cnes_from_files(
    estab_path: Path,
    leitos_path: Path,
    uf: UfCode,
    valid_cd_muns: set[CdMun],
) -> tuple[dict[CdMun, CnesMunRecord], list[CnesPoint], list[dict[str, str]]]:
    uf_prefix = UF_IBGE_CODES[uf]
    mun_lookup = build_mun_prefix6_map(valid_cd_muns)
    leitos_by_cnes, leitos_by_mun_direct = _load_leitos_by_cnes(leitos_path, uf_prefix, mun_lookup)

    handle = _open_csv_text(estab_path)
    try:
        first_line = handle.readline()
        if not first_line:
            raise ValueError(f"Arquivo CNES estabelecimentos vazio: {estab_path}")
        delimiter = ";" if first_line.count(";") >= first_line.count(",") else ","
        headers = [
            h.strip().strip('"').upper().lstrip("\ufeff")
            for h in next(csv.reader([first_line], delimiter=delimiter))
        ]
        cnes_idx = _find_header_index(headers, ("CO_CNES", "CNES"))
        nome_idx = _find_header_index(headers, ("NO_FANTASIA", "NO_RAZAO_SOCIAL", "NOME"))
        mun_idx = _find_header_index(
            headers, ("CO_IBGE", "CO_MUNICIPIO_GESTOR", "CO_MUNICIPIO", "CODUFMUN")
        )
        tipo_idx = _find_header_index(headers, ("TP_UNIDADE", "CO_TIPO_UNIDADE"))
        lat_idx = _find_header_index(headers, ("NU_LATITUDE", "LATITUDE"))
        lon_idx = _find_header_index(headers, ("NU_LONGITUDE", "LONGITUDE"))
        if mun_idx < 0:
            raise ValueError(f"Coluna de município ausente em CNES: {headers[:15]}")

        estab_count: dict[CdMun, int] = defaultdict(int)
        hosp_count: dict[CdMun, int] = defaultdict(int)
        leitos_by_mun: dict[CdMun, int] = defaultdict(int)
        points: list[CnesPoint] = []
        rejected: list[dict[str, str]] = []

        for row in csv.reader(handle, delimiter=delimiter):
            if len(row) <= mun_idx:
                continue
            raw_mun = "".join(ch for ch in row[mun_idx] if ch.isdigit())
            if not raw_mun.startswith(uf_prefix):
                continue
            cd_mun = mun_lookup.get(raw_mun) or mun_lookup.get(raw_mun[:6])
            if cd_mun is None:
                continue

            raw_cnes = (
                row[cnes_idx].strip().strip('"') if cnes_idx >= 0 and len(row) > cnes_idx else ""
            )
            cnes_id = raw_cnes.zfill(7) if raw_cnes.isdigit() else raw_cnes
            tipo = row[tipo_idx].strip().strip('"') if tipo_idx >= 0 and len(row) > tipo_idx else ""
            nome = row[nome_idx].strip().strip('"') if nome_idx >= 0 and len(row) > nome_idx else ""
            leitos = leitos_by_cnes.get(cnes_id, 0) if cnes_id else 0

            estab_count[cd_mun] += 1
            leitos_by_mun[cd_mun] += leitos
            is_hospital = tipo in HOSPITAL_TYPES or leitos > 0
            if is_hospital:
                hosp_count[cd_mun] += 1
                raw_lat = row[lat_idx].strip() if lat_idx >= 0 and len(row) > lat_idx else ""
                raw_lon = row[lon_idx].strip() if lon_idx >= 0 and len(row) > lon_idx else ""
                lat = _parse_float(raw_lat)
                lon = _parse_float(raw_lon)
                if (
                    lat is not None
                    and lon is not None
                    and -35.0 <= lat <= 6.0
                    and -75.0 <= lon <= -32.0
                ):
                    points.append(
                        CnesPoint(
                            cnes_id=cnes_id,
                            nome=nome or f"Hospital {cnes_id}",
                            cd_mun=cd_mun,
                            lat=lat,
                            lon=lon,
                            tipo_unidade=tipo or "05",
                            leitos=leitos,
                        )
                    )
                else:
                    rejected.append(
                        {
                            "source": "cnes",
                            "name": nome or cnes_id,
                            "reason": "coordenada_invalida_ou_ausente",
                            "raw_lat": raw_lat,
                            "raw_lon": raw_lon,
                        }
                    )

        # Fallback to direct municipality totals if CNES IDs did not overlap.
        records: dict[CdMun, CnesMunRecord] = {}
        for cd in sorted(valid_cd_muns):
            beds = leitos_by_mun.get(cd, 0)
            if beds == 0 and cd in leitos_by_mun_direct:
                beds = leitos_by_mun_direct[cd]
            records[cd] = CnesMunRecord(
                cd_mun=cd,
                estabelecimentos=estab_count.get(cd, 0),
                hospitais=hosp_count.get(cd, 0),
                leitos=beds,
            )

        points.sort(key=lambda p: (-p.leitos, p.cd_mun, p.cnes_id))
        return records, points, rejected
    finally:
        handle.close()


def ensure_cnes_raw_files(
    raw_root: Path | None = None,
    manifest_path: Path | None = None,
) -> tuple[ArtifactSync, ArtifactSync]:
    downloader = make_http_stream_downloader()
    estab_sync = ensure_raw_artifact_stream(
        source_id="cnes",
        filename=CNES_ESTAB_FILENAME,
        url=CNES_ESTAB_URL,
        downloader=downloader,
        raw_root=raw_root,
        manifest_path=manifest_path,
    )
    leitos_sync = ensure_raw_artifact_stream(
        source_id="cnes",
        filename=CNES_LEITOS_FILENAME,
        url=CNES_LEITOS_URL,
        downloader=downloader,
        raw_root=raw_root,
        manifest_path=manifest_path,
    )
    meta = {
        "orgao": "Ministério da Saúde / DATASUS (OpenDataSUS)",
        "ano_ref": CNES_YEAR,
        "licenca": "CC BY-ND 3.0 / Dados Abertos SUS",
        "cobertura": "BR",
    }
    upsert_manifest_entry(manifest_path, estab_sync, meta)
    upsert_manifest_entry(manifest_path, leitos_sync, meta)
    return estab_sync, leitos_sync
