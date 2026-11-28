from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pipeline.civ.rules import load_civ_rules
from pipeline.sources._common import atomic_write_bytes
from pipeline.types import UfCode

IBGE_DEFAULT_ORGAO = "IBGE"
IBGE_DEFAULT_LICENCA = "Dados Abertos IBGE (CC BY 4.0)"


def build_sources_catalog(
    manifest_path: Path,
    rules_path: Path,
    uf: UfCode,
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw_sources = manifest.get("sources", {})
    if not isinstance(raw_sources, dict):
        raise ValueError(f"Manifesto inválido em {manifest_path}")

    sources_out: list[dict[str, Any]] = []
    for key in sorted(raw_sources.keys()):
        entry = raw_sources[key]
        if not isinstance(entry, dict):
            continue
        orgao = str(entry.get("orgao") or "").strip()
        licenca = str(entry.get("licenca") or "").strip()
        if not orgao and key.startswith("ibge_"):
            orgao = IBGE_DEFAULT_ORGAO
        if not licenca and key.startswith("ibge_"):
            licenca = IBGE_DEFAULT_LICENCA
        url = str(entry.get("url") or "").strip()
        sha256 = str(entry.get("sha256") or "").strip()
        ano_ref = entry.get("ano_ref")
        cobertura = str(entry.get("cobertura") or ("SP" if "/sp_" in key else "BR"))
        fetched_at = str(entry.get("fetched_at") or "")
        sources_out.append(
            {
                "key": key,
                "orgao": orgao,
                "licenca": licenca,
                "url": url,
                "ano_ref": int(ano_ref) if isinstance(ano_ref, (int, float)) else None,
                "cobertura": cobertura,
                "fetched_at": fetched_at,
                "sha256": sha256,
            }
        )

    rules = load_civ_rules(rules_path)
    lenses_out = [
        {
            "id": r.id,
            "civ_name": r.civ_name,
            "br_name": r.br_name,
            "source_id": r.source_id,
            "source_label": r.source_label,
            "ano_ref": r.ano_ref,
            "unit": r.unit,
            "note": r.note,
        }
        for r in rules
    ]

    return {
        "uf": uf,
        "source_count": len(sources_out),
        "lens_count": len(lenses_out),
        "sources": sources_out,
        "lenses": lenses_out,
    }


def write_sources_catalog(
    manifest_path: Path,
    rules_path: Path,
    uf: UfCode,
    output_path: Path,
) -> int:
    catalog = build_sources_catalog(manifest_path=manifest_path, rules_path=rules_path, uf=uf)
    payload = json.dumps(catalog, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    atomic_write_bytes(output_path, payload)
    return len(payload)
