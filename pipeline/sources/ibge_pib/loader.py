from __future__ import annotations

import json
from collections import defaultdict
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

PIB_YEAR = 2021
PIB_VAR_CODES = {
    "37": "pib",
    "513": "vab_agro",
    "517": "vab_ind",
    "6575": "vab_serv",
    "525": "vab_adm",
}


@dataclass(frozen=True, slots=True)
class MunicipioPib:
    cd_mun: CdMun
    pib: float
    vab_agro: float
    vab_ind: float
    vab_serv: float
    vab_adm: float
    ano_ref: int


def pib_url_for_uf(uf: UfCode) -> str:
    uf_num = UF_IBGE_CODES[uf]
    var_list = ",".join(PIB_VAR_CODES.keys())
    return (
        f"https://apisidra.ibge.gov.br/values/t/5938/n6/in%20n3%20{uf_num}"
        f"/v/{var_list}/p/{PIB_YEAR}"
    )


def pib_filename_for_uf(uf: UfCode) -> str:
    return f"{uf.lower()}_pib_{PIB_YEAR}.json"


def load_pib_from_file(path: Path) -> dict[CdMun, MunicipioPib]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or len(raw) < 2:
        raise ValueError(f"Arquivo SIDRA PIB inválido ou vazio: {path}")

    grouped: dict[CdMun, dict[str, float]] = defaultdict(dict)
    years: dict[CdMun, int] = {}

    for row in raw[1:]:
        if not isinstance(row, dict):
            raise ValueError("Registro SIDRA PIB inválido")
        var_code = str(row.get("D2C", "")).strip()
        field = PIB_VAR_CODES.get(var_code)
        if field is None:
            continue
        cd_mun = parse_cd_mun(row.get("D1C"))
        val = parse_sidra_number(row.get("V"))
        if val is None:
            raise ValueError(
                f"Valor ausente no SIDRA PIB ({field}) para {cd_mun}: {row.get('V')!r}"
            )
        if field == "pib" and val < 0.0:
            raise ValueError(f"Valor negativo no SIDRA PIB ({field}) para {cd_mun}: {val}")
        ano_raw = str(row.get("D3C", "")).strip()
        if not ano_raw.isdigit():
            raise ValueError(f"Ano inválido no SIDRA PIB para {cd_mun}: {ano_raw!r}")
        ano_int = int(ano_raw)
        if cd_mun in years and years[cd_mun] != ano_int:
            raise ValueError(f"Anos divergentes no SIDRA PIB para {cd_mun}")
        years[cd_mun] = ano_int
        if field in grouped[cd_mun]:
            raise ValueError(f"Campo duplicado {field} no SIDRA PIB para {cd_mun}")
        grouped[cd_mun][field] = val

    required_fields = set(PIB_VAR_CODES.values())
    records: dict[CdMun, MunicipioPib] = {}
    for cd_mun in sorted(grouped):
        fields = grouped[cd_mun]
        missing = sorted(required_fields - set(fields))
        if missing:
            raise ValueError(f"Campos PIB/VAB ausentes para {cd_mun}: {missing}")
        records[cd_mun] = MunicipioPib(
            cd_mun=cd_mun,
            pib=fields["pib"],
            vab_agro=fields["vab_agro"],
            vab_ind=fields["vab_ind"],
            vab_serv=fields["vab_serv"],
            vab_adm=fields["vab_adm"],
            ano_ref=years[cd_mun],
        )
    return records


def ensure_pib_raw_file(
    uf: UfCode,
    raw_root: Path | None = None,
    manifest_path: Path | None = None,
    fetcher: Fetcher | None = None,
) -> tuple[ArtifactSync, dict[CdMun, MunicipioPib]]:
    resolved_manifest = manifest_path if manifest_path is not None else MANIFEST_PATH
    sync = ensure_raw_artifact(
        source_id="ibge_pib",
        filename=pib_filename_for_uf(uf),
        url=pib_url_for_uf(uf),
        raw_root=raw_root,
        manifest_path=resolved_manifest,
        fetcher=fetcher,
    )
    records = load_pib_from_file(sync.path)
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
