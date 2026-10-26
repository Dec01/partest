"""Counting the steps of a walk — for tests that guard against a walk that never ends.

A recursive walker (``partest.redact._scrub`` and its kin) calls itself through its
module-level name, so a counting wrapper put there with ``monkeypatch`` sees every step. The
wrapper stops the walk the moment it passes its ceiling: a regression — a cycle not cut,
shared references walked once per path — then fails at once instead of hanging the run.

The stop is a ``BaseException``: the package's "never raises" wrappers (``_body_text``,
``_field_value``) catch ``Exception`` and would turn it into a placeholder.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable


class RunawayWalk(BaseException):
    """More steps than the test allows."""


def count_steps(monkeypatch: Any, module: Any, names: Iterable[str], ceiling: int) -> Dict[str, int]:
    """Wrap *names* of *module*; returns ``{"n": steps so far, "ceiling": ...}``.

    Both keys may be reset between walks. Past ``ceiling`` the next step raises
    :class:`RunawayWalk`.
    """
    state = {"n": 0, "ceiling": ceiling}
    for name in names:
        real = getattr(module, name)

        def counting(*args: Any, _real: Any = real, **kwargs: Any) -> Any:
            state["n"] += 1
            if state["n"] > state["ceiling"]:
                raise RunawayWalk(f"more than {state['ceiling']} steps: the walk does not stop")
            return _real(*args, **kwargs)

        monkeypatch.setattr(module, name, counting)
    return state
