"""Runtime storage for API call coverage.

Structures:
- call_count[(method, endpoint, description)] -> int
- call_type[(method, endpoint, description)] -> list[str]  (canonical TC types)
- call_meta[(method, endpoint, description)] -> list[dict]  (optional details)

Thread-safe within a process. For pytest-xdist each worker has its own process —
use :func:`dump_storage` / :func:`merge_storage` in a session-finish hook to
combine coverage (L5.6).
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

Key = Tuple[str, str, str]

_lock = threading.RLock()

call_count: Dict[Key, int] = {}
call_type: Dict[Key, List[str]] = {}
call_meta: Dict[Key, List[Dict[str, Any]]] = {}
# Cached subtype per (method, path) after classification
endpoint_subtype: Dict[Tuple[str, str], str] = {}


def reset_storage() -> None:
    """Clear all coverage counters (session fixture)."""
    with _lock:
        call_count.clear()
        call_type.clear()
        call_meta.clear()
        endpoint_subtype.clear()


def record_call(
    key: Key,
    test_type: str,
    *,
    meta: Optional[Dict[str, Any]] = None,
    subtype: Optional[str] = None,
) -> None:
    """Increment call counter and append test type."""
    with _lock:
        call_count[key] = call_count.get(key, 0) + 1
        call_type[key] = call_type.get(key, []) + [test_type]
        if meta:
            call_meta.setdefault(key, []).append(meta)
        if subtype:
            endpoint_subtype[(key[0], key[1])] = subtype


def dump_storage() -> Dict[str, Any]:
    """Serialize counters for cross-process merge (xdist workers)."""
    with _lock:
        return {
            "call_count": { _key_str(k): v for k, v in call_count.items() },
            "call_type": { _key_str(k): list(v) for k, v in call_type.items() },
            "call_meta": { _key_str(k): list(v) for k, v in call_meta.items() },
            "endpoint_subtype": {
                f"{m}\t{p}": s for (m, p), s in endpoint_subtype.items()
            },
        }


def load_storage(data: Dict[str, Any], *, merge: bool = True) -> None:
    """Load dump into process storage (optionally merging)."""
    if not merge:
        reset_storage()
    with _lock:
        for ks, n in (data.get("call_count") or {}).items():
            key = _key_parse(ks)
            call_count[key] = call_count.get(key, 0) + int(n)
        for ks, types in (data.get("call_type") or {}).items():
            key = _key_parse(ks)
            call_type.setdefault(key, []).extend(list(types))
        for ks, metas in (data.get("call_meta") or {}).items():
            key = _key_parse(ks)
            call_meta.setdefault(key, []).extend(list(metas))
        for ks, sub in (data.get("endpoint_subtype") or {}).items():
            if "\t" in ks:
                m, p = ks.split("\t", 1)
                endpoint_subtype[(m, p)] = sub


def dump_storage_file(path: Union[str, Path]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dump_storage(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_storage_file(path: Union[str, Path], *, merge: bool = True) -> None:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    load_storage(data, merge=merge)


def merge_storage_files(paths: Iterable[Union[str, Path]]) -> Dict[str, Any]:
    """Merge several worker dumps into current process storage; return dump."""
    for p in paths:
        load_storage_file(p, merge=True)
    return dump_storage()


def _key_str(key: Key) -> str:
    return "\t".join(key)


def _key_parse(s: str) -> Key:
    parts = s.split("\t")
    if len(parts) != 3:
        raise ValueError(f"invalid storage key {s!r}")
    return parts[0], parts[1], parts[2]
