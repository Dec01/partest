<!-- Part of the partest package: generated documentation, not hand-written.
     Read it with `python -m partest.docs`. Local edits are lost on upgrade. -->

# Security cookbook

Project-agnostic helpers for OWASP-oriented API tests. **Entity PROFILES stay
in the consumer** — library only provides the model and transports.

## Risk profile → depth

```python
from partest import RiskProfile
from partest.security import by_level, writable, level_of

PROFILES = {
    "users": RiskProfile("users", writes=True, authz=True, pii=True),
    "items": RiskProfile("items", writes=True, fk_traversal=True),
    "enums": RiskProfile("enums"),
}

for p in by_level(PROFILES, "critical"):
    ...  # deep authz + tamper matrix
for p in writable(PROFILES):
    ...  # write abuse / IDOR candidates
```

| Level | Meaning | Suggested depth |
|-------|---------|-----------------|
| critical | authz or (pii∧writes) | full matrix: JWT, RBAC, mass-assign |
| high | writes∧fk_traversal | IDOR + incorrect body + authz smoke |
| medium | writes | create/update negative + extra fields |
| low | read catalogs | auth optional, benchmark |

## SecHttp (raw transport)

Use when you need response **headers**, non-JSON, or crafted Authorization
outside coverage ApiClient (security suite often separate from zorro counters).

```python
from partest.security import SecHttp

sec = SecHttp(base_url, token_or_manager=tm, instrument=True)
r = await sec.get("/admin", expected_status=403)
r = await sec.post("/items", json={...}, expected_status=(400, 422))
```

## JWT craft

```python
from partest.security import build_tampered_set, build_alg_none_token

tokens = build_tampered_set(valid_jwt)
# alg=none, payload tweaks, signature break
await sec.get("/me", headers={"Authorization": f"Bearer {tokens['alg_none']}"},
              expected_status=(401, 403), auth=False)
```

## IncorrectBody (transport) via ApiClient

Prefer **ApiClient** so coverage still counts:

```python
from partest import TypesTestCases
types = TypesTestCases

await api.make_request(
    "POST", "/items",
    content=b'{"name":',          # broken JSON
    content_type="application/json",
    expected_status_code=(400, 415),
    type=types.request_incorrect_body,
)

await api.make_request(
    "POST", "/items",
    content=b"not-json",
    content_type="text/plain",
    expected_status_code=(400, 415),
    type=types.request_incorrect_body,
)
```

Structured field abuse (missing required / extra props) uses normal `json_data=`
with `type=request_elements` / `request_extra_data`.

## Headers / CSRF-ish probes

```python
from partest.http import Config
cfg = Config()
h = cfg.get_headers(["Accept", "Content-Type"], token=token)
h_no_auth = {k: v for k, v in h.items() if k.lower() != "authorization"}
await api.make_request("GET", "/secure", headers=h_no_auth, expected_status_code=401)
```

## Never in library

Product RBAC matrices, stand admin credentials, SQL injection payloads bound to
schema names, container platform and SSH access — consumer-only.
