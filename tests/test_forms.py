"""
Tests for DynamicForm and ApprovalStepForm.
"""

from datetime import date
from decimal import Decimal

from django_forms_workflows.forms import ApprovalStepForm, DynamicForm
from django_forms_workflows.models import (
    ApprovalTask,
    FormField,
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

    def test_excludes_approval_step_fields(self, form_definition, user):
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
            approval_step=1,
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

    def test_legacy_prefill_source(self, form_definition, user):
        FormField.objects.create(
            form_definition=form_definition,
            field_name="legacy_email",
            field_label="Email",
            field_type="email",
            order=1,
            prefill_source="user.email",
        )
        form = DynamicForm(form_definition, user=user)
        assert form.fields["legacy_email"].initial == "test@example.com"

    def test_current_date_prefill(self, form_definition, user):
        FormField.objects.create(
            form_definition=form_definition,
            field_name="today",
            field_label="Today",
            field_type="date",
            order=1,
            prefill_source="current_date",
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
            show_if_field="trigger",
            show_if_value="yes",
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
    def _make_approval_task(self, submission, group, step_number=1, stage=None):
        return ApprovalTask.objects.create(
            submission=submission,
            assigned_group=group,
            step_name="Review",
            status="pending",
            step_number=step_number,
            workflow_stage=stage,
        )

    def test_legacy_step_fields(
        self, form_definition, submission, approval_group, user
    ):
        FormField.objects.create(
            form_definition=form_definition,
            field_name="approver_name",
            field_label="Approver Name",
            field_type="text",
            order=100,
            approval_step=1,
        )
        task = self._make_approval_task(submission, approval_group)
        form = ApprovalStepForm(form_definition, submission, task, user=user)
        assert "approver_name" in form.fields
        # Auto-fill approver name
        assert form.fields["approver_name"].initial == "Test User"

    def test_staged_workflow_fields(
        self, form_definition, submission, approval_group, user
    ):
        wf = WorkflowDefinition.objects.create(
            form_definition=form_definition, requires_approval=True
        )
        stage = WorkflowStage.objects.create(
            workflow=wf, name="Manager Review", order=1
        )
        stage.approval_groups.add(approval_group)
        FormField.objects.create(
            form_definition=form_definition,
            field_name="stage_field",
            field_label="Stage Field",
            field_type="text",
            order=100,
            workflow_stage=stage,
        )
        task = ApprovalTask.objects.create(
            submission=submission,
            assigned_group=approval_group,
            step_name="Manager Review",
            status="pending",
            workflow_stage=stage,
        )
        form = ApprovalStepForm(form_definition, submission, task, user=user)
        assert "stage_field" in form.fields

    def test_date_auto_fill(self, form_definition, submission, approval_group, user):
        FormField.objects.create(
            form_definition=form_definition,
            field_name="approval_date",
            field_label="Approval Date",
            field_type="date",
            order=100,
            approval_step=1,
        )
        task = self._make_approval_task(submission, approval_group)
        form = ApprovalStepForm(form_definition, submission, task, user=user)
        assert form.fields["approval_date"].initial == date.today()

    def test_get_updated_form_data(
        self, form_definition, submission, approval_group, user
    ):
        FormField.objects.create(
            form_definition=form_definition,
            field_name="reviewer_notes",
            field_label="Notes",
            field_type="text",
            order=100,
            approval_step=1,
            required=False,
        )
        task = self._make_approval_task(submission, approval_group)
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
