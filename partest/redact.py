"""Redact secrets from logs and Allure attaches (LIB-16)."""

from __future__ import annotations

import base64
import binascii
import bisect
import copy
import dataclasses
import json
import re
from enum import Enum
from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Set, Tuple
from urllib.parse import unquote

DEFAULT_SENSITIVE_HEADERS = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "x-auth-token",
        "api-key",
    }
)

DEFAULT_SENSITIVE_BODY_KEYS = frozenset(
    {
        "password",
        "passwd",
        "secret",
        "token",
        "access_token",
        "refresh_token",
        "id_token",
        "client_secret",
        "authorization",
        "api_key",
        "apikey",
        "private_key",
    }
)

_BEARER_RE = re.compile(r"(?i)^(bearer\s+)(.+)$")


def mask_secret(value: Any, *, keep_prefix: int = 8) -> str:
    """Mask a secret string; keep short prefix for debugging."""
    if value is None:
        return ""
    s = str(value)
    if not s:
        return ""
    m = _BEARER_RE.match(s)
    if m:
        prefix, token = m.group(1), m.group(2)
        if len(token) <= keep_prefix:
            return f"{prefix}***"
        return f"{prefix}{token[:keep_prefix]}…[masked]"
    if len(s) <= keep_prefix:
        return "***"
    return f"{s[:keep_prefix]}…[masked]"


_TEXT_KEYS = sorted(
    {k.lower() for k in DEFAULT_SENSITIVE_BODY_KEYS | DEFAULT_SENSITIVE_HEADERS}, key=len, reverse=True
)
_KEYS_ALT = "|".join(re.escape(k) for k in _TEXT_KEYS)
# A secret key and its separator: `key: `, `"key": `, `key=`, `'key'=`, and `\"key\": ` — a JSON
# document encoded once more inside a string. The value is found by `_value_end`, not by the
# pattern: it may be quoted, an object or an array to its balancing bracket, or bare text.
_TEXT_KEY_RE = re.compile(
    r"""(?i)(?P<q>\\?["']|)\b(?P<key>""" + _KEYS_ALT + r""")(?P=q)(?P<sep>[ \t]*[:=][ \t]*)"""
)
# `('key', 'value')` — a tuple, as in an OrderedDict repr. Only after an opening parenthesis:
# `["password", "email"]` and `"field": "password", "message": …` are not pairs.
_TEXT_TUPLE_RE = re.compile(
    r"""(?i)(\(\s*)(["'])(""" + _KEYS_ALT + r""")\2(\s*,\s*)(["'])(?:\\.|(?!\5)[^\\])*\5"""
)
# `Cookie: a=1; session=…` — every pair of the header is a credential, to the end of the line.
_TEXT_COOKIE_RE = re.compile(r"""(?im)\b((?:set-)?cookie)(\s*:\s*)(?!["'\s])[^\r\n]*""")
# `Bearer <token>` — but not the parameters of a challenge, `Bearer realm="api", error="…"`
# (`WWW-Authenticate`): they name the scheme's settings, not a credential.
_TEXT_BEARER_RE = re.compile(
    r"(?i)\b(bearer\s+)(?!(?:realm|error|error_description|error_uri|scope)\s*=)"
    r"[A-Za-z0-9\-._~+/]+=*"
)
# `Basic <base64 of user:password>` — masked when the token decodes to something with a colon,
# so "basic information" stays as it is.
_TEXT_BASIC_RE = re.compile(r"(?i)\b(basic\s+)([A-Za-z0-9+/]{4,1024}={0,2})(?![A-Za-z0-9+/=])")
_AUTH_SCHEME_RE = re.compile(r"(?i)(?:bearer|basic)\s+")
# A bare value runs to whitespace, a separator or a closing bracket. A quote is part of it:
# in free text there is no telling which string a quote closes (`password=abc"def`).
_BARE_STOP = frozenset(" \t\r\n,;&})]")
# A string prefix before a quoted value: bytes, raw, unicode, f-string, SQL's national
# literal — `token=b'…'`, `rb"…"`, `u'…'`, `f"…"`, `N'…'`.
_STR_PREFIX_RE = re.compile(r"(?i)(?:rb|br|fr|rf|b|r|u|f|n)(?=[\"'])")
# A PEM private key anywhere in text: masked whole, whatever key — if any — it sits under.
_PEM_BEGIN_RE = re.compile(r"-----BEGIN [A-Z0-9 ]{0,40}PRIVATE KEY-----")
_PEM_END = "-----END "


