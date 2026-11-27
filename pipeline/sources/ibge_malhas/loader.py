from __future__ import annotations

import hashlib
import json
import os
import tempfile
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from shapely import make_valid
from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.geometry.base import BaseGeometry

SP_MALHA_URL = (
    "https://servicodados.ibge.gov.br/api/v3/malhas/estados/35"
    "?intrarregiao=municipio&formato=application/vnd.geo+json&qualidade=intermediaria"
)
SP_MUNICIPIOS_URL = "https://servicodados.ibge.gov.br/api/v1/localidades/estados/35/municipios"

MALHA_FILENAME = "sp_malha_municipios.geojson"
MUNICIPIOS_FILENAME = "sp_municipios.json"
DEFAULT_RAW_ROOT = Path("/workspace/civbr-dados/raw")

Fetcher = Callable[[str], bytes]


class FetchError(RuntimeError):
    pass


class IntegrityError(ValueError):
    pass


class ManifestCorruptedError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Municipio:
    cd_mun: str
    nome: str
    geometry: BaseGeometry


@dataclass(frozen=True, slots=True)
class SyncResult:
    malha_path: Path
    municipios_path: Path
    downloaded_files: tuple[str, ...]
    feature_count: int


def get_raw_root() -> Path:
    return Path(os.environ.get("CIVBR_RAW", str(DEFAULT_RAW_ROOT)))


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        if tmp_path.exists():
            tmp_path.unlink()
        raise


