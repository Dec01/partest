"""Project-local partest configuration (not shipped as library defaults).

Copy this file next to your tests and adjust paths.

Coverage modes (LIB-07)
-----------------------
* **Matrix (default):** ``zorro()`` / analyzer use methodology subtype × P1 TC
  from ``partest.methodology`` — ignore flat ``test_types_coverage`` unless you
  pass ``use_matrix=False``.
* **Flat (legacy):** set ``test_types_coverage`` list and call
  ``generate_coverage_report(use_matrix=False)`` or legacy conf paths.

Plugin (LIB-02)
---------------
Pytest entry point ``partest`` is ON by default. Disable dual Allure hooks::

    pytest_plugin = False
    # or env: PARTEST_PYTEST_PLUGIN=0
    # or CLI: pytest -p no:partest

This flag covers the Allure side only. What the run selected is recorded separately and
stays on when the Allure hooks are off — that is deliberate, see ``run_metadata`` below.
"""

# TLS. Certificates are verified by default. A stand with a self-signed certificate needs
# one of these — and then every response in the run comes from whoever answered, which is
# why turning it off warns once per process.
#
#     tls_verify = False
#     tls_verify = "/etc/ssl/corp-ca.pem"   # better: trust your own CA, keep checking
#
# The environment wins over this file: PARTEST_TLS_VERIFY=0 or a bundle path. Note that the
# same switch covers loading the specification, and that host is often a different one.

# Run metadata (the half the plugin flag no longer hides). On by default: recording which
# tests a run selected writes nothing to Allure and nothing to disk, and without it a
# marker-filtered run is indistinguishable from a full one in the report.
#
#     run_metadata = False
#     # or env: PARTEST_RUN_METADATA=0

# OpenAPI sources: name -> [source_type, path_or_url]
# source_type: 'local' | 'url'
swagger_files = {
    # Example (relative path from project root):
    # 'petstore': ['url', 'https://petstore.swagger.io/v2/swagger.json'],
    # 'service': ['local', 'docs/openapi.yaml'],
}

# Legacy flat list used when generate_coverage_report(use_matrix=False).
# Prefer methodology matrix (default use_matrix=True).
test_types_coverage = [
    "request_default",
    "request_not_allowed",
    "request_params",
]

# Types that mark an endpoint as 100% covered (e.g. health-only).
test_types_exception = [
    "health",
]

# Optional: disable auto Allure title / failure_summary plugin
# pytest_plugin = False

