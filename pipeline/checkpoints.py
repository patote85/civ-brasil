from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pipeline.sources._common import atomic_write_bytes


def write_stage_checkpoint(output_path: Path, stages: dict[str, Any]) -> None:
    payload = json.dumps(stages, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    atomic_write_bytes(output_path, payload.encode("utf-8"))
