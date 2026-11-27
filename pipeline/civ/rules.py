from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

import yaml

LensKind = Literal["sum", "rate"]
LensScale = Literal["quantile", "linear"]

_REQUIRED_FIELDS = (
    "id",
    "civ_name",
    "br_name",
    "source_id",
    "source_label",
    "ano_ref",
    "column",
    "kind",
    "unit",
    "scale",
    "palette",
    "note",
)


class CivRulesError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class LensRule:
    id: str
    civ_name: str
    br_name: str
    source_id: str
    source_label: str
    ano_ref: int
    column: str
    kind: LensKind
    unit: str
    scale: LensScale
    palette: str
    note: str


def load_civ_rules(path: Path) -> list[LensRule]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise CivRulesError(f"civ_rules.yaml deve ser um objeto YAML: {path}")
    raw_lenses = raw.get("lenses")
    if not isinstance(raw_lenses, list) or not raw_lenses:
        raise CivRulesError(f"Campo 'lenses' ausente ou vazio em {path}")

    seen_ids: set[str] = set()
    rules: list[LensRule] = []
    for idx, entry in enumerate(raw_lenses):
        if not isinstance(entry, dict):
            raise CivRulesError(f"Lente #{idx} inválida em {path}")
        missing = [
            field for field in _REQUIRED_FIELDS if field not in entry or entry[field] is None
        ]
        if missing:
            raise CivRulesError(f"Lente #{idx} sem campos obrigatórios: {missing}")

        lens_id = str(entry["id"]).strip()
        if not lens_id or lens_id in seen_ids:
            raise CivRulesError(f"ID de lente inválido ou duplicado: {lens_id!r}")
        seen_ids.add(lens_id)

        kind_raw = str(entry["kind"]).strip()
        if kind_raw not in {"sum", "rate"}:
            raise CivRulesError(f"kind inválido na lente {lens_id}: {kind_raw!r}")

        scale_raw = str(entry["scale"]).strip()
        if scale_raw not in {"quantile", "linear"}:
            raise CivRulesError(f"scale inválido na lente {lens_id}: {scale_raw!r}")

        ano_raw = entry["ano_ref"]
        if not isinstance(ano_raw, int) or ano_raw < 1990 or ano_raw > 2100:
            raise CivRulesError(f"ano_ref inválido na lente {lens_id}: {ano_raw!r}")

        text_fields = (
            "civ_name",
            "br_name",
            "source_id",
            "source_label",
            "column",
            "unit",
            "palette",
            "note",
        )
        for text_field in text_fields:
            if not isinstance(entry[text_field], str) or not entry[text_field].strip():
                raise CivRulesError(f"Campo {text_field!r} vazio na lente {lens_id}")

        rules.append(
            LensRule(
                id=lens_id,
                civ_name=entry["civ_name"].strip(),
                br_name=entry["br_name"].strip(),
                source_id=entry["source_id"].strip(),
                source_label=entry["source_label"].strip(),
                ano_ref=ano_raw,
                column=entry["column"].strip(),
                kind=cast(LensKind, kind_raw),
                unit=entry["unit"].strip(),
                scale=cast(LensScale, scale_raw),
                palette=entry["palette"].strip(),
                note=entry["note"].strip(),
            )
        )
    return rules
