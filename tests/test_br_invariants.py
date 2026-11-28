from __future__ import annotations

import json
import math
from pathlib import Path

import h3
import openpyxl
import pytest

from pipeline.grid.br import (
    BR_OFFICIAL_AREA_KM2,
    BR_OFFICIAL_POP_2022,
    UfHexRecord,
    aggregate_res5_to_res3,
    export_br_res3_web_bundle,
)
from pipeline.sources.ibge_arranjos import load_arranjos_from_file
from pipeline.sources.ibge_malhas import malha_url_for_uf, municipios_url_for_uf
from pipeline.types import UF_IBGE_CODES


def test_ibge_malhas_urls_cover_all_27_ufs() -> None:
    assert len(UF_IBGE_CODES) == 27
    for uf, ibge_code in UF_IBGE_CODES.items():
        m_url = malha_url_for_uf(uf)
        l_url = municipios_url_for_uf(uf)
        assert f"/estados/{ibge_code}?" in m_url
        assert "qualidade=intermediaria" in m_url
        assert f"/estados/{ibge_code}/municipios" in l_url


def test_ibge_arranjos_parser_reads_synthetic_xlsx(tmp_path: Path) -> None:
    xlsx_path = tmp_path / "tab01.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Tabela 1.1_Revisada"
    ws.append(["Tabela 1.1 Municípios brasileiros que participam de arranjos populacionais"])
    ws.append([
        "Arranjos populacionais e municípios brasileiros",
        "Código do município",
        "População",
        "Núcleo",
        "Pessoas",
        "Índice de integração",
    ])
    ws.append(["São Paulo/SP", None, None, None, None, None])
    ws.append(["São Paulo (SP)", 3550308, 11253503, "Sim", 100000, 0.12])
    ws.append(["Guarulhos (SP)", 3518800, 1221979, "Não", 80000, 0.25])
    ws.append(["Adrianópolis/PR - Ribeira/SP", None, None, None, None, None])
    ws.append(["Ribeira (SP)", 3542800, 3358, "Sim", 180, 0.083604])
    ws.append(["Fonte: IBGE", None, None, None, None, None])
    wb.save(xlsx_path)

    records = load_arranjos_from_file(xlsx_path)
    assert len(records) == 3
    assert records["3550308"].nome_arranjo == "São Paulo/SP"
    assert records["3550308"].is_nucleo is True
    assert records["3518800"].is_nucleo is False
    assert records["3542800"].nome_arranjo == "Adrianópolis/PR - Ribeira/SP"
    assert math.isclose(records["3542800"].indice_integracao or 0.0, 0.083604, rel_tol=1e-9)


def test_aggregate_res5_to_res3_conserves_sums_across_interstate_borders() -> None:
    cell_a = h3.latlng_to_cell(-22.8, -46.5, 5)
    cell_b = h3.latlng_to_cell(-22.7, -46.4, 5)
    parent_a = h3.cell_to_parent(cell_a, 3)

    records = [
        UfHexRecord(
            uf="SP",
            h3=cell_a,
            area_km2=120.5,
            pop=50_000.0,
            pib_mil=2_000_000.0,
            pib_agro_mil=50_000.0,
            pib_ind_mil=600_000.0,
            pib_serv_mil=1_100_000.0,
            pib_adm_mil=250_000.0,
            mun_count=2,
        ),
        UfHexRecord(
            uf="MG",
            h3=cell_a,
            area_km2=80.25,
            pop=12_000.0,
            pib_mil=400_000.0,
            pib_agro_mil=80_000.0,
            pib_ind_mil=100_000.0,
            pib_serv_mil=150_000.0,
            pib_adm_mil=70_000.0,
            mun_count=1,
        ),
        UfHexRecord(
            uf="MG",
            h3=cell_b,
            area_km2=210.0,
            pop=30_000.0,
            pib_mil=900_000.0,
            pib_agro_mil=200_000.0,
            pib_ind_mil=200_000.0,
            pib_serv_mil=350_000.0,
            pib_adm_mil=150_000.0,
            mun_count=1,
        ),
    ]

    res3 = aggregate_res5_to_res3(records)
    assert len(res3) >= 1
    assert any(h.h3 == parent_a for h in res3)
    assert math.isclose(sum(h.area_km2 for h in res3), 410.75, rel_tol=1e-9)
    assert math.isclose(sum(h.pop for h in res3), 92_000.0, rel_tol=1e-9)
    assert math.isclose(sum(h.pib_mil for h in res3), 3_300_000.0, rel_tol=1e-9)

    p_row = next(h for h in res3 if h.h3 == parent_a)
    assert set(p_row.ufs) == {"MG", "SP"}


