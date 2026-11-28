from __future__ import annotations

import json
from pathlib import Path

from pipeline.civ.almanac import build_sources_catalog


def test_almanac_catalog_covers_all_manifest_sources_with_license() -> None:
    manifest_path = Path("data/manifest.json")
    rules_path = Path("pipeline/civ/civ_rules.yaml")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_keys = set(manifest["sources"].keys())

    catalog = build_sources_catalog(manifest_path=manifest_path, rules_path=rules_path, uf="SP")
    catalog_keys = {entry["key"] for entry in catalog["sources"]}
    assert catalog_keys == manifest_keys

    for entry in catalog["sources"]:
        assert entry["orgao"], f"Fonte {entry['key']} sem orgao"
        assert entry["licenca"], f"Fonte {entry['key']} sem licenca"
        assert entry["url"].startswith(("http://", "https://", "ftp://")), (
            f"URL inválida em {entry['key']}"
        )
        assert len(entry["sha256"]) == 64

    assert len(catalog["lenses"]) >= 11


def test_vercel_json_has_strict_csp_and_security_headers() -> None:
    vercel_cfg = json.loads(Path("vercel.json").read_text(encoding="utf-8"))
    headers_rules = vercel_cfg.get("headers", [])
    assert headers_rules, "vercel.json deve definir headers de segurança"

    all_headers: dict[str, str] = {}
    has_immutable_assets = False
    for rule in headers_rules:
        src = str(rule.get("source", ""))
        for h in rule.get("headers", []):
            key = str(h.get("key", "")).lower()
            val = str(h.get("value", ""))
            all_headers[key] = val
            if "/assets/" in src and key == "cache-control" and "immutable" in val:
                has_immutable_assets = True

    csp = all_headers.get("content-security-policy", "")
    assert "default-src 'self'" in csp
    assert "object-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp
    assert all_headers.get("x-content-type-options") == "nosniff"
    assert "referrer-policy" in all_headers
    assert has_immutable_assets
    assert Path("web/public/404.html").is_file()
