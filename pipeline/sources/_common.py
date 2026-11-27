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

DEFAULT_RAW_ROOT = Path("data/raw")
MANIFEST_PATH = Path("data/manifest.json")

Fetcher = Callable[[str], bytes]


class FetchError(RuntimeError):
    pass


class IntegrityError(ValueError):
    pass


class ManifestCorruptedError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ArtifactSync:
    path: Path
    source_key: str
    url: str
    sha256: str
    fetched_at: str
    downloaded: bool


def get_raw_root() -> Path:
    configured = os.environ.get("CIVBR_RAW", "").strip()
    return Path(configured) if configured else DEFAULT_RAW_ROOT


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_bytes(path: Path, data: bytes) -> None:
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


def default_fetcher(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "civ-brasil/0.2"})
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            status = getattr(response, "status", 200)
            if status != 200:
                raise FetchError(f"HTTP {status} ao buscar {url}")
            payload = bytes(response.read())
    except (urllib.error.URLError, OSError) as exc:
        raise FetchError(f"Falha ao buscar {url}: {exc}") from exc
    if not payload:
        raise FetchError(f"Resposta vazia ao buscar {url}")
    return payload


def read_sha256sums(source_dir: Path) -> dict[str, str]:
    sums_path = source_dir / "SHA256SUMS"
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


def read_manifest(manifest_path: Path) -> dict[str, dict[str, Any]]:
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


def write_manifest(manifest_path: Path, sources: dict[str, dict[str, Any]]) -> None:
    payload = json.dumps(
        {"sources": sources},
        indent=2,
        ensure_ascii=False,
        sort_keys=True,
    )
    atomic_write_bytes(manifest_path, (payload + "\n").encode("utf-8"))


def ensure_raw_artifact(
    source_id: str,
    filename: str,
    url: str,
    raw_root: Path | None = None,
    manifest_path: Path | None = None,
    fetcher: Fetcher | None = None,
) -> ArtifactSync:
    resolved_raw_root = raw_root if raw_root is not None else get_raw_root()
    source_dir = resolved_raw_root / source_id
    source_dir.mkdir(parents=True, exist_ok=True)
    resolved_manifest = manifest_path if manifest_path is not None else MANIFEST_PATH

    existing_sources = read_manifest(resolved_manifest)
    checksums = read_sha256sums(source_dir)
    active_fetcher = fetcher if fetcher is not None else default_fetcher

    target = source_dir / filename
    source_key = f"{source_id}/{filename}"
    manifest_entry = existing_sources.get(source_key)
    expected_manifest_sha = (
        manifest_entry.get("sha256")
        if isinstance(manifest_entry, dict) and isinstance(manifest_entry.get("sha256"), str)
        else None
    )
    expected_sums_sha = checksums.get(filename)

    if target.is_file():
        actual_sha = sha256_file(target)
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
        if (
            isinstance(manifest_entry, dict)
            and expected_manifest_sha == actual_sha
            and isinstance(manifest_entry.get("fetched_at"), str)
        ):
            fetched_at = manifest_entry["fetched_at"]
        else:
            fetched_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        return ArtifactSync(
            path=target,
            source_key=source_key,
            url=url,
            sha256=actual_sha,
            fetched_at=fetched_at,
            downloaded=False,
        )

    payload = active_fetcher(url)
    if not payload:
        raise FetchError(f"Resposta vazia ao buscar {url}")
    actual_sha = sha256_bytes(payload)
    if expected_sums_sha is not None and actual_sha != expected_sums_sha:
        raise IntegrityError(
            f"SHA-256 baixado diverge de SHA256SUMS para {filename}: "
            f"esperado {expected_sums_sha}, obtido {actual_sha}"
        )
    atomic_write_bytes(target, payload)
    fetched_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    return ArtifactSync(
        path=target,
        source_key=source_key,
        url=url,
        sha256=actual_sha,
        fetched_at=fetched_at,
        downloaded=True,
    )
