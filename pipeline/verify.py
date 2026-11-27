from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import h3
import pyarrow.parquet as pq

from pipeline.grid.h3_grid import H3_RESOLUTION, SP_OFFICIAL_AREA_KM2

MIN_SP_HEXES = 900
MAX_SP_HEXES = 1100
EXPECTED_SP_MUNICIPIOS = 645


def verify_artifacts(
    dist_dir: Path = Path("web/dist"),
    public_json: Path = Path("web/public/data/sp_hex.json"),
    parquet_path: Path = Path("data/processed/sp_municipio_hex.parquet"),
) -> list[str]:
    errors: list[str] = []

    if not dist_dir.is_dir():
        errors.append(f"Diretório de build ausente: {dist_dir}")
        return errors

    index_html = dist_dir / "index.html"
    if not index_html.is_file() or index_html.stat().st_size == 0:
        errors.append(f"Arquivo index.html ausente ou vazio em {index_html}")

    assets_dir = dist_dir / "assets"
    if not assets_dir.is_dir() or not any(assets_dir.glob("*.js")):
        errors.append(f"Bundles JS ausentes em {assets_dir}")

    dist_json = dist_dir / "data" / "sp_hex.json"
    for candidate in (public_json, dist_json):
        if not candidate.is_file():
            errors.append(f"JSON ausente: {candidate}")

    if errors:
        return errors

    public_bytes = public_json.read_bytes()
    dist_bytes = dist_json.read_bytes()
    if public_bytes != dist_bytes:
        errors.append("web/dist/data/sp_hex.json diverge de web/public/data/sp_hex.json")

    try:
        payload = json.loads(public_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        errors.append(f"sp_hex.json inválido: {exc}")
        return errors

    if not isinstance(payload, dict):
        errors.append("sp_hex.json deve ser um objeto JSON")
        return errors

    if payload.get("state") != "SP":
        errors.append(f"Campo state inválido: {payload.get('state')!r}")
    if payload.get("resolution") != H3_RESOLUTION:
        errors.append(f"Campo resolution inválido: {payload.get('resolution')!r}")

    hexes = payload.get("hexes")
    if not isinstance(hexes, list):
        errors.append("Campo hexes ausente ou não é lista")
        return errors

    hex_count = len(hexes)
    if payload.get("hex_count") != hex_count:
        errors.append(f"hex_count ({payload.get('hex_count')}) != len(hexes) ({hex_count})")
    if not (MIN_SP_HEXES <= hex_count <= MAX_SP_HEXES):
        errors.append(
            f"Contagem de hexes fora do invariante [{MIN_SP_HEXES}, {MAX_SP_HEXES}]: {hex_count}"
        )

    seen_hexes: set[str] = set()
    all_cd_muns: set[str] = set()
    sum_area_km2 = 0.0

    for idx, entry in enumerate(hexes):
        if not isinstance(entry, dict):
            errors.append(f"Entrada hexes[{idx}] inválida")
            continue
        cell = entry.get("h3")
        municipios = entry.get("municipios")
        cd_muns = entry.get("cd_muns")
        mun_count = entry.get("municipio_count")
        area_km2 = entry.get("area_km2")

        if not isinstance(cell, str) or not h3.is_valid_cell(cell):
            errors.append(f"Índice H3 inválido em hexes[{idx}]: {cell!r}")
            continue
        if h3.get_resolution(cell) != H3_RESOLUTION:
            errors.append(f"Resolução H3 incorreta para {cell}")
        if cell in seen_hexes:
            errors.append(f"Hexágono duplicado em sp_hex.json: {cell}")
        seen_hexes.add(cell)

        if (
            not isinstance(municipios, list)
            or not isinstance(cd_muns, list)
            or not isinstance(mun_count, int)
            or mun_count < 1
            or mun_count != len(municipios)
            or mun_count != len(cd_muns)
        ):
            errors.append(f"Metadados de municípios inconsistentes no hex {cell}")
            continue

        for cd in cd_muns:
            if not isinstance(cd, str) or len(cd) != 7 or not cd.isdigit():
                errors.append(f"Código municipal inválido no hex {cell}: {cd!r}")
            else:
                all_cd_muns.add(cd)

        if not isinstance(area_km2, (int, float)) or area_km2 <= 0.0:
            errors.append(f"Área inválida no hex {cell}: {area_km2!r}")
        else:
            sum_area_km2 += float(area_km2)

    if len(all_cd_muns) != EXPECTED_SP_MUNICIPIOS:
        errors.append(
            f"Municípios distintos em sp_hex.json: {len(all_cd_muns)} "
            f"(esperado {EXPECTED_SP_MUNICIPIOS})"
        )

    rel_diff = abs(sum_area_km2 - SP_OFFICIAL_AREA_KM2) / SP_OFFICIAL_AREA_KM2
    if rel_diff > 0.005:
        errors.append(
            f"Área total {sum_area_km2:.2f} km² fora de ±0,5% de {SP_OFFICIAL_AREA_KM2:.0f} km²"
        )

    if parquet_path.is_file():
        table = pq.read_table(parquet_path)
        expected_cols = ["cd_mun", "h3", "area_km2", "frac"]
        if table.column_names != expected_cols:
            errors.append(f"Colunas Parquet inválidas: {table.column_names}")
        else:
            cd_col = table.column("cd_mun").to_pylist()
            h3_col = table.column("h3").to_pylist()
            frac_col = table.column("frac").to_pylist()
            frac_by_mun: dict[str, float] = defaultdict(float)
            for cd, frac in zip(cd_col, frac_col, strict=True):
                frac_by_mun[str(cd)] += float(frac)
            if len(frac_by_mun) != EXPECTED_SP_MUNICIPIOS:
                errors.append(
                    f"Parquet tem {len(frac_by_mun)} municípios (esperado {EXPECTED_SP_MUNICIPIOS})"
                )
            for cd, total_frac in frac_by_mun.items():
                if not math.isclose(total_frac, 1.0, abs_tol=1e-6):
                    errors.append(f"Parquet soma de frac inválida para {cd}: {total_frac}")
            if set(str(cell) for cell in h3_col) != seen_hexes:
                errors.append("Conjunto de hexes do Parquet diverge de sp_hex.json")

    return errors


def main() -> int:
    errors = verify_artifacts()
    if errors:
        for err in errors:
            print(f"ERRO: {err}", file=sys.stderr)
        return 1
    payload = json.loads(Path("web/public/data/sp_hex.json").read_text(encoding="utf-8"))
    print(
        "Verificacao OK: "
        f"web/dist presente, {payload['hex_count']} hexes H3 res {payload['resolution']}, "
        f"area={payload['total_area_km2']:.2f} km2."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
