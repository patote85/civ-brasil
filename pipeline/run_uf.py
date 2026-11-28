from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import pyarrow as pa

from pipeline.checkpoints import write_stage_checkpoint
from pipeline.civ import export_uf_web_bundle, load_civ_rules
from pipeline.civ.districts import (
    compute_citizen_sector_shares,
    compute_location_quotients,
    select_city_districts,
)
from pipeline.grid.h3_grid import (
    H3_RESOLUTION,
    build_hex_summaries,
    build_municipio_hex_table,
    write_municipio_hex_parquet,
    write_sp_hex_json,
)
from pipeline.reconcile import (
    AssignedPoint,
    PointKind,
    assign_points_to_grid,
    build_dasymetric_weights,
    reconcile_rate,
    reconcile_sum,
    sum_point_values_by_hex,
    write_parquet_atomic,
)
from pipeline.sources._common import atomic_write_bytes
from pipeline.sources.aneel_siga import ensure_aneel_siga_raw_file, load_aneel_siga_from_file
from pipeline.sources.antaq import ensure_antaq_raw_file, load_antaq_from_files
from pipeline.sources.cnes import ensure_cnes_raw_files, load_cnes_from_files
from pipeline.sources.ibge_censo import ensure_censo_raw_file
from pipeline.sources.ibge_grade import ensure_grade_raw_file, load_grade_cells_from_file
from pipeline.sources.ibge_malhas import ensure_sp_raw_files, load_municipios_from_files
from pipeline.sources.ibge_pib import ensure_pib_raw_file
from pipeline.sources.inep_escolar import ensure_inep_escolar_raw_file, load_inep_escolar_from_file
from pipeline.sources.inep_ideb import ensure_inep_ideb_raw_files, load_inep_ideb_from_files
from pipeline.sources.inep_superior import (
    ensure_inep_superior_raw_file,
    load_inep_superior_from_file,
)
from pipeline.sources.ipea_idhm import ensure_ipea_idhm_raw_files, load_ipea_idhm_from_files
from pipeline.sources.rais import ensure_rais_raw_file, load_rais_from_file
from pipeline.sources.ssp_sp import ensure_ssp_sp_raw_file, load_ssp_sp_from_file
from pipeline.sources.tse import ensure_tse_raw_file, load_tse_from_file
from pipeline.types import CdMun, H3Index, UfCode, parse_uf_code

RULES_PATH = Path("pipeline/civ/civ_rules.yaml")
MANIFEST_PATH = Path("data/manifest.json")


