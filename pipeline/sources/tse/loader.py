from __future__ import annotations

import csv
import io
import zipfile
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from pipeline.sources._common import (
    ArtifactSync,
    StreamDownloader,
    ensure_raw_artifact_stream,
    make_http_stream_downloader,
    normalize_pt_name,
)
from pipeline.types import CdMun, UfCode

TSE_2024_URL = (
    "https://cdn.tse.jus.br/estatistica/sead/odsele/"
    "detalhe_votacao_munzona/detalhe_votacao_munzona_2024.zip"
)

# Official spelling divergences between TSE 2024 and IBGE municipal names across Brazil.
TSE_NAME_ALIASES: dict[str, str] = {
    "moji mirim": "mogi mirim",
    "moji guacu": "mogi guacu",
    "sao luis do paraitinga": "sao luiz do paraitinga",
    "biritiba mirim": "biritiba mirim",
    "embu": "embu das artes",
    "florinia": "florinea",
    "camaca": "camacan",
    "governador edison lobao": "ribeiraozinho do maranhao",
    "barao de monte alto": "barao do monte alto",
    "dona eusebia": "dona euzebia",
    "sao thome das letras": "sao tome das letras",
    "santo antonio do leverger": "santo antonio de leverger",
    "eldorado dos carajas": "eldorado do carajas",
    "munhoz de mello": "munhoz de melo",
    "boa saude": "januario cicco",
    "alvorada do oeste": "alvorada d oeste",
    "espigao do oeste": "espigao d oeste",
    "sao luiz": "sao luiz do anaua",
    "amparo de sao francisco": "amparo do sao francisco",
}

TSE_POST_CENSO_2022_NAMES: frozenset[str] = frozenset({"boa esperanca do norte"})
TSE_NO_MUNICIPAL_ELECTION_CODES: frozenset[CdMun] = frozenset(
    {CdMun("2605459"), CdMun("5300108")}
)


@dataclass(frozen=True, slots=True)
class TseMunRecord:
    cd_mun: CdMun
    eleitorado: int
    comparecimento: int
    abstencoes: int
    votos_validos: int
    votos_brancos: int
    votos_nulos: int
    anulados_sub_judice: int
    participacao_pct: float


def _parse_int(raw: str | None) -> int:
    if not raw:
        return 0
    cleaned = raw.strip().strip('"')
    if not cleaned or cleaned in {"-1", "#NULO#", "#NE#"}:
        return 0
    try:
        return max(0, int(float(cleaned.replace(",", "."))))
    except ValueError:
        return 0


def _build_name_lookup(mun_names_by_cd: Mapping[CdMun, str]) -> dict[str, CdMun]:
    lookup: dict[str, CdMun] = {}
    for cd, nome in mun_names_by_cd.items():
        key = normalize_pt_name(nome)
        if key in lookup and lookup[key] != cd:
            raise ValueError(f"Colisão de nome normalizado {key!r} entre {lookup[key]} e {cd}")
        lookup[key] = cd
    return lookup


def _resolve_mun(raw_name: str, lookup: Mapping[str, CdMun]) -> CdMun | None:
    norm = normalize_pt_name(raw_name)
    if norm in lookup:
        return lookup[norm]
    alias = TSE_NAME_ALIASES.get(norm)
    if alias and alias in lookup:
        return lookup[alias]
    # Also match apostrophe/hyphen spacing differences (e.g., D'OESTE vs D OESTE).
    target = alias or norm
    compact = "".join(ch for ch in target if ch.isalnum())
    for candidate_key, cd in lookup.items():
        if "".join(ch for ch in candidate_key if ch.isalnum()) == compact:
            return cd
    return None