def _mask_pem(text: str) -> str:
    """``-----BEGIN … PRIVATE KEY-----`` … ``-----END …-----`` → the two lines around ``***``.

    Without its END line the key is masked to the end of the text.
    """
    if "-----BEGIN" not in text:
        return text
    out: List[str] = []
    pos = 0
    for m in _PEM_BEGIN_RE.finditer(text):
        if m.start() < pos:
            continue
        end = text.find(_PEM_END, m.end())
        if end < 0:
            out.append(text[pos : m.end()] + "***")
            pos = len(text)
            break
        close = text.find("-----", end + len(_PEM_END))
        close = len(text) if close < 0 else close + 5
        out.append(text[pos : m.end()] + "***" + text[end:close])
        pos = close
    out.append(text[pos:])
    return "".join(out)


def _basic_sub(m: "re.Match[str]") -> str:
    try:
        decoded = base64.b64decode(m.group(2), validate=True)
    except (binascii.Error, ValueError):
        return m.group(0)
    return f"{m.group(1)}***" if b":" in decoded else m.group(0)


# The rules below decide where the value of a secret key ends in free text. Telling which
# string a quote belongs to is not reliable there — an apostrophe, a lone quote in an error
# message, an SQL literal all look the same — so each rule errs towards masking more: a lost
# piece of text is cheaper than a shown secret.


def _value_end(
    text: str, i: int, key_quote: str, scan: "_Scan"
) -> Tuple[int, Optional[str]]:
    """Where the value starting at *i* ends, and what replaces it (``None`` — nothing to mask).

    * quoted — ``"…"``, ``'…'`` (also ``b'…'``, ``rb"…"``, ``u'…'``, ``f"…"``, ``N'…'``) or
      ``\\"…\\"``: to the same quote when it is not followed by a letter or a digit
      (otherwise it is an apostrophe inside the value); without one, to the end of the line;
    * ``{`` / ``[``: see :meth:`_Scan.bracket_end`;
    * anything else: to whitespace, ``&``, ``;``, ``,`` or a closing bracket.
    """
    n = len(text)
    if i >= n:
        return i, None
    prefix_m = _STR_PREFIX_RE.match(text, i)
    prefix = prefix_m.group(0) if prefix_m else ""
    j = i + len(prefix)
    for q in ('\\"', "\\'"):
        if text.startswith(q, j):
            line_end = scan.line_end(j)
            k = j + 2
            while True:
                k = text.find(q, k, line_end)
                if k < 0:
                    return line_end, "***"
                if not _continues(text, k + 2):
                    return k + 2, f"{prefix}{q}***{q}"
                k += 2
    if j < n and text[j] in "\"'":
        q = text[j]
        k = j + 1
        while k < n:
            ch = text[k]
            if ch == "\\":
                k += 2
                continue
            if ch == "\n":
                break
            if ch == q and text.startswith(q, k + 1) and k > j + 1:
                k += 2  # a doubled quote, SQL style: `'it''s'` — still inside the value
                continue
            if ch == q and not _continues(text, k + 1):
                return k + 1, f"{prefix}{q}***{q}"
            k += 1
        return min(k, n), "***"
    c = text[i]
    if c in "{[":
        masked = '"***"' if '"' in key_quote else "***"
        return scan.bracket_end(i, escaped=key_quote.startswith("\\")), masked
    m = _AUTH_SCHEME_RE.match(text, i)
    k = m.end() if m else i
    start_value = k
    while k < n and text[k] not in _BARE_STOP:
        k += 1
    if k == start_value:
        return i, None
    return k, "***"


def _continues(text: str, k: int) -> bool:
    """Whether the character at *k* goes on a word — a quote before it is not a closing one."""
    return k < len(text) and text[k].isalnum()


def _line_end(text: str, i: int) -> int:
    j = text.find("\n", i)
    return len(text) if j < 0 else j


# The package's own shortening marker (`_shorten`), taken only where `_shorten` puts it: at
# the very end of the text. A marker in the middle is data, and data could forge it to end a
# masked value early.
_TRUNCATED_RE = re.compile(r"\.\.\. \[truncated, \d+ chars total\]\s*\Z")


def _bracket_pairs(text: str, escaped: bool) -> Dict[int, int]:
    """Opening bracket position → end of its balancing bracket, for the whole text at once.

    Only brackets are counted; a string — between double or single quotes, or ``\\"…\\"`` in
    *escaped* mode (JSON encoded inside a string) — is skipped, so a bracket inside one does
    not close anything. An apostrophe opens a "string" too. Usually the pair is then not
    found and the value falls back to its indented block — masked more; but two apostrophes
    can hide brackets between them and let an earlier one close the value
    (``token: {a: it's {b: c'}, d: …}``) — a known gap of free text. A line break ends a
    string. One pass, so many values cost no more than one.
    """
    pairs: Dict[int, int] = {}
    stack: List[Tuple[str, int]] = []
    in_str = ""
    j, n = 0, len(text)
    while j < n:
        if escaped and text.startswith('\\"', j):
            in_str = "" if in_str else '\\"'
            j += 2
            continue
        ch = text[j]
        if ch == "\\":
            j += 2
            continue
        if ch == "\n":
            in_str = ""
        elif in_str:
            if ch == in_str:
                in_str = ""
        elif ch in "\"'" and not escaped:
            in_str = ch
        elif ch in "{[":
            stack.append((ch, j))
        elif ch in "}]":
            want = "{" if ch == "}" else "["
            if stack and stack[-1][0] == want:
                pairs[stack.pop()[1]] = j + 1
        j += 1
    return pairs


