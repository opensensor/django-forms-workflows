"""
Tests for django_forms_workflows.conditions — trigger condition evaluator.
"""

from django_forms_workflows.conditions import (
    _coerce_numeric,
    _evaluate_single,
    _is_empty_value,
    evaluate_conditions,
)

# ── helpers ───────────────────────────────────────────────────────────────


class TestCoerceNumeric:
    def test_int(self):
        assert _coerce_numeric(42) is not None

    def test_str_decimal(self):
        assert _coerce_numeric("3.14") is not None

    def test_none(self):
        assert _coerce_numeric(None) is None

    def test_non_numeric(self):
        assert _coerce_numeric("abc") is None


class TestIsEmptyValue:
    def test_none(self):
        assert _is_empty_value(None) is True

    def test_blank_string(self):
        assert _is_empty_value("  ") is True

    def test_non_empty(self):
        assert _is_empty_value("hello") is False

    def test_empty_list(self):
        assert _is_empty_value([]) is True

    def test_non_empty_list(self):
        assert _is_empty_value([1]) is False

    def test_empty_dict(self):
        assert _is_empty_value({}) is True


# ── _evaluate_single ──────────────────────────────────────────────────────


class TestEvaluateSingle:
    data = {"name": "Alice", "age": "30", "dept": "IT", "notes": ""}

    def test_equals(self):
        cond = {"field": "name", "operator": "equals", "value": "Alice"}
        assert _evaluate_single(cond, self.data) is True

    def test_equals_case_insensitive(self):
        cond = {"field": "name", "operator": "equals", "value": "alice"}
        assert _evaluate_single(cond, self.data) is True

    def test_not_equals(self):
        cond = {"field": "name", "operator": "not_equals", "value": "Bob"}
        assert _evaluate_single(cond, self.data) is True

    def test_contains(self):
        cond = {"field": "name", "operator": "contains", "value": "lic"}
        assert _evaluate_single(cond, self.data) is True

    def test_not_empty(self):
        cond = {"field": "name", "operator": "not_empty"}
        assert _evaluate_single(cond, self.data) is True

    def test_is_empty(self):
        cond = {"field": "notes", "operator": "is_empty"}
        assert _evaluate_single(cond, self.data) is True

    def test_is_empty_missing_field(self):
        cond = {"field": "nonexistent", "operator": "is_empty"}
        assert _evaluate_single(cond, self.data) is True

    def test_in_list(self):
        cond = {"field": "dept", "operator": "in", "value": ["IT", "HR", "Finance"]}
        assert _evaluate_single(cond, self.data) is True

    def test_in_csv(self):
        cond = {"field": "dept", "operator": "in", "value": "IT,HR,Finance"}
        assert _evaluate_single(cond, self.data) is True

    def test_gt(self):
        cond = {"field": "age", "operator": "gt", "value": "25"}
        assert _evaluate_single(cond, self.data) is True

    def test_lt(self):
        cond = {"field": "age", "operator": "lt", "value": "50"}
        assert _evaluate_single(cond, self.data) is True

    def test_gte(self):
        cond = {"field": "age", "operator": "gte", "value": "30"}
        assert _evaluate_single(cond, self.data) is True

    def test_lte(self):
        cond = {"field": "age", "operator": "lte", "value": "30"}
        assert _evaluate_single(cond, self.data) is True

    def test_numeric_comparison_non_numeric_returns_false(self):
        cond = {"field": "name", "operator": "gt", "value": "10"}
        assert _evaluate_single(cond, self.data) is False

    def test_unknown_operator(self):
        cond = {"field": "name", "operator": "foobar", "value": "x"}
        assert _evaluate_single(cond, self.data) is False


# ── evaluate_conditions (compound) ────────────────────────────────────────


