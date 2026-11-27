from __future__ import annotations

import json
import math
import zipfile
from pathlib import Path

import openpyxl
import pytest

from pipeline.civ.districts import compute_location_quotients
from pipeline.civ.rules import load_civ_rules
from pipeline.grid.h3_grid import build_municipio_hex_table
from pipeline.reconcile import build_dasymetric_weights, reconcile_rate, reconcile_sum
from pipeline.reconcile.points import assign_points_to_grid
from pipeline.sources.aneel_siga import load_aneel_siga_from_file
from pipeline.sources.antaq import load_antaq_from_files
from pipeline.sources.cnes import load_cnes_from_files
from pipeline.sources.ibge_grade import load_grade_cells_from_file
from pipeline.sources.ibge_malhas import load_municipios_from_files
from pipeline.sources.inep_escolar import load_inep_escolar_from_file
from pipeline.sources.inep_ideb import load_inep_ideb_from_files
from pipeline.sources.inep_superior import load_inep_superior_from_file
from pipeline.sources.rais import load_rais_from_file
from pipeline.types import CdMun, H3Index

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_MALHA = FIXTURES_DIR / "sp_sample_malha.geojson"
SAMPLE_MUNICIPIOS = FIXTURES_DIR / "sp_sample_municipios.json"
SAMPLE_GRADE = FIXTURES_DIR / "sp_sample_grade.geojson"


def test_rais_ql_invariants_and_zero_division_safety(tmp_path: Path) -> None:
    # Mix of 2025 comma-separated header and 6-digit municipality codes
    rais_csv = tmp_path / "rais_sample.csv"
    rais_csv.write_text(
        "Município,CNAE 2.0 Classe,Qtd Vínculos Ativos\n"
        "355030,62015,1000\n"
        "355030,30415,100\n"
        "354990,30415,900\n"
        "354990,62015,100\n"
        "354990,,50\n"
        "330455,62015,5000\n",
        encoding="utf-8",
    )
    valid = {CdMun("3550308"), CdMun("3549904"), CdMun("3509502")}
    records, stats = load_rais_from_file(rais_csv, uf="SP", valid_cd_muns=valid)

    assert stats["vinculos_sp"] == 2150
    assert sum(r.vinculos for r in records) == 2150

    scores, uf_ql = compute_location_quotients(records, sorted(valid))

    # UF-level QL must equal 1.0 for every active CNAE division
    for div, qval in uf_ql.items():
        assert math.isclose(qval, 1.0, abs_tol=1e-9), f"UF QL != 1.0 para divisão {div}: {qval}"

    # Campinas (3509502) has 0 vínculos -> QL must be 0.0, never ZeroDivisionError
    campinas_scores = [s for s in scores if s.cd_mun == CdMun("3509502")]
    assert all(s.ql == 0.0 for s in campinas_scores)

    # SJC (3549904) must show Aerospace (CNAE div 30) specialization with QL > 1.5
    sjc_aero = [s for s in scores if s.cd_mun == CdMun("3549904") and s.cnae_div == "30"]
    assert len(sjc_aero) == 1
    assert sjc_aero[0].ql > 1.5
    assert "Aeroespacial" in sjc_aero[0].district_name


