from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import pyarrow as pa

from pipeline.checkpoints import write_stage_checkpoint
from pipeline.reconcile import write_parquet_atomic
from pipeline.sources.aneel_siga import ensure_aneel_siga_raw_file, load_aneel_siga_from_file
from pipeline.sources.cnes import ensure_cnes_raw_files, load_cnes_from_files
from pipeline.sources.ibge_censo import ensure_censo_raw_file
from pipeline.sources.ibge_malhas import ensure_uf_raw_files, load_municipios_from_files
from pipeline.sources.ibge_pib import ensure_pib_raw_file
from pipeline.sources.ibge_saneamento import ensure_saneamento_raw_file
from pipeline.sources.inep_escolar import (
    ensure_inep_escolar_raw_file,
    load_inep_escolar_from_file,
)
from pipeline.sources.inep_ideb import ensure_inep_ideb_raw_files, load_inep_ideb_from_files
from pipeline.sources.inep_superior import (
    ensure_inep_superior_raw_file,
    load_inep_superior_from_file,
)
from pipeline.sources.ipea_atlas_violencia import ensure_atlas_violencia_raw_file
from pipeline.sources.ipea_idhm import ensure_ipea_idhm_raw_files, load_ipea_idhm_from_files
from pipeline.sources.mds_bolsa import ensure_bolsa_familia_raw_files
from pipeline.sources.rais import ensure_rais_raw_file, load_rais_from_file
from pipeline.sources.tse import ensure_tse_raw_file, load_tse_from_file
from pipeline.types import UF_IBGE_CODES, CdMun, UfCode

MANIFEST_PATH = Path("data/manifest.json")
NATIONAL_DESCONTENTAMENTO_SOURCE = "ipea_atlas_violencia"


