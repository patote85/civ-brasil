from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

import pytest

from pipeline.civ.export import export_uf_web_bundle
from pipeline.civ.rules import CivRulesError, load_civ_rules
from pipeline.grid.h3_grid import H3_RESOLUTION, build_municipio_hex_table
from pipeline.reconcile import (
    build_dasymetric_weights,
    reconcile_rate,
    reconcile_sum,
)
from pipeline.sources.ibge_censo import load_censo_from_file
from pipeline.sources.ibge_grade import load_grade_cells_from_file
from pipeline.sources.ibge_malhas import load_municipios_from_files
from pipeline.sources.ibge_pib import load_pib_from_file
from pipeline.types import CdMun, H3Index, parse_cd_mun, parse_sidra_number

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_MALHA = FIXTURES_DIR / "sp_sample_malha.geojson"
SAMPLE_MUNICIPIOS = FIXTURES_DIR / "sp_sample_municipios.json"
SAMPLE_CENSO = FIXTURES_DIR / "sp_sample_censo.json"
SAMPLE_PIB = FIXTURES_DIR / "sp_sample_pib.json"
SAMPLE_GRADE = FIXTURES_DIR / "sp_sample_grade.geojson"


def test_boundary_types_reject_invalid_ibge_and_parse_sidra_sentinels() -> None:
    assert parse_cd_mun("3550308") == CdMun("3550308")
    with pytest.raises(ValueError):
        parse_cd_mun("35503")
    with pytest.raises(ValueError):
        parse_cd_mun("ABCDEFG")

    for sentinel in ("-", "...", "X", "..", "", "  ", None):
        assert parse_sidra_number(sentinel) is None
    assert parse_sidra_number("44411238") == 44411238.0
    assert parse_sidra_number("123.45") == 123.45


