"""Load OpenAPI documents from local path or URL."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Union

import yaml

from partest.project_gen.ir import SuiteIR, build_ir_from_openapi_dict


def load_openapi_dict(source: Union[str, Path], *, source_type: str = "auto") -> Dict[str, Any]:
    """Load OpenAPI YAML/JSON from file path or HTTP(S) URL.

    Parameters
    ----------
    source:
        Local path or URL.
    source_type:
        ``local`` | ``url`` | ``auto`` (detect by scheme).
    """
    src = str(source)
    kind = source_type
    if kind == "auto":
        kind = "url" if src.startswith("http://") or src.startswith("https://") else "local"

    if kind == "url":
        import requests

        resp = requests.get(src, timeout=60)
        resp.raise_for_status()
        text = resp.text
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = yaml.safe_load(text)
    elif kind == "local":
        path = Path(src)
        if not path.is_file():
            raise FileNotFoundError(f"OpenAPI file not found: {path}")
        text = path.read_text(encoding="utf-8")
        if path.suffix.lower() == ".json":
            data = json.loads(text)
        else:
            try:
                data = yaml.safe_load(text)
            except Exception:
                data = json.loads(text)
    else:
        raise ValueError("source_type must be local, url, or auto")

    if not isinstance(data, dict):
        raise ValueError("OpenAPI document must be a JSON/YAML object")
    return data


def load_openapi(source: Union[str, Path], *, source_type: str = "auto") -> SuiteIR:
    """Load OpenAPI and return SuiteIR."""
    data = load_openapi_dict(source, source_type=source_type)
    return build_ir_from_openapi_dict(data, source=str(source))
