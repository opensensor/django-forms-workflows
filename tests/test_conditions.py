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
