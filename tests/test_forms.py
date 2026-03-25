"""
Tests for DynamicForm and ApprovalStepForm.
"""

from datetime import date
from decimal import Decimal

import pytest

from django_forms_workflows.forms import ApprovalStepForm, DynamicForm
from django_forms_workflows.models import (
    ApprovalTask,
    FormField,
    PrefillSource,
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