class _Scan:
    """What `_mask_pairs` needs to know about the whole text, computed once."""

    def __init__(self, text: str):
        self.text = text
        self._pairs: Dict[bool, Dict[int, int]] = {}
        self._newlines = [m.start() for m in re.finditer("\n", text)]
        marker = _TRUNCATED_RE.search(text)
        self.limit = marker.start() if marker else len(text)

    def line_end(self, i: int) -> int:
        k = bisect.bisect_left(self._newlines, i)
        return self._newlines[k] if k < len(self._newlines) else len(self.text)

    def _indent(self, line_start: int) -> int:
        text, k = self.text, line_start
        while k < len(text) and text[k] in " \t":
            k += 1
        return k - line_start

    def bracket_end(self, i: int, *, escaped: bool) -> int:
        """End of the object or array starting at *i*: its balancing bracket.

        Without one — or when it lies past the package's ``... [truncated,`` marker — the
        value is the indented block it opens: the rest of the key's line, every following
        line indented deeper than the key's, and a line at the key's indent that starts with
        the closing bracket; never past the marker.
        """
        if escaped not in self._pairs:
            self._pairs[escaped] = _bracket_pairs(self.text, escaped)
        end = self._pairs[escaped].get(i)
        if end is not None and end <= self.limit:
            return end
        return min(self._block_end(i), self.limit)

    def _block_end(self, i: int) -> int:
        """End of the indented block a value opened at *i* without closing it."""
        text, n = self.text, len(self.text)
        k = bisect.bisect_left(self._newlines, i)
        line_start = self._newlines[k - 1] + 1 if k > 0 else 0
        indent = self._indent(line_start)
        end = self.line_end(i)
        while end < n:
            start = end + 1
            depth = self._indent(start)
            line_end = self.line_end(start)
            body = start + depth
            if body < line_end and depth > indent:
                end = line_end
                continue
            if body < line_end and text[body] in "}]" and depth == indent:
                end = line_end
            break
        return end


def _mask_pairs(text: str) -> str:
    out: List[str] = []
    emitted = 0
    scan = _Scan(text)
    for m in _TEXT_KEY_RE.finditer(text):
        if m.start() < emitted:
            continue
        end, replacement = _value_end(text, m.end(), m.group("q"), scan)
        if replacement is None:
            continue
        out.append(text[emitted : m.end()])
        out.append(replacement)
        emitted = end
    out.append(text[emitted:])
    return "".join(out)


def redact_text(text: str) -> str:
    """Mask secrets inside free text: values of sensitive keys, and bearer tokens.

    For text whose structure is gone — a ``repr`` of a model, a response body kept as a
    string, a log line. It recognises ``key: value``, ``"key": "value"``, ``key=value``,
    ``key='value'``, ``\\"key\\": \\"value\\"`` and ``('key', 'value')`` for the keys
    :func:`redact_mapping` and :func:`redact_headers` mask — a value that is an object or an
    array to its balancing bracket, or to the end of the indented block it opens — a whole
    ``Cookie:`` / ``Set-Cookie:`` header line, ``Bearer <token>`` and ``Basic <credentials>``
    anywhere (not the parameters of a ``Bearer realm="…"`` challenge), and a PEM private key
    (``-----BEGIN … PRIVATE KEY-----`` to its END line) whole, under any key or none. A
    quoted value keeps its quotes. Where a value ends is decided towards masking
    more: free text gives no reliable way to tell which string a quote belongs to. Pattern-
    based, so best effort: prefer :func:`redact_mapping` while the data is still a mapping.
    """
    if not text:
        return text
    masked = _TEXT_COOKIE_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}***", _mask_pem(text))
    masked = _mask_pairs(masked)
    masked = _TEXT_TUPLE_RE.sub(
        lambda m: f"{m.group(1)}{m.group(2)}{m.group(3)}{m.group(2)}{m.group(4)}{m.group(5)}***{m.group(5)}",
        masked,
    )
    masked = _TEXT_BASIC_RE.sub(_basic_sub, masked)
    return _TEXT_BEARER_RE.sub(lambda m: f"{m.group(1)}***", masked)


