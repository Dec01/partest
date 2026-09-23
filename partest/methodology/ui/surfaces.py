"""Surface types (axis A of the UI methodology).

A surface is what a user looks at: a list, a form, a card, the chrome around them.
The axis exists for one reason — **the kind of surface changes which checks are
required**. A type that does not change that set is not a type, it is a synonym, and it
is left out on purpose.

There is deliberately **no classifier here**. On the API side the subtype is derived from
the specification, because a specification exists and is machine-readable. No project has
a machine-readable description of its screens, so the surface type is *declared by the
consumer* next to its own page object::

    from partest.methodology import SurfaceType

    class ClientsPage(BasePage):
        surface = SurfaceType.LIST_TABLE

Guessing the type from markup would be research with unpredictable accuracy, and a wrong
guess here is worse than no guess: it silently swaps in the required set of another kind
of screen, exactly the failure mode the API classifier already has.
"""

from enum import Enum
from typing import Dict


class SurfaceType(str, Enum):
    """Kind of screen, declared by the consumer.

    Six types, each earning its place by requiring a different set of checks: a list is
    the only surface with columns and paging, a form submits where a card only reads, a
    modal cannot survive a reload at all, and a report is the only one where a pixel
    baseline is the cheapest assertion available rather than the last resort.
    """

    LIST_TABLE = "list_table"
    EDIT_FORM = "edit_form"
    ENTITY_CARD = "entity_card"
    NAV_SHELL = "nav_shell"
    MODAL = "modal"
    REPORT_VIEW = "report_view"

    # Fallback: the consumer has not declared a type yet. Symmetric with
    # MethodSubtype.UNKNOWN, and with the same consequence — a generic required set.
    UNKNOWN = "unknown"


SURFACE_LABELS: Dict[SurfaceType, str] = {
    SurfaceType.LIST_TABLE: "LIST / TABLE",
    SurfaceType.EDIT_FORM: "CREATE / EDIT FORM",
    SurfaceType.ENTITY_CARD: "ENTITY CARD",
    SurfaceType.NAV_SHELL: "NAVIGATION SHELL",
    SurfaceType.MODAL: "MODAL DIALOG",
    SurfaceType.REPORT_VIEW: "REPORT VIEW",
    SurfaceType.UNKNOWN: "UNKNOWN",
}

# What each type means, in one line — for report legends and for the reader deciding
# which one to declare. A surface that is two of these at once (a list inside a modal)
# is two surfaces; declare the one whose checks you are writing.
SURFACE_DESCRIPTIONS: Dict[SurfaceType, str] = {
    SurfaceType.LIST_TABLE: (
        "many rows with a column set, filters, sorting and paging; its view state is "
        "something the user configures"
    ),
    SurfaceType.EDIT_FORM: "fields the user fills in and submits, creating or changing one object",
    SurfaceType.ENTITY_CARD: "read-only presentation of a single object",
    SurfaceType.NAV_SHELL: (
        "the chrome: menu, header, breadcrumbs — what every screen is drawn inside"
    ),
    SurfaceType.MODAL: "a dialog over another surface; it disappears on reload",
    SurfaceType.REPORT_VIEW: "aggregates, charts and printable output derived from parameters",
    SurfaceType.UNKNOWN: "not declared",
}


def surface_label(surface: SurfaceType) -> str:
    """Human label for a surface type."""
    return SURFACE_LABELS[SurfaceType(surface)]
