"""partest — methodology-driven API autotest harness with OpenAPI coverage."""

from partest.access import (
    AccessCase,
    UserActivity,
    access_cases,
    anonymous_headers,
    invalid_bearer_headers,
)
from partest.auth import TokenManager, decode_jwt_payload, jwt_claim
from partest.call_storage import (
    call_count,
    call_meta,
    call_type,
    dump_storage,
    dump_storage_file,
    endpoint_subtype,
    load_storage,
    load_storage_file,
    merge_storage_files,
    reset_storage,
)
from partest.client import (
    ApiClient,
    Delete,
    Get,
    Patch,
    Post,
    Put,
    format_status_mismatch,
    status_matches,
)
from partest.collections import BaseCollection, CollectionsManager
from partest.conf import load_confpartest, require_confpartest, validate_confpartest
from partest.coverage import is_valid_uuid, track_api_calls
from partest.data_marker import (
    TEST_MARKER,
    fill_with_marker,
    marked_code,
    marked_name,
    marked_short,
    prefix_marker,
)
from partest.methods import MethodsList
from partest.payloads import BaseRequestBody
from partest.test_types import (
    CORE_TEST_TYPES,
    PERMISSION_CELLS,
    PERMISSION_CELL_EXPECTATIONS,
    TYPE_LABELS,
    TypesTestCases,
    canonicalize_type,
    permission_cell_label,
)
from partest.tracking import (
    CreatedRegistry,
    TrackingApiClient,
    chain_extractors,
    default_id_extractor,
    field_id_extractor,
    nested_id_extractor,
)
from partest.validation import (
    BaseModelWithConfig,
    BaseResponseValidator,
    ProblemDetailBody,
    ProblemDetailValidation,
    RAW_INCORRECT_BODY_CASES,
    assert_raw_incorrect_body,
)

__version__ = "1.8.0"

# Lazy-friendly optional: security / http always available
from partest.http import Config, HeadersBind  # noqa: E402
from partest.security import RiskProfile, SecHttp, build_tampered_set  # noqa: E402

__all__ = [
    "__version__",
    "ApiClient",
    "Get",
    "Post",
    "Patch",
    "Put",
    "Delete",
    "format_status_mismatch",
    "status_matches",
    "TrackingApiClient",
    "CreatedRegistry",
    "default_id_extractor",
    "nested_id_extractor",
    "field_id_extractor",
    "chain_extractors",
    "TokenManager",
    "decode_jwt_payload",
    "jwt_claim",
    "BaseRequestBody",
    "BaseCollection",
    "CollectionsManager",
    "BaseModelWithConfig",
    "BaseResponseValidator",
    "ProblemDetailBody",
    "ProblemDetailValidation",
    "RAW_INCORRECT_BODY_CASES",
    "assert_raw_incorrect_body",
    "TEST_MARKER",
    "marked_name",
    "marked_code",
    "marked_short",
    "fill_with_marker",
    "prefix_marker",
    "track_api_calls",
    "is_valid_uuid",
    "call_count",
    "call_type",
    "call_meta",
    "endpoint_subtype",
    "reset_storage",
    "dump_storage",
    "load_storage",
    "dump_storage_file",
    "load_storage_file",
    "merge_storage_files",
    "TypesTestCases",
    "PERMISSION_CELLS",
    "AccessCase",
    "UserActivity",
    "access_cases",
    "anonymous_headers",
    "invalid_bearer_headers",
    "PERMISSION_CELL_EXPECTATIONS",
    "permission_cell_label",
    "CORE_TEST_TYPES",
    "TYPE_LABELS",
    "canonicalize_type",
    "MethodsList",
    "Config",
    "HeadersBind",
    "SecHttp",
    "RiskProfile",
    "build_tampered_set",
    "load_confpartest",
    "require_confpartest",
    "validate_confpartest",
]
