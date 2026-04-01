"""
Tests for DynamicForm and ApprovalStepForm.
"""

from datetime import date
from decimal import Decimal

import pytest
from django import forms as dj_forms

from django_forms_workflows.forms import ApprovalStepForm, DynamicForm
from django_forms_workflows.models import (
    ApprovalTask,
    FormField,
    PrefillSource,
    SharedOptionList,
    WorkflowDefinition,
    WorkflowStage,
)


class TestDynamicFormFieldGeneration:
    """Test that DynamicForm correctly generates Django form fields."""

    def test_text_field(self, form_with_fields, user):
        form = DynamicForm(form_with_fields, user=user)
        assert "full_name" in form.fields
        assert form.fields["full_name"].required is True

    def test_email_field(self, form_with_fields, user):
        form = DynamicForm(form_with_fields, user=user)
        assert "email" in form.fields

    def test_select_field(self, form_with_fields, user):
        form = DynamicForm(form_with_fields, user=user)
        field = form.fields["department"]
        choices = field.choices
        # First choice is the blank placeholder
        assert choices[0] == ("", "-- Select --")
        assert ("hr", "Human Resources") in choices

    def test_decimal_field(self, form_with_fields, user):
        form = DynamicForm(form_with_fields, user=user)
        field = form.fields["amount"]
        assert field.min_value == Decimal("0")
        assert field.max_value == Decimal("10000")

    def test_textarea_field(self, form_with_fields, user):
        form = DynamicForm(form_with_fields, user=user)
        assert "notes" in form.fields

    def test_excludes_stage_scoped_fields(self, form_definition, user):
        wf = WorkflowDefinition.objects.create(
            form_definition=form_definition, requires_approval=True
        )
        stage = WorkflowStage.objects.create(workflow=wf, name="Review", order=1)
        FormField.objects.create(
            form_definition=form_definition,
            field_name="submitter_name",
            field_label="Name",
            field_type="text",
            order=1,
        )
        FormField.objects.create(
            form_definition=form_definition,
            field_name="approver_notes",
            field_label="Approver Notes",
            field_type="text",
            order=2,
            workflow_stage=stage,
        )
        form = DynamicForm(form_definition, user=user)
        assert "submitter_name" in form.fields
        assert "approver_notes" not in form.fields

    def test_excludes_section_headers(self, form_definition, user):
        FormField.objects.create(
            form_definition=form_definition,
            field_name="section_header",
            field_label="Section",
            field_type="section",
            order=1,
        )
        FormField.objects.create(
            form_definition=form_definition,
            field_name="text_field",
            field_label="Text",
            field_type="text",
            order=2,
        )
        form = DynamicForm(form_definition, user=user)
        assert "section_header" not in form.fields
        assert "text_field" in form.fields

    def test_all_field_types(self, form_definition, user):
        """Verify each field type creates the correct Django field."""
        types_to_test = [
            ("phone", "Phone Test", "phone"),
            ("number", "Number Test", "number"),
            ("date", "Date Test", "date"),
            ("datetime", "DateTime Test", "datetime"),
            ("time", "Time Test", "time"),
            ("url", "URL Test", "url"),
            ("checkbox", "Check Test", "checkbox"),
            ("hidden", "Hidden Test", "hidden"),
            ("file", "File Test", "file"),
        ]
        for i, (ftype, label, name) in enumerate(types_to_test):
            FormField.objects.create(
                form_definition=form_definition,
                field_name=name,
                field_label=label,
                field_type=ftype,
                order=10 + i,
            )
        form = DynamicForm(form_definition, user=user)
        for _, _, name in types_to_test:
            assert name in form.fields, f"Field {name} not found in form"


class TestDynamicFormChoices:
    def test_json_choices(self, form_definition, user):
        FormField.objects.create(
            form_definition=form_definition,
            field_name="color",
            field_label="Color",
            field_type="select",
            order=1,
            choices=[
                {"value": "red", "label": "Red"},
                {"value": "blue", "label": "Blue"},
            ],
        )
        form = DynamicForm(form_definition, user=user)
        choices = form.fields["color"].choices
        assert ("red", "Red") in choices

    def test_comma_separated_choices(self, form_definition, user):
        FormField.objects.create(
            form_definition=form_definition,
            field_name="size",
            field_label="Size",
            field_type="radio",
            order=1,
            choices="Small, Medium, Large",
        )
        form = DynamicForm(form_definition, user=user)
        choices = form.fields["size"].choices
        assert ("Small", "Small") in choices
        assert ("Large", "Large") in choices

    def test_empty_choices(self, form_definition, user):
        form = DynamicForm(form_definition, user=user)
        result = form._parse_choices(None)
        assert result == []
        result = form._parse_choices("")
        assert result == []


