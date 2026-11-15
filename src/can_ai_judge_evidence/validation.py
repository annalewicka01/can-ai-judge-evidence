"""Strict parsing of decoded proposals; errors are data, not batch crashes."""
from collections.abc import Mapping
from dataclasses import dataclass

from .domain import MAX_COUNT, Plan, require_integer, require_text


@dataclass(frozen=True)
class ValidationIssue:
    field: str
    code: str
    message: str


def field_issues(raw: Mapping, expected: set[str], prefix: str = '') -> list[ValidationIssue]:
    issues = [ValidationIssue(prefix + key, 'missing_field', 'Required field is absent')
              for key in sorted(expected - set(raw))]
    issues.extend(ValidationIssue(prefix + str(key), 'unknown_field', 'Unexpected field')
                  for key in sorted(set(raw) - expected, key=repr))
    return issues


def parse_plan(raw: object) -> tuple[Plan | None, tuple[ValidationIssue, ...]]:
    if isinstance(raw, Plan):
        return raw, ()
    if not isinstance(raw, Mapping):
        return None, (ValidationIssue('plan', 'wrong_type', 'Expected one plan object'),)
    expected = {'channel', 'population', 'n', 'analysis_month'}
    issues = field_issues(raw, expected)
    for name in sorted(expected & set(raw)):
        try:
            if name in ('channel', 'population'):
                require_text(raw[name], name)
            elif name == 'n':
                require_integer(raw[name], name, minimum=1, maximum=MAX_COUNT)
            else:
                require_integer(raw[name], name)
        except ValueError as exc:
            issues.append(ValidationIssue(name, 'invalid_value', str(exc)))
    if issues:
        return None, tuple(issues)
    return Plan(**raw), ()
