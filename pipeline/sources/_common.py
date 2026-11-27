from __future__ import annotations

import ftplib
import hashlib
import json
import os
import ssl
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pipeline.types import CdMun

DEFAULT_RAW_ROOT = Path("data/raw")
MANIFEST_PATH = Path("data/manifest.json")
RNP_INTERMEDIATE_CERT_URL = "https://secure.globalsign.com/cacert/rnpicpedugr46ovtlsca2025.crt"
RNP_INTERMEDIATE_CERT_SHA256 = "e10747d4da7bab09cba9952f019d3534cb9fba070bf13d8791b1699cd2ff59dd"

Fetcher = Callable[[str], bytes]
StreamDownloader = Callable[[str, Path], None]


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
        os.chmod(tmp_path, 0o644)
        os.replace(tmp_path, path)
    except BaseException:
        if tmp_path.exists():
            tmp_path.unlink()
        raise


def default_fetcher(url: str) -> bytes:
    last_exc: Exception | None = None
    for attempt in range(3):
        request = urllib.request.Request(url, headers={"User-Agent": "civ-brasil/0.3"})
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                status = getattr(response, "status", 200)
                if status != 200:
                    raise FetchError(f"HTTP {status} ao buscar {url}")
                payload = bytes(response.read())
                if not payload:
                    raise FetchError(f"Resposta vazia ao buscar {url}")
                return payload
        except (urllib.error.URLError, OSError) as exc:
            last_exc = exc
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
    raise FetchError(f"Falha ao buscar {url}: {last_exc}") from last_exc


def build_inep_ssl_context(raw_root: Path | None = None) -> ssl.SSLContext:
    resolved_root = raw_root if raw_root is not None else get_raw_root()
    cert_path = resolved_root / "_certs" / "rnpicpedugr46ovtlsca2025.crt"
    if not cert_path.is_file():
        der = default_fetcher(RNP_INTERMEDIATE_CERT_URL)
        digest = sha256_bytes(der)
        if digest != RNP_INTERMEDIATE_CERT_SHA256:
            raise IntegrityError(
                f"SHA-256 inesperado para certificado RNP: {digest} != "
                f"{RNP_INTERMEDIATE_CERT_SHA256}"
            )
        atomic_write_bytes(cert_path, der)
    der_bytes = cert_path.read_bytes()
    cached_digest = sha256_bytes(der_bytes)
    if cached_digest != RNP_INTERMEDIATE_CERT_SHA256:
        raise IntegrityError(
            f"SHA-256 inválido no cache do certificado RNP: {cached_digest} != "
            f"{RNP_INTERMEDIATE_CERT_SHA256}"
        )
    pem = ssl.DER_cert_to_PEM_cert(der_bytes)
    ctx = ssl.create_default_context()
    ctx.load_verify_locations(cadata=pem)
    return ctx


def make_http_stream_downloader(
    ssl_context: ssl.SSLContext | None = None,
    timeout: int = 300,
) -> StreamDownloader:
    def _download(url: str, dest: Path) -> None:
        last_exc: Exception | None = None
        for attempt in range(3):
            request = urllib.request.Request(url, headers={"User-Agent": "civ-brasil/0.3"})
            try:
                with (
                    urllib.request.urlopen(request, timeout=timeout, context=ssl_context) as resp,
                    dest.open("wb") as out,
                ):
                    status = getattr(resp, "status", 200)
                    if status != 200:
                        raise FetchError(f"HTTP {status} ao baixar {url}")
                    total = 0
                    while True:
                        chunk = resp.read(262144)
                        if not chunk:
                            break
                        out.write(chunk)
                        total += len(chunk)
                    out.flush()
                    os.fsync(out.fileno())
                if total == 0:
                    raise FetchError(f"Arquivo vazio baixado de {url}")
                return
            except (urllib.error.URLError, OSError) as exc:
                last_exc = exc
                if attempt < 2:
                    time.sleep(2.0 * (attempt + 1))
        raise FetchError(f"Falha ao baixar {url}: {last_exc}") from last_exc

    return _download


def ftp_stream_downloader(url: str, dest: Path) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme.lower() != "ftp" or not parsed.hostname:
        raise FetchError(f"URL FTP inválida: {url}")
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            ftp = ftplib.FTP(parsed.hostname, timeout=180, encoding="latin-1")
            try:
                ftp.login()
                remote_path = urllib.parse.unquote(parsed.path)
                total = 0
                with dest.open("wb") as out:
                    def _write(chunk: bytes) -> None:
                        nonlocal total
                        out.write(chunk)
                        total += len(chunk)

                    ftp.retrbinary(f"RETR {remote_path}", _write, blocksize=262144)
                    out.flush()
                    os.fsync(out.fileno())
                if total == 0:
                    raise FetchError(f"Arquivo FTP vazio em {url}")
                return
            finally:
                try:
                    ftp.quit()
                except Exception:
                    ftp.close()
        except Exception as exc:
            last_exc = exc
            if attempt < 2:
                time.sleep(2.0 * (attempt + 1))
    raise FetchError(f"Falha FTP ao baixar {url}: {last_exc}") from last_exc


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


def upsert_manifest_entry(
    manifest_path: Path | None,
    sync: ArtifactSync,
    metadata: dict[str, Any],
) -> None:
    resolved_manifest = manifest_path if manifest_path is not None else MANIFEST_PATH
    sources = read_manifest(resolved_manifest)
    entry: dict[str, Any] = {
        "url": sync.url,
        "sha256": sync.sha256,
        "fetched_at": sync.fetched_at,
        **metadata,
    }
    if sources.get(sync.source_key) != entry:
        sources[sync.source_key] = entry
        write_manifest(resolved_manifest, sources)


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


def ensure_raw_artifact_stream(
    source_id: str,
    filename: str,
    url: str,
    downloader: StreamDownloader,
    raw_root: Path | None = None,
    manifest_path: Path | None = None,
) -> ArtifactSync:
    resolved_raw_root = raw_root if raw_root is not None else get_raw_root()
    source_dir = resolved_raw_root / source_id
    source_dir.mkdir(parents=True, exist_ok=True)
    resolved_manifest = manifest_path if manifest_path is not None else MANIFEST_PATH

    existing_sources = read_manifest(resolved_manifest)
    checksums = read_sha256sums(source_dir)
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

    fd, tmp_name = tempfile.mkstemp(dir=source_dir, prefix=f".{filename}.", suffix=".tmp")
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        downloader(url, tmp_path)
        actual_sha = sha256_file(tmp_path)
        if expected_sums_sha is not None and actual_sha != expected_sums_sha:
            raise IntegrityError(
                f"SHA-256 baixado diverge de SHA256SUMS para {filename}: "
                f"esperado {expected_sums_sha}, obtido {actual_sha}"
            )
        os.chmod(tmp_path, 0o644)
        os.replace(tmp_path, target)
    except BaseException:
        if tmp_path.exists():
            tmp_path.unlink()
        raise

    fetched_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    return ArtifactSync(
        path=target,
        source_key=source_key,
        url=url,
        sha256=actual_sha,
        fetched_at=fetched_at,
        downloaded=True,
    )


def build_mun_prefix6_map(valid_cd_muns: set[CdMun]) -> dict[str, CdMun]:
    mapping: dict[str, CdMun] = {}
    for cd in valid_cd_muns:
        s = str(cd)
        mapping[s] = cd
        if len(s) == 7:
            mapping[s[:6]] = cd
    return mapping


def normalize_pt_name(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.strip().lower())
    without_accents = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return " ".join(without_accents.split())