def redact_headers(
    headers: Optional[Mapping[str, Any]],
    *,
    extra_keys: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """Return a copy of headers with sensitive values masked."""
    if not headers:
        return {}
    sensitive = {k.lower() for k in DEFAULT_SENSITIVE_HEADERS}
    if extra_keys:
        sensitive |= {k.lower() for k in extra_keys}
    out: Dict[str, Any] = {}
    for k, v in headers.items():
        if str(k).lower() in sensitive and v is not None and str(v):
            out[k] = mask_secret(v)
        else:
            out[k] = v
    return out


def redact_mapping(
    data: Any,
    *,
    sensitive_keys: Optional[Set[str]] = None,
    depth: int = 6,
) -> Any:
    """Deep-copy mapping/list masking values under sensitive keys."""
    keys = {k.lower() for k in (sensitive_keys or DEFAULT_SENSITIVE_BODY_KEYS)}
    return _redact(data, keys, depth)


def _redact(data: Any, keys: Set[str], depth: int) -> Any:
    if depth < 0:
        return data
    if isinstance(data, Mapping):
        out = {}
        for k, v in data.items():
            if str(k).lower() in keys and v is not None and str(v) != "":
                out[k] = mask_secret(v)
            else:
                out[k] = _redact(v, keys, depth - 1)
        return out
    if isinstance(data, list):
        return [_redact(x, keys, depth - 1) for x in data]
    if isinstance(data, tuple):
        return tuple(_redact(x, keys, depth - 1) for x in data)
    return data


# --- the package's own output channels -----------------------------------------------------
#
# Every place the package shows what went over the wire — the request/response log, assertion
# messages, ErrorDesc, Allure attachments — goes through the helpers below. Private: the public
# surface stays the functions above, and `redact_mapping` keeps its behaviour.
#
# Two walkers for structures, one rule for secret keys: a value under a secret key is replaced
# whole, with no prefix kept.
# * `_scrub` — HTTP bodies and the like: any other string leaf gets only narrow patterns — URL
#   credentials and secret query values, Bearer/Basic credentials, a JWT — so
#   `{"missing": ["password", "email"]}`, `{"field": "password"}` and `"token: expired"` stay
#   readable and the JSON stays valid. A leaf that is itself a JSON document is walked too.
# * `_scrub_check` — values of `check_*` and `sideeffects`, chosen by a test's author: every
#   string, bytes value and text key, at any level, gets the free-text rule — closed when in
#   doubt.
# Text whose structure is gone (a body that is not JSON, an exception message) gets the full
# `redact_text` (`_scrub_text`).

_MASK = "***"
_CYCLE = "<cycle>"
_TOO_LARGE = "<too large>"
# Containers one walk may open. Shared references (a DAG, YAML anchors) are walked once per
# path, so twenty levels of shared children would open a million nodes; past the budget a
# container is replaced by `<too large>` — kept apart from `***` (a secret, or the depth
# limit). Both walkers share
# the rule.
_MAX_NODES = 100_000


class _WalkState(set):
    """The containers on the current path (a cycle check) and how many one walk has opened."""

    visited = 0

    def enter(self, value: Any) -> Optional[str]:
        """``None`` to go on, or what to show instead of *value*."""
        if id(value) in self:
            return _CYCLE
        self.visited += 1
        if self.visited > _MAX_NODES:
            return _TOO_LARGE
        self.add(id(value))
        return None


def _norm_key(key: Any) -> str:
    """A key as the secret lists spell it: an Enum by its value, bytes decoded, lower case,
    and ``-`` / spaces read as ``_`` — so ``client-secret`` and ``Client Secret`` are
    ``client_secret``."""
    if isinstance(key, Enum):
        key = key.value
    if isinstance(key, (bytes, bytearray)):
        key = bytes(key).decode("utf-8", errors="replace")
    return re.sub(r"[-\s]+", "_", str(key).strip().lower())


_SECRET_KEYS = frozenset(_norm_key(k) for k in DEFAULT_SENSITIVE_BODY_KEYS | DEFAULT_SENSITIVE_HEADERS)
# A header is secret when it is one of the secret names (`Authorization`, `Cookie`,
# `X-Api-Key` …) or when its name — lower case, without `-`, `_` and spaces, and without a
# numeric or `sha1`/`sha256`/`sha512` tail (`X-Hub-Signature-256`) — ends with one of these.
# A name can carry a credential under many spellings (`CSRFPreventionToken`, `X-Authtoken`,
# `PVEAuthCookie`, `X-RestSvcSessionId`), so the rule errs towards masking: a cursor such as
# `X-Next-Page-Token` is masked too. The four names below describe authentication, they do
# not carry it.
_HEADER_SECRET_ENDINGS = (
    "token", "key", "apikey", "secret", "password", "passwd", "pwd", "passphrase", "signature",
    "cookie", "authorization", "authentication", "auth", "session", "sessionid", "sid", "jwt",
    "ticket", "otp", "credential", "credentials", "pass", "cred", "assertion", "hmac",
)
_HEADER_NOT_SECRET = frozenset(
    {"wwwauthenticate", "proxyauthenticate", "authenticationinfo", "signatureinput",
     "accesscontrolallowcredentials"}
)
_HEADER_TAIL_RE = re.compile(r"(?:sha(?:1|256|512)|v\d+|\d+)$")
# A query or fragment parameter is secret under these names too — names that mean one thing
# only: pre-signed URLs carry their credential there.
_QUERY_SECRET_KEYS = _SECRET_KEYS | frozenset(
    {"x_amz_signature", "x_amz_security_token", "x_amz_credential", "x_goog_signature",
     "signature", "sig", "auth_token", "sessionid", "session_id", "jsessionid"}
)
# Deeper than this, a value is replaced whole rather than shown unexamined.
_MAX_DEPTH = 32

# Userinfo runs to the *last* ``@`` before the host: a raw ``@`` in a password is common. A
# password with a raw ``/`` is taken too (`user:pa/ss@host`), unless what follows the colon
# reads as a port (`host:8080/path@x`). Quantifiers that can backtrack are bounded (a scheme of
# 32, userinfo of 512 characters): unbounded, a text built to look like many half-URLs — or a
# 64 KB response body quoted in a status message — takes quadratic time to clean.
_URL_RE = re.compile(
    r"(?P<scheme>\b[a-zA-Z][a-zA-Z0-9+.-]{0,31}://)"
    r"(?P<userinfo>[^/\s'\"<>?#]{0,512}@"
    r"|[^/\s'\"<>?#:@]{1,128}:(?![0-9]{1,5}(?:[/\s'\"<>?#]|$))[^\s'\"<>?#@]{0,512}@)?"
    r"(?P<rest>[^\s?#'\"<>]*)(?P<query>\?[^\s#'\"<>)]*)?(?P<frag>#[^\s'\"<>)]*)?"
)
# ``user:password@host/...`` without a scheme.
_BARE_USERINFO_RE = re.compile(
    r"(?<![\w/@:.%+~-])[\w.%+~-]{1,128}:[^\s/'\"<>]{0,512}@"
    r"(?=[A-Za-z0-9.-]{1,253}(?::\d{1,5})?(?:[/\s'\")]|$))"
)
# A query string or fragment after a bare path, as in ``... for url: /openapi.json?token=...``.
_PATH_QUERY_RE = re.compile(
    r"(?P<path>(?<![\w:/])/[^\s?#'\"<>]*)(?P<query>\?[^\s#'\"<>)]*)?(?P<frag>#[^\s'\"<>)]*)?"
)
# `token=…` at the start of a string or after `?` / `&` / `;` / `#`, outside a URL.
# `token=…` / `sig=…` at the start of a string or after `?` / `&` / `;` / `#`, outside a URL —
# the query names, spelled with `-` or `_` alike.
_QUERY_KEYS_ALT = "|".join(
    re.escape(k).replace("_", "[-_]") for k in sorted(_QUERY_SECRET_KEYS, key=len, reverse=True)
)
_QUERY_PAIR_RE = re.compile(r"(?i)(?:^|(?<=[?&;#]))(" + _QUERY_KEYS_ALT + r")=[^&;\s#'\"<>]+")
# A Java session id in a URL path: `/app;jsessionid=…?x=1` (a common `Location`).
_JSESSIONID_RE = re.compile(r"(?i)(;jsessionid=)[^?#;/\s'\"<>]+")
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]*")


