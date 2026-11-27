from __future__ import annotations

from pathlib import Path

from pipeline.grid.h3_grid import (
    H3_RESOLUTION,
    build_hex_summaries,
    build_municipio_hex_table,
    write_municipio_hex_parquet,
    write_sp_hex_json,
)
from pipeline.sources.ibge_malhas import (
    ensure_sp_raw_files,
    load_municipios_from_files,
)

MANIFEST_PATH = Path("data/manifest.json")
PARQUET_OUTPUT = Path("data/processed/sp_municipio_hex.parquet")
WEB_HEX_JSON_OUTPUT = Path("web/public/data/sp_hex.json")


def run_sp_pipeline(
    raw_root: Path | None = None,
    manifest_path: Path = MANIFEST_PATH,
    parquet_output: Path = PARQUET_OUTPUT,
    web_json_output: Path = WEB_HEX_JSON_OUTPUT,
) -> None:
    sync = ensure_sp_raw_files(raw_root=raw_root, manifest_path=manifest_path)
    if sync.downloaded_files:
        downloaded_list = ", ".join(sync.downloaded_files)
        print(f"IBGE malhas SP: download realizado ({downloaded_list}).")
    else:
        print("IBGE malhas SP: arquivos locais validos (sem download).")

    municipios = load_municipios_from_files(sync.malha_path, sync.municipios_path)
    rows = build_municipio_hex_table(municipios, resolution=H3_RESOLUTION)
    nomes_por_cd = {m.cd_mun: m.nome for m in municipios}
    summaries = build_hex_summaries(rows, nomes_por_cd)

    write_municipio_hex_parquet(rows, parquet_output)
    write_sp_hex_json(summaries, web_json_output)

    total_area_km2 = sum(row.area_km2 for row in rows)
    print(
        f"Grade SP H3 res {H3_RESOLUTION} gerada: "
        f"{len(municipios)} municipios, {len(rows)} linhas, "
        f"{len(summaries)} hexes, area={total_area_km2:.2f} km2."
    )


def main() -> None:
    run_sp_pipeline()


if __name__ == "__main__":
    main()
