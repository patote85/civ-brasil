from __future__ import annotations

import math
from collections import defaultdict
from pathlib import Path

import pytest

from pipeline.grid.h3_grid import (
    H3_RESOLUTION,
    SP_OFFICIAL_AREA_KM2,
    build_hex_summaries,
    build_municipio_hex_table,
    compute_equal_area_km2,
)
from pipeline.sources.ibge_malhas import (
    MALHA_FILENAME,
    MUNICIPIOS_FILENAME,
    get_raw_root,
    load_municipios_from_files,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_MALHA = FIXTURES_DIR / "sp_sample_malha.geojson"
SAMPLE_MUNICIPIOS = FIXTURES_DIR / "sp_sample_municipios.json"


def _raw_ibge_dir() -> Path:
    return get_raw_root() / "ibge_malhas"


def _has_sp_raw_files() -> bool:
    ibge_dir = _raw_ibge_dir()
    return (ibge_dir / MALHA_FILENAME).is_file() and (ibge_dir / MUNICIPIOS_FILENAME).is_file()


def test_fixture_invariants_coverage_fractions_area_and_determinism() -> None:
    municipios = load_municipios_from_files(SAMPLE_MALHA, SAMPLE_MUNICIPIOS)
    assert len(municipios) == 4

    rows_first = build_municipio_hex_table(municipios, resolution=H3_RESOLUTION)
    rows_second = build_municipio_hex_table(municipios, resolution=H3_RESOLUTION)

    assert rows_first == rows_second

    by_mun: dict[str, list[tuple[str, float, float]]] = defaultdict(list)
    for row in rows_first:
        assert row.area_km2 > 0.0
        assert 0.0 < row.frac <= 1.0 + 1e-9
        by_mun[row.cd_mun].append((row.h3, row.area_km2, row.frac))

    expected_codes = {m.cd_mun for m in municipios}
    assert set(by_mun.keys()) == expected_codes

    for cd_mun, items in by_mun.items():
        assert len(items) >= 1, f"{cd_mun} sem hexes"
        frac_sum = sum(frac for _, _, frac in items)
        assert math.isclose(frac_sum, 1.0, abs_tol=1e-6), f"{cd_mun}: soma frac={frac_sum}"

    total_projected = compute_equal_area_km2(municipios)
    total_table_area = sum(row.area_km2 for row in rows_first)
    assert math.isclose(total_table_area, total_projected, rel_tol=1e-6)

    nomes = {m.cd_mun: m.nome for m in municipios}
    summaries = build_hex_summaries(rows_first, nomes)
    assert len(summaries) == len({row.h3 for row in rows_first})
    assert all(s.municipio_count == len(s.municipios) >= 1 for s in summaries)


@pytest.mark.skipif(
    not _has_sp_raw_files(),
    reason="Brutos locais do IBGE indisponíveis em CIVBR_RAW",
)
def test_sp_full_invariants() -> None:
    ibge_dir = _raw_ibge_dir()
    municipios = load_municipios_from_files(
        ibge_dir / MALHA_FILENAME,
        ibge_dir / MUNICIPIOS_FILENAME,
    )

    assert len(municipios) == 645

    rows_first = build_municipio_hex_table(municipios, resolution=H3_RESOLUTION)
    rows_second = build_municipio_hex_table(municipios, resolution=H3_RESOLUTION)

    assert rows_first == rows_second

    by_mun_frac: dict[str, float] = defaultdict(float)
    by_mun_count: dict[str, int] = defaultdict(int)
    hexes: set[str] = set()
    total_table_area = 0.0

    for row in rows_first:
        by_mun_frac[row.cd_mun] += row.frac
        by_mun_count[row.cd_mun] += 1
        hexes.add(row.h3)
        total_table_area += row.area_km2

    expected_codes = {m.cd_mun for m in municipios}
    assert set(by_mun_count.keys()) == expected_codes
    assert len(by_mun_count) == 645

    for cd_mun in expected_codes:
        assert by_mun_count[cd_mun] >= 1
        assert math.isclose(by_mun_frac[cd_mun], 1.0, abs_tol=1e-6)

    projected_state_area = compute_equal_area_km2(municipios)
    assert math.isclose(total_table_area, projected_state_area, rel_tol=1e-6)
    rel_diff_official = abs(projected_state_area - SP_OFFICIAL_AREA_KM2) / SP_OFFICIAL_AREA_KM2
    assert rel_diff_official <= 0.005, (
        f"Área projetada {projected_state_area:.2f} km² fora de ±0,5% de {SP_OFFICIAL_AREA_KM2}"
    )

    assert 900 <= len(hexes) <= 1100, f"Contagem de hexes fora de [900, 1100]: {len(hexes)}"