def _mask_params(params: str) -> str:
    """``a=1&token=x;sig=y`` → ``a=1&token=***;sig=***``: the values of secret keys only."""
    parts = re.split(r"([&;])", params)
    for i in range(0, len(parts), 2):
        key, sep, value = parts[i].partition("=")
        if sep and value and _norm_key(unquote(key)) in _QUERY_SECRET_KEYS:
            parts[i] = f"{key}={_MASK}"
    return "".join(parts)


def _scrub_urls(text: Any, *, drop_query: bool = False) -> str:
    """URLs in *text*: credentials removed, the query string masked by key — or dropped.

    ``scheme://user:password@host`` and a bare ``user:password@host`` lose the userinfo. With
    *drop_query* every query string becomes ``?…`` (errors about the project's configuration,
    :func:`partest.conf._strip_url_secrets`); otherwise only the values of secret keys go. A
    fragment (``#access_token=…``) is masked by key either way.
    """
    s = "" if text is None else str(text)
    if not s:
        return s

    def tail(m: "re.Match[str]") -> str:
        q, f = m.group("query"), m.group("frag")
        out = ""
        if q:
            out += "?…" if drop_query else "?" + _mask_params(q[1:])
        if f:
            out += "#" + _mask_params(f[1:])
        return out

    s = _URL_RE.sub(lambda m: m.group("scheme") + m.group("rest") + tail(m), s)
    s = _BARE_USERINFO_RE.sub("", s)
    s = _PATH_QUERY_RE.sub(lambda m: m.group("path") + tail(m), s)
    return _JSESSIONID_RE.sub(lambda m: m.group(1) + _MASK, s)


