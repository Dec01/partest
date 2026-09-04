"""Project scaffold generator (G1–G5: API monorepo + UI layout).

Legacy modules ``models_*`` remain for compatibility; new code uses IR + CLI.
"""

from partest.project_gen.emitters.resources import emit_resources
from partest.project_gen.ir import OpIR, ParamIR, SuiteIR, build_ir_from_openapi_dict
from partest.project_gen.openapi_load import load_openapi
from partest.project_gen.ui_layout import build_ui_files

__all__ = [
    "OpIR",
    "ParamIR",
    "SuiteIR",
    "build_ir_from_openapi_dict",
    "load_openapi",
    "emit_resources",
    "build_ui_files",
]