def test_inep_escolar_superior_and_ideb_reconciliation(tmp_path: Path) -> None:
    municipios = load_municipios_from_files(SAMPLE_MALHA, SAMPLE_MUNICIPIOS)
    valid = {CdMun(m.cd_mun) for m in municipios}
    mun_hex = build_municipio_hex_table(municipios)
    grade = load_grade_cells_from_file(SAMPLE_GRADE)
    weights = build_dasymetric_weights(municipios, mun_hex, grade)

    esc_csv = tmp_path / "microdados_ed_basica_2024.csv"
    esc_csv.write_text(
        "CO_MUNICIPIO;TP_SITUACAO_FUNCIONAMENTO;QT_MAT_BAS\n"
        "3500105;1;1200\n"
        "3500105;1;800\n"
        "3500105;2;500\n"
        "3500204;1;600\n"
        ";1;100\n",
        encoding="latin-1",
    )
    esc_zip = tmp_path / "escolar.zip"
    with zipfile.ZipFile(esc_zip, "w") as zf:
        zf.write(esc_csv, arcname="dados/microdados_ed_basica_2024.csv")

    esc_map = load_inep_escolar_from_file(esc_zip, uf="SP", valid_cd_muns=valid)
    assert esc_map[CdMun("3500105")].escolas == 2
    assert esc_map[CdMun("3500105")].matriculas_basica == 2000
    assert esc_map[CdMun("3500204")].matriculas_basica == 600

    mat_by_mun = {cd: float(rec.matriculas_basica) for cd, rec in esc_map.items()}
    hex_mat = reconcile_sum(mat_by_mun, weights)
    assert math.isclose(sum(hex_mat.values()), 2600.0, rel_tol=1e-6)

    sup_csv = tmp_path / "MICRODADOS_CADASTRO_CURSOS_2025.CSV"
    sup_csv.write_text(
        "CO_MUNICIPIO;CO_IES;QT_MAT\n3500105;101;450\n3500105;101;150\n3500204;202;300\n",
        encoding="latin-1",
    )
    sup_zip = tmp_path / "superior.zip"
    with zipfile.ZipFile(sup_zip, "w") as zf:
        zf.write(sup_csv, arcname="dados/MICRODADOS_CADASTRO_CURSOS_2025.CSV")

    sup_map = load_inep_superior_from_file(sup_zip, uf="SP", valid_cd_muns=valid)
    assert sup_map[CdMun("3500105")].ies == 1
    assert sup_map[CdMun("3500105")].matriculas_superior == 600
    assert sup_map[CdMun("3500204")].matriculas_superior == 300

    def _make_ideb_xlsx(dest: Path, rows: list[list[object]]) -> None:
        wb = openpyxl.Workbook()
        ws = wb.active
        assert ws is not None
        for _ in range(8):
            ws.append(["Cabeçalho INEP"])
        ws.append(["SG_UF", "CO_MUNICIPIO", "NO_MUNICIPIO", "REDE", "VL_OBSERVADO_2025"])
        for row in rows:
            ws.append(row)
        wb.save(dest)

    ai_xlsx = tmp_path / "ideb_ai.xlsx"
    af_xlsx = tmp_path / "ideb_af.xlsx"
    em_xlsx = tmp_path / "ideb_em.xlsx"
    _make_ideb_xlsx(
        ai_xlsx,
        [
            ["SP", "3500105", "Mun A", "Pública", 6.8],
            ["SP", "3500204", "Mun B", "Pública", "-"],
        ],
    )
    _make_ideb_xlsx(
        af_xlsx,
        [
            ["SP", "3500105", "Mun A", "Pública", 5.6],
            ["SP", "3500204", "Mun B", "Pública", 5.2],
        ],
    )
    _make_ideb_xlsx(
        em_xlsx,
        [
            ["SP", "3500105", "Mun A", "Pública", 4.9],
            ["SP", "3500204", "Mun B", "Pública", "ND"],
        ],
    )

    ideb_map = load_inep_ideb_from_files(ai_xlsx, af_xlsx, em_xlsx, uf="SP", valid_cd_muns=valid)
    assert ideb_map[CdMun("3500105")].ideb_ai == 6.8
    assert ideb_map[CdMun("3500204")].ideb_ai is None
    assert ideb_map[CdMun("3500204")].ideb_af == 5.2

    pop_by_mun = {CdMun(m.cd_mun): 10000.0 for m in municipios}
    rate_by_mun = {cd: rec.ideb_medio for cd, rec in ideb_map.items() if rec.ideb_medio is not None}
    hex_ideb = reconcile_rate(rate_by_mun, weights, pop_by_mun)
    non_null = [v for v in hex_ideb.values() if v is not None]
    assert non_null
    assert all(4.5 <= v <= 7.0 for v in non_null)


