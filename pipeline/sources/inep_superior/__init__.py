from __future__ import annotations

from pipeline.sources.inep_superior.loader import (
    INEP_SUPERIOR_YEAR,
    SuperiorRecord,
    ensure_inep_superior_raw_file,
    load_inep_superior_from_file,
)

__all__ = [
    "INEP_SUPERIOR_YEAR",
    "SuperiorRecord",
    "ensure_inep_superior_raw_file",
    "load_inep_superior_from_file",
]
