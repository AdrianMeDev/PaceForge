"""Validating a week plan: all checks of ``planning.rules`` run, the findings collected.

A plan is *valid* when there is no error; warnings are for the user to weigh. A plan that is not
valid is never confirmed (see ``planning.services``). Nothing here touches the database: the
facts come in as a ``PlanContext``.
"""

from dataclasses import dataclass

from .context import PlanContext
from .rules import ALL_CHECKS, Finding, Severity
from .schema import WeekPlan


@dataclass(frozen=True)
class Report:
    findings: tuple[Finding, ...]

    @property
    def errors(self) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.severity is Severity.ERROR)

    @property
    def warnings(self) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.severity is Severity.WARNING)

    @property
    def valid(self) -> bool:
        return not self.errors


def validate_week(plan: WeekPlan, context: PlanContext) -> Report:
    """The report of all checks, in a stable order: structure, zones and capacity first, then
    rhythm and progression. The same plan and context always give the same report."""
    return Report(tuple(finding for check in ALL_CHECKS for finding in check(plan, context)))
