from __future__ import annotations

from pipeline.sources.inep_escolar.loader import (
    INEP_ESCOLAR_YEAR,
    EscolarRecord,
    ensure_inep_escolar_raw_file,
    load_inep_escolar_from_file,
)

__all__ = [
    "INEP_ESCOLAR_YEAR",
    "EscolarRecord",
    "ensure_inep_escolar_raw_file",
    "load_inep_escolar_from_file",
]
