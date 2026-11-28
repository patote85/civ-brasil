from __future__ import annotations

import json
import math
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from pipeline.run_br_sources import NATIONAL_DESCONTENTAMENTO_SOURCE
from pipeline.sources.ibge_saneamento import load_saneamento_from_file
from pipeline.sources.ipea_atlas_violencia import load_atlas_violencia_from_file
from pipeline.sources.mds_bolsa import load_bolsa_familia_from_files
from pipeline.types import CdMun


def test_atlas_violencia_loader_picks_latest_municipal_year(tmp_path: Path) -> None:
    sample = {
        "value": [
            {
                "SERCODIGO": "AVIOL12_THOMIC",
                "VALDATA": "2020-01-01T00:00:00-03:00",
                "VALVALOR": 12.5,
                "NIVNOME": "Municípios",
                "TERCODIGO": "3550308",
            },
            {
                "SERCODIGO": "AVIOL12_THOMIC",
                "VALDATA": "2022-01-01T00:00:00-03:00",
                "VALVALOR": 8.4,
                "NIVNOME": "Municípios",
                "TERCODIGO": "3550308",
            },
            {
                "SERCODIGO": "AVIOL12_THOMIC",
                "VALDATA": "2022-01-01T00:00:00-03:00",
                "VALVALOR": 21.0,
                "NIVNOME": "Estados",
                "TERCODIGO": "35",
            },
        ]
    }
    p = tmp_path / "atlas.json"
    p.write_text(json.dumps(sample), encoding="utf-8")
    records = load_atlas_violencia_from_file(p)
    assert len(records) == 1
    rec = records[CdMun("3550308")]
    assert rec.ano_ref == 2022
    assert math.isclose(rec.taxa_homic_100k, 8.4, rel_tol=1e-9)


def test_mds_bolsa_loader_parses_families_and_values(tmp_path: Path) -> None:
    fam_path = tmp_path / "fam.json"
    val_path = tmp_path / "val.json"
    fam_path.write_text(
        json.dumps({
            "value": [
                {
                    "VALDATA": "2021-01-01T00:00:00-03:00",
                    "VALVALOR": 5000.0,
                    "NIVNOME": "Municípios",
                    "TERCODIGO": "3550308",
                },
                {
                    "VALDATA": "2023-01-01T00:00:00-03:00",
                    "VALVALOR": 6200.0,
                    "NIVNOME": "Municípios",
                    "TERCODIGO": "3550308",
                },
            ]
        }),
        encoding="utf-8",
    )
    val_path.write_text(
        json.dumps({
            "value": [
                {
                    "VALDATA": "2023-01-01T00:00:00-03:00",
                    "VALVALOR": 4200.0,
                    "NIVNOME": "Municípios",
                    "TERCODIGO": "3550308",
                },
            ]
        }),
        encoding="utf-8",
    )
    records = load_bolsa_familia_from_files(fam_path, val_path)
    assert len(records) == 1
    rec = records[CdMun("3550308")]
    assert rec.ano_ref == 2023
    assert rec.familias == 6200
    assert math.isclose(rec.valor_mil_reais or 0.0, 4200.0, rel_tol=1e-9)


def test_ibge_saneamento_loader_parses_sidra_6805(tmp_path: Path) -> None:
    p = tmp_path / "saneamento.json"
    p.write_text(
        json.dumps([
            {"D1C": "Município (Código)", "D3C": "Ano", "V": "Valor"},
            {"D1C": "3550308", "D3C": "2022", "V": "95.23"},
            {"D1C": "1302603", "D3C": "2022", "V": "-"},
        ]),
        encoding="utf-8",
    )
    records = load_saneamento_from_file(p)
    assert len(records) == 2
    assert math.isclose(records[CdMun("3550308")].esgoto_adequado_pct or 0.0, 95.23, rel_tol=1e-9)
    assert records[CdMun("1302603")].esgoto_adequado_pct is None


def test_national_descontentamento_shield_never_mixes_ssp_sp_or_sinesp() -> None:
    assert NATIONAL_DESCONTENTAMENTO_SOURCE == "ipea_atlas_violencia"
    src_text = Path("pipeline/run_br_sources.py").read_text(encoding="utf-8")
    assert "ssp_sp" not in src_text
    assert "sinesp_vde" not in src_text


def test_real_br_sources_checkpoint_and_parquet_invariants() -> None:
    ckpt_path = Path("data/checkpoints/br_sources.json")
    parquet_path = Path("data/processed/br_municipios_indicators.parquet")
    if not ckpt_path.is_file() or not parquet_path.is_file():
        pytest.skip("Artefatos nacionais PR 7 não gerados neste ambiente")

    ckpt = json.loads(ckpt_path.read_text(encoding="utf-8"))
    assert ckpt["mun_count"] == 5570
    assert ckpt["descontentamento_nacional_source"] == "ipea_atlas_violencia"

    tbl = pq.read_table(parquet_path)
    assert tbl.num_rows == 5570
    cds = tbl.column("cd_mun").to_pylist()
    assert len(set(cds)) == 5570

    # IDHM 2010 must have 5,565 populated + 5 post-2010 municipalities explicitly null
    idhm_vals = tbl.column("idhm_2010").to_pylist()
    non_null_idhm = [v for v in idhm_vals if v is not None]
    assert len(non_null_idhm) == 5565
    assert all(0.0 <= float(v) <= 1.0 for v in non_null_idhm)

    # Sanitation must cover all 5,570 municipalities in [0, 100]
    esg_vals = [v for v in tbl.column("saneamento_esgoto_pct").to_pylist() if v is not None]
    assert len(esg_vals) >= 5500
    assert all(0.0 <= float(v) <= 100.0 for v in esg_vals)

    # TSE invariant: comparecimento <= aptos
    for aptos, comp in zip(
        tbl.column("tse_aptos").to_pylist(),
        tbl.column("tse_comparecimento").to_pylist(),
        strict=True,
    ):
        if aptos is not None and comp is not None:
            assert int(comp) <= int(aptos)