class TestSharedOptionListChoices:
    """Test that SharedOptionList integrates correctly with choice resolution."""

    def test_shared_option_list_overrides_inline_choices(self, form_definition, user):
        sol = SharedOptionList.objects.create(
            name="Departments",
            slug="departments",
            items=[
                {"value": "eng", "label": "Engineering"},
                {"value": "mkt", "label": "Marketing"},
            ],
        )
        FormField.objects.create(
            form_definition=form_definition,
            field_name="dept",
            field_label="Department",
            field_type="select",
            order=1,
            choices="Should,Be,Ignored",
            shared_option_list=sol,
        )
        form = DynamicForm(form_definition, user=user)
        choices = form.fields["dept"].choices
        # First choice is the blank placeholder
        assert choices[0] == ("", "-- Select --")
        assert ("eng", "Engineering") in choices
        assert ("mkt", "Marketing") in choices
        # Inline choices should NOT appear
        assert ("Should", "Should") not in choices

    def test_shared_option_list_with_radio(self, form_definition, user):
        sol = SharedOptionList.objects.create(
            name="Sizes",
            slug="sizes",
            items=["Small", "Medium", "Large"],
        )
        FormField.objects.create(
            form_definition=form_definition,
            field_name="size",
            field_label="Size",
            field_type="radio",
            order=1,
            shared_option_list=sol,
        )
        form = DynamicForm(form_definition, user=user)
        choices = form.fields["size"].choices
        assert ("Small", "Small") in choices
        assert ("Large", "Large") in choices

    def test_shared_option_list_with_checkboxes(self, form_definition, user):
        sol = SharedOptionList.objects.create(
            name="Skills",
            slug="skills",
            items=["Python", "Django", "JavaScript"],
        )
        FormField.objects.create(
            form_definition=form_definition,
            field_name="skills",
            field_label="Skills",
            field_type="checkboxes",
            order=1,
            shared_option_list=sol,
        )
        form = DynamicForm(form_definition, user=user)
        choices = form.fields["skills"].choices
        assert ("Python", "Python") in choices
        assert ("Django", "Django") in choices

    def test_no_shared_list_falls_back_to_inline(self, form_definition, user):
        FormField.objects.create(
            form_definition=form_definition,
            field_name="color",
            field_label="Color",
            field_type="select",
            order=1,
            choices=[
                {"value": "red", "label": "Red"},
                {"value": "blue", "label": "Blue"},
            ],
        )
        form = DynamicForm(form_definition, user=user)
        choices = form.fields["color"].choices
        assert ("red", "Red") in choices

    def test_deleted_shared_list_falls_back_to_inline(self, form_definition, user):
        sol = SharedOptionList.objects.create(
            name="Temp", slug="temp", items=["A", "B"]
        )
        field = FormField.objects.create(
            form_definition=form_definition,
            field_name="pick",
            field_label="Pick",
            field_type="select",
            order=1,
            choices="X, Y, Z",
            shared_option_list=sol,
        )
        sol.delete()
        field.refresh_from_db()
        form = DynamicForm(form_definition, user=user)
        choices = form.fields["pick"].choices
        # Should fall back to inline choices
        assert ("X", "X") in choices


class TestDynamicFormPrefill:
    def test_initial_data_takes_precedence(self, form_with_fields, user):
        initial = {"full_name": "Override Name"}
        form = DynamicForm(form_with_fields, user=user, initial_data=initial)
        assert form.fields["full_name"].initial == "Override Name"

    def test_user_prefill(self, form_definition, user, prefill_source):
        FormField.objects.create(
            form_definition=form_definition,
            field_name="email_pf",
            field_label="Email",
            field_type="email",
            order=1,
            prefill_source_config=prefill_source,
        )
        form = DynamicForm(form_definition, user=user)
        assert form.fields["email_pf"].initial == "test@example.com"

    def test_current_date_prefill(self, form_definition, user):
        ps = PrefillSource.objects.create(
            name="Current Date",
            source_type="system",
            source_key="current_date",
        )
        FormField.objects.create(
            form_definition=form_definition,
            field_name="today",
            field_label="Today",
            field_type="date",
            order=1,
            prefill_source_config=ps,
        )
        form = DynamicForm(form_definition, user=user)
        assert form.fields["today"].initial == date.today()

    def test_default_value_fallback(self, form_definition, user):
        FormField.objects.create(
            form_definition=form_definition,
            field_name="defaulted",
            field_label="Defaulted",
            field_type="text",
            order=1,
            default_value="fallback",
        )
        form = DynamicForm(form_definition, user=user)
        assert form.fields["defaulted"].initial == "fallback"


