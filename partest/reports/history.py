"""Dated coverage.json snapshots, pruned to the last few runs.

A coverage directory that grows without bound is a directory nobody reads. Two runs
are enough for the only question a history answers day to day: did this run get
better or worse than the previous one.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union


DEFAULT_KEEP = 2


def append_snapshot(
    payload: dict[str, Any],
    directory: Union[str, Path],
    *,
    when: Optional[datetime] = None,
    keep: Optional[int] = DEFAULT_KEEP,
) -> Path:
    """Write ``<dir>/<utc-stamp>.json`` and prune older runs. Does not mutate ``payload``.

    ``keep=None`` retains everything (the pre-1.7 behaviour).
    """
    stamp = (when or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(directory)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{stamp}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if keep is not None:
        prune_snapshots(out_dir, keep=keep)
    return path.resolve()


def list_snapshots(directory: Union[str, Path]) -> list:
    out_dir = Path(directory)
    if not out_dir.is_dir():
        return []
    return sorted(out_dir.glob("*.json"))


def prune_snapshots(directory: Union[str, Path], *, keep: int = DEFAULT_KEEP) -> int:
    """Delete all but the newest ``keep`` snapshots; returns how many were removed."""
    if keep < 0:
        return 0
    files = list_snapshots(directory)
    removed = 0
    for path in files[: max(len(files) - keep, 0)]:
        try:
            path.unlink()
            removed += 1
        except OSError:
            pass
    return removed


def previous_snapshot(directory: Union[str, Path], *, before: Optional[Path] = None) -> Optional[dict]:
    """Payload of the run before the newest one, for run-over-run deltas."""
    files = list_snapshots(directory)
    if before is not None:
        files = [f for f in files if f.name != Path(before).name]
    if len(files) < 1:
        return None
    try:
        return json.loads(files[-1].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def latest_snapshot(directory: Union[str, Path]) -> Optional[Path]:
    out_dir = Path(directory)
    if not out_dir.is_dir():
        return None
    files = sorted(out_dir.glob("*.json"))
    return files[-1] if files else None
