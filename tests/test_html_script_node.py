"""The interactive report's script runs on the payloads 2.7.0 can produce — executed, not grepped.

`test_summary_avg_null.py` checks the template by substrings; a `null` average reaching a
`.toFixed` the substrings missed would still blank the page. Here the page's own script runs
in node against a permissive stand-in for the DOM: every element accepts any property and
call, so what can fail is the script's own handling of the data. Skipped without `node`.
"""

from __future__ import annotations

import copy
import json
import re
import shutil
import subprocess

import pytest

from partest.reports.interactive_html import render_html
from partest.reports.payload import build_payload

from test_summary_avg_null import _endpoint, _report

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not in PATH")

HARNESS = r"""
const fs = require("fs");
const [data, script] = [fs.readFileSync(process.argv[2], "utf8"), fs.readFileSync(process.argv[3], "utf8")];
const assigned = [];
function fake(path) {
  const store = {};
  const target = function () {};
  return new Proxy(target, {
    get(t, key) {
      if (key === Symbol.iterator) return function* () {};
      if (key === Symbol.toPrimitive) return () => "";
      if (key === "length") return 0;
      if (key === "textContent" && path === "coverage-data") return data;
      if (key in store) return store[key];
      if (key === "then") return undefined;
      return (store[key] = fake(path + "." + String(key)));
    },
    set(t, key, value) { store[key] = value; assigned.push(value); return true; },
    apply() { return fake(path + "()"); },
  });
}
const document = {
  getElementById: (id) => fake(id),
  querySelector: (sel) => fake(sel),
  querySelectorAll: () => [],
  createElement: (tag) => fake(tag),
  addEventListener: () => {},
  documentElement: fake("html"),
  body: fake("body"),
};
const sandbox = {
  document, window: null, localStorage: { getItem: () => null, setItem: () => {} },
  location: { search: "", hash: "", pathname: "/report.html", href: "file:///report.html" },
  history: { replaceState: () => {}, pushState: () => {} },
  navigator: { clipboard: { writeText: () => Promise.resolve() } },
  matchMedia: () => ({ matches: false, addEventListener: () => {} }),
  Blob: function () {}, URL: { createObjectURL: () => "", revokeObjectURL: () => {} },
  setTimeout, clearTimeout, URLSearchParams, console,
};
sandbox.window = sandbox;
sandbox.addEventListener = () => {};
const vm = require("vm");
vm.runInNewContext(script, sandbox, { filename: "report.js" });
const text = assigned.filter((v) => typeof v === "string").join("\n");
if (/NaN|undefined%|null%/.test(text)) { console.error("suspicious output:\n" + text); process.exit(3); }
console.log("ok " + assigned.length);
"""


def _script() -> str:
    page = render_html(build_payload(_report([])), title="t")
    scripts = re.findall(r"<script>(.*?)</script>", page, re.S)
    assert len(scripts) == 1
    return scripts[0]


def _run(tmp_path, payload: dict) -> subprocess.CompletedProcess:
    (tmp_path / "harness.js").write_text(HARNESS, encoding="utf-8")
    (tmp_path / "data.json").write_text(json.dumps(payload), encoding="utf-8")
    (tmp_path / "report.js").write_text(_script(), encoding="utf-8")
    return subprocess.run(
        [NODE, str(tmp_path / "harness.js"), str(tmp_path / "data.json"), str(tmp_path / "report.js")],
        capture_output=True, text=True, timeout=60,
    )


def _empty() -> dict:
    return build_payload(_report([]))


def _legacy_empty() -> dict:
    doc = copy.deepcopy(_empty())
    doc["summary"]["avg"] = 0.0
    doc["summary"]["avgAll"] = 0.0
    return doc


def _measured() -> dict:
    return build_payload(_report([
        _endpoint("/a", calls=3, kind="full", status="full", pct=100.0),
        _endpoint("/b", calls=0, kind="unseen", status="empty", pct=0.0),
    ]))


@pytest.mark.parametrize(
    "payload", [_empty, _legacy_empty, _measured], ids=["null-avg", "legacy-0.0", "measured"]
)
def test_the_report_script_runs_on_the_payload(tmp_path, payload):
    result = _run(tmp_path, payload())
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.startswith("ok ")


def test_the_harness_catches_a_script_error(tmp_path):
    """A stand-in DOM that swallowed everything would prove nothing."""
    broken = _empty()
    broken["endpoints"] = "not a list"
    result = _run(tmp_path, broken)
    assert result.returncode != 0