def test_export_br_res3_web_bundle_is_deterministic(tmp_path: Path) -> None:
    cell_sp = h3.latlng_to_cell(-23.55, -46.63, 5)
    cell_am = h3.latlng_to_cell(-3.12, -60.02, 5)
    res3 = aggregate_res5_to_res3([
        UfHexRecord("SP", cell_sp, 200.0, 100_000.0, 5_000_000.0, 10_000.0, 1_000_000.0, 3_500_000.0, 490_000.0, 1),
        UfHexRecord("AM", cell_am, 250.0, 50_000.0, 1_200_000.0, 50_000.0, 500_000.0, 500_000.0, 150_000.0, 1),
    ])
    uf_summaries = [
        {"uf": "AM", "nome": "Amazonas", "mun_count": 62, "hex_count": 1, "pop": 50_000, "pib_mil": 1_200_000.0, "area_km2": 250.0},
        {"uf": "SP", "nome": "São Paulo", "mun_count": 645, "hex_count": 1, "pop": 100_000, "pib_mil": 5_000_000.0, "area_km2": 200.0},
    ]
    out1 = tmp_path / "run1" / "br_res3.json"
    out2 = tmp_path / "run2" / "br_res3.json"
    export_br_res3_web_bundle(res3, uf_summaries, out1)
    export_br_res3_web_bundle(res3, uf_summaries, out2)
    assert out1.read_bytes() == out2.read_bytes()
    parsed = json.loads(out1.read_text(encoding="utf-8"))
    assert parsed["uf"] == "BR"
    assert parsed["resolution"] == 3
    assert parsed["hex_count"] == 2
    assert len(parsed["ufs"]) == 2


def test_real_br_checkpoint_and_budgets_when_present() -> None:
    ckpt_path = Path("data/checkpoints/br.json")
    if not ckpt_path.is_file():
        pytest.skip("data/checkpoints/br.json não gerado neste ambiente")

    ckpt = json.loads(ckpt_path.read_text(encoding="utf-8"))
    assert ckpt["mun_count"] == 5570
    assert len(ckpt["ufs"]) == 27
    assert 33_000 <= ckpt["unique_h3_res5_count"] <= 36_500
    assert abs(ckpt["area_km2"] - BR_OFFICIAL_AREA_KM2) / BR_OFFICIAL_AREA_KM2 <= 0.005
    assert abs(ckpt["pop_total"] - BR_OFFICIAL_POP_2022) / BR_OFFICIAL_POP_2022 <= 0.001

    sp_pilot = json.loads(Path("web/public/data/sp/grid.json").read_text(encoding="utf-8"))
    sp_br = json.loads(Path("web/public/data/br/sp_grid.json").read_text(encoding="utf-8"))
    assert sp_br["hex_count"] == sp_pilot["hex_count"]
    assert math.isclose(sp_br["total_pop"], sp_pilot["total_pop"], rel_tol=1e-9)
    assert math.isclose(sp_br["total_pib_mil"], sp_pilot["total_pib_mil"], rel_tol=1e-9)
    assert math.isclose(sp_br["total_area_km2"], sp_pilot["total_area_km2"], rel_tol=1e-9)

    assert Path("web/public/data/br/br_res3.json").stat().st_size <= 500_000
    assert Path("web/public/data/br/am_grid.json").stat().st_size <= 1_000_000
    for lens_file in Path("web/public/data/br/am_lenses").glob("*.json"):
        assert lens_file.stat().st_size <= 80_000
