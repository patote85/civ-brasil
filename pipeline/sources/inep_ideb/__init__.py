from __future__ import annotations

from pipeline.sources.inep_ideb.loader import (
    INEP_IDEB_YEAR,
    IdebRecord,
    ensure_inep_ideb_raw_files,
    load_inep_ideb_from_files,
)

__all__ = [
    "INEP_IDEB_YEAR",
    "IdebRecord",
    "ensure_inep_ideb_raw_files",
    "load_inep_ideb_from_files",
]
