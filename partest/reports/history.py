"""Append dated coverage.json snapshots (LIB-COV-HIST)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union


def append_snapshot(
    payload: dict[str, Any],
    directory: Union[str, Path],
    *,
    when: Optional[datetime] = None,
) -> Path:
    """Write ``<dir>/<utc-stamp>.json``. Does not mutate ``payload``."""
    stamp = (when or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(directory)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{stamp}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path.resolve()


def latest_snapshot(directory: Union[str, Path]) -> Optional[Path]:
    out_dir = Path(directory)
    if not out_dir.is_dir():
        return None
    files = sorted(out_dir.glob("*.json"))
    return files[-1] if files else None