def run_uf_pipeline(
    uf: UfCode,
    raw_root: Path | None = None,
    manifest_path: Path = MANIFEST_PATH,
    rules_path: Path = RULES_PATH,
) -> None:
    if uf != "SP":
        raise NotImplementedError(f"Expansão para UF={uf} entra no PR 6 (piloto atual: SP)")

    uf_slug = uf.lower()
    malhas_sync = ensure_sp_raw_files(raw_root=raw_root, manifest_path=manifest_path)
    censo_sync, censo = ensure_censo_raw_file(
        uf=uf,
        raw_root=raw_root,
        manifest_path=manifest_path,
    )
    pib_sync, pib = ensure_pib_raw_file(
        uf=uf,
        raw_root=raw_root,
        manifest_path=manifest_path,
    )
    grade_sync = ensure_grade_raw_file(raw_root=raw_root, manifest_path=manifest_path)
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
    antaq_sync = ensure_antaq_raw_file(raw_root=raw_root, manifest_path=manifest_path)
    tse_sync = ensure_tse_raw_file(raw_root=raw_root, manifest_path=manifest_path)
    idhm_sync, gini_sync = ensure_ipea_idhm_raw_files(
        raw_root=raw_root,
        manifest_path=manifest_path,
    )
    ssp_sync = ensure_ssp_sp_raw_file(raw_root=raw_root, manifest_path=manifest_path)

    sources_status = [
        ("ibge_malhas", len(malhas_sync.downloaded_files) > 0),
        ("ibge_censo", censo_sync.downloaded),
        ("ibge_pib", pib_sync.downloaded),
        ("ibge_grade", grade_sync.downloaded),
        ("rais", rais_sync.downloaded),
        ("inep_escolar", esc_sync.downloaded),
        ("inep_superior", sup_sync.downloaded),
        (
            "inep_ideb",
            ideb_ai_sync.downloaded or ideb_af_sync.downloaded or ideb_em_sync.downloaded,
        ),
        ("cnes", cnes_estab_sync.downloaded or cnes_leitos_sync.downloaded),
        ("aneel_siga", aneel_sync.downloaded),
        ("antaq", antaq_sync.downloaded),
        ("tse_2024", tse_sync.downloaded),
        ("ipea_idhm", idhm_sync.downloaded or gini_sync.downloaded),
        ("ssp_sp", ssp_sync.downloaded),
    ]
    no_download_count = sum(1 for _, downloaded in sources_status if not downloaded)
    print(f"Fontes {uf} sincronizadas (sem download: {no_download_count}/{len(sources_status)}).")

    municipios = load_municipios_from_files(malhas_sync.malha_path, malhas_sync.municipios_path)
    mun_hex_rows = build_municipio_hex_table(municipios, resolution=H3_RESOLUTION)
    nomes_por_cd = {m.cd_mun: m.nome for m in municipios}
    ordered_muns = [CdMun(m.cd_mun) for m in sorted(municipios, key=lambda x: x.cd_mun)]
    valid_cd_muns = set(ordered_muns)

    write_municipio_hex_parquet(mun_hex_rows, Path("data/processed/sp_municipio_hex.parquet"))
    write_sp_hex_json(
        build_hex_summaries(mun_hex_rows, nomes_por_cd),
        Path("web/public/data/sp_hex.json"),
    )

    minx = min(m.geometry.bounds[0] for m in municipios)
    miny = min(m.geometry.bounds[1] for m in municipios)
    maxx = max(m.geometry.bounds[2] for m in municipios)
    maxy = max(m.geometry.bounds[3] for m in municipios)
    grade_cells = load_grade_cells_from_file(grade_sync.path, bbox=(minx, miny, maxx, maxy))

    weights = build_dasymetric_weights(municipios, mun_hex_rows, grade_cells)
    fallback_muns = sorted({w.cd_mun for w in weights if w.method == "area_fallback"})

    pop_by_mun = {cd: float(rec.pop) for cd, rec in censo.items()}
    pib_by_mun = {cd: rec.pib for cd, rec in pib.items()}
    vab_agro_by_mun = {cd: rec.vab_agro for cd, rec in pib.items()}
    vab_ind_by_mun = {cd: rec.vab_ind for cd, rec in pib.items()}
    vab_serv_by_mun = {cd: rec.vab_serv for cd, rec in pib.items()}
    vab_adm_by_mun = {cd: rec.vab_adm for cd, rec in pib.items()}

    hex_pop = reconcile_sum(pop_by_mun, weights)
    hex_pib = reconcile_sum(pib_by_mun, weights)
    hex_vab_agro = reconcile_sum(vab_agro_by_mun, weights)
    hex_vab_ind = reconcile_sum(vab_ind_by_mun, weights)
    hex_vab_serv = reconcile_sum(vab_serv_by_mun, weights)
    hex_vab_adm = reconcile_sum(vab_adm_by_mun, weights)

    proc_dir = Path("data/processed") / uf_slug
    weights_table = pa.table(
        {
            "cd_mun": [str(w.cd_mun) for w in weights],
            "h3": [str(w.h3) for w in weights],
            "weight": [w.weight for w in weights],
            "method": [w.method for w in weights],
        }
    )
    write_parquet_atomic(weights_table, proc_dir / "dasymetric_weights.parquet")

    mun_base_table = pa.table(
        {
            "cd_mun": [str(cd) for cd in ordered_muns],
            "nome": [nomes_por_cd[str(cd)] for cd in ordered_muns],
            "pop": [censo[cd].pop for cd in ordered_muns],
            "pib": [pib[cd].pib for cd in ordered_muns],
            "vab_agro": [pib[cd].vab_agro for cd in ordered_muns],
            "vab_ind": [pib[cd].vab_ind for cd in ordered_muns],
            "vab_serv": [pib[cd].vab_serv for cd in ordered_muns],
            "vab_adm": [pib[cd].vab_adm for cd in ordered_muns],
        }
    )
    write_parquet_atomic(mun_base_table, proc_dir / "mun_base.parquet")

    ordered_hexes = sorted(hex_pop.keys())
    valid_hexes = set(ordered_hexes)
    hex_base_table = pa.table(
        {
            "h3": [str(cell) for cell in ordered_hexes],
            "pop": [hex_pop[cell] for cell in ordered_hexes],
            "pib": [hex_pib[cell] for cell in ordered_hexes],
            "vab_agro": [hex_vab_agro[cell] for cell in ordered_hexes],
            "vab_ind": [hex_vab_ind[cell] for cell in ordered_hexes],
            "vab_serv": [hex_vab_serv[cell] for cell in ordered_hexes],
            "vab_adm": [hex_vab_adm[cell] for cell in ordered_hexes],
        }
    )
    write_parquet_atomic(hex_base_table, proc_dir / "hex_base.parquet")

    # --- PR 3: Economy, Services, Points & City View ---
    rais_records, rais_stats = load_rais_from_file(
        rais_sync.path, uf=uf, valid_cd_muns=valid_cd_muns
    )
    district_scores, uf_ql = compute_location_quotients(rais_records, ordered_muns)
    city_districts = select_city_districts(district_scores)
    citizen_shares = compute_citizen_sector_shares(rais_records)

    vinculos_by_mun: dict[CdMun, int] = defaultdict(int)
    estab_rais_by_mun: dict[CdMun, int] = defaultdict(int)
    for rec in rais_records:
        vinculos_by_mun[rec.cd_mun] += rec.vinculos
        estab_rais_by_mun[rec.cd_mun] += rec.estabelecimentos

    max_ql_by_mun: dict[CdMun, float] = {}
    top_district_by_mun: dict[CdMun, str] = {}
    for cd in ordered_muns:
        top_list = city_districts.get(cd, [])
        if top_list:
            max_ql_by_mun[cd] = top_list[0].ql
            top_district_by_mun[cd] = top_list[0].district_name
        else:
            max_ql_by_mun[cd] = 0.0
            top_district_by_mun[cd] = "Diversificado"

    esc_map = load_inep_escolar_from_file(esc_sync.path, uf=uf, valid_cd_muns=valid_cd_muns)
    sup_map = load_inep_superior_from_file(sup_sync.path, uf=uf, valid_cd_muns=valid_cd_muns)
    ideb_map = load_inep_ideb_from_files(
        ideb_ai_sync.path,
        ideb_af_sync.path,
        ideb_em_sync.path,
        uf=uf,
        valid_cd_muns=valid_cd_muns,
    )
    cnes_mun, cnes_points, cnes_pre_rej = load_cnes_from_files(
        cnes_estab_sync.path,
        cnes_leitos_sync.path,
        uf=uf,
        valid_cd_muns=valid_cd_muns,
    )
    plants, aneel_pre_rej = load_aneel_siga_from_file(aneel_sync.path, uf=uf)
    mun_name_to_cd = {m.nome: CdMun(m.cd_mun) for m in municipios}
    optional_cargo = antaq_sync.path.parent / "antaq_carga.csv"
    ports, antaq_pre_rej = load_antaq_from_files(
        antaq_sync.path,
        uf=uf,
        mun_name_to_cd=mun_name_to_cd,
        cargo_path=optional_cargo if optional_cargo.is_file() else None,
    )

    plant_items: list[tuple[PointKind, str, str, float, str, float, float, str]] = [
        ("usina", p.nome, p.fonte, p.potencia_mw, "MW", p.lat, p.lon, "") for p in plants
    ]
    port_items: list[tuple[PointKind, str, str, float, str, float, float, str]] = [
        (
            "porto",
            p.nome,
            p.tipo,
            p.carga_toneladas,
            "t",
            p.lat,
            p.lon,
            str(p.cd_mun) if p.cd_mun else "",
        )
        for p in ports
    ]
    hosp_items: list[tuple[PointKind, str, str, float, str, float, float, str]] = [
        (
            "hospital",
            p.nome,
            f"Tipo {p.tipo_unidade}",
            float(p.leitos),
            "leitos",
            p.lat,
            p.lon,
            str(p.cd_mun),
        )
        for p in cnes_points
    ]

    acc_plants, rej_plants = assign_points_to_grid(plant_items, valid_hexes, "aneel_siga")
    acc_ports, rej_ports = assign_points_to_grid(port_items, valid_hexes, "antaq")
    acc_hosps, rej_hosps = assign_points_to_grid(hosp_items, valid_hexes, "cnes")
    all_points: list[AssignedPoint] = [*acc_plants, *acc_ports, *acc_hosps]

    all_rejected: list[dict[str, str]] = [
        *aneel_pre_rej,
        *antaq_pre_rej,
        *cnes_pre_rej,
        *[
            {
                "source": r.source,
                "name": r.name,
                "reason": r.reason,
                "raw_lat": r.raw_lat,
                "raw_lon": r.raw_lon,
            }
            for r in (*rej_plants, *rej_ports, *rej_hosps)
        ],
    ]
    all_rejected.sort(key=lambda r: (r["source"], r["reason"], r["name"]))
    atomic_write_bytes(
        proc_dir / "rejected_points.json",
        (
            json.dumps(
                {"uf": uf, "count": len(all_rejected), "items": all_rejected},
                indent=2,
                ensure_ascii=False,
            )
            + "\n"
        ).encode("utf-8"),
    )

    # Reconcile PR 3 variables onto H3 res 5
    hex_vinculos = reconcile_sum(
        {cd: float(vinculos_by_mun.get(cd, 0)) for cd in ordered_muns}, weights
    )
    hex_max_ql = reconcile_rate(max_ql_by_mun, weights, pop_by_mun)
    hex_mat_bas = reconcile_sum(
        {cd: float(esc_map[cd].matriculas_basica) for cd in ordered_muns}, weights
    )
    hex_mat_sup = reconcile_sum(
        {cd: float(sup_map[cd].matriculas_superior) for cd in ordered_muns}, weights
    )
    hex_ideb = reconcile_rate(
        {cd: ideb_map[cd].ideb_medio for cd in ordered_muns}, weights, pop_by_mun
    )
    hex_cnes_estab = reconcile_sum(
        {cd: float(cnes_mun[cd].estabelecimentos) for cd in ordered_muns}, weights
    )
    hex_leitos = reconcile_sum({cd: float(cnes_mun[cd].leitos) for cd in ordered_muns}, weights)
    hex_mw = sum_point_values_by_hex(acc_plants, ordered_hexes)
    port_count_by_hex: dict[H3Index, int] = defaultdict(int)
    for pt in acc_ports:
        port_count_by_hex[pt.h3] += 1

    write_parquet_atomic(
        pa.table(
            {
                "cd_mun": [str(cd) for cd in ordered_muns],
                "vinculos": [vinculos_by_mun.get(cd, 0) for cd in ordered_muns],
                "estabelecimentos": [estab_rais_by_mun.get(cd, 0) for cd in ordered_muns],
                "max_ql": [max_ql_by_mun[cd] for cd in ordered_muns],
                "top_district": [top_district_by_mun[cd] for cd in ordered_muns],
            }
        ),
        proc_dir / "mun_trabalho.parquet",
    )
    write_parquet_atomic(
        pa.table(
            {
                "cd_mun": [str(s.cd_mun) for s in district_scores],
                "cnae_div": [s.cnae_div for s in district_scores],
                "cnae_secao": [s.cnae_secao for s in district_scores],
                "district_name": [s.district_name for s in district_scores],
                "vinculos": [s.vinculos for s in district_scores],
                "ql": [s.ql for s in district_scores],
            }
        ),
        proc_dir / "mun_distritos.parquet",
    )
    write_parquet_atomic(
        pa.table(
            {
                "cd_mun": [str(cd) for cd in ordered_muns],
                "escolas": [esc_map[cd].escolas for cd in ordered_muns],
                "matriculas_basica": [esc_map[cd].matriculas_basica for cd in ordered_muns],
                "ies": [sup_map[cd].ies for cd in ordered_muns],
                "matriculas_superior": [sup_map[cd].matriculas_superior for cd in ordered_muns],
                "ideb_ai": [ideb_map[cd].ideb_ai for cd in ordered_muns],
                "ideb_af": [ideb_map[cd].ideb_af for cd in ordered_muns],
                "ideb_em": [ideb_map[cd].ideb_em for cd in ordered_muns],
                "ideb_medio": [ideb_map[cd].ideb_medio for cd in ordered_muns],
                "cnes_estabelecimentos": [cnes_mun[cd].estabelecimentos for cd in ordered_muns],
                "cnes_hospitais": [cnes_mun[cd].hospitais for cd in ordered_muns],
                "cnes_leitos": [cnes_mun[cd].leitos for cd in ordered_muns],
            }
        ),
        proc_dir / "mun_servicos.parquet",
    )
    write_parquet_atomic(
        pa.table(
            {
                "h3": [str(cell) for cell in ordered_hexes],
                "vinculos": [hex_vinculos[cell] for cell in ordered_hexes],
                "max_ql": [hex_max_ql[cell] for cell in ordered_hexes],
                "matriculas_basica": [hex_mat_bas[cell] for cell in ordered_hexes],
                "matriculas_superior": [hex_mat_sup[cell] for cell in ordered_hexes],
                "ideb_medio": [hex_ideb[cell] for cell in ordered_hexes],
                "cnes_estabelecimentos": [hex_cnes_estab[cell] for cell in ordered_hexes],
                "leitos": [hex_leitos[cell] for cell in ordered_hexes],
                "potencia_mw": [hex_mw[cell] for cell in ordered_hexes],
                "portos_count": [port_count_by_hex.get(cell, 0) for cell in ordered_hexes],
            }
        ),
        proc_dir / "hex_economia.parquet",
    )
    write_parquet_atomic(
        pa.table(
            {
                "kind": [p.kind for p in all_points],
                "name": [p.name for p in all_points],
                "category": [p.category for p in all_points],
                "value": [p.value for p in all_points],
                "unit": [p.unit for p in all_points],
                "h3": [str(p.h3) for p in all_points],
                "lat": [p.lat for p in all_points],
                "lon": [p.lon for p in all_points],
                "cd_mun": [p.cd_mun for p in all_points],
            }
        ),
        proc_dir / "pontos_infra.parquet",
    )

    # Build City View profiles for top 80 UF municipalities by population.
    hex_to_muns: dict[H3Index, set[CdMun]] = defaultdict(set)
    for row in mun_hex_rows:
        hex_to_muns[H3Index(row.h3)].add(CdMun(row.cd_mun))

    mw_by_mun_approx: dict[CdMun, float] = defaultdict(float)
    usinas_by_mun_approx: dict[CdMun, int] = defaultdict(int)
    for pt in acc_plants:
        muns_in_hex = sorted(hex_to_muns.get(pt.h3, set()))
        if muns_in_hex:
            # Attribute to highest-population municipality overlapping that hex
            owner = max(muns_in_hex, key=lambda c: pop_by_mun.get(c, 0.0))
            mw_by_mun_approx[owner] += pt.value
            usinas_by_mun_approx[owner] += 1

    portos_by_mun: dict[CdMun, int] = defaultdict(int)
    for pt in acc_ports:
        if pt.cd_mun:
            portos_by_mun[CdMun(pt.cd_mun)] += 1

    mun_names_cd: dict[CdMun, str] = {CdMun(k): v for k, v in nomes_por_cd.items()}
    pop_int_by_mun: dict[CdMun, int] = {cd: censo[cd].pop for cd in ordered_muns}

    tse_map = load_tse_from_file(tse_sync.path, uf=uf, mun_names_by_cd=mun_names_cd)
    idhm_map = load_ipea_idhm_from_files(
        idhm_sync.path, gini_sync.path, valid_cd_muns=valid_cd_muns
    )
    ssp_map = load_ssp_sp_from_file(
        ssp_sync.path,
        mun_names_by_cd=mun_names_cd,
        pop_by_mun=pop_int_by_mun,
    )

    hex_participacao = reconcile_rate(
        {cd: tse_map[cd].participacao_pct for cd in ordered_muns},
        weights,
        pop_by_mun,
    )
    hex_idhm = reconcile_rate(
        {cd: idhm_map[cd].idhm for cd in ordered_muns},
        weights,
        pop_by_mun,
    )
    hex_gini = reconcile_rate(
        {cd: idhm_map[cd].gini for cd in ordered_muns},
        weights,
        pop_by_mun,
    )
    hex_hom_100k = reconcile_rate(
        {cd: ssp_map[cd].homicidio_100k for cd in ordered_muns},
        weights,
        pop_by_mun,
    )
    hex_roubo_100k = reconcile_rate(
        {cd: ssp_map[cd].roubo_100k for cd in ordered_muns},
        weights,
        pop_by_mun,
    )

    write_parquet_atomic(
        pa.table(
            {
                "cd_mun": [str(cd) for cd in ordered_muns],
                "eleitorado": [tse_map[cd].eleitorado for cd in ordered_muns],
                "comparecimento": [tse_map[cd].comparecimento for cd in ordered_muns],
                "abstencoes": [tse_map[cd].abstencoes for cd in ordered_muns],
                "votos_validos": [tse_map[cd].votos_validos for cd in ordered_muns],
                "votos_brancos": [tse_map[cd].votos_brancos for cd in ordered_muns],
                "votos_nulos": [tse_map[cd].votos_nulos for cd in ordered_muns],
                "anulados_sub_judice": [tse_map[cd].anulados_sub_judice for cd in ordered_muns],
                "participacao_pct": [tse_map[cd].participacao_pct for cd in ordered_muns],
                "idhm": [idhm_map[cd].idhm for cd in ordered_muns],
                "gini": [idhm_map[cd].gini for cd in ordered_muns],
                "homicidio": [ssp_map[cd].homicidio for cd in ordered_muns],
                "roubo": [ssp_map[cd].roubo for cd in ordered_muns],
                "furto": [ssp_map[cd].furto for cd in ordered_muns],
                "homicidio_100k": [ssp_map[cd].homicidio_100k for cd in ordered_muns],
                "roubo_100k": [ssp_map[cd].roubo_100k for cd in ordered_muns],
                "baixa_populacao": [ssp_map[cd].baixa_populacao for cd in ordered_muns],
            }
        ),
        proc_dir / "mun_sensivel.parquet",
    )
    write_parquet_atomic(
        pa.table(
            {
                "h3": [str(h) for h in ordered_hexes],
                "participacao_pct": [hex_participacao.get(h) for h in ordered_hexes],
                "idhm": [hex_idhm.get(h) for h in ordered_hexes],
                "gini": [hex_gini.get(h) for h in ordered_hexes],
                "homicidio_100k": [hex_hom_100k.get(h) for h in ordered_hexes],
                "roubo_100k": [hex_roubo_100k.get(h) for h in ordered_hexes],
            }
        ),
        proc_dir / "hex_sensivel.parquet",
    )

    ranked_cities = sorted(ordered_muns, key=lambda c: (-pop_by_mun.get(c, 0.0), str(c)))[:80]
    city_profiles: list[dict[str, Any]] = []
    for cd in ranked_cities:
        dists = [
            {
                "div": d.cnae_div,
                "name": d.district_name,
                "ql": round(d.ql, 2),
                "vinculos": d.vinculos,
            }
            for d in city_districts.get(cd, [])
        ]
        city_profiles.append(
            {
                "cd_mun": str(cd),
                "nome": nomes_por_cd[str(cd)],
                "pop": censo[cd].pop,
                "pib_mil": round(pib[cd].pib, 1),
                "vinculos": vinculos_by_mun.get(cd, 0),
                "estabelecimentos_rais": estab_rais_by_mun.get(cd, 0),
                "districts": dists,
                "citizens": citizen_shares.get(cd, []),
                "education": {
                    "escolas": esc_map[cd].escolas,
                    "matriculas_basica": esc_map[cd].matriculas_basica,
                    "ies": sup_map[cd].ies,
                    "matriculas_superior": sup_map[cd].matriculas_superior,
                    "ideb_ai": ideb_map[cd].ideb_ai,
                    "ideb_af": ideb_map[cd].ideb_af,
                    "ideb_em": ideb_map[cd].ideb_em,
                    "ideb_medio": ideb_map[cd].ideb_medio,
                },
                "health": {
                    "estabelecimentos": cnes_mun[cd].estabelecimentos,
                    "hospitais": cnes_mun[cd].hospitais,
                    "leitos": cnes_mun[cd].leitos,
                },
                "infra": {
                    "usinas": usinas_by_mun_approx.get(cd, 0),
                    "potencia_mw": round(mw_by_mun_approx.get(cd, 0.0), 1),
                    "portos": portos_by_mun.get(cd, 0),
                },
                "sensitive": {
                    "participacao_pct": tse_map[cd].participacao_pct,
                    "idhm": idhm_map[cd].idhm,
                    "gini": idhm_map[cd].gini,
                    "homicidio_100k": ssp_map[cd].homicidio_100k,
                    "roubo_100k": ssp_map[cd].roubo_100k,
                    "baixa_populacao": ssp_map[cd].baixa_populacao,
                },
            }
        )

    explorer_rows: list[dict[str, Any]] = []
    for cd in ordered_muns:
        pop_val = max(1, censo[cd].pop)
        pib_mil_val = round(pib[cd].pib, 1)
        explorer_rows.append(
            {
                "cd_mun": str(cd),
                "nome": nomes_por_cd[str(cd)],
                "pop": censo[cd].pop,
                "pib_mil": pib_mil_val,
                "pib_pc": round(1000.0 * pib[cd].pib / pop_val, 1),
                "vinculos": vinculos_by_mun.get(cd, 0),
                "ideb_medio": ideb_map[cd].ideb_medio,
                "leitos": cnes_mun[cd].leitos,
                "idhm": idhm_map[cd].idhm,
                "gini": idhm_map[cd].gini,
                "participacao_pct": tse_map[cd].participacao_pct,
                "homicidio_100k": ssp_map[cd].homicidio_100k,
                "roubo_100k": ssp_map[cd].roubo_100k,
                "baixa_populacao": ssp_map[cd].baixa_populacao,
            }
        )

    rules = load_civ_rules(rules_path)
    hex_metrics: dict[str, dict[H3Index, float | None]] = {
        "pop": dict(hex_pop),
        "pib": dict(hex_pib),
        "vab_agro": dict(hex_vab_agro),
        "vab_ind": dict(hex_vab_ind),
        "vab_serv": dict(hex_vab_serv),
        "vab_adm": dict(hex_vab_adm),
        "max_ql": dict(hex_max_ql),
        "matriculas_superior": dict(hex_mat_sup),
        "leitos": dict(hex_leitos),
        "potencia_mw": dict(hex_mw),
        "participacao_pct": dict(hex_participacao),
        "idhm": dict(hex_idhm),
        "homicidio_100k": dict(hex_hom_100k),
    }
    web_bytes = export_uf_web_bundle(
        uf=uf,
        municipios=municipios,
        mun_hex_rows=mun_hex_rows,
        hex_metrics=hex_metrics,
        rules=rules,
        output_dir=Path("web/public/data") / uf_slug,
        pop_by_mun=pop_by_mun,
        pib_by_mun=pib_by_mun,
        points=all_points,
        rejected_points_count=len(all_rejected),
        city_profiles=city_profiles,
        explorer_rows=explorer_rows,
    )
    from pipeline.civ.almanac import write_sources_catalog
    from pipeline.sources._common import MANIFEST_PATH

    web_bytes["sources.json"] = write_sources_catalog(
        manifest_path=manifest_path if manifest_path is not None else MANIFEST_PATH,
        rules_path=rules_path,
        uf=uf,
        output_path=Path("web/public/data") / uf_slug / "sources.json",
    )

    write_stage_checkpoint(
        Path("data/checkpoints") / f"{uf_slug}.json",
        {
            "uf": uf,
            "stage_1_raw": {
                "no_download_ratio": f"{no_download_count}/{len(sources_status)}",
                "censo_sha256": censo_sync.sha256,
                "pib_sha256": pib_sync.sha256,
                "grade_sha256": grade_sync.sha256,
                "rais_sha256": rais_sync.sha256,
                "inep_escolar_sha256": esc_sync.sha256,
                "inep_superior_sha256": sup_sync.sha256,
                "cnes_estab_sha256": cnes_estab_sync.sha256,
                "cnes_leitos_sha256": cnes_leitos_sync.sha256,
                "aneel_siga_sha256": aneel_sync.sha256,
                "antaq_sha256": antaq_sync.sha256,
                "tse_2024_sha256": tse_sync.sha256,
                "ipea_idhm_sha256": idhm_sync.sha256,
                "ipea_gini_sha256": gini_sync.sha256,
                "ssp_sp_sha256": ssp_sync.sha256,
            },
            "stage_2_municipal": {
                "municipios": len(ordered_muns),
                "pop_total": int(sum(censo[cd].pop for cd in ordered_muns)),
                "pib_total_mil": round(sum(pib[cd].pib for cd in ordered_muns), 2),
                "vab_ind_total_mil": round(sum(pib[cd].vab_ind for cd in ordered_muns), 2),
                "vab_agro_total_mil": round(sum(pib[cd].vab_agro for cd in ordered_muns), 2),
                "vinculos_total": int(sum(vinculos_by_mun.values())),
                "rais_cnae_divisions": len(uf_ql),
                "escolas_total": int(sum(r.escolas for r in esc_map.values())),
                "matriculas_basica_total": int(sum(r.matriculas_basica for r in esc_map.values())),
                "matriculas_superior_total": int(
                    sum(r.matriculas_superior for r in sup_map.values())
                ),
                "cnes_estabelecimentos_total": int(
                    sum(r.estabelecimentos for r in cnes_mun.values())
                ),
                "cnes_leitos_total": int(sum(r.leitos for r in cnes_mun.values())),
            },
            "stage_3_dasymetric": {
                "grade_cells_bbox": len(grade_cells),
                "weight_rows": len(weights),
                "area_fallback_count": len(fallback_muns),
                "area_fallback_muns": [str(cd) for cd in fallback_muns],
            },
            "stage_4_hex_base": {
                "hex_count": len(ordered_hexes),
                "pop_total": round(sum(hex_pop.values()), 2),
                "pib_total_mil": round(sum(hex_pib.values()), 2),
                "vinculos_total": round(sum(hex_vinculos.values()), 2),
                "matriculas_superior_total": round(sum(hex_mat_sup.values()), 2),
                "leitos_total": round(sum(hex_leitos.values()), 2),
                "potencia_mw_total": round(sum(hex_mw.values()), 2),
                "points_accepted": {
                    "usinas": len(acc_plants),
                    "portos": len(acc_ports),
                    "hospitais": len(acc_hosps),
                },
                "points_rejected": len(all_rejected),
            },
            "stage_5_web_json": web_bytes,
            "rais_stats": rais_stats,
        },
    )

    total_leitos = sum(r.leitos for r in cnes_mun.values())
    print(
        f"Base {uf} gerada: {len(ordered_muns)} mun, {len(ordered_hexes)} hexes, "
        f"vinculos={sum(vinculos_by_mun.values()):,}, leitos={total_leitos:,}, "
        f"usinas={len(acc_plants)} ({sum(hex_mw.values()):,.1f} MW), portos={len(acc_ports)}, "
        f"rejeitados={len(all_rejected)}, web_pontos={web_bytes.get('pontos.json', 0)} B."
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Executa pipeline determinístico do civ-brasil por UF",
    )
    parser.add_argument("--uf", default="SP", help="Sigla da UF (ex.: SP)")
    args = parser.parse_args()
    run_uf_pipeline(parse_uf_code(args.uf))


if __name__ == "__main__":
    main()