class TestDynamicFormConditionalValidation:
    """Tests for the server-side clean() conditional validation logic."""

    def _make_trigger_field(self, form_definition, choices=None):
        return FormField.objects.create(
            form_definition=form_definition,
            field_name="travel_type",
            field_label="Type of Travel",
            field_type="select",
            order=1,
            required=True,
            choices=choices
            or [
                {"value": "domestic", "label": "Domestic"},
                {"value": "international", "label": "International"},
            ],
        )

    def test_hidden_field_bypasses_required(self, form_definition, user):
        """A required field with a 'show' rule is not enforced when hidden."""
        self._make_trigger_field(form_definition)
        FormField.objects.create(
            form_definition=form_definition,
            field_name="advisor",
            field_label="Advisor",
            field_type="text",
            order=2,
            required=False,  # DB flag is False; frontend enforces via 'require' rule
            conditional_rules={
                "operator": "AND",
                "conditions": [
                    {
                        "field": "travel_type",
                        "operator": "equals",
                        "value": "international",
                    }
                ],
                "action": "show",
            },
        )
        # Submit with domestic – advisor field should be hidden, no error expected.
        form = DynamicForm(
            form_definition,
            user=user,
            data={"travel_type": "domestic", "advisor": ""},
        )
        assert form.is_valid(), form.errors

    def test_visible_field_enforces_required(self, form_definition, user):
        """When the show condition IS met the field must still validate normally."""
        self._make_trigger_field(form_definition)
        FormField.objects.create(
            form_definition=form_definition,
            field_name="advisor",
            field_label="Advisor",
            field_type="text",
            order=2,
            required=True,
            conditional_rules={
                "operator": "AND",
                "conditions": [
                    {
                        "field": "travel_type",
                        "operator": "equals",
                        "value": "international",
                    }
                ],
                "action": "show",
            },
        )
        # Submit with international but leave advisor empty – should fail.
        form = DynamicForm(
            form_definition,
            user=user,
            data={"travel_type": "international", "advisor": ""},
        )
        assert not form.is_valid()
        assert "advisor" in form.errors

    def test_hide_action_clears_required_error(self, form_definition, user):
        """A 'hide' rule removes required errors when the hide condition is met."""
        self._make_trigger_field(form_definition)
        FormField.objects.create(
            form_definition=form_definition,
            field_name="visa_number",
            field_label="Visa Number",
            field_type="text",
            order=2,
            required=True,
            conditional_rules={
                "operator": "AND",
                "conditions": [
                    {
                        "field": "travel_type",
                        "operator": "equals",
                        "value": "domestic",
                    }
                ],
                "action": "hide",
            },
        )
        # domestic → visa_number is hidden → required error should be suppressed.
        form = DynamicForm(
            form_definition,
            user=user,
            data={"travel_type": "domestic", "visa_number": ""},
        )
        assert form.is_valid(), form.errors

    def test_require_action_enforces_required(self, form_definition, user):
        """A 'require' rule adds a required error when its condition is met."""
        self._make_trigger_field(form_definition)
        FormField.objects.create(
            form_definition=form_definition,
            field_name="admissions_counselor",
            field_label="Admissions Counselor",
            field_type="text",
            order=2,
            required=False,  # not required by default
            conditional_rules={
                "operator": "AND",
                "conditions": [
                    {
                        "field": "travel_type",
                        "operator": "equals",
                        "value": "international",
                    }
                ],
                "action": "require",
            },
        )
        # international → counselor becomes required → missing value should fail.
        form = DynamicForm(
            form_definition,
            user=user,
            data={"travel_type": "international", "admissions_counselor": ""},
        )
        assert not form.is_valid()
        assert "admissions_counselor" in form.errors

    def test_require_action_not_enforced_when_hidden(self, form_definition, user):
        """A 'require' rule is not enforced when its condition is not met."""
        self._make_trigger_field(form_definition)
        FormField.objects.create(
            form_definition=form_definition,
            field_name="admissions_counselor",
            field_label="Admissions Counselor",
            field_type="text",
            order=2,
            required=False,
            conditional_rules={
                "operator": "AND",
                "conditions": [
                    {
                        "field": "travel_type",
                        "operator": "equals",
                        "value": "international",
                    }
                ],
                "action": "require",
            },
        )
        # domestic → counselor is NOT required → should pass without a value.
        form = DynamicForm(
            form_definition,
            user=user,
            data={"travel_type": "domestic", "admissions_counselor": ""},
        )
        assert form.is_valid(), form.errors

    def test_hidden_field_dropped_from_cleaned_data(self, form_definition, user):
        """Hidden fields must not appear in cleaned_data after validation."""
        self._make_trigger_field(form_definition)
        FormField.objects.create(
            form_definition=form_definition,
            field_name="advisor",
            field_label="Advisor",
            field_type="text",
            order=2,
            required=False,
            conditional_rules={
                "operator": "AND",
                "conditions": [
                    {
                        "field": "travel_type",
                        "operator": "equals",
                        "value": "international",
                    }
                ],
                "action": "show",
            },
        )
        form = DynamicForm(
            form_definition,
            user=user,
            data={"travel_type": "domestic", "advisor": "some value"},
        )
        assert form.is_valid(), form.errors
        assert "advisor" not in form.cleaned_data

    def test_list_of_rules_all_evaluated(self, form_definition, user):
        """conditional_rules stored as a list: all rules are checked."""
        self._make_trigger_field(form_definition)
        FormField.objects.create(
            form_definition=form_definition,
            field_name="special_field",
            field_label="Special Field",
            field_type="text",
            order=2,
            required=True,
            conditional_rules=[
                {
                    "operator": "AND",
                    "conditions": [
                        {
                            "field": "travel_type",
                            "operator": "equals",
                            "value": "international",
                        }
                    ],
                    "action": "show",
                }
            ],
        )
        # domestic → field hidden → no required error.
        form = DynamicForm(
            form_definition,
            user=user,
            data={"travel_type": "domestic", "special_field": ""},
        )
        assert form.is_valid(), form.errors


