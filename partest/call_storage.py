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
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple, Union
from urllib.parse import urlsplit

Key = Tuple[str, str, str]

_lock = threading.RLock()

call_count: Dict[Key, int] = {}
call_type: Dict[Key, List[str]] = {}
call_meta: Dict[Key, List[Dict[str, Any]]] = {}
# Cached subtype per (method, path) after classification
endpoint_subtype: Dict[Tuple[str, str], str] = {}

#: How this run was produced. Read by the report so the numbers can be labelled
#: honestly: ``merged=False`` with ``workers > 1`` means they are one worker's slice,
#: a non-empty ``selection`` means the run covered a chosen subset of the suite, and
#: ``tlsVerified=False`` means **at least one** connection in it went without checking a
#: certificate — not that every one did. The two readings are far apart: one auxiliary
#: host accepted unverified turns the flag off for a run in which the system under test
#: was checked throughout, and that is the ordinary case, not the exotic one. Which hosts
#: those were is in :data:`unverified_hosts`.
run_info: Dict[str, Any] = {
    "workers": 1,
    "merged": False,
    "selection": {},
    "tlsVerified": True,
}

#: Hosts this run reached with certificate verification off, and hosts whose TLS partest
#: did not decide and cannot read (an injected ``client=``). **Sets**, like
#: :data:`deselected_nodes` and for the same reason: a host is either in the run or not,
#: and two workers that both reached it must report it once.
#:
#: They exist because ``tlsVerified`` is one bit for a whole run and a single auxiliary
#: service switches it off for everything. A measured case: on one consumer a plugin signs
#: into an auxiliary service with a self-signed certificate during ``pytest_configure``, so
#: every run of that project — including runs that never touch the API — reported
#: ``tlsVerified: false``, and "the suite skipped verification entirely" became
#: indistinguishable from "one service host was accepted, the stand was verified".
unverified_hosts: Set[str] = set()
unknown_tls_hosts: Set[str] = set()

#: Ports that add nothing to a host name; anything else is part of what was reached,
#: because two services on one machine are two different certificates.
_DEFAULT_PORTS = {"http": 80, "https": 443, "ws": 80, "wss": 443}

#: Node ids this process saw deselected. A **set**, and the thing that crosses a shard:
#: under ``-n`` every worker collects the whole suite and deselects the same tests, so
#: summing worker counts would report the filter once per worker. Unioning ids reports it
#: once — and makes a repeated call on one process idempotent for free.
deselected_nodes: Set[str] = set()

SHARD_DIR_ENV = "PARTEST_CALL_STORAGE_DIR"
DEFAULT_SHARD_DIR = ".partest/call_storage"


def reset_storage() -> None:
    """Clear all coverage counters (session fixture)."""
    with _lock:
        call_count.clear()
        call_type.clear()
        call_meta.clear()
        endpoint_subtype.clear()
        # `selection` deliberately survives: it describes the pytest invocation, is known
        # at collection time — before the session fixture that calls this — and cannot be
        # recovered afterwards. Clearing it here would silently disarm the partial-run flag.
        # `tlsVerified` survives for the same reason: the clients are built before this,
        # and so are the hosts already recorded next to it — the measured case that put
        # them there happens during `pytest_configure`.
        run_info.update({"workers": 1, "merged": False})


def record_deselected(node_ids: Iterable[str]) -> None:
    """Remember node ids removed from this run and keep the reported count in step."""
    with _lock:
        deselected_nodes.update(str(n) for n in node_ids)
        if deselected_nodes:
            run_info.setdefault("selection", {})["deselected"] = len(deselected_nodes)


def host_of(url: Any) -> str:
    """``host`` or ``host:port`` of *url*; ``""`` when it names no host.

    Credentials are dropped, not merely unused: ``https://svc:token@stand/`` is a URL a
    consumer can build, and the run artifact is a file people attach to tickets. The port
    is kept unless it is the scheme's default — a stand on ``:443`` and an admin console
    on ``:9443`` are two certificates, and collapsing them would undo the point of the list.
    """
    try:
        parts = urlsplit(str(url))
        host = parts.hostname
        port = parts.port
    except ValueError:  # a malformed URL must not take the report down
        return ""
    if not host:
        return ""
    if port is not None and port != _DEFAULT_PORTS.get(parts.scheme.lower()):
        return f"{host}:{port}"
    return host


def record_unverified_host(url: Any) -> None:
    """Remember that this run reached *url*'s host without checking its certificate."""
    host = host_of(url)
    if not host:
        return
    with _lock:
        unverified_hosts.add(host)


def record_unknown_tls_host(url: Any) -> None:
    """Remember a host whose TLS this run did not decide and cannot read.

    Saying nothing here is what made ``tlsVerified: true`` an overstatement: partest
    *knows* that an injected client settled its own ``verify=`` out of sight, and used to
    report the run as verified anyway.
    """
    host = host_of(url)
    if not host:
        return
    with _lock:
        unknown_tls_hosts.add(host)


def reset_selection() -> None:
    """Forget how *this process* was selected.

    A fresh process starts empty, so this is for the second ``pytest.main()`` in one
    interpreter: without it a full run inherits the previous run's deselected tests and
    declares itself filtered by an expression it never saw.
    """
    with _lock:
        deselected_nodes.clear()
        run_info["selection"] = {}


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
    """Serialize counters for cross-process merge (xdist workers).

    Carries the selection too. Under xdist the controller does not collect, so neither
    ``pytest_collection_modifyitems`` nor ``pytest_deselected`` ever fires there: without
    these two keys a ``-m``-filtered parallel run produced an empty ``selection`` and the
    report called itself complete.
    """
    with _lock:
        return {
            "call_count": { _key_str(k): v for k, v in call_count.items() },
            "call_type": { _key_str(k): list(v) for k, v in call_type.items() },
            "call_meta": { _key_str(k): list(v) for k, v in call_meta.items() },
            "endpoint_subtype": {
                f"{m}\t{p}": s for (m, p), s in endpoint_subtype.items()
            },
            "selection": {
                k: v for k, v in (run_info.get("selection") or {}).items()
                if k in {"markexpr", "keyword"}
            },
            "deselected_nodes": sorted(deselected_nodes),
            "tls_verified": bool(run_info.get("tlsVerified", True)),
            "tls_unverified_hosts": sorted(unverified_hosts),
            "tls_unknown_hosts": sorted(unknown_tls_hosts),
        }


def load_storage(data: Dict[str, Any], *, merge: bool = True) -> None:
    """Load dump into process storage (optionally merging)."""
    if not merge:
        reset_storage()
    with _lock:
        selection = run_info.setdefault("selection", {})
        for key, value in (data.get("selection") or {}).items():
            # First writer wins: every worker is run with the same expression, and the
            # controller's own copy is as good as any.
            if value and not selection.get(key):
                selection[key] = value
        nodes = data.get("deselected_nodes") or []
        if nodes:
            deselected_nodes.update(str(n) for n in nodes)
            selection["deselected"] = len(deselected_nodes)
        if data.get("tls_verified") is False:
            # One worker running unverified is enough to taint the whole run.
            run_info["tlsVerified"] = False
        # Unioned, not summed: every worker reaches the same hosts, and the question the
        # list answers is "which", not "how many times".
        unverified_hosts.update(str(h) for h in (data.get("tls_unverified_hosts") or []))
        unknown_tls_hosts.update(str(h) for h in (data.get("tls_unknown_hosts") or []))
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
