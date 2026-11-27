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
MAX_SP_HEXES = 1150
EXPECTED_SP_MUNICIPIOS = 645
EXPECTED_SP_POP_2022 = 44_411_238
MAX_SP_GRID_JSON_BYTES = 220_000
MAX_SP_LENS_JSON_BYTES = 50_000
MAX_SP_POINTS_JSON_BYTES = 200_000
MAX_SP_CITIES_JSON_BYTES = 200_000
MAX_JS_BUNDLE_BYTES = 150_000
MIN_PR3_LENSES = 8


def verify_artifacts(
    dist_dir: Path = Path("web/dist"),
    public_json: Path = Path("web/public/data/sp_hex.json"),
    parquet_path: Path = Path("data/processed/sp_municipio_hex.parquet"),
    sp_processed_dir: Path = Path("data/processed/sp"),
    sp_public_dir: Path = Path("web/public/data/sp"),
) -> list[str]:
    errors: list[str] = []

    if not dist_dir.is_dir():
        errors.append(f"Diretório de build ausente: {dist_dir}")
        return errors

    index_html = dist_dir / "index.html"
    if not index_html.is_file() or index_html.stat().st_size == 0:
        errors.append(f"Arquivo index.html ausente ou vazio em {index_html}")

    assets_dir = dist_dir / "assets"
    js_files = sorted(assets_dir.glob("*.js")) if assets_dir.is_dir() else []
    if not js_files:
        errors.append(f"Bundles JS ausentes em {assets_dir}")
    else:
        total_js_bytes = sum(f.stat().st_size for f in js_files)
        if total_js_bytes > MAX_JS_BUNDLE_BYTES:
            errors.append(
                f"Bundle JS total ({total_js_bytes} B) excede orçamento ({MAX_JS_BUNDLE_BYTES} B)"
            )
        for js_file in js_files:
            content = js_file.read_text(encoding="utf-8", errors="ignore")
            if "unpkg.com" in content:
                errors.append(f"Referência externa 'unpkg.com' encontrada em {js_file.name}")

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
            if {str(cell) for cell in h3_col} != seen_hexes:
                errors.append("Conjunto de hexes do Parquet diverge de sp_hex.json")

    _verify_pr2_reconciliation_and_web(
        errors=errors,
        dist_dir=dist_dir,
        sp_processed_dir=sp_processed_dir,
        sp_public_dir=sp_public_dir,
        expected_hex_count=hex_count,
    )
    _verify_pr3_economy_services_and_points(
        errors=errors,
        dist_dir=dist_dir,
        sp_processed_dir=sp_processed_dir,
        sp_public_dir=sp_public_dir,
        expected_hex_count=hex_count,
        seen_hexes=seen_hexes,
    )

    return errors