class TestDynamicFormValidation:
    def test_regex_validation(self, form_definition, user):
        FormField.objects.create(
            form_definition=form_definition,
            field_name="code",
            field_label="Code",
            field_type="text",
            order=1,
            regex_validation=r"^[A-Z]{3}$",
            regex_error_message="Must be 3 uppercase letters",
        )
        form = DynamicForm(form_definition, user=user, data={"code": "abc"})
        assert not form.is_valid()
        form = DynamicForm(form_definition, user=user, data={"code": "ABC"})
        assert form.is_valid()

    def test_readonly_not_required(self, form_definition, user):
        FormField.objects.create(
            form_definition=form_definition,
            field_name="ro_field",
            field_label="Read Only",
            field_type="text",
            order=1,
            required=True,
            readonly=True,
        )
        form = DynamicForm(form_definition, user=user)
        assert form.fields["ro_field"].required is False


class TestDynamicFormLayout:
    def _layout_has_submit(self, layout, name):
        """Recursively check if layout contains a Submit with given name."""
        from crispy_forms.layout import Submit

        for field in layout.fields:
            if isinstance(field, Submit) and field.name == name:
                return True
            if hasattr(field, "fields"):
                if self._layout_has_submit(field, name):
                    return True
        return False

    def test_draft_button(self, form_with_fields, user):
        form = DynamicForm(form_with_fields, user=user)
        assert self._layout_has_submit(form.helper.layout, "save_draft")

    def test_no_draft_button(self, form_definition, user):
        form_definition.allow_save_draft = False
        form_definition.save()
        FormField.objects.create(
            form_definition=form_definition,
            field_name="f1",
            field_label="F1",
            field_type="text",
            order=1,
        )
        form = DynamicForm(form_definition, user=user)
        assert not self._layout_has_submit(form.helper.layout, "save_draft")

    def test_form_id(self, form_with_fields, user):
        form = DynamicForm(form_with_fields, user=user)
        assert form.helper.form_id == "form_test-form"


class TestDynamicFormEnhancements:
    def test_enhancements_config_basic(self, form_with_fields, user):
        config = DynamicForm(form_with_fields, user=user).get_enhancements_config()
        assert "autoSaveEnabled" in config
        assert "conditionalRules" in config
        assert "validationRules" in config

    def test_conditional_rules(self, form_definition, user):
        FormField.objects.create(
            form_definition=form_definition,
            field_name="trigger",
            field_label="Trigger",
            field_type="select",
            order=1,
            choices=[
                {"value": "yes", "label": "Yes"},
                {"value": "no", "label": "No"},
            ],
        )
        FormField.objects.create(
            form_definition=form_definition,
            field_name="dependent",
            field_label="Dependent",
            field_type="text",
            order=2,
            conditional_rules={
                "operator": "AND",
                "conditions": [
                    {"field": "trigger", "operator": "equals", "value": "yes"}
                ],
                "action": "show",
            },
        )
        form = DynamicForm(form_definition, user=user)
        config = form.get_enhancements_config()
        rules = config["conditionalRules"]
        assert len(rules) == 1
        assert rules[0]["targetField"] == "dependent"

    def test_validation_rules_output(self, form_with_fields, user):
        form = DynamicForm(form_with_fields, user=user)
        config = form.get_enhancements_config()
        rules = config["validationRules"]
        # full_name is required, should generate a required rule
        name_rules = [r for r in rules if r["field"] == "full_name"]
        assert len(name_rules) == 1
        assert any(r["type"] == "required" for r in name_rules[0]["rules"])

    def test_min_max_value_rules(self, form_with_fields, user):
        form = DynamicForm(form_with_fields, user=user)
        config = form.get_enhancements_config()
        rules = config["validationRules"]
        amount_rules = [r for r in rules if r["field"] == "amount"]
        assert len(amount_rules) == 1
        rule_types = {r["type"] for r in amount_rules[0]["rules"]}
        assert "min_value" in rule_types
        assert "max_value" in rule_types


