from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from pipeline.sources.ibge_malhas import (
    MALHA_FILENAME,
    MUNICIPIOS_FILENAME,
    SP_MALHA_URL,
    SP_MUNICIPIOS_URL,
    FetchError,
    IntegrityError,
    ManifestCorruptedError,
    ensure_sp_raw_files,
    load_municipios_from_files,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_MALHA = FIXTURES_DIR / "sp_sample_malha.geojson"
SAMPLE_MUNICIPIOS = FIXTURES_DIR / "sp_sample_municipios.json"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_ensure_sp_raw_files_downloads_when_missing_and_skips_second_run(tmp_path: Path) -> None:
    malha_bytes = SAMPLE_MALHA.read_bytes()
    mun_bytes = SAMPLE_MUNICIPIOS.read_bytes()
    manifest_path = tmp_path / "data" / "manifest.json"
    calls: list[str] = []

    def fake_fetcher(url: str) -> bytes:
        calls.append(url)
        if url == SP_MALHA_URL:
            return malha_bytes
        if url == SP_MUNICIPIOS_URL:
            return mun_bytes
        raise AssertionError(f"URL inesperada: {url}")

    first = ensure_sp_raw_files(
        raw_root=tmp_path / "raw",
        manifest_path=manifest_path,
        fetcher=fake_fetcher,
    )
    assert set(first.downloaded_files) == {MALHA_FILENAME, MUNICIPIOS_FILENAME}
    assert first.feature_count == 4
    assert len(calls) == 2

    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    malha_entry = manifest_data["sources"][f"ibge_malhas/{MALHA_FILENAME}"]
    assert malha_entry["url"] == SP_MALHA_URL
    assert malha_entry["sha256"] == _sha256(malha_bytes)
    assert malha_entry["feature_count"] == 4

    def forbidden_fetcher(url: str) -> bytes:
        raise AssertionError(f"Não deveria baixar novamente: {url}")

    second = ensure_sp_raw_files(
        raw_root=tmp_path / "raw",
        manifest_path=manifest_path,
        fetcher=forbidden_fetcher,
    )
    assert second.downloaded_files == ()
    assert second.feature_count == 4


def test_ensure_sp_raw_files_reuses_local_files_matching_sha256sums(tmp_path: Path) -> None:
    ibge_dir = tmp_path / "raw" / "ibge_malhas"
    ibge_dir.mkdir(parents=True)
    malha_bytes = SAMPLE_MALHA.read_bytes()
    mun_bytes = SAMPLE_MUNICIPIOS.read_bytes()
    (ibge_dir / MALHA_FILENAME).write_bytes(malha_bytes)
    (ibge_dir / MUNICIPIOS_FILENAME).write_bytes(mun_bytes)
    (ibge_dir / "SHA256SUMS").write_text(
        f"{_sha256(malha_bytes)}  {MALHA_FILENAME}\n{_sha256(mun_bytes)}  {MUNICIPIOS_FILENAME}\n",
        encoding="utf-8",
    )

    def forbidden_fetcher(url: str) -> bytes:
        raise AssertionError(f"Não deveria chamar rede: {url}")

    result = ensure_sp_raw_files(
        raw_root=tmp_path / "raw",
        manifest_path=tmp_path / "manifest.json",
        fetcher=forbidden_fetcher,
    )
    assert result.downloaded_files == ()
    assert result.feature_count == 4


def test_ensure_sp_raw_files_fails_on_network_error_without_partial_files(tmp_path: Path) -> None:
    def failing_fetcher(url: str) -> bytes:
        raise FetchError(f"HTTP 503 em {url}")

    with pytest.raises(FetchError):
        ensure_sp_raw_files(
            raw_root=tmp_path / "raw",
            manifest_path=tmp_path / "manifest.json",
            fetcher=failing_fetcher,
        )

    ibge_dir = tmp_path / "raw" / "ibge_malhas"
    assert not (ibge_dir / MALHA_FILENAME).exists()
    assert not (tmp_path / "manifest.json").exists()


def test_ensure_sp_raw_files_detects_corrupted_local_file_and_manifest(tmp_path: Path) -> None:
    ibge_dir = tmp_path / "raw" / "ibge_malhas"
    ibge_dir.mkdir(parents=True)
    (ibge_dir / MALHA_FILENAME).write_bytes(b"corrompido")
    (ibge_dir / MUNICIPIOS_FILENAME).write_bytes(SAMPLE_MUNICIPIOS.read_bytes())
    (ibge_dir / "SHA256SUMS").write_text(
        f"{_sha256(SAMPLE_MALHA.read_bytes())}  {MALHA_FILENAME}\n",
        encoding="utf-8",
    )

    with pytest.raises(IntegrityError):
        ensure_sp_raw_files(
            raw_root=tmp_path / "raw",
            manifest_path=tmp_path / "manifest.json",
        )

    bad_manifest = tmp_path / "bad_manifest.json"
    bad_manifest.write_text("{json quebrado", encoding="utf-8")
    with pytest.raises(ManifestCorruptedError):
        ensure_sp_raw_files(
            raw_root=tmp_path / "raw",
            manifest_path=bad_manifest,
        )


def test_load_municipios_validates_boundary_schema(tmp_path: Path) -> None:
    municipios = load_municipios_from_files(SAMPLE_MALHA, SAMPLE_MUNICIPIOS)
    assert [m.cd_mun for m in municipios] == ["3500105", "3500204", "3500303", "3500402"]
    assert municipios[0].nome == "Adamantina"

    bad_mun = tmp_path / "bad_mun.json"
    bad_mun.write_text(json.dumps([{"id": "123", "nome": "Curto"}]), encoding="utf-8")
    with pytest.raises(ValueError, match="Código IBGE"):
        load_municipios_from_files(SAMPLE_MALHA, bad_mun)
