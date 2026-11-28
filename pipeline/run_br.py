from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

import pyarrow as pa

from pipeline.checkpoints import write_stage_checkpoint
from pipeline.grid.br import (
    UF_NAMES,
    UfHexRecord,
    aggregate_res5_to_res3,
    export_br_res3_web_bundle,
    export_uf_compact_grid_and_base_lenses,
)
from pipeline.grid.h3_grid import (
    H3_RESOLUTION,
    build_municipio_hex_table,
    write_municipio_hex_parquet,
)
from pipeline.reconcile import (
    build_dasymetric_weights,
    reconcile_sum,
    write_parquet_atomic,
)
from pipeline.sources.ibge_arranjos import ensure_arranjos_raw_file
from pipeline.sources.ibge_censo import ensure_censo_raw_file
from pipeline.sources.ibge_grade import ensure_grade_raw_file, load_grade_cells_from_file
from pipeline.sources.ibge_malhas import ensure_uf_raw_files, load_municipios_from_files
from pipeline.sources.ibge_pib import ensure_pib_raw_file
from pipeline.types import UF_IBGE_CODES, CdMun, H3Index, UfCode

MANIFEST_PATH = Path("data/manifest.json")


def run_br_pipeline(
    raw_root: Path | None = None,
    manifest_path: Path = MANIFEST_PATH,
    web_br_dir: Path = Path("web/public/data/br"),
    processed_dir: Path = Path("data/processed"),
) -> dict[str, Any]:
    grade_sync = ensure_grade_raw_file(raw_root=raw_root, manifest_path=manifest_path)
    arranjos_sync, arranjos = ensure_arranjos_raw_file(
        raw_root=raw_root,
        manifest_path=manifest_path,
    )

    arranjos_table = pa.table(
        {
            "cd_mun": [str(cd) for cd in sorted(arranjos)],
            "nome_arranjo": [arranjos[cd].nome_arranjo for cd in sorted(arranjos)],
            "is_nucleo": [arranjos[cd].is_nucleo for cd in sorted(arranjos)],
            "indice_integracao": [arranjos[cd].indice_integracao for cd in sorted(arranjos)],
        },
        schema=pa.schema(
            [
                ("cd_mun", pa.string()),
                ("nome_arranjo", pa.string()),
                ("is_nucleo", pa.bool_()),
                ("indice_integracao", pa.float64()),
            ]
        ),
    )
    write_parquet_atomic(arranjos_table, processed_dir / "br_arranjos.parquet")

    downloads_count = (1 if grade_sync.downloaded else 0) + (1 if arranjos_sync.downloaded else 0)
    all_uf_hex_records: list[UfHexRecord] = []
    unique_res5_cells: set[str] = set()
    uf_summaries: list[dict[str, Any]] = []
    ufs_ckpt: dict[str, dict[str, Any]] = {}

    total_muns = 0
    total_area_km2 = 0.0
    total_pop = 0.0
    total_pib_mil = 0.0

    ordered_ufs: list[UfCode] = sorted(UF_IBGE_CODES.keys())
    for uf in ordered_ufs:
        uf_slug = uf.lower()
        malhas_sync = ensure_uf_raw_files(
            uf=uf,
            raw_root=raw_root,
            manifest_path=manifest_path,
        )
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
        uf_downloads = (
            len(malhas_sync.downloaded_files)
            + (1 if censo_sync.downloaded else 0)
            + (1 if pib_sync.downloaded else 0)
        )
        downloads_count += uf_downloads

        municipios = load_municipios_from_files(
            malhas_sync.malha_path,
            malhas_sync.municipios_path,
        )
        mun_hex_rows = build_municipio_hex_table(municipios, resolution=H3_RESOLUTION)
        write_municipio_hex_parquet(
            mun_hex_rows,
            processed_dir / f"{uf_slug}_municipio_hex.parquet",
        )

        bounds = [m.geometry.bounds for m in municipios]
        uf_bbox = (
            min(b[0] for b in bounds) - 0.05,
            min(b[1] for b in bounds) - 0.05,
            max(b[2] for b in bounds) + 0.05,
            max(b[3] for b in bounds) + 0.05,
        )
        grade_cells = load_grade_cells_from_file(grade_sync.path, bbox=uf_bbox)
        dasymetric_weights = build_dasymetric_weights(municipios, mun_hex_rows, grade_cells)
        weights_table = pa.table(
            {
                "cd_mun": [str(w.cd_mun) for w in dasymetric_weights],
                "h3": [str(w.h3) for w in dasymetric_weights],
                "weight": [w.weight for w in dasymetric_weights],
                "method": [w.method for w in dasymetric_weights],
            },
            schema=pa.schema(
                [
                    ("cd_mun", pa.string()),
                    ("h3", pa.string()),
                    ("weight", pa.float64()),
                    ("method", pa.string()),
                ]
            ),
        )
        write_parquet_atomic(
            weights_table,
            processed_dir / f"{uf_slug}_dasymetric_weights.parquet",
        )

        pop_by_mun: dict[CdMun, float] = {cd: float(rec.pop) for cd, rec in censo.items()}
        pib_by_mun: dict[CdMun, float] = {cd: rec.pib for cd, rec in pib.items()}
        agro_by_mun: dict[CdMun, float] = {cd: rec.vab_agro for cd, rec in pib.items()}
        ind_by_mun: dict[CdMun, float] = {cd: rec.vab_ind for cd, rec in pib.items()}
        serv_by_mun: dict[CdMun, float] = {cd: rec.vab_serv for cd, rec in pib.items()}
        adm_by_mun: dict[CdMun, float] = {cd: rec.vab_adm for cd, rec in pib.items()}

        hex_pop = reconcile_sum(pop_by_mun, dasymetric_weights)
        hex_pib = reconcile_sum(pib_by_mun, dasymetric_weights)
        hex_agro = reconcile_sum(agro_by_mun, dasymetric_weights)
        hex_ind = reconcile_sum(ind_by_mun, dasymetric_weights)
        hex_serv = reconcile_sum(serv_by_mun, dasymetric_weights)
        hex_adm = reconcile_sum(adm_by_mun, dasymetric_weights)

        pop_mun_sum = sum(pop_by_mun.values())
        pop_hex_sum = sum(hex_pop.values())
        if pop_mun_sum > 0 and abs(pop_hex_sum - pop_mun_sum) / pop_mun_sum > 0.001:
            raise ValueError(
                f"Falha de conservação de população em {uf}: mun={pop_mun_sum}, hex={pop_hex_sum}"
            )

        area_by_hex: dict[str, float] = defaultdict(float)
        muns_by_hex: dict[str, set[str]] = defaultdict(set)
        for row in mun_hex_rows:
            area_by_hex[row.h3] += row.area_km2
            muns_by_hex[row.h3].add(row.cd_mun)

        pop_by_hex_str = {str(k): v for k, v in hex_pop.items()}
        pib_by_hex_str = {str(k): v for k, v in hex_pib.items()}

        export_uf_compact_grid_and_base_lenses(
            uf=uf,
            municipios=municipios,
            mun_hex_rows=mun_hex_rows,
            pop_by_hex=pop_by_hex_str,
            pib_by_hex=pib_by_hex_str,
            pop_by_mun=pop_by_mun,
            pib_by_mun=pib_by_mun,
            out_dir=web_br_dir,
            vab_totals={
                "vab_agro_mil": sum(hex_agro.values()),
                "vab_ind_mil": sum(hex_ind.values()),
                "vab_serv_mil": sum(hex_serv.values()),
                "vab_adm_mil": sum(hex_adm.values()),
            },
        )

        ordered_hexes = sorted(area_by_hex.keys())
        for cell in ordered_hexes:
            unique_res5_cells.add(cell)
            h_idx = H3Index(cell)
            all_uf_hex_records.append(
                UfHexRecord(
                    uf=uf,
                    h3=cell,
                    area_km2=area_by_hex[cell],
                    pop=pop_by_hex_str.get(cell, 0.0),
                    pib_mil=pib_by_hex_str.get(cell, 0.0),
                    pib_agro_mil=hex_agro.get(h_idx, 0.0),
                    pib_ind_mil=hex_ind.get(h_idx, 0.0),
                    pib_serv_mil=hex_serv.get(h_idx, 0.0),
                    pib_adm_mil=hex_adm.get(h_idx, 0.0),
                    mun_count=len(muns_by_hex[cell]),
                )
            )

        uf_area = sum(area_by_hex.values())
        uf_pib = sum(pib_by_hex_str.values())
        total_muns += len(municipios)
        total_area_km2 += uf_area
        total_pop += pop_hex_sum
        total_pib_mil += uf_pib

        summary = {
            "uf": uf,
            "nome": UF_NAMES[uf],
            "mun_count": len(municipios),
            "hex_count": len(ordered_hexes),
            "pop": int(round(pop_hex_sum)),
            "pib_mil": round(uf_pib, 1),
            "area_km2": round(uf_area, 2),
        }
        uf_summaries.append(summary)
        ufs_ckpt[uf] = summary
        print(
            f"[{uf}] {len(municipios):>3} mun | {len(ordered_hexes):>4} hexes | "
            f"pop={int(round(pop_hex_sum)):>10,} | area={uf_area:>10,.1f} km² | dl={uf_downloads}"
        )

    res3_hexes = aggregate_res5_to_res3(all_uf_hex_records)
    export_br_res3_web_bundle(res3_hexes, uf_summaries, web_br_dir / "br_res3.json")

    checkpoint: dict[str, Any] = {
        "uf": "BR",
        "mun_count": total_muns,
        "unique_h3_res5_count": len(unique_res5_cells),
        "res3_hex_count": len(res3_hexes),
        "area_km2": round(total_area_km2, 3),
        "pop_total": int(round(total_pop)),
        "pib_total_mil": round(total_pib_mil, 1),
        "arranjos_mun_count": len(arranjos),
        "downloads_count": downloads_count,
        "ufs": ufs_ckpt,
    }
    write_stage_checkpoint(Path("data/checkpoints/br.json"), checkpoint)
    print(
        f"Base BR concluída: {total_muns} mun, {len(unique_res5_cells)} hexes res5, "
        f"{len(res3_hexes)} hexes res3, pop={int(round(total_pop)):,}, "
        f"area={total_area_km2:,.2f} km², downloads={downloads_count}."
    )
    return checkpoint