def _scrub_leaf_text(s: str) -> str:
    """Narrow patterns for a string found inside a structure."""
    s = _scrub_urls(s)
    s = _QUERY_PAIR_RE.sub(lambda m: f"{m.group(1)}={_MASK}", s)
    s = _TEXT_BASIC_RE.sub(_basic_sub, s)
    s = _TEXT_BEARER_RE.sub(lambda m: f"{m.group(1)}{_MASK}", s)
    return _JWT_RE.sub(_MASK, _mask_pem(s))


def _scrub_text(text: Any) -> str:
    """Free text — an exception message, a body that is not JSON, a log line.

    A JSON object or array is walked instead (:func:`_scrub`); anything else gets URL
    credentials and secret query values removed, then the full :func:`redact_text`, then JWTs.
    """
    s = "" if text is None else str(text)
    if not s:
        return s
    parsed = _parsed_json(s)
    if parsed is not None:
        return _dumps(_scrub(parsed))
    return _free_text(s)


def _free_text(s: str) -> str:
    """The free-text rule itself: URL credentials and secret query values, the full
    :func:`redact_text`, JWTs."""
    s = _QUERY_PAIR_RE.sub(lambda m: f"{m.group(1)}={_MASK}", _scrub_urls(s))
    return _JWT_RE.sub(_MASK, redact_text(s))


def _check_key(key: Any) -> Any:
    """A dict key in a check value: text keys are free text too (``{"password: …": 1}``)."""
    key = _json_key(key)
    return _free_text(key) if isinstance(key, str) else key


def _scrub_check(value: Any, depth: int = 0, _active: Optional[Set[int]] = None) -> Any:
    """A value of a ``check_*`` — closed when in doubt, at every level.

    The author of a test chose the value, and it can be anything: a log line, a header dump, a
    list of them. So every string and every ``bytes`` / ``bytearray`` / ``memoryview`` — at
    the top, as a dict value, as an element of a list, tuple or set — gets the full free-text
    rule (``password: …`` included), not only the narrow patterns of a body's leaf; a string
    holding JSON is walked in this mode too. The structure stays (a leaf is masked in place,
    so an attachment stays valid JSON), and a value under a secret key is ``***`` whole. HTTP
    bodies keep the body rule (:func:`_scrub`); this is for checks only.
    """
    if depth > _MAX_DEPTH:
        return _MASK
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, Enum):
        return _scrub_check(value.value, depth, _active)
    if isinstance(value, (bytes, bytearray, memoryview)):
        value = bytes(value).decode("utf-8", errors="replace")
    if isinstance(value, str):
        parsed = _parsed_json(value)
        if parsed is not None:
            return _dumps(_scrub_check(parsed, depth + 1, _active))
        return _free_text(value)
    active = _active if _active is not None else _WalkState()
    stop = active.enter(value)
    if stop is not None:
        return stop
    try:
        if isinstance(value, Mapping):
            return {
                _check_key(k): (
                    _MASK
                    if _is_secret_key(k) and not _is_blank(v)
                    else _scrub_check(v, depth + 1, active)
                )
                for k, v in value.items()
            }
        if isinstance(value, tuple) and hasattr(value, "_asdict"):
            return _scrub_check(value._asdict(), depth + 1, active)
        if isinstance(value, (list, tuple)):
            return [_scrub_check(v, depth + 1, active) for v in value]
        if isinstance(value, (set, frozenset)):
            return [_scrub_check(v, depth + 1, active) for v in sorted(value, key=repr)]
        dump = getattr(value, "model_dump", None)
        if callable(dump) and not isinstance(value, type):
            return _scrub_check(dump(), depth + 1, active)
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            return _scrub_check(
                {f.name: getattr(value, f.name, None) for f in dataclasses.fields(value)},
                depth + 1,
                active,
            )
        return _free_text(str(value))
    finally:
        active.discard(id(value))


_MASKED_MARK = "_partest_masked"


def _mark_masked(exc: Any) -> Any:
    """Mark an exception the package raises with a message it already masked. Returns it.

    The mark is on the instance, set only where the package itself raises: an exception of
    the same class raised by a suite (a ``StatusMismatchError`` with raw text, anything
    carrying ``validation_errors``) is not marked and is masked like any other text.
    """
    try:
        setattr(exc, _MASKED_MARK, True)
    except Exception:  # an exception type that refuses attributes stays unmarked
        pass
    return exc


def _already_masked(exc: Any) -> bool:
    """Whether the package raised *exc* with a masked message (see :func:`_mark_masked`).

    Its text is shown as is: a second pass reads the JSON in it as free text and breaks it
    (``"detail": "token: expired"`` loses its value and its closing quote). Only the mark in
    the instance's own ``__dict__`` counts — not a class attribute, not a mock's attribute.
    """
    try:
        return vars(exc).get(_MASKED_MARK) is True
    except TypeError:
        return False