class TestApprovalStepForm:
    def _make_stage_and_task(self, form_definition, submission, group):
        wf = WorkflowDefinition.objects.create(
            form_definition=form_definition, requires_approval=True
        )
        stage = WorkflowStage.objects.create(workflow=wf, name="Review", order=1)
        stage.approval_groups.add(group)
        task = ApprovalTask.objects.create(
            submission=submission,
            assigned_group=group,
            step_name="Review",
            status="pending",
            workflow_stage=stage,
        )
        return stage, task

    def test_stage_fields(self, form_definition, submission, approval_group, user):
        stage, task = self._make_stage_and_task(
            form_definition, submission, approval_group
        )
        FormField.objects.create(
            form_definition=form_definition,
            field_name="approver_name",
            field_label="Approver Name",
            field_type="text",
            order=100,
            workflow_stage=stage,
        )
        form = ApprovalStepForm(form_definition, submission, task, user=user)
        assert "approver_name" in form.fields
        # Auto-fill approver name
        assert form.fields["approver_name"].initial == "Test User"

    def test_date_auto_fill(self, form_definition, submission, approval_group, user):
        stage, task = self._make_stage_and_task(
            form_definition, submission, approval_group
        )
        FormField.objects.create(
            form_definition=form_definition,
            field_name="approval_date",
            field_label="Approval Date",
            field_type="date",
            order=100,
            workflow_stage=stage,
        )
        form = ApprovalStepForm(form_definition, submission, task, user=user)
        assert form.fields["approval_date"].initial == date.today()

    def test_get_updated_form_data(
        self, form_definition, submission, approval_group, user
    ):
        stage, task = self._make_stage_and_task(
            form_definition, submission, approval_group
        )
        FormField.objects.create(
            form_definition=form_definition,
            field_name="reviewer_notes",
            field_label="Notes",
            field_type="text",
            order=100,
            workflow_stage=stage,
            required=False,
        )
        form = ApprovalStepForm(
            form_definition,
            submission,
            task,
            user=user,
            data={"reviewer_notes": "Looks good"},
        )
        assert form.is_valid()
        updated = form.get_updated_form_data()
        assert updated["reviewer_notes"] == "Looks good"
        # Original data preserved
        assert updated["full_name"] == "Test User"


# ── File field validators ────────────────────────────────────────────────


class TestMaxFileSizeValidator:
    def test_accepts_small_file(self):
        from django_forms_workflows.forms import MaxFileSizeValidator

        validator = MaxFileSizeValidator(5)  # 5 MB

        class FakeFile:
            size = 1 * 1024 * 1024  # 1 MB

        # Should not raise
        validator(FakeFile())

    def test_rejects_large_file(self):
        from django.core.exceptions import ValidationError

        from django_forms_workflows.forms import MaxFileSizeValidator

        validator = MaxFileSizeValidator(2)  # 2 MB

        class FakeFile:
            size = 5 * 1024 * 1024  # 5 MB

        with pytest.raises(ValidationError):
            validator(FakeFile())

    def test_equality(self):
        from django_forms_workflows.forms import MaxFileSizeValidator

        assert MaxFileSizeValidator(5) == MaxFileSizeValidator(5)
        assert MaxFileSizeValidator(5) != MaxFileSizeValidator(10)