def test_censo_and_pib_parsers_validate_schema_and_reject_missing_values(tmp_path: Path) -> None:
    censo = load_censo_from_file(SAMPLE_CENSO)
    assert len(censo) == 4
    assert censo[CdMun("3500105")].pop == 34687
    assert censo[CdMun("3500105")].ano_ref == 2022

    pib = load_pib_from_file(SAMPLE_PIB)
    assert len(pib) == 4
    assert pib[CdMun("3500105")].pib == 1350000.0
    assert pib[CdMun("3500105")].vab_agro == 120000.0
    assert pib[CdMun("3500105")].vab_ind == 210000.0
    assert pib[CdMun("3500105")].vab_serv == 720000.0
    assert pib[CdMun("3500105")].vab_adm == 180000.0
    assert pib[CdMun("3500105")].ano_ref == 2021

    bad_censo = tmp_path / "bad_censo.json"
    bad_censo.write_text(
        json.dumps(
            [
                {"D1C": "Município", "D2C": "Var", "D3C": "Ano", "V": "Valor"},
                {"D1C": "3500105", "D2C": "93", "D3C": "2022", "V": "..."},
            ]
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="ausente"):
        load_censo_from_file(bad_censo)


def test_dasymetric_weights_and_reconcile_invariants_with_area_fallback() -> None:
    municipios = load_municipios_from_files(SAMPLE_MALHA, SAMPLE_MUNICIPIOS)
    mun_hex_rows = build_municipio_hex_table(municipios, resolution=H3_RESOLUTION)
    grade_cells = load_grade_cells_from_file(SAMPLE_GRADE)
    censo = load_censo_from_file(SAMPLE_CENSO)
    pib = load_pib_from_file(SAMPLE_PIB)

    weights_first = build_dasymetric_weights(municipios, mun_hex_rows, grade_cells)
    weights_second = build_dasymetric_weights(municipios, mun_hex_rows, grade_cells)
    assert weights_first == weights_second

    by_mun_weight: dict[CdMun, float] = defaultdict(float)
    methods_by_mun: dict[CdMun, set[str]] = defaultdict(set)
    for row in weights_first:
        assert row.weight >= 0.0
        by_mun_weight[row.cd_mun] += row.weight
        methods_by_mun[row.cd_mun].add(row.method)

    assert len(by_mun_weight) == 4
    for cd_mun, total_w in by_mun_weight.items():
        assert math.isclose(total_w, 1.0, abs_tol=1e-9), f"{cd_mun}: sum(w)={total_w}"

    assert methods_by_mun[CdMun("3500105")] == {"grade_1km"}
    assert methods_by_mun[CdMun("3500402")] == {"area_fallback"}

    pop_by_mun = {cd: float(rec.pop) for cd, rec in censo.items()}
    pib_by_mun = {cd: rec.pib for cd, rec in pib.items()}

    pop_hex = reconcile_sum(pop_by_mun, weights_first)
    pib_hex = reconcile_sum(pib_by_mun, weights_first)

    assert math.isclose(sum(pop_hex.values()), sum(pop_by_mun.values()), rel_tol=1e-6)
    assert math.isclose(sum(pib_hex.values()), sum(pib_by_mun.values()), rel_tol=1e-6)
    assert all(val >= 0.0 for val in pop_hex.values())

    rates_by_mun: dict[CdMun, float | None] = {
        CdMun("3500105"): 0.80,
        CdMun("3500204"): 0.60,
        CdMun("3500303"): None,
        CdMun("3500402"): 0.70,
    }
    rate_hex = reconcile_rate(rates_by_mun, weights_first, pop_by_mun)
    non_null_rates = [val for val in rate_hex.values() if val is not None]
    assert non_null_rates
    assert all(0.60 - 1e-9 <= val <= 0.80 + 1e-9 for val in non_null_rates)
    mun3_hexes = {
        H3Index(row.h3)
        for row in mun_hex_rows
        if row.cd_mun == "3500303"
    }
    mun3_only_hexes = mun3_hexes - {
        H3Index(row.h3)
        for row in mun_hex_rows
        if row.cd_mun != "3500303"
    }
    assert mun3_only_hexes
    for cell in mun3_only_hexes:
        assert rate_hex[cell] is None


def test_civ_rules_validation_and_positional_web_export(tmp_path: Path) -> None:
    bad_rules = tmp_path / "bad_rules.yaml"
    bad_rules.write_text(
        "lenses:\n  - id: ouro\n    civ_name: Ouro\n",
        encoding="utf-8",
    )
    with pytest.raises(CivRulesError):
        load_civ_rules(bad_rules)

    rules = load_civ_rules(Path("pipeline/civ/civ_rules.yaml"))
    assert {lens.id for lens in rules} >= {"ouro", "producao", "comida", "cidadaos"}

    municipios = load_municipios_from_files(SAMPLE_MALHA, SAMPLE_MUNICIPIOS)
    mun_hex_rows = build_municipio_hex_table(municipios, resolution=H3_RESOLUTION)
    grade_cells = load_grade_cells_from_file(SAMPLE_GRADE)
    censo = load_censo_from_file(SAMPLE_CENSO)
    pib = load_pib_from_file(SAMPLE_PIB)
    weights = build_dasymetric_weights(municipios, mun_hex_rows, grade_cells)

    hex_metrics: dict[str, dict[H3Index, float]] = {
        "pop": reconcile_sum({cd: float(r.pop) for cd, r in censo.items()}, weights),
        "pib": reconcile_sum({cd: r.pib for cd, r in pib.items()}, weights),
        "vab_ind": reconcile_sum({cd: r.vab_ind for cd, r in pib.items()}, weights),
        "vab_agro": reconcile_sum({cd: r.vab_agro for cd, r in pib.items()}, weights),
        "vab_serv": reconcile_sum({cd: r.vab_serv for cd, r in pib.items()}, weights),
        "vab_adm": reconcile_sum({cd: r.vab_adm for cd, r in pib.items()}, weights),
    }

    out_dir = tmp_path / "web_data" / "sp"
    export_uf_web_bundle(
        uf="SP",
        municipios=municipios,
        mun_hex_rows=mun_hex_rows,
        hex_metrics=hex_metrics,
        rules=[r for r in rules if r.column in hex_metrics],
        output_dir=out_dir,
    )

    grid = json.loads((out_dir / "grid.json").read_text(encoding="utf-8"))
    index = json.loads((out_dir / "lentes" / "index.json").read_text(encoding="utf-8"))
    ouro_raw = (out_dir / "lentes" / "ouro.json").read_text(encoding="utf-8")
    ouro = json.loads(ouro_raw)

    assert grid["hex_count"] == len(grid["h3"])
    assert len(ouro["values"]) == grid["hex_count"]
    assert "85a8" not in ouro_raw
    assert math.isclose(
        sum(val for val in ouro["values"] if val is not None),
        sum(r.pib for r in pib.values()),
        rel_tol=1e-3,
    )
    assert len(index["lenses"]) >= 4
    for entry in index["lenses"]:
        assert entry["source_id"]
        assert isinstance(entry["ano_ref"], int)
        assert entry["unit"]