def _parsed_json(text: str) -> Any:
    """``text`` parsed when it is a JSON object or array, else ``None``. Never raises:
    a document nested too deep for the parser (``RecursionError``) is not JSON here. A
    byte-order mark in front is ignored."""
    try:
        stripped = text.lstrip("\ufeff \t\r\n")
        if not stripped or stripped[0] not in "{[":
            return None
        value = json.loads(stripped)
    except Exception:
        return None
    return value if isinstance(value, (dict, list)) else None


def _dumps(value: Any, indent: Optional[int] = None) -> str:
    return json.dumps(value, ensure_ascii=False, default=str, indent=indent)


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value == "")


def _is_secret_key(key: Any) -> bool:
    try:
        return _norm_key(key) in _SECRET_KEYS
    except Exception:
        return False


def _is_secret_header(name: Any) -> bool:
    try:
        norm = _norm_key(name)
    except Exception:
        return False
    if norm in _SECRET_KEYS:
        return True
    compact = norm.replace("_", "")
    while True:
        shorter = _HEADER_TAIL_RE.sub("", compact)
        if shorter == compact:
            break
        compact = shorter
    if compact in _HEADER_NOT_SECRET:
        return False
    return compact.endswith(_HEADER_SECRET_ENDINGS)


def _json_key(key: Any) -> Any:
    if isinstance(key, Enum):
        key = key.value
    if isinstance(key, (bytes, bytearray)):
        return bytes(key).decode("utf-8", errors="replace")
    return key if isinstance(key, (str, int, float, bool)) or key is None else str(key)


def _scrub(value: Any, depth: int = 0, _active: Optional[Set[int]] = None) -> Any:
    """A JSON-able copy of *value* with secrets masked (see the comment above).

    A container met again on the path that leads to it is ``"<cycle>"``.
    """
    if depth > _MAX_DEPTH:
        return _MASK
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, Enum):
        value = value.value
        if value is None or isinstance(value, (bool, int, float)):
            return value
    if isinstance(value, (bytes, bytearray, memoryview)):
        value = bytes(value).decode("utf-8", errors="replace")
    if isinstance(value, str):
        parsed = _parsed_json(value)
        if parsed is not None:
            return _dumps(_scrub(parsed, depth + 1))
        return _scrub_leaf_text(value)
    active = _active if _active is not None else _WalkState()
    stop = active.enter(value)
    if stop is not None:
        return stop
    try:
        return _scrub_container(value, depth, active)
    finally:
        active.discard(id(value))


def _scrub_container(value: Any, depth: int, active: Set[int]) -> Any:
    if isinstance(value, Mapping):
        return {
            _json_key(k): (
                _MASK if _is_secret_key(k) and not _is_blank(v) else _scrub(v, depth + 1, active)
            )
            for k, v in value.items()
        }
    if isinstance(value, tuple) and hasattr(value, "_asdict"):  # a namedtuple
        return _scrub(value._asdict(), depth + 1, active)
    if isinstance(value, (list, tuple)):
        return [_scrub(v, depth + 1, active) for v in value]
    if isinstance(value, (set, frozenset)):
        return [_scrub(v, depth + 1, active) for v in sorted(value, key=repr)]
    dump = getattr(value, "model_dump", None)
    if callable(dump) and not isinstance(value, type):  # a pydantic model
        return _scrub(dump(), depth + 1, active)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _scrub(
            {f.name: getattr(value, f.name, None) for f in dataclasses.fields(value)},
            depth + 1,
            active,
        )
    return _scrub_text(str(value))


def _shorten(text: str, limit: Optional[int]) -> str:
    if limit is None or len(text) <= limit:
        return text
    return text[:limit] + f"... [truncated, {len(text)} chars total]"


def _not_shown(value: Any) -> str:
    return f"<{type(value).__name__}: not shown, it could not be masked>"


def _body_text(value: Any, *, limit: Optional[int] = 2000, indent: Optional[int] = None) -> str:
    """Any body as text for a log or a message: masked, then shortened. Never raises.

    The one implementation behind every "body in a message" in the package. A structure, or
    text holding a JSON object or array, is walked (:func:`_scrub`) and serialised as JSON;
    other text gets :func:`_scrub_text`. ``None`` stays ``"None"``. When masking fails, a
    placeholder is shown — never the raw value.
    """
    try:
        if value is None:
            return "None"
        if isinstance(value, (bytes, bytearray, memoryview)):
            value = bytes(value).decode("utf-8", errors="replace")
        if isinstance(value, str):
            parsed = _parsed_json(value)
            text = _scrub_text(value) if parsed is None else _dumps(_scrub(parsed), indent)
        else:
            walked = _scrub(value)
            text = walked if isinstance(walked, str) else _dumps(walked, indent)
    except Exception:
        return _not_shown(value)
    return _shorten(text, limit)


