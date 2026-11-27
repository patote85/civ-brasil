from __future__ import annotations

import argparse
from pathlib import Path

import pyarrow as pa

from pipeline.checkpoints import write_stage_checkpoint
from pipeline.civ import export_uf_web_bundle, load_civ_rules
from pipeline.grid.h3_grid import (
    H3_RESOLUTION,
    build_hex_summaries,
    build_municipio_hex_table,
    write_municipio_hex_parquet,
    write_sp_hex_json,
)
from pipeline.reconcile import (
    build_dasymetric_weights,
    reconcile_sum,
    write_parquet_atomic,
)
from pipeline.sources.ibge_censo import ensure_censo_raw_file
from pipeline.sources.ibge_grade import ensure_grade_raw_file, load_grade_cells_from_file
from pipeline.sources.ibge_malhas import ensure_sp_raw_files, load_municipios_from_files
from pipeline.sources.ibge_pib import ensure_pib_raw_file
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

    sources_status = [
        ("ibge_malhas", len(malhas_sync.downloaded_files) > 0),
        ("ibge_censo", censo_sync.downloaded),
        ("ibge_pib", pib_sync.downloaded),
        ("ibge_grade", grade_sync.downloaded),
    ]
    no_download_count = sum(1 for _, downloaded in sources_status if not downloaded)
    print(f"Fontes {uf} sincronizadas (sem download: {no_download_count}/{len(sources_status)}).")

    municipios = load_municipios_from_files(malhas_sync.malha_path, malhas_sync.municipios_path)
    mun_hex_rows = build_municipio_hex_table(municipios, resolution=H3_RESOLUTION)
    nomes_por_cd = {m.cd_mun: m.nome for m in municipios}

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

    ordered_muns = [CdMun(m.cd_mun) for m in sorted(municipios, key=lambda x: x.cd_mun)]
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

    rules = load_civ_rules(rules_path)
    hex_metrics: dict[str, dict[H3Index, float]] = {
        "pop": hex_pop,
        "pib": hex_pib,
        "vab_agro": hex_vab_agro,
        "vab_ind": hex_vab_ind,
        "vab_serv": hex_vab_serv,
        "vab_adm": hex_vab_adm,
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
            },
            "stage_2_municipal": {
                "municipios": len(ordered_muns),
                "pop_total": int(sum(censo[cd].pop for cd in ordered_muns)),
                "pib_total_mil": round(sum(pib[cd].pib for cd in ordered_muns), 2),
                "vab_ind_total_mil": round(sum(pib[cd].vab_ind for cd in ordered_muns), 2),
                "vab_agro_total_mil": round(sum(pib[cd].vab_agro for cd in ordered_muns), 2),
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
                "vab_ind_total_mil": round(sum(hex_vab_ind.values()), 2),
                "vab_agro_total_mil": round(sum(hex_vab_agro.values()), 2),
            },
            "stage_5_web_json": web_bytes,
        },
    )

    print(
        f"Base {uf} gerada: {len(ordered_muns)} municipios, {len(ordered_hexes)} hexes, "
        f"pop={sum(hex_pop.values()):,.0f}, pib=R$ {sum(hex_pib.values())/1e6:,.2f} bi, "
        f"fallback_area={len(fallback_muns)}, web_grid={web_bytes['grid.json']} B."
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