def _verify_pr2_reconciliation_and_web(
    errors: list[str],
    dist_dir: Path,
    sp_processed_dir: Path,
    sp_public_dir: Path,
    expected_hex_count: int,
) -> None:
    weights_path = sp_processed_dir / "dasymetric_weights.parquet"
    mun_base_path = sp_processed_dir / "mun_base.parquet"
    hex_base_path = sp_processed_dir / "hex_base.parquet"

    missing_parquets = [p for p in (weights_path, mun_base_path, hex_base_path) if not p.is_file()]
    for path in missing_parquets:
        errors.append(f"Parquet PR 2 ausente: {path}")

    mun_totals: dict[str, float] = {}
    if not missing_parquets:
        w_table = pq.read_table(weights_path)
        w_by_mun: dict[str, float] = defaultdict(float)
        for cd, w in zip(
            w_table.column("cd_mun").to_pylist(),
            w_table.column("weight").to_pylist(),
            strict=True,
        ):
            wf = float(w)
            if wf < 0.0:
                errors.append(f"Peso dasimétrico negativo para {cd}: {wf}")
            w_by_mun[str(cd)] += wf
        if len(w_by_mun) != EXPECTED_SP_MUNICIPIOS:
            errors.append(f"dasymetric_weights tem {len(w_by_mun)} municípios")
        for cd, total_w in w_by_mun.items():
            if not math.isclose(total_w, 1.0, abs_tol=1e-9):
                errors.append(f"Soma de w inválida para {cd}: {total_w}")

        mun_table = pq.read_table(mun_base_path)
        hex_table = pq.read_table(hex_base_path)
        if mun_table.num_rows != EXPECTED_SP_MUNICIPIOS:
            errors.append(f"mun_base.parquet tem {mun_table.num_rows} linhas")
        if hex_table.num_rows != expected_hex_count:
            errors.append(f"hex_base.parquet tem {hex_table.num_rows} linhas")

        for col in ("pop", "pib", "vab_agro", "vab_ind", "vab_serv", "vab_adm"):
            m_vals = [float(v) for v in mun_table.column(col).to_pylist()]
            h_vals = [float(v) for v in hex_table.column(col).to_pylist()]
            if any(v < 0.0 for v in m_vals) or any(v < 0.0 for v in h_vals):
                errors.append(f"Valor negativo encontrado na coluna {col}")
            m_sum = sum(m_vals)
            h_sum = sum(h_vals)
            mun_totals[col] = m_sum
            if not math.isclose(h_sum, m_sum, rel_tol=1e-6):
                errors.append(f"Conservação quebrada em {col}: hex={h_sum} vs mun={m_sum}")

        pop_rel = abs(mun_totals["pop"] - EXPECTED_SP_POP_2022) / EXPECTED_SP_POP_2022
        if pop_rel > 0.001:
            errors.append(
                f"População SP ({mun_totals['pop']:.0f}) fora de ±0,1% de {EXPECTED_SP_POP_2022}"
            )

    grid_public = sp_public_dir / "grid.json"
    grid_dist = dist_dir / "data" / "sp" / "grid.json"
    index_public = sp_public_dir / "lentes" / "index.json"
    index_dist = dist_dir / "data" / "sp" / "lentes" / "index.json"
    for candidate in (grid_public, grid_dist, index_public, index_dist):
        if not candidate.is_file():
            errors.append(f"Artefato web PR 2 ausente: {candidate}")

    if grid_public.is_file():
        if grid_dist.is_file() and grid_public.read_bytes() != grid_dist.read_bytes():
            errors.append("web/dist/data/sp/grid.json diverge de web/public/data/sp/grid.json")
        if grid_public.stat().st_size > MAX_SP_GRID_JSON_BYTES:
            errors.append(
                f"grid.json ({grid_public.stat().st_size} B) excede {MAX_SP_GRID_JSON_BYTES} B"
            )

    if not index_public.is_file():
        return

    if index_dist.is_file() and index_public.read_bytes() != index_dist.read_bytes():
        errors.append(
            "web/dist/data/sp/lentes/index.json diverge de web/public/data/sp/lentes/index.json"
        )

    index_data = json.loads(index_public.read_text(encoding="utf-8"))
    lenses = index_data.get("lenses", [])
    if len(lenses) < MIN_PR3_LENSES:
        errors.append(f"Menos de {MIN_PR3_LENSES} lentes no index.json: {len(lenses)}")

    col_map = {"ouro": "pib", "producao": "vab_ind", "comida": "vab_agro", "cidadaos": "pop"}
    for entry in lenses:
        lid = str(entry.get("id", ""))
        if not entry.get("source_id") or not entry.get("ano_ref") or not entry.get("unit"):
            errors.append(f"Lente {lid} sem source_id, ano_ref ou unit")
        lp = sp_public_dir / "lentes" / f"{lid}.json"
        ld = dist_dir / "data" / "sp" / "lentes" / f"{lid}.json"
        if not lp.is_file() or not ld.is_file():
            errors.append(f"Arquivo de lente ausente: {lid}")
            continue
        if lp.read_bytes() != ld.read_bytes():
            errors.append(f"Lente {lid} em dist diverge de public")
        if lp.stat().st_size > MAX_SP_LENS_JSON_BYTES:
            errors.append(f"Lente {lid} ({lp.stat().st_size} B) excede {MAX_SP_LENS_JSON_BYTES} B")
        raw_text = lp.read_text(encoding="utf-8")
        if "85a8" in raw_text:
            errors.append(f"Lente {lid} repete strings H3 em vez de formato posicional")
        ldata = json.loads(raw_text)
        vals = ldata.get("values", [])
        if len(vals) != expected_hex_count:
            errors.append(f"Lente {lid} tem {len(vals)} valores (esperado {expected_hex_count})")
        mapped_col = col_map.get(lid)
        if mapped_col and mapped_col in mun_totals:
            lens_sum = sum(float(v) for v in vals if v is not None)
            if not math.isclose(lens_sum, mun_totals[mapped_col], rel_tol=1e-3):
                errors.append(
                    f"Soma da lente {lid} ({lens_sum}) diverge de "
                    f"{mapped_col} ({mun_totals[mapped_col]})"
                )


