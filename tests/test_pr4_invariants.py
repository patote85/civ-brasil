from __future__ import annotations

import json
import math
from pathlib import Path

from pipeline.civ.rules import load_civ_rules
from pipeline.grid.h3_grid import build_municipio_hex_table
from pipeline.reconcile.dasymetric import build_dasymetric_weights, reconcile_rate
from pipeline.sources.ibge_censo import load_censo_from_file
from pipeline.sources.ibge_grade import load_grade_cells_from_file
from pipeline.sources.ibge_malhas import load_municipios_from_files
from pipeline.sources.ipea_idhm import load_ipea_idhm_from_files
from pipeline.sources.ssp_sp import load_ssp_sp_from_file
from pipeline.sources.tse import load_tse_from_file
from pipeline.types import CdMun

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_MALHA = FIXTURES_DIR / "sp_sample_malha.geojson"
SAMPLE_MUNICIPIOS = FIXTURES_DIR / "sp_sample_municipios.json"
SAMPLE_GRADE = FIXTURES_DIR / "sp_sample_grade.geojson"
SAMPLE_CENSO = FIXTURES_DIR / "sp_sample_censo.json"

FORBIDDEN_LOYALTY_TERMS = (
    "melhor partido",
    "pior partido",
    "ranking de partido",
    "esquerda",
    "direita",
    "conservador",
    "progressista",
    "corrupto",
    "radical",
    "extremista",
)


def test_tse_reconciliation_and_neutrality(tmp_path: Path) -> None:
    municipios = load_municipios_from_files(SAMPLE_MALHA, SAMPLE_MUNICIPIOS)
    valid_muns = {CdMun(m.cd_mun): m.nome for m in municipios}

    tse_csv = tmp_path / "detalhe_votacao_munzona_2024_SP.csv"
    lines = [
        "NR_TURNO;SG_UF;CD_CARGO;NM_MUNICIPIO;QT_APTOS;QT_COMPARECIMENTO;QT_ABSTENCOES;"
        "QT_VOTOS_NOMINAIS_VALIDOS;QT_VOTOS_LEGENDA_VALIDOS;QT_VOTOS_BRANCOS;QT_VOTOS_NULOS;"
        "QT_VOTOS_NULOS_TECNICOS;QT_VOTOS_ANULADOS_APU_SEP"
    ]
    for idx, (_cd, nome) in enumerate(sorted(valid_muns.items())):
        aptos = 10000 + idx * 1000
        comp = 8000 + idx * 700
        abst = aptos - comp
        validos = comp - 500
        brancos = 200
        nulos = 250
        sub_judice = 50
        lines.append(
            f"1;SP;11;{nome.upper()};{aptos};{comp};{abst};{validos};0;{brancos};{nulos};0;{sub_judice}"
        )
    tse_csv.write_text("\n".join(lines) + "\n", encoding="latin-1")

    records = load_tse_from_file(tse_csv, uf="SP", mun_names_by_cd=valid_muns)
    assert set(records.keys()) == set(valid_muns.keys())

    for cd, rec in records.items():
        assert rec.eleitorado > 0
        assert rec.comparecimento <= rec.eleitorado
        assert rec.comparecimento + rec.abstencoes == rec.eleitorado
        total_votos = (
            rec.votos_validos + rec.votos_brancos + rec.votos_nulos + rec.anulados_sub_judice
        )
        assert total_votos == rec.comparecimento, f"Divergência de votos em {cd}"
        assert 0.0 <= rec.participacao_pct <= 100.0

    rules = load_civ_rules(Path("pipeline/civ/civ_rules.yaml"))
    loyalty = next(r for r in rules if r.id == "lealdade")
    combined_text = f"{loyalty.civ_name} {loyalty.br_name} {loyalty.note}".lower()
    for term in FORBIDDEN_LOYALTY_TERMS:
        assert term not in combined_text, f"Termo proibido na lente lealdade: {term}"