class TestEvaluateConditions:
    data = {"status": "active", "amount": "1000", "dept": "IT"}

    def test_none_is_unconditional(self):
        assert evaluate_conditions(None, self.data) is True

    def test_empty_dict_is_unconditional(self):
        assert evaluate_conditions({}, self.data) is True

    def test_simple_single_condition(self):
        cond = {"field": "status", "operator": "equals", "value": "active"}
        assert evaluate_conditions(cond, self.data) is True

    def test_and_all_true(self):
        cond = {
            "operator": "AND",
            "conditions": [
                {"field": "status", "operator": "equals", "value": "active"},
                {"field": "amount", "operator": "gt", "value": "500"},
            ],
        }
        assert evaluate_conditions(cond, self.data) is True

    def test_and_one_false(self):
        cond = {
            "operator": "AND",
            "conditions": [
                {"field": "status", "operator": "equals", "value": "active"},
                {"field": "amount", "operator": "lt", "value": "500"},
            ],
        }
        assert evaluate_conditions(cond, self.data) is False

    def test_or_one_true(self):
        cond = {
            "operator": "OR",
            "conditions": [
                {"field": "status", "operator": "equals", "value": "inactive"},
                {"field": "dept", "operator": "equals", "value": "IT"},
            ],
        }
        assert evaluate_conditions(cond, self.data) is True

    def test_or_all_false(self):
        cond = {
            "operator": "OR",
            "conditions": [
                {"field": "status", "operator": "equals", "value": "inactive"},
                {"field": "dept", "operator": "equals", "value": "HR"},
            ],
        }
        assert evaluate_conditions(cond, self.data) is False

    def test_simple_single_condition_format(self):
        """evaluate_conditions handles the shorthand {'field': ..., 'operator': ...}
        format that omits the wrapping 'conditions' list."""
        cond = {"field": "status", "operator": "equals", "value": "active"}
        assert evaluate_conditions(cond, self.data) is True

    def test_simple_single_condition_format_false(self):
        cond = {"field": "status", "operator": "equals", "value": "inactive"}
        assert evaluate_conditions(cond, self.data) is False

    def test_no_field_no_conditions_is_unconditional(self):
        """A dict with neither 'field' nor 'conditions' keys is unconditional."""
        assert evaluate_conditions({"operator": "AND"}, self.data) is True

    def test_or_all_true_short_circuits(self):
        """OR operator returns True when all conditions are True."""
        cond = {
            "operator": "OR",
            "conditions": [
                {"field": "status", "operator": "equals", "value": "active"},
                {"field": "dept", "operator": "equals", "value": "IT"},
            ],
        }
        assert evaluate_conditions(cond, self.data) is True


# ── Additional _is_empty_value edge cases ─────────────────────────────────


class TestIsEmptyValueEdgeCases:
    def test_whitespace_only_string_is_empty(self):
        from django_forms_workflows.conditions import _is_empty_value

        assert _is_empty_value("   \t\n") is True

    def test_zero_is_not_empty(self):
        from django_forms_workflows.conditions import _is_empty_value

        # Numeric zero should not be treated as empty (it's not None/blank/list)
        assert _is_empty_value(0) is False

    def test_false_is_not_empty(self):
        from django_forms_workflows.conditions import _is_empty_value

        assert _is_empty_value(False) is False


# ── _evaluate_single: in operator edge cases ──────────────────────────────


class TestEvaluateSingleInOperator:
    def test_in_list_case_insensitive(self):
        from django_forms_workflows.conditions import _evaluate_single

        cond = {"field": "dept", "operator": "in", "value": ["IT", "HR"]}
        assert _evaluate_single(cond, {"dept": "it"}) is True

    def test_in_comma_string(self):
        from django_forms_workflows.conditions import _evaluate_single

        cond = {"field": "dept", "operator": "in", "value": "IT, HR, Finance"}
        assert _evaluate_single(cond, {"dept": "Finance"}) is True

    def test_in_missing_field_returns_false(self):
        from django_forms_workflows.conditions import _evaluate_single

        cond = {"field": "missing_field", "operator": "in", "value": ["a", "b"]}
        assert _evaluate_single(cond, {}) is False


# ── _coerce_numeric edge cases ────────────────────────────────────────────


class TestCoerceNumericEdgeCases:
    def test_float_string(self):
        from decimal import Decimal

        from django_forms_workflows.conditions import _coerce_numeric

        assert _coerce_numeric("3.14") == Decimal("3.14")

    def test_integer_value(self):
        from decimal import Decimal

        from django_forms_workflows.conditions import _coerce_numeric

        assert _coerce_numeric(42) == Decimal("42")

    def test_negative_number(self):
        from decimal import Decimal

        from django_forms_workflows.conditions import _coerce_numeric

        assert _coerce_numeric("-5") == Decimal("-5")