def _verify_pr3_economy_services_and_points(
    errors: list[str],
    dist_dir: Path,
    sp_processed_dir: Path,
    sp_public_dir: Path,
    expected_hex_count: int,
    seen_hexes: set[str],
) -> None:
    trabalho_path = sp_processed_dir / "mun_trabalho.parquet"
    distritos_path = sp_processed_dir / "mun_distritos.parquet"
    servicos_path = sp_processed_dir / "mun_servicos.parquet"
    hex_econ_path = sp_processed_dir / "hex_economia.parquet"
    pontos_pq_path = sp_processed_dir / "pontos_infra.parquet"

    pr3_parquets = (trabalho_path, distritos_path, servicos_path, hex_econ_path, pontos_pq_path)
    missing = [p for p in pr3_parquets if not p.is_file()]
    for path in missing:
        errors.append(f"Parquet PR 3 ausente: {path}")

    if not missing:
        trab_tbl = pq.read_table(trabalho_path)
        dist_tbl = pq.read_table(distritos_path)
        serv_tbl = pq.read_table(servicos_path)
        hecon_tbl = pq.read_table(hex_econ_path)
        pts_tbl = pq.read_table(pontos_pq_path)

        if serv_tbl.num_rows != EXPECTED_SP_MUNICIPIOS:
            errors.append(f"mun_servicos.parquet tem {serv_tbl.num_rows} linhas")
        if hecon_tbl.num_rows != expected_hex_count:
            errors.append(f"hex_economia.parquet tem {hecon_tbl.num_rows} linhas")
        if dist_tbl.num_rows == 0:
            errors.append("mun_distritos.parquet vazio")

        trab_vinc_sum = sum(float(v) for v in trab_tbl.column("vinculos").to_pylist())
        hex_vinc_sum = sum(float(v) for v in hecon_tbl.column("vinculos").to_pylist())
        if trab_vinc_sum <= 0 or not math.isclose(hex_vinc_sum, trab_vinc_sum, rel_tol=1e-6):
            errors.append(
                f"Conservação quebrada em vinculos: hex={hex_vinc_sum} vs mun={trab_vinc_sum}"
            )

        for mun_col, hex_col in (
            ("matriculas_basica", "matriculas_basica"),
            ("matriculas_superior", "matriculas_superior"),
            ("cnes_estabelecimentos", "cnes_estabelecimentos"),
            ("cnes_leitos", "leitos"),
        ):
            m_sum = sum(float(v) for v in serv_tbl.column(mun_col).to_pylist())
            h_sum = sum(float(v) for v in hecon_tbl.column(hex_col).to_pylist())
            if m_sum <= 0 or not math.isclose(h_sum, m_sum, rel_tol=1e-6):
                errors.append(f"Conservação quebrada em {hex_col}: hex={h_sum} vs mun={m_sum}")

        pts_h3 = pts_tbl.column("h3").to_pylist()
        pts_kind = pts_tbl.column("kind").to_pylist()
        pts_val = pts_tbl.column("value").to_pylist()
        outside = [str(c) for c in pts_h3 if str(c) not in seen_hexes]
        if outside:
            errors.append(f"pontos_infra.parquet tem {len(outside)} pontos fora do grid H3 de SP")

        usinas_mw = sum(
            float(v) for k, v in zip(pts_kind, pts_val, strict=True) if str(k) == "usina"
        )
        hex_mw = sum(float(v) for v in hecon_tbl.column("potencia_mw").to_pylist())
        if usinas_mw <= 0 or not math.isclose(hex_mw, usinas_mw, rel_tol=1e-6):
            errors.append(f"Conservação quebrada em potencia_mw: hex={hex_mw} vs pts={usinas_mw}")

    pontos_public = sp_public_dir / "pontos.json"
    pontos_dist = dist_dir / "data" / "sp" / "pontos.json"
    cities_public = sp_public_dir / "cities.json"
    cities_dist = dist_dir / "data" / "sp" / "cities.json"
    for candidate in (pontos_public, pontos_dist, cities_public, cities_dist):
        if not candidate.is_file():
            errors.append(f"Artefato web PR 3 ausente: {candidate}")

    if pontos_public.is_file():
        if pontos_dist.is_file() and pontos_public.read_bytes() != pontos_dist.read_bytes():
            errors.append("web/dist/data/sp/pontos.json diverge de web/public/data/sp/pontos.json")
        if pontos_public.stat().st_size > MAX_SP_POINTS_JSON_BYTES:
            errors.append(
                f"pontos.json ({pontos_public.stat().st_size} B) excede "
                f"{MAX_SP_POINTS_JSON_BYTES} B"
            )

    if cities_public.is_file():
        if cities_dist.is_file() and cities_public.read_bytes() != cities_dist.read_bytes():
            errors.append("web/dist/data/sp/cities.json diverge de web/public/data/sp/cities.json")
        if cities_public.stat().st_size > MAX_SP_CITIES_JSON_BYTES:
            errors.append(
                f"cities.json ({cities_public.stat().st_size} B) excede "
                f"{MAX_SP_CITIES_JSON_BYTES} B"
            )
        cities_payload = json.loads(cities_public.read_text(encoding="utf-8"))
        cities_list = cities_payload.get("cities", [])
        if len(cities_list) < 20:
            errors.append(f"cities.json tem poucas cidades: {len(cities_list)}")


def main() -> int:
    errors = verify_artifacts()
    if errors:
        for err in errors:
            print(f"ERRO: {err}", file=sys.stderr)
        return 1
    payload = json.loads(Path("web/public/data/sp/grid.json").read_text(encoding="utf-8"))
    idx_payload = json.loads(
        Path("web/public/data/sp/lentes/index.json").read_text(encoding="utf-8")
    )
    js_total = sum(f.stat().st_size for f in Path("web/dist/assets").glob("*.js"))
    print(
        "Verificacao OK: "
        f"web/dist presente ({js_total} B JS, 0 unpkg), "
        f"{payload['hex_count']} hexes H3 res {payload['resolution']}, "
        f"{len(idx_payload['lenses'])} lentes, "
        f"pop={payload['yields']['pop']:,}, area={payload['total_area_km2']:.2f} km2."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