def test_cnes_aneel_antaq_points_and_rejection_report(tmp_path: Path) -> None:
    municipios = load_municipios_from_files(SAMPLE_MALHA, SAMPLE_MUNICIPIOS)
    valid = {CdMun(m.cd_mun) for m in municipios}
    mun_hex = build_municipio_hex_table(municipios)
    valid_hexes = {H3Index(r.h3) for r in mun_hex}
    rep = municipios[0].geometry.representative_point()

    estab_csv = tmp_path / "cnes_estabelecimentos.csv"
    estab_csv.write_text(
        "CO_CNES;NO_FANTASIA;CO_IBGE;TP_UNIDADE;NU_LATITUDE;NU_LONGITUDE\n"
        f"1000001;HOSPITAL A;350010;05;{rep.y};{rep.x}\n"
        "1000002;CLINICA B;350010;22;999.0;999.0\n",
        encoding="latin-1",
    )
    leitos_csv = tmp_path / "cnes_leitos_2025.csv"
    leitos_csv.write_text(
        "CO_CNES;CO_MUNICIPIO;QT_EXIST\n1000001;350010;120\n1000001;350010;30\n",
        encoding="latin-1",
    )
    cnes_mun, cnes_pts, cnes_rej = load_cnes_from_files(
        estab_csv, leitos_csv, uf="SP", valid_cd_muns=valid
    )
    assert cnes_mun[CdMun("3500105")].estabelecimentos == 2
    assert cnes_mun[CdMun("3500105")].hospitais == 1
    assert cnes_mun[CdMun("3500105")].leitos == 150
    assert len(cnes_pts) == 1
    assert len(cnes_rej) == 0  # clínica não-hospitalar sem ponto não gera rejeição hospitalar

    siga_json = tmp_path / "epe_usinas.json"
    siga_json.write_text(
        json.dumps(
            {
                "features": [
                    {
                        "properties": {
                            "nome": "UHE Teste SP",
                            "potencia": 50000.0,
                            "ceg": "UHE.PH.SP.000001-0.01",
                            "fonte": "UHE",
                        },
                        "geometry": {"type": "Point", "coordinates": [rep.x, rep.y]},
                    },
                    {
                        "properties": {
                            "nome": "Usina Coordenada Trocada",
                            "potencia": 10000.0,
                            "ceg": "UFV.RS.SP.000002-0.01",
                            "fonte": "UFV",
                        },
                        "geometry": {"type": "Point", "coordinates": [rep.y, rep.x]},
                    },
                    {
                        "properties": {
                            "nome": "Usina Fora de SP",
                            "potencia": 25000.0,
                            "ceg": "UHE.PH.SP.000003-0.01",
                            "fonte": "UHE",
                        },
                        "geometry": {"type": "Point", "coordinates": [-60.0, -3.0]},
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    plants, pre_rejected = load_aneel_siga_from_file(siga_json, uf="SP")
    accepted, grid_rejected = assign_points_to_grid(
        [("usina", p.nome, p.fonte, p.potencia_mw, "MW", p.lat, p.lon, "") for p in plants],
        valid_hexes=valid_hexes,
        source_name="aneel_siga",
    )
    total_rejected = len(pre_rejected) + len(grid_rejected)
    assert len(accepted) == 1
    assert accepted[0].h3 in valid_hexes
    assert math.isclose(accepted[0].value, 50.0, rel_tol=1e-6)
    assert total_rejected == 2

    ports_geojson = tmp_path / "portos.geojson"
    ports_geojson.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {
                            "nome": "Porto Teste",
                            "tipo": "Porto Organizado",
                            "uf": "SP",
                            "municipio": municipios[0].nome,
                            "hidrovia": "Hidrovia Teste",
                        },
                        "geometry": {"type": "Point", "coordinates": [rep.x, rep.y]},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    ports, port_rej = load_antaq_from_files(
        ports_geojson,
        uf="SP",
        mun_name_to_cd={municipios[0].nome.lower(): CdMun(municipios[0].cd_mun)},
    )
    assert len(ports) == 1
    assert ports[0].cd_mun == CdMun(municipios[0].cd_mun)
    assert not port_rej


def test_civ_rules_contains_all_pr3_lenses() -> None:
    rules = load_civ_rules(Path("pipeline/civ/civ_rules.yaml"))
    ids = {r.id for r in rules}
    expected = {
        "ouro",
        "producao",
        "comida",
        "cidadaos",
        "distritos",
        "ciencia_educacao",
        "saude",
        "infra",
    }
    assert expected.issubset(ids)


def test_cnes_partial_id_match_preserves_full_municipal_beds(tmp_path: Path) -> None:
    estab_csv = tmp_path / "estab.csv"
    estab_csv.write_text(
        "CO_CNES;NO_FANTASIA;CO_IBGE;TP_UNIDADE;NU_LATITUDE;NU_LONGITUDE\n"
        "1000001;Hospital A;350010;05;-21.68;-51.07\n",
        encoding="latin-1",
    )
    leitos_csv = tmp_path / "leitos.csv"
    leitos_csv.write_text(
        "COMPETENCIA;IBGE;CNES;QTDE_EXISTENTE\n"
        "202512;350010;1000001;80\n"
        "202512;350010;9999999;45\n",
        encoding="latin-1",
    )
    cnes_mun, _, _ = load_cnes_from_files(
        estab_csv, leitos_csv, uf="SP", valid_cd_muns={CdMun("3500105")}
    )
    assert cnes_mun[CdMun("3500105")].leitos == 125


def test_inep_ssl_context_rejects_tampered_cached_cert(tmp_path: Path) -> None:
    from pipeline.sources._common import (
        RNP_INTERMEDIATE_CERT_URL,
        IntegrityError,
        build_inep_ssl_context,
    )

    assert RNP_INTERMEDIATE_CERT_URL.startswith("https://")
    cert_dir = tmp_path / "_certs"
    cert_dir.mkdir(parents=True)
    (cert_dir / "rnpicpedugr46ovtlsca2025.crt").write_bytes(b"forged-cert-bytes")
    with pytest.raises(IntegrityError):
        build_inep_ssl_context(raw_root=tmp_path)

