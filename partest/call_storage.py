"""Runtime storage for API call coverage.

Structures:
- call_count[(method, endpoint, description)] -> int
- call_type[(method, endpoint, description)] -> list[str]  (canonical TC types)
- call_meta[(method, endpoint, description)] -> list[dict]  (optional details)

Thread-safe within a process, but **per process**. Under pytest-xdist every worker
counts only its own calls, and the test that renders the report runs on one of them —
so an unmerged parallel run reports one worker's slice as if it were the whole suite.
A measured example: ``-n 3`` on a green suite produced 25.7% average and 58 endpoints
marked unseen.

The fix has two halves, wired up by the pytest plugin:

* each worker writes its counters to a shard file when its session ends
  (:func:`write_shard`);
* the controller merges every shard into its own process before the report is
  produced (:func:`merge_shards`).

The specification for this proposed appending one JSON line per call. Writing one
shard per worker at session end reaches the same merge contract without per-call
locking or torn lines on Windows; the cost is that a worker killed mid-run
contributes nothing, which is a broken run anyway.
"""

from __future__ import annotations

import json
import os
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

#: How this run was produced. Read by the report so the numbers can be labelled
#: honestly: ``merged=False`` with ``workers > 1`` means they are one worker's slice.
run_info: Dict[str, Any] = {"workers": 1, "merged": False}

SHARD_DIR_ENV = "PARTEST_CALL_STORAGE_DIR"
DEFAULT_SHARD_DIR = ".partest/call_storage"


def reset_storage() -> None:
    """Clear all coverage counters (session fixture)."""
    with _lock:
        call_count.clear()
        call_type.clear()
        call_meta.clear()
        endpoint_subtype.clear()
        run_info.update({"workers": 1, "merged": False})


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


def update_last_meta(key: Key, patch: Dict[str, Any]) -> None:
    """Amend the most recent meta entry for *key* (used for timing after the call)."""
    with _lock:
        entries = call_meta.get(key)
        if entries:
            entries[-1].update(patch)


# --- xdist sharding -------------------------------------------------------


def worker_id() -> str:
    """``gw0``/``gw1``/… under xdist, ``master`` otherwise."""
    return os.getenv("PYTEST_XDIST_WORKER") or "master"


def shard_dir(base: Optional[Union[str, Path]] = None) -> Path:
    """Directory holding per-worker shards.

    Override with ``PARTEST_CALL_STORAGE_DIR`` when the default is not writable or
    when several suites share a checkout.
    """
    if base is not None:
        return Path(base)
    return Path(os.getenv(SHARD_DIR_ENV) or DEFAULT_SHARD_DIR)


def write_shard(base: Optional[Union[str, Path]] = None) -> Path:
    """Write this process's counters as ``<worker>.json``.

    Written atomically: a temporary file plus a replace, so a controller reading the
    directory concurrently never sees a half-written shard.
    """
    directory = shard_dir(base)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{worker_id()}.json"
    tmp = directory / f".{worker_id()}.json.tmp"
    tmp.write_text(
        json.dumps(dump_storage(), ensure_ascii=False), encoding="utf-8"
    )
    os.replace(tmp, target)
    return target


def read_shards(base: Optional[Union[str, Path]] = None) -> List[Path]:
    directory = shard_dir(base)
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.glob("*.json") if not p.name.startswith("."))


def clear_shards(base: Optional[Union[str, Path]] = None) -> None:
    for path in read_shards(base):
        try:
            path.unlink()
        except OSError:
            pass


def merge_shards(base: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
    """Merge every shard into this process and record how many workers contributed.

    Counts are summed and executed types are unioned per endpoint, so a later
    ``request_default`` never overwrites an earlier ``request_elements``.
    """
    # Never re-load our own dump: this process already holds those calls, and
    # loading them again would double every count.
    own = f"{worker_id()}.json"
    paths = [p for p in read_shards(base) if p.name != own]
    for path in paths:
        try:
            load_storage_file(path, merge=True)
        except (OSError, ValueError):
            # A shard that cannot be read must not take the whole report down;
            # the worker count below still reflects that something is missing.
            continue
    with _lock:
        run_info["workers"] = max(len(paths), 1)
        run_info["merged"] = bool(paths)
    return dump_storage()


def _key_str(key: Key) -> str:
    return "\t".join(key)


def _key_parse(s: str) -> Key:
    parts = s.split("\t")
    if len(parts) != 3:
        raise ValueError(f"invalid storage key {s!r}")
    return parts[0], parts[1], parts[2]