def run_br_sources_pipeline(
    raw_root: Path | None = None,
    manifest_path: Path = MANIFEST_PATH,
    processed_dir: Path = Path("data/processed"),
) -> dict[str, Any]:
    downloads_count = 0

    atlas_sync, atlas_records = ensure_atlas_violencia_raw_file(
        raw_root=raw_root,
        manifest_path=manifest_path,
    )
    bf_fam_sync, bf_val_sync, bf_records = ensure_bolsa_familia_raw_files(
        raw_root=raw_root,
        manifest_path=manifest_path,
    )
    san_sync, san_records = ensure_saneamento_raw_file(
        raw_root=raw_root,
        manifest_path=manifest_path,
    )
    rais_sync = ensure_rais_raw_file(raw_root=raw_root, manifest_path=manifest_path)
    esc_sync = ensure_inep_escolar_raw_file(raw_root=raw_root, manifest_path=manifest_path)
    sup_sync = ensure_inep_superior_raw_file(raw_root=raw_root, manifest_path=manifest_path)
    ideb_ai_sync, ideb_af_sync, ideb_em_sync = ensure_inep_ideb_raw_files(
        raw_root=raw_root,
        manifest_path=manifest_path,
    )
    cnes_estab_sync, cnes_leitos_sync = ensure_cnes_raw_files(
        raw_root=raw_root,
        manifest_path=manifest_path,
    )
    aneel_sync = ensure_aneel_siga_raw_file(raw_root=raw_root, manifest_path=manifest_path)
    tse_sync = ensure_tse_raw_file(raw_root=raw_root, manifest_path=manifest_path)
    idhm_sync, gini_sync = ensure_ipea_idhm_raw_files(
        raw_root=raw_root,
        manifest_path=manifest_path,
    )

    downloads_count += sum(
        1
        for flag in (
            atlas_sync.downloaded,
            bf_fam_sync.downloaded,
            bf_val_sync.downloaded,
            san_sync.downloaded,
            rais_sync.downloaded,
            esc_sync.downloaded,
            sup_sync.downloaded,
            ideb_ai_sync.downloaded,
            ideb_af_sync.downloaded,
            ideb_em_sync.downloaded,
            cnes_estab_sync.downloaded,
            cnes_leitos_sync.downloaded,
            aneel_sync.downloaded,
            tse_sync.downloaded,
            idhm_sync.downloaded,
            gini_sync.downloaded,
        )
        if flag
    )

    ordered_ufs: list[UfCode] = sorted(UF_IBGE_CODES.keys())
    all_muns: dict[CdMun, tuple[UfCode, str]] = {}
    pop_by_mun: dict[CdMun, int] = {}
    pib_by_mun: dict[CdMun, float] = {}
    muns_by_uf: dict[UfCode, dict[CdMun, str]] = {}

    for uf in ordered_ufs:
        m_sync = ensure_uf_raw_files(uf=uf, raw_root=raw_root, manifest_path=manifest_path)
        c_sync, censo = ensure_censo_raw_file(uf=uf, raw_root=raw_root, manifest_path=manifest_path)
        p_sync, pib = ensure_pib_raw_file(uf=uf, raw_root=raw_root, manifest_path=manifest_path)
        downloads_count += (
            len(m_sync.downloaded_files)
            + (1 if c_sync.downloaded else 0)
            + (1 if p_sync.downloaded else 0)
        )
        muns = load_municipios_from_files(m_sync.malha_path, m_sync.municipios_path)
        uf_map: dict[CdMun, str] = {}
        for m in muns:
            cd = CdMun(m.cd_mun)
            all_muns[cd] = (uf, m.nome)
            uf_map[cd] = m.nome
            pop_by_mun[cd] = censo[cd].pop
            pib_by_mun[cd] = pib[cd].pib
        muns_by_uf[uf] = uf_map

    all_cds = set(all_muns.keys())
    idhm_all = load_ipea_idhm_from_files(idhm_sync.path, gini_sync.path, all_cds)

    vinculos_by_mun: dict[CdMun, int] = defaultdict(int)
    mat_esc_by_mun: dict[CdMun, int] = {}
    mat_sup_by_mun: dict[CdMun, int] = {}
    ideb_af_by_mun: dict[CdMun, float | None] = {}
    leitos_by_mun: dict[CdMun, int] = {}
    tse_aptos_by_mun: dict[CdMun, int] = {}
    tse_comp_by_mun: dict[CdMun, int] = {}
    usinas_by_uf: dict[str, tuple[int, float]] = {}

    rais_rows_all, _rais_stats = load_rais_from_file(
        rais_sync.path,
        uf=None,
        valid_cd_muns=all_cds,
    )
    for row in rais_rows_all:
        vinculos_by_mun[row.cd_mun] += row.vinculos
    print(f"[PR7 RAIS BR] vinculos={sum(vinculos_by_mun.values()):,}")

    esc_all = load_inep_escolar_from_file(esc_sync.path, uf=None, valid_cd_muns=all_cds)
    for cd, esc_rec in esc_all.items():
        mat_esc_by_mun[cd] = esc_rec.matriculas_basica
    print(f"[PR7 INEP Escolar BR] matriculas={sum(mat_esc_by_mun.values()):,}")

    sup_all = load_inep_superior_from_file(sup_sync.path, uf=None, valid_cd_muns=all_cds)
    for cd, sup_rec in sup_all.items():
        mat_sup_by_mun[cd] = sup_rec.matriculas_superior
    print(f"[PR7 INEP Superior BR] matriculas={sum(mat_sup_by_mun.values()):,}")

    ideb_all = load_inep_ideb_from_files(
        ideb_ai_sync.path,
        ideb_af_sync.path,
        ideb_em_sync.path,
        uf=None,
        valid_cd_muns=all_cds,
    )
    for cd, ideb_rec in ideb_all.items():
        ideb_af_by_mun[cd] = ideb_rec.ideb_af
    print(f"[PR7 INEP IDEB BR] cobertos={sum(1 for v in ideb_af_by_mun.values() if v is not None)}")

    cnes_all, _cnes_pts, _cnes_rej = load_cnes_from_files(
        cnes_estab_sync.path,
        cnes_leitos_sync.path,
        uf=None,
        valid_cd_muns=all_cds,
    )
    for cd, cnes_rec in cnes_all.items():
        leitos_by_mun[cd] = cnes_rec.leitos
    print(f"[PR7 CNES BR] leitos={sum(leitos_by_mun.values()):,}")

    for uf in ordered_ufs:
        uf_map = muns_by_uf[uf]
        plants_uf, _plants_rej = load_aneel_siga_from_file(aneel_sync.path, uf=uf)
        usinas_by_uf[uf] = (len(plants_uf), round(sum(p.potencia_mw for p in plants_uf), 1))

        if uf != "DF":
            tse_uf = load_tse_from_file(tse_sync.path, uf=uf, mun_names_by_cd=uf_map)
            for cd, tse_rec in tse_uf.items():
                tse_aptos_by_mun[cd] = tse_rec.eleitorado
                tse_comp_by_mun[cd] = tse_rec.comparecimento

    sorted_cds = sorted(all_cds)
    rows_cd: list[str] = []
    rows_uf: list[str] = []
    rows_nome: list[str] = []
    rows_pop: list[int] = []
    rows_pib: list[float] = []
    rows_vinc: list[int] = []
    rows_esc: list[int] = []
    rows_sup: list[int] = []
    rows_ideb: list[float | None] = []
    rows_leitos: list[int] = []
    rows_tse_aptos: list[int | None] = []
    rows_tse_comp: list[int | None] = []
    rows_idhm: list[float | None] = []
    rows_gini: list[float | None] = []
    rows_homic: list[float | None] = []
    rows_homic_low_pop: list[bool] = []
    rows_bf_fam: list[int | None] = []
    rows_bf_val: list[float | None] = []
    rows_san: list[float | None] = []

    post_2010_missing_idhm: list[str] = []
    for cd in sorted_cds:
        uf, nome = all_muns[cd]
        pop_val = pop_by_mun[cd]
        rows_cd.append(str(cd))
        rows_uf.append(uf)
        rows_nome.append(nome)
        rows_pop.append(pop_val)
        rows_pib.append(pib_by_mun[cd])
        rows_vinc.append(vinculos_by_mun.get(cd, 0))
        rows_esc.append(mat_esc_by_mun.get(cd, 0))
        rows_sup.append(mat_sup_by_mun.get(cd, 0))
        rows_ideb.append(ideb_af_by_mun.get(cd))
        rows_leitos.append(leitos_by_mun.get(cd, 0))
        rows_tse_aptos.append(tse_aptos_by_mun.get(cd))
        rows_tse_comp.append(tse_comp_by_mun.get(cd))

        idhm_rec = idhm_all.get(cd)
        if idhm_rec is None or idhm_rec.idhm is None:
            post_2010_missing_idhm.append(str(cd))
            rows_idhm.append(None)
            rows_gini.append(idhm_rec.gini if idhm_rec is not None else None)
        else:
            rows_idhm.append(idhm_rec.idhm)
            rows_gini.append(idhm_rec.gini)

        atlas_rec = atlas_records.get(cd)
        rows_homic.append(atlas_rec.taxa_homic_100k if atlas_rec is not None else None)
        rows_homic_low_pop.append(pop_val < 20_000)

        bf_rec = bf_records.get(cd)
        rows_bf_fam.append(bf_rec.familias if bf_rec is not None else None)
        rows_bf_val.append(bf_rec.valor_mil_reais if bf_rec is not None else None)

        san_rec = san_records.get(cd)
        rows_san.append(san_rec.esgoto_adequado_pct if san_rec is not None else None)

    table = pa.table(
        {
            "cd_mun": rows_cd,
            "uf": rows_uf,
            "nome": rows_nome,
            "pop_2022": rows_pop,
            "pib_mil_2021": rows_pib,
            "vinculos_rais": rows_vinc,
            "mat_escolar": rows_esc,
            "mat_superior": rows_sup,
            "ideb_af": rows_ideb,
            "leitos_cnes": rows_leitos,
            "tse_aptos": rows_tse_aptos,
            "tse_comparecimento": rows_tse_comp,
            "idhm_2010": rows_idhm,
            "gini_2010": rows_gini,
            "homic_taxa_atlas": rows_homic,
            "homic_baixa_pop": rows_homic_low_pop,
            "bf_familias": rows_bf_fam,
            "bf_valor_mil": rows_bf_val,
            "saneamento_esgoto_pct": rows_san,
        },
        schema=pa.schema(
            [
                ("cd_mun", pa.string()),
                ("uf", pa.string()),
                ("nome", pa.string()),
                ("pop_2022", pa.int64()),
                ("pib_mil_2021", pa.float64()),
                ("vinculos_rais", pa.int64()),
                ("mat_escolar", pa.int64()),
                ("mat_superior", pa.int64()),
                ("ideb_af", pa.float64()),
                ("leitos_cnes", pa.int64()),
                ("tse_aptos", pa.int64()),
                ("tse_comparecimento", pa.int64()),
                ("idhm_2010", pa.float64()),
                ("gini_2010", pa.float64()),
                ("homic_taxa_atlas", pa.float64()),
                ("homic_baixa_pop", pa.bool_()),
                ("bf_familias", pa.int64()),
                ("bf_valor_mil", pa.float64()),
                ("saneamento_esgoto_pct", pa.float64()),
            ]
        ),
    )
    out_parquet = processed_dir / "br_municipios_indicators.parquet"
    write_parquet_atomic(table, out_parquet)

    checkpoint: dict[str, Any] = {
        "uf": "BR",
        "mun_count": len(sorted_cds),
        "descontentamento_nacional_source": NATIONAL_DESCONTENTAMENTO_SOURCE,
        "downloads_count": downloads_count,
        "coverage": {
            "rais": sum(1 for v in rows_vinc if v > 0),
            "inep_escolar": sum(1 for v in rows_esc if v > 0),
            "inep_superior": sum(1 for v in rows_sup if v > 0),
            "inep_ideb_af": sum(1 for v in rows_ideb if v is not None),
            "cnes_leitos": sum(1 for v in rows_leitos if v > 0),
            "tse_2024": sum(1 for v in rows_tse_aptos if v is not None),
            "ipea_idhm_2010": sum(1 for v in rows_idhm if v is not None),
            "ipea_atlas_violencia": sum(1 for v in rows_homic if v is not None),
            "mds_bolsa_familia": sum(1 for v in rows_bf_fam if v is not None),
            "ibge_saneamento_2022": sum(1 for v in rows_san if v is not None),
        },
        "post_2010_missing_idhm": post_2010_missing_idhm,
        "totals": {
            "pop_2022": sum(rows_pop),
            "vinculos_rais": sum(rows_vinc),
            "mat_escolar": sum(rows_esc),
            "mat_superior": sum(rows_sup),
            "leitos_cnes": sum(rows_leitos),
            "tse_aptos": sum(v for v in rows_tse_aptos if v is not None),
            "tse_comparecimento": sum(v for v in rows_tse_comp if v is not None),
            "bf_familias": sum(v for v in rows_bf_fam if v is not None),
            "usinas_count": sum(c for c, _ in usinas_by_uf.values()),
            "usinas_mw": round(sum(mw for _, mw in usinas_by_uf.values()), 1),
        },
    }
    write_stage_checkpoint(Path("data/checkpoints/br_sources.json"), checkpoint)
    print(json.dumps(checkpoint["totals"], indent=2, ensure_ascii=False))
    print(json.dumps(checkpoint["coverage"], indent=2, ensure_ascii=False))
    return checkpoint


if __name__ == "__main__":
    run_br_sources_pipeline()