def _default_fetcher(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "civ-brasil/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            status = getattr(response, "status", 200)
            if status != 200:
                raise FetchError(f"HTTP {status} ao buscar {url}")
            payload = bytes(response.read())
    except (urllib.error.URLError, OSError) as exc:
        raise FetchError(f"Falha ao buscar {url}: {exc}") from exc
    if not payload:
        raise FetchError(f"Resposta vazia ao buscar {url}")
    return payload


def _read_sha256sums(ibge_dir: Path) -> dict[str, str]:
    sums_path = ibge_dir / "SHA256SUMS"
    if not sums_path.is_file():
        return {}
    result: dict[str, str] = {}
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split()
        if len(parts) < 2:
            raise IntegrityError(f"Linha inválida em {sums_path}: {line!r}")
        result[parts[1].lstrip("*")] = parts[0].lower()
    return result


def _read_manifest(manifest_path: Path) -> dict[str, dict[str, Any]]:
    if not manifest_path.exists():
        return {}
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ManifestCorruptedError(f"Manifesto JSON inválido em {manifest_path}") from exc
    if not isinstance(raw, dict):
        raise ManifestCorruptedError(f"Manifesto deve ser um objeto JSON em {manifest_path}")
    sources = raw.get("sources")
    if not isinstance(sources, dict):
        raise ManifestCorruptedError(f"Campo 'sources' inválido em {manifest_path}")
    validated: dict[str, dict[str, Any]] = {}
    for key, value in sources.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            raise ManifestCorruptedError(f"Entrada inválida no manifesto: {key!r}")
        validated[key] = dict(value)
    return validated


def _validate_cd_mun(raw_code: object) -> str:
    code = str(raw_code).strip()
    if len(code) != 7 or not code.isdigit():
        raise ValueError(f"Código IBGE de município inválido: {raw_code!r}")
    return code


def _normalize_geometry(raw_geometry: object) -> BaseGeometry:
    if not isinstance(raw_geometry, dict):
        raise ValueError("Geometria GeoJSON ausente ou inválida")
    geom = shape(raw_geometry)
    if not geom.is_valid:
        geom = make_valid(geom)
    if geom.is_empty or not isinstance(geom, (Polygon, MultiPolygon)):
        raise ValueError(f"Geometria municipal deve ser Polygon ou MultiPolygon: {geom.geom_type}")
    return geom


def load_municipios_from_files(
    malha_path: Path,
    municipios_path: Path,
) -> list[Municipio]:
    raw_municipios = json.loads(municipios_path.read_text(encoding="utf-8"))
    if not isinstance(raw_municipios, list):
        raise ValueError("Lista de municípios deve ser um array JSON")

    nomes_por_codigo: dict[str, str] = {}
    for entry in raw_municipios:
        if not isinstance(entry, dict):
            raise ValueError("Registro de município inválido")
        cd_mun = _validate_cd_mun(entry.get("id"))
        nome = entry.get("nome")
        if not isinstance(nome, str) or not nome.strip():
            raise ValueError(f"Nome inválido para município {cd_mun}")
        if cd_mun in nomes_por_codigo:
            raise ValueError(f"Código de município duplicado na lista: {cd_mun}")
        nomes_por_codigo[cd_mun] = nome.strip()

    raw_malha = json.loads(malha_path.read_text(encoding="utf-8"))
    if not isinstance(raw_malha, dict) or raw_malha.get("type") != "FeatureCollection":
        raise ValueError("Malha deve ser um GeoJSON FeatureCollection")
    features = raw_malha.get("features")
    if not isinstance(features, list):
        raise ValueError("Campo 'features' ausente ou inválido na malha")

    geoms_por_codigo: dict[str, BaseGeometry] = {}
    for feature in features:
        if not isinstance(feature, dict):
            raise ValueError("Feature GeoJSON inválida")
        props = feature.get("properties")
        if not isinstance(props, dict):
            raise ValueError("Propriedades ausentes em feature GeoJSON")
        cd_mun = _validate_cd_mun(props.get("codarea"))
        if cd_mun in geoms_por_codigo:
            raise ValueError(f"Código de município duplicado na malha: {cd_mun}")
        geoms_por_codigo[cd_mun] = _normalize_geometry(feature.get("geometry"))

    if set(nomes_por_codigo) != set(geoms_por_codigo):
        missing_in_malha = sorted(set(nomes_por_codigo) - set(geoms_por_codigo))
        missing_in_list = sorted(set(geoms_por_codigo) - set(nomes_por_codigo))
        raise ValueError(
            "Divergência entre lista e malha de municípios: "
            f"faltam na malha={missing_in_malha[:5]}, faltam na lista={missing_in_list[:5]}"
        )

    return [
        Municipio(cd_mun=cd_mun, nome=nomes_por_codigo[cd_mun], geometry=geoms_por_codigo[cd_mun])
        for cd_mun in sorted(nomes_por_codigo)
    ]


def ensure_sp_raw_files(
    raw_root: Path | None = None,
    manifest_path: Path | None = None,
    fetcher: Fetcher | None = None,
) -> SyncResult:
    resolved_raw_root = raw_root if raw_root is not None else get_raw_root()
    ibge_dir = resolved_raw_root / "ibge_malhas"
    ibge_dir.mkdir(parents=True, exist_ok=True)
    resolved_manifest = manifest_path if manifest_path is not None else Path("data/manifest.json")

    existing_sources = _read_manifest(resolved_manifest)
    checksums = _read_sha256sums(ibge_dir)
    active_fetcher = fetcher if fetcher is not None else _default_fetcher

    artifacts = (
        (MALHA_FILENAME, SP_MALHA_URL),
        (MUNICIPIOS_FILENAME, SP_MUNICIPIOS_URL),
    )

    downloaded: list[str] = []
    file_hashes: dict[str, str] = {}
    fetched_timestamps: dict[str, str] = {}

    for filename, url in artifacts:
        target = ibge_dir / filename
        source_key = f"ibge_malhas/{filename}"
        manifest_entry = existing_sources.get(source_key)
        expected_manifest_sha = (
            manifest_entry.get("sha256")
            if isinstance(manifest_entry, dict) and isinstance(manifest_entry.get("sha256"), str)
            else None
        )
        expected_sums_sha = checksums.get(filename)

        if target.is_file():
            actual_sha = _sha256_file(target)
            if expected_manifest_sha is not None and actual_sha != expected_manifest_sha:
                raise IntegrityError(
                    f"SHA-256 divergente do manifesto para {target}: "
                    f"esperado {expected_manifest_sha}, obtido {actual_sha}"
                )
            if expected_sums_sha is not None and actual_sha != expected_sums_sha:
                raise IntegrityError(
                    f"SHA-256 divergente de SHA256SUMS para {target}: "
                    f"esperado {expected_sums_sha}, obtido {actual_sha}"
                )
            file_hashes[source_key] = actual_sha
            if (
                isinstance(manifest_entry, dict)
                and expected_manifest_sha == actual_sha
                and isinstance(manifest_entry.get("fetched_at"), str)
            ):
                fetched_timestamps[source_key] = manifest_entry["fetched_at"]
            else:
                fetched_timestamps[source_key] = (
                    datetime.now(UTC).isoformat().replace("+00:00", "Z")
                )
        else:
            payload = active_fetcher(url)
            if not payload:
                raise FetchError(f"Resposta vazia ao buscar {url}")
            actual_sha = _sha256_bytes(payload)
            if expected_sums_sha is not None and actual_sha != expected_sums_sha:
                raise IntegrityError(
                    f"SHA-256 baixado diverge de SHA256SUMS para {filename}: "
                    f"esperado {expected_sums_sha}, obtido {actual_sha}"
                )
            _atomic_write_bytes(target, payload)
            downloaded.append(filename)
            file_hashes[source_key] = actual_sha
            fetched_timestamps[source_key] = datetime.now(UTC).isoformat().replace("+00:00", "Z")

    malha_path = ibge_dir / MALHA_FILENAME
    municipios_path = ibge_dir / MUNICIPIOS_FILENAME
    municipios = load_municipios_from_files(malha_path, municipios_path)
    feature_count = len(municipios)

    updated_sources = dict(existing_sources)
    for filename, url in artifacts:
        source_key = f"ibge_malhas/{filename}"
        updated_sources[source_key] = {
            "url": url,
            "fetched_at": fetched_timestamps[source_key],
            "sha256": file_hashes[source_key],
            "feature_count": feature_count,
        }

    manifest_payload = json.dumps(
        {"sources": updated_sources},
        indent=2,
        ensure_ascii=False,
        sort_keys=True,
    )
    _atomic_write_bytes(resolved_manifest, (manifest_payload + "\n").encode("utf-8"))

    return SyncResult(
        malha_path=malha_path,
        municipios_path=municipios_path,
        downloaded_files=tuple(downloaded),
        feature_count=feature_count,
    )