def _parse_tse_stream(
    handle: TextIO,
    uf: UfCode,
    mun_names_by_cd: Mapping[CdMun, str],
) -> dict[CdMun, TseMunRecord]:
    first_line = handle.readline()
    if not first_line:
        raise ValueError("CSV do TSE vazio")
    delimiter = ";" if first_line.count(";") >= first_line.count(",") else ","
    headers = [
        h.strip().strip('"').upper().lstrip("\ufeff")
        for h in next(csv.reader([first_line], delimiter=delimiter))
    ]

    def _idx(*candidates: str) -> int:
        for c in candidates:
            if c in headers:
                return headers.index(c)
        return -1

    turno_idx = _idx("NR_TURNO")
    uf_idx = _idx("SG_UF")
    cargo_idx = _idx("CD_CARGO")
    mun_idx = _idx("NM_MUNICIPIO")
    aptos_idx = _idx("QT_APTOS")
    comp_idx = _idx("QT_COMPARECIMENTO")
    abst_idx = _idx("QT_ABSTENCOES")
    nom_val_idx = _idx("QT_VOTOS_NOMINAIS_VALIDOS", "QT_VOTOS_NOMINAIS")
    leg_val_idx = _idx("QT_VOTOS_LEGENDA_VALIDOS", "QT_TOTAL_VOTOS_LEG_VALIDOS")
    brancos_idx = _idx("QT_VOTOS_BRANCOS")
    nulos_idx = _idx("QT_VOTOS_NULOS", "QT_TOTAL_VOTOS_NULOS")
    nulos_tec_idx = _idx("QT_VOTOS_NULOS_TECNICOS", "QT_VOTOS_NULOS_APU_SEP")
    sub_jud_idx = _idx("QT_VOTOS_ANULADOS_APU_SEP", "QT_VOTOS_ANULADOS_SUB_JUDICE")
    anulados_idx = _idx("QT_VOTOS_ANULADOS")

    if mun_idx < 0 or aptos_idx < 0 or comp_idx < 0:
        raise ValueError(f"Colunas obrigatórias ausentes no CSV do TSE: {headers[:15]}")

    lookup = _build_name_lookup(mun_names_by_cd)
    agg: dict[CdMun, list[int]] = defaultdict(lambda: [0, 0, 0, 0, 0, 0, 0])
    unmatched: set[str] = set()

    for row in csv.reader(handle, delimiter=delimiter):
        if len(row) <= max(mun_idx, aptos_idx, comp_idx):
            continue
        if uf_idx >= 0 and row[uf_idx].strip().strip('"').upper() != uf:
            continue
        if turno_idx >= 0 and row[turno_idx].strip().strip('"') != "1":
            continue
        # Cargo 11 = Prefeito (1 race per municipality in 1st round)
        if cargo_idx >= 0 and row[cargo_idx].strip().strip('"') != "11":
            continue

        raw_mun = row[mun_idx].strip().strip('"')
        cd = _resolve_mun(raw_mun, lookup)
        if cd is None:
            if normalize_pt_name(raw_mun) in TSE_POST_CENSO_2022_NAMES:
                continue
            unmatched.add(raw_mun)
            continue

        aptos = _parse_int(row[aptos_idx])
        comp = _parse_int(row[comp_idx])
        abst = _parse_int(row[abst_idx]) if abst_idx >= 0 else max(0, aptos - comp)
        validos = _parse_int(row[nom_val_idx]) if nom_val_idx >= 0 else 0
        if leg_val_idx >= 0:
            validos += _parse_int(row[leg_val_idx])
        brancos = _parse_int(row[brancos_idx]) if brancos_idx >= 0 else 0
        nulos = _parse_int(row[nulos_idx]) if nulos_idx >= 0 else 0
        if nulos_tec_idx >= 0 and nulos_tec_idx != sub_jud_idx:
            nulos += _parse_int(row[nulos_tec_idx])
        sub_jud = _parse_int(row[sub_jud_idx]) if sub_jud_idx >= 0 else 0
        if anulados_idx >= 0 and anulados_idx != sub_jud_idx:
            sub_jud += _parse_int(row[anulados_idx])

        # Reconcile residual technical/annulled votes when TSE omits a sub-bucket
        accounted = validos + brancos + nulos + sub_jud
        if comp > accounted:
            sub_jud += comp - accounted

        bucket = agg[cd]
        bucket[0] += aptos
        bucket[1] += comp
        bucket[2] += abst
        bucket[3] += validos
        bucket[4] += brancos
        bucket[5] += nulos
        bucket[6] += sub_jud

    if unmatched:
        raise ValueError(
            f"Municípios TSE sem correspondência IBGE ({len(unmatched)}): {sorted(unmatched)[:10]}"
        )

    expected_cds = set(mun_names_by_cd.keys()) - TSE_NO_MUNICIPAL_ELECTION_CODES
    missing = expected_cds - set(agg.keys())
    if missing:
        missing_names = [mun_names_by_cd[c] for c in sorted(missing)[:10]]
        raise ValueError(f"Municípios IBGE ausentes no TSE ({len(missing)}): {missing_names}")

    records: dict[CdMun, TseMunRecord] = {}
    for cd in sorted(expected_cds):
        aptos, comp, abst, validos, brancos, nulos, sub_jud = agg[cd]
        pct = round(100.0 * comp / aptos, 2) if aptos > 0 else 0.0
        records[cd] = TseMunRecord(
            cd_mun=cd,
            eleitorado=aptos,
            comparecimento=comp,
            abstencoes=abst,
            votos_validos=validos,
            votos_brancos=brancos,
            votos_nulos=nulos,
            anulados_sub_judice=sub_jud,
            participacao_pct=pct,
        )
    return records


def load_tse_from_file(
    path: Path,
    uf: UfCode,
    mun_names_by_cd: Mapping[CdMun, str],
) -> dict[CdMun, TseMunRecord]:
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path, "r") as zf:
            uf_lower = f"_{uf.lower()}.csv"
            candidates = [
                n
                for n in zf.namelist()
                if n.lower().endswith(uf_lower) and not n.startswith("__MACOSX")
            ]
            if not candidates:
                candidates = [
                    n
                    for n in zf.namelist()
                    if n.lower().endswith(".csv") and not n.startswith("__MACOSX")
                ]
            if not candidates:
                raise ValueError(f"Nenhum CSV encontrado em {path}")
            with zf.open(candidates[0], "r") as raw_fp:
                text_fp = io.TextIOWrapper(raw_fp, encoding="latin-1", errors="replace", newline="")
                return _parse_tse_stream(text_fp, uf=uf, mun_names_by_cd=mun_names_by_cd)

    with path.open("r", encoding="latin-1", errors="replace", newline="") as handle:
        return _parse_tse_stream(handle, uf=uf, mun_names_by_cd=mun_names_by_cd)


def ensure_tse_raw_file(
    raw_root: Path | None = None,
    manifest_path: Path | None = None,
    downloader: StreamDownloader | None = None,
) -> ArtifactSync:
    from pipeline.sources._common import upsert_manifest_entry

    sync = ensure_raw_artifact_stream(
        source_id="tse",
        filename="detalhe_votacao_munzona_2024.zip",
        url=TSE_2024_URL,
        downloader=downloader or make_http_stream_downloader(timeout=180),
        raw_root=raw_root,
        manifest_path=manifest_path,
    )
    upsert_manifest_entry(
        manifest_path,
        sync,
        {
            "orgao": "TSE",
            "ano_ref": 2024,
            "licenca": "Dados Abertos TSE",
            "cobertura": "BR",
        },
    )
    return sync