class TestBuildFileValidators:
    def test_no_restrictions(self, form_definition):
        from django_forms_workflows.forms import _build_file_validators

        field = FormField.objects.create(
            form_definition=form_definition,
            field_name="doc",
            field_label="Document",
            field_type="file",
            order=1,
        )
        validators = _build_file_validators(field)
        assert validators == []

    def test_extension_only(self, form_definition):
        from django.core.validators import FileExtensionValidator

        from django_forms_workflows.forms import _build_file_validators

        field = FormField.objects.create(
            form_definition=form_definition,
            field_name="doc",
            field_label="Document",
            field_type="file",
            order=1,
            allowed_extensions="pdf,doc,docx",
        )
        validators = _build_file_validators(field)
        assert len(validators) == 1
        assert isinstance(validators[0], FileExtensionValidator)

    def test_size_only(self, form_definition):
        from django_forms_workflows.forms import (
            MaxFileSizeValidator,
            _build_file_validators,
        )

        field = FormField.objects.create(
            form_definition=form_definition,
            field_name="doc",
            field_label="Document",
            field_type="file",
            order=1,
            max_file_size_mb=10,
        )
        validators = _build_file_validators(field)
        assert len(validators) == 1
        assert isinstance(validators[0], MaxFileSizeValidator)

    def test_both_restrictions(self, form_definition):
        from django_forms_workflows.forms import _build_file_validators

        field = FormField.objects.create(
            form_definition=form_definition,
            field_name="doc",
            field_label="Document",
            field_type="file",
            order=1,
            allowed_extensions="pdf",
            max_file_size_mb=5,
        )
        validators = _build_file_validators(field)
        assert len(validators) == 2


class TestFileFieldAcceptAttribute:
    def test_accept_attr_set(self, form_definition, user):
        FormField.objects.create(
            form_definition=form_definition,
            field_name="upload",
            field_label="Upload",
            field_type="file",
            order=1,
            allowed_extensions="pdf,docx",
        )
        form = DynamicForm(form_definition, user=user)
        widget = form.fields["upload"].widget
        assert "accept" in widget.attrs
        assert ".pdf" in widget.attrs["accept"]
        assert ".docx" in widget.attrs["accept"]

    def test_no_accept_attr_when_no_extensions(self, form_definition, user):
        FormField.objects.create(
            form_definition=form_definition,
            field_name="upload",
            field_label="Upload",
            field_type="file",
            order=1,
        )
        form = DynamicForm(form_definition, user=user)
        widget = form.fields["upload"].widget
        assert widget.attrs.get("accept") is None


class TestFileValidationRulesInConfig:
    def test_file_type_rule_emitted(self, form_definition, user):
        FormField.objects.create(
            form_definition=form_definition,
            field_name="upload",
            field_label="Upload",
            field_type="file",
            order=1,
            allowed_extensions="pdf,doc",
        )
        form = DynamicForm(form_definition, user=user)
        config = form.get_enhancements_config()
        rules = config["validationRules"]
        upload_rules = [r for r in rules if r["field"] == "upload"]
        assert len(upload_rules) == 1
        type_rules = [r for r in upload_rules[0]["rules"] if r["type"] == "file_type"]
        assert len(type_rules) == 1
        assert "pdf" in type_rules[0]["value"]

    def test_file_size_rule_emitted(self, form_definition, user):
        FormField.objects.create(
            form_definition=form_definition,
            field_name="upload",
            field_label="Upload",
            field_type="file",
            order=1,
            max_file_size_mb=10,
        )
        form = DynamicForm(form_definition, user=user)
        config = form.get_enhancements_config()
        rules = config["validationRules"]
        upload_rules = [r for r in rules if r["field"] == "upload"]
        assert len(upload_rules) == 1
        size_rules = [r for r in upload_rules[0]["rules"] if r["type"] == "file_size"]
        assert len(size_rules) == 1
        assert size_rules[0]["value"] == 10

    def test_no_file_rules_for_non_file(self, form_with_fields, user):
        form = DynamicForm(form_with_fields, user=user)
        config = form.get_enhancements_config()
        rules = config["validationRules"]
        for r in rules:
            for rule in r["rules"]:
                assert rule["type"] not in ("file_type", "file_size")


# ── Signature field ─────────────────────────────────────────────────────


