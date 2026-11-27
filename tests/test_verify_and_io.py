from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.grid.h3_grid import (
    build_hex_summaries,
    build_municipio_hex_table,
    write_municipio_hex_parquet,
    write_sp_hex_json,
)
from pipeline.sources.ibge_malhas import load_municipios_from_files
from pipeline.verify import verify_artifacts

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_MALHA = FIXTURES_DIR / "sp_sample_malha.geojson"
SAMPLE_MUNICIPIOS = FIXTURES_DIR / "sp_sample_municipios.json"


def test_atomic_writes_preserve_previous_file_on_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    municipios = load_municipios_from_files(SAMPLE_MALHA, SAMPLE_MUNICIPIOS)
    rows = build_municipio_hex_table(municipios)
    summaries = build_hex_summaries(rows, {m.cd_mun: m.nome for m in municipios})

    parquet_path = tmp_path / "out.parquet"
    json_path = tmp_path / "out.json"
    parquet_path.write_bytes(b"anterior-parquet")
    json_path.write_text('{"anterior": true}', encoding="utf-8")

    def boom(_src: object, _dst: object) -> None:
        raise OSError("I/O interrompido")

    monkeypatch.setattr("os.replace", boom)

    with pytest.raises(OSError, match="I/O interrompido"):
        write_municipio_hex_parquet(rows, parquet_path)
    with pytest.raises(OSError, match="I/O interrompido"):
        write_sp_hex_json(summaries, json_path)

    assert parquet_path.read_bytes() == b"anterior-parquet"
    assert json_path.read_text(encoding="utf-8") == '{"anterior": true}'
    assert not list(tmp_path.glob("*.tmp"))


def test_verify_artifacts_rejects_missing_build_and_bad_hex_count(tmp_path: Path) -> None:
    missing_errors = verify_artifacts(
        dist_dir=tmp_path / "missing_dist",
        public_json=tmp_path / "public.json",
        parquet_path=tmp_path / "missing.parquet",
    )
    assert missing_errors

    dist_dir = tmp_path / "dist"
    (dist_dir / "assets").mkdir(parents=True)
    (dist_dir / "data").mkdir(parents=True)
    (dist_dir / "index.html").write_text("<html></html>", encoding="utf-8")
    (dist_dir / "assets" / "index.js").write_text("console.log(1);", encoding="utf-8")

    bad_payload = json.dumps(
        {
            "resolution": 5,
            "state": "SP",
            "hex_count": 1,
            "total_area_km2": 100.0,
            "hexes": [
                {
                    "h3": "85a81003fffffff",
                    "municipios": ["Adamantina"],
                    "cd_muns": ["3500105"],
                    "municipio_count": 1,
                    "area_km2": 100.0,
                }
            ],
        }
    )
    public_json = tmp_path / "sp_hex.json"
    public_json.write_text(bad_payload, encoding="utf-8")
    (dist_dir / "data" / "sp_hex.json").write_text(bad_payload, encoding="utf-8")

    errors = verify_artifacts(
        dist_dir=dist_dir,
        public_json=public_json,
        parquet_path=tmp_path / "none.parquet",
    )
    assert any("Contagem de hexes fora do invariante" in err for err in errors)


def test_verify_artifacts_checks_pr2_web_even_when_parquets_missing(tmp_path: Path) -> None:
    dist_dir = tmp_path / "dist"
    (dist_dir / "assets").mkdir(parents=True)
    (dist_dir / "data").mkdir(parents=True)
    (dist_dir / "index.html").write_text("<html></html>", encoding="utf-8")
    (dist_dir / "assets" / "index.js").write_text("console.log(1);", encoding="utf-8")

    payload = json.dumps(
        {
            "resolution": 5,
            "state": "SP",
            "hex_count": 1,
            "total_area_km2": 100.0,
            "hexes": [
                {
                    "h3": "85a81003fffffff",
                    "municipios": ["Adamantina"],
                    "cd_muns": ["3500105"],
                    "municipio_count": 1,
                    "area_km2": 100.0,
                }
            ],
        }
    )
    public_json = tmp_path / "sp_hex.json"
    public_json.write_text(payload, encoding="utf-8")
    (dist_dir / "data" / "sp_hex.json").write_text(payload, encoding="utf-8")

    sp_public_dir = tmp_path / "public_sp"
    (sp_public_dir / "lentes").mkdir(parents=True)
    (sp_public_dir / "grid.json").write_text('{"hex_count": 1}', encoding="utf-8")
    (sp_public_dir / "lentes" / "index.json").write_text('{"lenses": []}', encoding="utf-8")

    errors = verify_artifacts(
        dist_dir=dist_dir,
        public_json=public_json,
        parquet_path=tmp_path / "none.parquet",
        sp_processed_dir=tmp_path / "missing_parquets",
        sp_public_dir=sp_public_dir,
    )
    assert any("Parquet PR 2 ausente" in err for err in errors)
    assert any("Artefato web PR 2 ausente" in err for err in errors)