def _body_structure(value: Any) -> Any:
    """A body kept as a structure, for an attachment that serialises it itself.

    A string stays a string (a JSON one walked and re-serialised, other text through
    :func:`_scrub_text`); anything else through :func:`_scrub`. Never raises.
    """
    try:
        if isinstance(value, (bytes, bytearray, memoryview)):
            value = bytes(value).decode("utf-8", errors="replace")
        if isinstance(value, str):
            return _scrub_text(value)
        return _scrub(value)
    except Exception:
        return _not_shown(value)


def _scrub_headers(headers: Any) -> Any:
    """Headers for a log, a message or an attachment.

    A secret header is ``***`` whole — no prefix. Secret here is wider than for a body key:
    one of the secret names, or a name that ends with ``token``, ``key``, ``secret``,
    ``password``, ``signature``, ``cookie``, ``auth``, ``authorization``, ``session``,
    ``sessionid``, ``sid``, ``jwt``, ``ticket``, ``otp``, ``credential(s)`` … once lower-cased,
    without separators and a numeric or ``sha…`` tail (``_HEADER_SECRET_ENDINGS``;
    ``WWW-Authenticate`` and ``Signature-Input`` are not). The value of any other header goes
    through the narrow patterns, so a ``Location`` or ``Referer`` URL loses its credentials
    and secret query values.
    """
    if headers is None:
        return None
    try:
        items = headers.items() if hasattr(headers, "items") else list(headers)
        return {
            str(k): (
                _MASK if _is_secret_header(k) and not _is_blank(v) else _scrub_leaf_text(str(v))
            )
            for k, v in items
        }
    except Exception:
        return _not_shown(headers)


def _scrub_params(params: Any) -> Any:
    """Query parameters: a mapping or a list of pairs masked by key; text as text."""
    if params is None:
        return None
    try:
        if isinstance(params, (list, tuple)) and all(
            isinstance(p, (list, tuple)) and len(p) == 2 for p in params
        ):
            return [
                [_json_key(k), _MASK if _norm_key(k) in _QUERY_SECRET_KEYS else _scrub(v, 1)]
                for k, v in params
            ]
        if isinstance(params, str):
            return _scrub_text(params)
        if isinstance(params, Mapping):
            return {
                _json_key(k): (
                    _MASK
                    if _norm_key(k) in _QUERY_SECRET_KEYS and not _is_blank(v)
                    else _scrub(v, 1)
                )
                for k, v in params.items()
            }
        return _scrub(params)
    except Exception:
        return _not_shown(params)


def _scrub_cookies(cookies: Any) -> Any:
    """Response cookies: names kept, every value ``***``."""
    if cookies is None:
        return None

    def masked(value: Any) -> str:
        return _MASK if not _is_blank(value) else ""

    jar = getattr(cookies, "jar", None)
    if jar is not None:
        try:
            return {c.name: masked(c.value) for c in jar}
        except Exception:
            pass
    if isinstance(cookies, Mapping):
        return {k: masked(v) for k, v in cookies.items()}
    return "<cookies>"


def _files_summary(files: Any) -> Any:
    """Files of a request as field, file name, size and content type — never the content."""
    if files is None:
        return None
    try:
        items = files.items() if isinstance(files, Mapping) else list(files)
        out: List[Dict[str, Any]] = []
        for field, spec in items:
            filename = content_type = None
            content: Any = spec
            if isinstance(spec, (list, tuple)):
                filename = spec[0] if len(spec) > 0 else None
                content = spec[1] if len(spec) > 1 else None
                content_type = spec[2] if len(spec) > 2 else None
            else:
                filename = getattr(spec, "name", None)
            size = len(content) if isinstance(content, (bytes, bytearray, str)) else None
            out.append(
                {
                    "field": str(field),
                    "filename": None if filename is None else _scrub_leaf_text(str(filename)),
                    "size": size,
                    "content_type": content_type,
                }
            )
        return out
    except Exception:
        return _not_shown(files)


def _field_value(field: Any, value: Any) -> Any:
    """A checked value for a message or an attachment: whole ``***`` under a secret field,
    otherwise :func:`_scrub_check` — free text at every level.

    Never raises: a value that cannot be walked is a placeholder.
    """
    try:
        if _is_secret_key(field) and not _is_blank(value):
            return _MASK
        return _scrub_check(value)
    except Exception:
        return _not_shown(value)


def _scrub_at(data: Any, path: Any, missing: Any = None) -> Any:
    """The walked node at *path* — ``***`` when a key on the way is secret.

    For a message that quotes one element of a body: the element is masked as it would be in
    the whole body, so a parent stored under ``token`` is not shown because the path into it
    skipped the key. *missing* when the path does not resolve.
    """
    node = data
    for part in path:
        if isinstance(node, Mapping):
            if part not in node:
                return missing
            if _is_secret_key(part) and not _is_blank(node[part]):
                return _MASK
            node = node[part]
        elif isinstance(node, list) and isinstance(part, int) and -len(node) <= part < len(node):
            node = node[part]
        else:
            return missing
    return node