class TestSignatureFieldDynamicForm:
    """Tests for signature field type in DynamicForm."""

    SAMPLE_SIGNATURE = (
        "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAf"
        "FcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    )

    def test_signature_field_created(self, form_definition, user):
        """A signature field should produce a CharField with HiddenInput."""
        FormField.objects.create(
            form_definition=form_definition,
            field_name="sig",
            field_label="Your Signature",
            field_type="signature",
            order=1,
            required=True,
        )
        form = DynamicForm(form_definition, user=user)
        assert "sig" in form.fields
        field = form.fields["sig"]
        assert field.required is True
        assert field.label == "Your Signature"
        # Widget should be HiddenInput with the data-signature-field attr
        assert field.widget.attrs.get("data-signature-field") == "sig"

    def test_signature_field_not_required(self, form_definition, user):
        FormField.objects.create(
            form_definition=form_definition,
            field_name="opt_sig",
            field_label="Optional Signature",
            field_type="signature",
            order=1,
            required=False,
        )
        form = DynamicForm(form_definition, user=user)
        assert form.fields["opt_sig"].required is False

    def test_signature_valid_with_data(self, form_definition, user):
        FormField.objects.create(
            form_definition=form_definition,
            field_name="sig",
            field_label="Signature",
            field_type="signature",
            order=1,
            required=True,
        )
        form = DynamicForm(
            form_definition, user=user, data={"sig": self.SAMPLE_SIGNATURE}
        )
        assert form.is_valid(), form.errors

    def test_signature_invalid_when_required_and_empty(self, form_definition, user):
        FormField.objects.create(
            form_definition=form_definition,
            field_name="sig",
            field_label="Signature",
            field_type="signature",
            order=1,
            required=True,
        )
        form = DynamicForm(form_definition, user=user, data={"sig": ""})
        assert not form.is_valid()
        assert "sig" in form.errors


class TestNewFieldTypes:
    """Tests for the four new field types: rating, slider, address, matrix."""

    def test_rating_field_creates_choice_field(self, form_definition, user):
        FormField.objects.create(
            form_definition=form_definition,
            field_name="satisfaction",
            field_label="Satisfaction",
            field_type="rating",
            order=1,
            max_value=5,
        )
        form = DynamicForm(form_definition, user=user)
        field = form.fields["satisfaction"]
        assert isinstance(field, dj_forms.ChoiceField)
        choice_values = [v for v, _ in field.choices if v]
        assert "1" in choice_values
        assert "5" in choice_values

    def test_rating_field_default_max_5_stars(self, form_definition, user):
        """Rating field with no max_value defaults to 5 stars."""
        FormField.objects.create(
            form_definition=form_definition,
            field_name="rating",
            field_label="Rating",
            field_type="rating",
            order=1,
        )
        form = DynamicForm(form_definition, user=user)
        non_blank = [(v, lbl) for v, lbl in form.fields["rating"].choices if v]
        assert len(non_blank) == 5

    def test_rating_field_custom_max_stars(self, form_definition, user):
        """Rating field with max_value=3 produces exactly 3 choices."""
        FormField.objects.create(
            form_definition=form_definition,
            field_name="nps",
            field_label="NPS",
            field_type="rating",
            order=1,
            max_value=3,
        )
        form = DynamicForm(form_definition, user=user)
        non_blank = [(v, lbl) for v, lbl in form.fields["nps"].choices if v]
        assert len(non_blank) == 3

    def test_slider_field_creates_decimal_field(self, form_definition, user):
        FormField.objects.create(
            form_definition=form_definition,
            field_name="volume",
            field_label="Volume",
            field_type="slider",
            order=1,
            min_value=0,
            max_value=100,
        )
        form = DynamicForm(form_definition, user=user)
        field = form.fields["volume"]
        assert isinstance(field, dj_forms.DecimalField)
        assert field.widget.attrs.get("data-slider-field") == "true"
        # class includes "form-range" marker (strip since there may be trailing space)
        assert "form-range" in field.widget.attrs.get("class", "")

    def test_slider_field_respects_min_max(self, form_definition, user):
        """Slider field min/max are passed through to the DecimalField validators."""
        from decimal import Decimal

        FormField.objects.create(
            form_definition=form_definition,
            field_name="pct",
            field_label="Percentage",
            field_type="slider",
            order=1,
            min_value=10,
            max_value=90,
        )
        form = DynamicForm(form_definition, user=user)
        field = form.fields["pct"]
        # DecimalField stores min/max as Decimal for validation
        assert field.min_value == Decimal("10")
        assert field.max_value == Decimal("90")

    def test_address_field_creates_char_with_textarea(self, form_definition, user):
        FormField.objects.create(
            form_definition=form_definition,
            field_name="home_address",
            field_label="Home Address",
            field_type="address",
            order=1,
        )
        form = DynamicForm(form_definition, user=user)
        field = form.fields["home_address"]
        assert isinstance(field, dj_forms.CharField)
        assert isinstance(field.widget, dj_forms.Textarea)
        assert field.widget.attrs.get("data-address-field") == "true"

    def test_address_field_max_length(self, form_definition, user):
        FormField.objects.create(
            form_definition=form_definition,
            field_name="addr",
            field_label="Address",
            field_type="address",
            order=1,
        )
        form = DynamicForm(form_definition, user=user)
        assert form.fields["addr"].max_length == 500

    def test_matrix_field_creates_subfields(self, form_definition, user):
        FormField.objects.create(
            form_definition=form_definition,
            field_name="skills",
            field_label="Skills",
            field_type="matrix",
            order=1,
            choices={"rows": ["Python", "Django"], "columns": ["Novice", "Expert"]},
        )
        form = DynamicForm(form_definition, user=user)
        # Hidden marker field
        assert "skills" in form.fields
        assert isinstance(form.fields["skills"].widget, dj_forms.HiddenInput)
        assert form.fields["skills"].widget.attrs.get("data-matrix-field") == "true"
        # One sub-field per row
        assert "skills__Python" in form.fields
        assert "skills__Django" in form.fields

    def test_matrix_subfield_choices_match_columns(self, form_definition, user):
        FormField.objects.create(
            form_definition=form_definition,
            field_name="agree",
            field_label="Agreement",
            field_type="matrix",
            order=1,
            choices={
                "rows": ["Statement A"],
                "columns": ["Agree", "Neutral", "Disagree"],
            },
        )
        form = DynamicForm(form_definition, user=user)
        sub = form.fields["agree__Statement A"]
        col_values = [v for v, _ in sub.choices if v]
        assert col_values == ["Agree", "Neutral", "Disagree"]

    def test_matrix_field_no_config_fallback_textarea(self, form_definition, user):
        """Matrix field with no rows/columns falls back to a Textarea."""
        FormField.objects.create(
            form_definition=form_definition,
            field_name="matrix_no_cfg",
            field_label="Matrix",
            field_type="matrix",
            order=1,
            choices=None,
        )
        form = DynamicForm(form_definition, user=user)
        assert "matrix_no_cfg" in form.fields
        assert isinstance(form.fields["matrix_no_cfg"].widget, dj_forms.Textarea)


class TestDynamicFormCaptcha:
    """Tests for CAPTCHA field injection and server-side verification."""

    def test_captcha_field_added_when_enabled(self, form_definition, user):
        form_definition.enable_captcha = True
        form_definition.save()
        FormField.objects.create(
            form_definition=form_definition,
            field_name="name",
            field_label="Name",
            field_type="text",
            order=1,
        )
        form = DynamicForm(form_definition, user=user)
        assert "captcha_token" in form.fields
        assert isinstance(form.fields["captcha_token"].widget, dj_forms.HiddenInput)

    def test_captcha_field_not_added_when_disabled(self, form_definition, user):
        form_definition.enable_captcha = False
        form_definition.save()
        FormField.objects.create(
            form_definition=form_definition,
            field_name="name",
            field_label="Name",
            field_type="text",
            order=1,
        )
        form = DynamicForm(form_definition, user=user)
        assert "captcha_token" not in form.fields

    def test_captcha_verify_fail_open_without_key(
        self, form_definition, user, settings
    ):
        """When no secret key is configured, _verify_captcha_token returns True."""
        settings.FORMS_WORKFLOWS_CAPTCHA_SECRET_KEY = ""
        form_definition.enable_captcha = True
        form_definition.save()
        FormField.objects.create(
            form_definition=form_definition,
            field_name="name",
            field_label="Name",
            field_type="text",
            order=1,
        )
        form = DynamicForm(form_definition, user=user)
        assert form._verify_captcha_token("any-token") is True

    def test_captcha_verify_returns_false_on_network_error(
        self, form_definition, user, settings, monkeypatch
    ):
        """Network errors during CAPTCHA verification return False."""
        settings.FORMS_WORKFLOWS_CAPTCHA_SECRET_KEY = "test-secret"

        def _raise(*args, **kwargs):
            raise OSError("network error")

        monkeypatch.setattr("urllib.request.urlopen", _raise)
        form_definition.enable_captcha = True
        form_definition.save()
        FormField.objects.create(
            form_definition=form_definition,
            field_name="name",
            field_label="Name",
            field_type="text",
            order=1,
        )
        form = DynamicForm(form_definition, user=user)
        assert form._verify_captcha_token("bad-token") is False


class TestSignatureFieldApprovalStepForm:
    """Signature field in ApprovalStepForm."""

    def test_signature_in_approval_form(
        self, form_definition, submission, approval_group, user
    ):
        wf = WorkflowDefinition.objects.create(
            form_definition=form_definition, requires_approval=True
        )
        stage = WorkflowStage.objects.create(workflow=wf, name="Sign", order=1)
        stage.approval_groups.add(approval_group)
        task = ApprovalTask.objects.create(
            submission=submission,
            assigned_group=approval_group,
            step_name="Sign",
            status="pending",
            workflow_stage=stage,
        )
        FormField.objects.create(
            form_definition=form_definition,
            field_name="approver_sig",
            field_label="Approver Signature",
            field_type="signature",
            order=200,
            workflow_stage=stage,
            required=False,
        )
        form = ApprovalStepForm(form_definition, submission, task, user=user)
        assert "approver_sig" in form.fields
        assert (
            form.fields["approver_sig"].widget.attrs.get("data-signature-field")
            == "approver_sig"
        )
