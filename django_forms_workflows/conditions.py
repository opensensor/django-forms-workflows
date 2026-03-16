"""
Evaluate trigger_conditions against form submission data.

Condition format (same as FormField.conditional_rules):

    {
        "operator": "AND" | "OR",
        "conditions": [
            {
                "field": "field_name",
                "operator": "equals" | "not_equals" | "gt" | "lt" |
                            "gte" | "lte" | "contains" | "in",
                "value": <expected_value>
            },
            ...
        ]
    }

``evaluate_conditions(conditions, data)`` returns ``True`` when the
submission data satisfies the rule set, or when ``conditions`` is
``None`` / empty (unconditional).
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import Any

logger = logging.getLogger(__name__)


def _coerce_numeric(val: Any) -> Decimal | None:
    """Try to coerce a value to Decimal for numeric comparisons."""
    if val is None:
        return None
    try:
        return Decimal(str(val))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _is_empty_value(actual: Any) -> bool:
    """Return True when ``actual`` represents an empty / absent value."""
    if actual is None:
        return True
    if isinstance(actual, str):
        return actual.strip() == ""
    if isinstance(actual, list | dict):
        return len(actual) == 0
    return False


def _evaluate_single(condition: dict, data: dict) -> bool:
    """Evaluate a single condition dict against submission data."""
    field = condition.get("field", "")
    operator = condition.get("operator", "equals")
    expected = condition.get("value")

    actual = data.get(field)

    # Presence / absence operators (no expected value needed)
    if operator == "not_empty":
        return not _is_empty_value(actual)

    if operator == "is_empty":
        return _is_empty_value(actual)

    # Normalise to strings for simple comparisons
    actual_str = str(actual).strip() if actual is not None else ""
    expected_str = str(expected).strip() if expected is not None else ""

    if operator == "equals":
        return actual_str.lower() == expected_str.lower()

    if operator == "not_equals":
        return actual_str.lower() != expected_str.lower()

    if operator == "contains":
        return expected_str.lower() in actual_str.lower()

    if operator == "in":
        # expected should be a list; check if actual is in it
        if isinstance(expected, list):
            return actual_str.lower() in [str(v).strip().lower() for v in expected]
        # Fallback: comma-separated string
        return actual_str.lower() in [
            v.strip().lower() for v in expected_str.split(",")
        ]

    # Numeric comparisons
    actual_num = _coerce_numeric(actual)
    expected_num = _coerce_numeric(expected)
    if actual_num is None or expected_num is None:
        logger.debug(
            "Non-numeric comparison attempted: field=%s op=%s actual=%r expected=%r",
            field,
            operator,
            actual,
            expected,
        )
        return False

    if operator == "gt":
        return actual_num > expected_num
    if operator == "lt":
        return actual_num < expected_num
    if operator == "gte":
        return actual_num >= expected_num
    if operator == "lte":
        return actual_num <= expected_num

    logger.warning("Unknown condition operator: %s", operator)
    return False


def evaluate_conditions(conditions: dict | None, data: dict) -> bool:
    """Evaluate a trigger_conditions rule set against form data.

    Supports two formats:

    *Compound* (multi-condition group)::

        {
            "operator": "AND" | "OR",
            "conditions": [
                {"field": "foo", "operator": "equals", "value": "bar"},
                ...
            ]
        }

    *Simple* (single condition, no wrapping ``conditions`` list)::

        {"field": "foo", "operator": "not_empty"}

    Returns ``True`` when:
    - ``conditions`` is ``None`` or an empty dict (unconditional — always matches)
    - The condition(s) evaluate to True according to the configured logic
    """
    if not conditions:
        return True

    condition_list = conditions.get("conditions")

    # Simple single-condition format: {"field": "...", "operator": "..."}
    if not condition_list:
        if "field" in conditions:
            return _evaluate_single(conditions, data)
        # No conditions key and no field key — unconditional
        return True

    group_operator = conditions.get("operator", "AND").upper()

    results = [_evaluate_single(c, data) for c in condition_list]

    if group_operator == "OR":
        return any(results)
    # Default: AND
    return all(results)