def test_ipea_idhm_and_gini_bounds_and_rate_reconciliation(tmp_path: Path) -> None:
    municipios = load_municipios_from_files(SAMPLE_MALHA, SAMPLE_MUNICIPIOS)
    valid = {CdMun(m.cd_mun) for m in municipios}
    mun_hex_rows = build_municipio_hex_table(municipios)
    grade_cells = load_grade_cells_from_file(SAMPLE_GRADE)
    censo = load_censo_from_file(SAMPLE_CENSO)
    weights = build_dasymetric_weights(municipios, mun_hex_rows, grade_cells)

    idhm_json = tmp_path / "adh_idhm.json"
    gini_json = tmp_path / "adh_gini.json"
    idhm_vals = [
        {"TERCODIGO": str(cd), "VALDATA": "2010-01-01T00:00:00-02:00", "VALVALOR": 0.78}
        for cd in sorted(valid)
    ]
    gini_vals = [
        {"TERCODIGO": str(cd), "VALDATA": "2010-01-01T00:00:00-02:00", "VALVALOR": 0.45}
        for cd in sorted(valid)
    ]
    idhm_json.write_text(json.dumps({"value": idhm_vals}), encoding="utf-8")
    gini_json.write_text(json.dumps({"value": gini_vals}), encoding="utf-8")

    records = load_ipea_idhm_from_files(idhm_json, gini_json, valid_cd_muns=valid)
    assert set(records.keys()) == valid
    for rec in records.values():
        assert rec.idhm is not None and 0.0 <= rec.idhm <= 1.0
        assert rec.gini is not None and 0.0 <= rec.gini <= 1.0

    pop_by_mun = {cd: float(r.pop) for cd, r in censo.items()}
    hex_idhm = reconcile_rate(
        {cd: rec.idhm for cd, rec in records.items()},
        weights,
        pop_by_mun,
    )
    for val in hex_idhm.values():
        if val is not None:
            assert math.isclose(val, 0.78, abs_tol=1e-6)


def test_ssp_sp_rates_and_low_population_flag(tmp_path: Path) -> None:
    municipios = load_municipios_from_files(SAMPLE_MALHA, SAMPLE_MUNICIPIOS)
    valid_muns = {CdMun(m.cd_mun): m.nome for m in municipios}
    censo = load_censo_from_file(SAMPLE_CENSO)
    pop_by_mun = {cd: r.pop for cd, r in censo.items()}

    ssp_json = tmp_path / "ssp_sp_2025.json"
    items = []
    for idx, (_cd, nome) in enumerate(sorted(valid_muns.items())):
        items.append(
            {
                "nome": nome,
                "ano": 2025,
                "homicidio": 2 + idx,
                "furto": 120 + idx * 10,
                "roubo": 30 + idx * 5,
                "furtoVeiculo": 10,
                "rouboVeiculo": 4,
            }
        )
    ssp_json.write_text(json.dumps({"ano": 2025, "municipios": items}), encoding="utf-8")

    records = load_ssp_sp_from_file(ssp_json, mun_names_by_cd=valid_muns, pop_by_mun=pop_by_mun)
    assert set(records.keys()) == set(valid_muns.keys())
    for cd, rec in records.items():
        pop = pop_by_mun[cd]
        expected_hom = 100_000.0 * rec.homicidio / pop
        expected_roubo = 100_000.0 * rec.roubo / pop
        assert math.isclose(rec.homicidio_100k, expected_hom, rel_tol=1e-5, abs_tol=1e-2)
        assert math.isclose(rec.roubo_100k, expected_roubo, rel_tol=1e-5, abs_tol=1e-2)
        assert rec.baixa_populacao == (pop < 20_000)


def test_civ_rules_contains_all_pr4_sensitive_lenses_with_required_notes() -> None:
    rules = load_civ_rules(Path("pipeline/civ/civ_rules.yaml"))
    by_id = {r.id: r for r in rules}
    for required in ("lealdade", "desenvolvimento", "descontentamento"):
        assert required in by_id
    assert by_id["desenvolvimento"].ano_ref == 2010
    assert "2010" in by_id["desenvolvimento"].note
    assert "subnotifica" in by_id["descontentamento"].note.lower()
