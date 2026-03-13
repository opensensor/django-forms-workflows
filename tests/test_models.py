"""
Tests for django_forms_workflows models.
"""

from datetime import date

import pytest
from django.contrib.auth.models import Group, User
from django.db import IntegrityError

from django_forms_workflows.models import (
    ActionExecutionLog,
    ApprovalTask,
    AuditLog,
    FormCategory,
    FormDefinition,
    FormField,
    FormSubmission,
    FormTemplate,
    LDAPGroupProfile,
    ManagedFile,
    PostSubmissionAction,
    PrefillSource,
    SubWorkflowDefinition,
    SubWorkflowInstance,
    UserProfile,
    WorkflowDefinition,
)

# ── FormCategory ──────────────────────────────────────────────────────────


class TestFormCategory:
    def test_create(self, category):
        assert category.name == "HR Forms"
        assert category.slug == "hr-forms"
        assert str(category) == "HR Forms"

    def test_ordering(self, db):
        c1 = FormCategory.objects.create(name="Z Category", slug="z-cat", order=2)
        c2 = FormCategory.objects.create(name="A Category", slug="a-cat", order=1)
        cats = list(FormCategory.objects.all())
        assert cats[0] == c2
        assert cats[1] == c1

    def test_parent_child(self, category):
        child = FormCategory.objects.create(
            name="Sub HR", slug="sub-hr", parent=category, order=0
        )
        assert child.parent == category
        assert category.children.first() == child

    def test_get_ancestors(self, category):
        child = FormCategory.objects.create(
            name="Level 2", slug="level-2", parent=category
        )
        grandchild = FormCategory.objects.create(
            name="Level 3", slug="level-3", parent=child
        )
        ancestors = grandchild.get_ancestors()
        assert ancestors == [category, child]

    def test_full_path(self, category):
        child = FormCategory.objects.create(
            name="Benefits", slug="benefits", parent=category
        )
        assert child.full_path() == "HR Forms > Benefits"

    def test_allowed_groups(self, category):
        g = Group.objects.create(name="HR Group")
        category.allowed_groups.add(g)
        assert g in category.allowed_groups.all()


# ── FormDefinition ────────────────────────────────────────────────────────


class TestFormDefinition:
    def test_create(self, form_definition):
        assert form_definition.name == "Test Form"
        assert form_definition.slug == "test-form"
        assert form_definition.is_active is True
        assert str(form_definition) == "Test Form"

    def test_unique_slug(self, form_definition, db):
        with pytest.raises(IntegrityError):
            FormDefinition.objects.create(
                name="Duplicate",
                slug="test-form",
                description="dup",
            )

    def test_pdf_generation_choices(self, db):
        fd = FormDefinition.objects.create(
            name="PDF Form", slug="pdf-form", description="t", pdf_generation="anytime"
        )
        assert fd.pdf_generation == "anytime"

    def test_m2m_groups(self, form_definition):
        g = Group.objects.create(name="Submitters")
        form_definition.submit_groups.add(g)
        assert form_definition.submit_groups.count() == 1

    def test_allow_resubmit(self, db):
        fd = FormDefinition.objects.create(
            name="Resubmit Form",
            slug="resubmit-form",
            description="t",
            allow_resubmit=True,
        )
        assert fd.allow_resubmit is True


# ── PrefillSource ─────────────────────────────────────────────────────────


class TestPrefillSource:
    def test_user_source(self, prefill_source):
        assert prefill_source.source_type == "user"
        assert prefill_source.get_source_identifier() == "user.email"

    def test_database_source_single_column(self, db_prefill_source):
        assert db_prefill_source.source_type == "database"
        expected = "{{ dbo.EMPLOYEES.FULL_NAME }}"
        assert db_prefill_source.get_source_identifier() == expected
        assert db_prefill_source.has_custom_query() is False
        assert db_prefill_source.has_template() is False

    def test_database_source_template(self, db):
        ps = PrefillSource.objects.create(
            name="Full Name Template",
            source_type="database",
            source_key="dbo.EMP.*",
            db_schema="dbo",
            db_table="EMP",
            db_columns=["FIRST_NAME", "LAST_NAME"],
            db_template="{FIRST_NAME} {LAST_NAME}",
        )
        assert ps.has_template() is True
        assert ".*" in ps.get_source_identifier()

    def test_database_query_key(self, db):
        ps = PrefillSource.objects.create(
            name="Custom Query",
            source_type="database",
            source_key="custom",
            database_query_key="employee_full_name",
        )
        assert ps.has_custom_query() is True
        assert ps.get_source_identifier() == "dbquery.employee_full_name"

    def test_ldap_source(self, db):
        ps = PrefillSource.objects.create(
            name="LDAP Dept",
            source_type="ldap",
            source_key="ldap.department",
            ldap_attribute="department",
        )
        assert ps.get_source_identifier() == "ldap.department"


# ── FormField ─────────────────────────────────────────────────────────────


class TestFormField:
    def test_create(self, form_with_fields):
        fields = form_with_fields.fields.all()
        assert fields.count() == 5
        names = list(fields.values_list("field_name", flat=True))
        assert "full_name" in names
        assert "email" in names

    def test_field_types(self, form_with_fields):
        f = form_with_fields.fields.get(field_name="department")
        assert f.field_type == "select"
        assert isinstance(f.choices, list)
        assert len(f.choices) == 3

    def test_unique_together(self, form_with_fields):
        with pytest.raises(IntegrityError):
            FormField.objects.create(
                form_definition=form_with_fields,
                field_name="full_name",
                field_label="Duplicate",
                field_type="text",
            )

    def test_prefill_source_config(self, form_definition, prefill_source):
        field = FormField.objects.create(
            form_definition=form_definition,
            field_name="pf_test",
            field_label="PF Test",
            field_type="text",
            prefill_source_config=prefill_source,
        )
        assert field.get_prefill_source_key() == "user.email"

    def test_no_prefill(self, form_definition):
        field = FormField.objects.create(
            form_definition=form_definition,
            field_name="no_pf",
            field_label="No PF",
            field_type="text",
        )
        assert field.get_prefill_source_key() == ""

    def test_workflow_stage(self, form_definition, staged_workflow):
        stage = staged_workflow.stages.first()
        field = FormField.objects.create(
            form_definition=form_definition,
            field_name="approval_field",
            field_label="Approval Field",
            field_type="text",
            workflow_stage=stage,
        )
        assert field.workflow_stage == stage

    def test_validation_fields(self, form_definition):
        field = FormField.objects.create(
            form_definition=form_definition,
            field_name="validated",
            field_label="Validated",
            field_type="text",
            min_length=2,
            max_length=100,
            regex_validation=r"^[A-Z]",
            regex_error_message="Must start with uppercase",
        )
        assert field.min_length == 2
        assert field.max_length == 100
        assert field.regex_validation == r"^[A-Z]"

    def test_conditional_display(self, form_definition):
        rules = {
            "operator": "AND",
            "conditions": [
                {"field": "department", "operator": "equals", "value": "hr"}
            ],
            "action": "show",
        }
        field = FormField.objects.create(
            form_definition=form_definition,
            field_name="conditional",
            field_label="Conditional",
            field_type="text",
            conditional_rules=rules,
        )
        assert field.conditional_rules["conditions"][0]["field"] == "department"


# ── WorkflowDefinition & WorkflowStage ────────────────────────────────────


class TestWorkflowDefinition:
    def test_create(self, workflow):
        assert workflow.requires_approval is True
        assert str(workflow) == "Workflow for Test Form"

    def test_staged_workflow(self, staged_workflow):
        stages = list(staged_workflow.stages.order_by("order"))
        assert len(stages) == 2
        assert stages[0].name == "Manager Review"
        assert stages[1].name == "Finance Review"

    def test_notification_cadence(self, form_definition):
        wf = WorkflowDefinition.objects.create(
            form_definition=form_definition,
            requires_approval=True,
            notification_cadence="daily",
        )
        assert wf.notification_cadence == "daily"

    def test_multiple_workflows_per_form(self, form_definition):
        wf1 = WorkflowDefinition.objects.create(
            form_definition=form_definition,
            requires_approval=True,
            name_label="Track A",
        )
        WorkflowDefinition.objects.create(
            form_definition=form_definition,
            requires_approval=True,
            name_label="Track B",
        )
        assert form_definition.workflows.count() == 2
        # Backward-compatible .workflow property returns first
        assert form_definition.workflow == wf1


class TestWorkflowStage:
    def test_str(self, staged_workflow):
        stage = staged_workflow.stages.first()
        assert "Stage" in str(stage)

    def test_approve_label(self, staged_workflow):
        stage = staged_workflow.stages.first()
        stage.approve_label = "Sign Off"
        stage.save()
        stage.refresh_from_db()
        assert stage.approve_label == "Sign Off"


# ── PostSubmissionAction ──────────────────────────────────────────────────


class TestPostSubmissionAction:
    def test_create(self, post_action_email):
        assert post_action_email.action_type == "email"
        assert post_action_email.trigger == "on_approve"

    def test_should_execute_active(self, post_action_email, submission):
        assert post_action_email.should_execute(submission) is True

    def test_should_execute_inactive(self, post_action_email, submission):
        post_action_email.is_active = False
        post_action_email.save()
        assert post_action_email.should_execute(submission) is False

    def test_condition_equals(self, form_definition, submission):
        action = PostSubmissionAction.objects.create(
            form_definition=form_definition,
            name="Conditional",
            action_type="email",
            trigger="on_approve",
            condition_field="department",
            condition_operator="equals",
            condition_value="it",
        )
        assert action.should_execute(submission) is True

    def test_condition_not_equals(self, form_definition, submission):
        action = PostSubmissionAction.objects.create(
            form_definition=form_definition,
            name="Conditional NE",
            action_type="email",
            trigger="on_approve",
            condition_field="department",
            condition_operator="not_equals",
            condition_value="hr",
        )
        assert action.should_execute(submission) is True

    def test_condition_greater_than(self, form_definition, submission):
        action = PostSubmissionAction.objects.create(
            form_definition=form_definition,
            name="Amount Check",
            action_type="email",
            trigger="on_approve",
            condition_field="amount",
            condition_operator="greater_than",
            condition_value="100",
        )
        assert action.should_execute(submission) is True

    def test_condition_less_than(self, form_definition, submission):
        action = PostSubmissionAction.objects.create(
            form_definition=form_definition,
            name="Amount Check LT",
            action_type="email",
            trigger="on_approve",
            condition_field="amount",
            condition_operator="less_than",
            condition_value="100",
        )
        assert action.should_execute(submission) is False

    def test_condition_contains(self, form_definition, submission):
        action = PostSubmissionAction.objects.create(
            form_definition=form_definition,
            name="Contains",
            action_type="email",
            trigger="on_approve",
            condition_field="notes",
            condition_operator="contains",
            condition_value="Test",
        )
        assert action.should_execute(submission) is True

    def test_condition_is_empty(self, form_definition):
        sub = FormSubmission.objects.create(
            form_definition=form_definition,
            submitter=User.objects.create_user("emptyu", password="pass"),
            form_data={"notes": ""},
            status="submitted",
        )
        action = PostSubmissionAction.objects.create(
            form_definition=form_definition,
            name="Empty Check",
            action_type="email",
            trigger="on_approve",
            condition_field="notes",
            condition_operator="is_empty",
            condition_value="",
        )
        assert action.should_execute(sub) is True

    def test_condition_is_not_empty(self, form_definition, submission):
        action = PostSubmissionAction.objects.create(
            form_definition=form_definition,
            name="Not Empty",
            action_type="email",
            trigger="on_approve",
            condition_field="notes",
            condition_operator="is_not_empty",
            condition_value="",
        )
        assert action.should_execute(submission) is True

    def test_condition_is_true(self, form_definition):
        sub = FormSubmission.objects.create(
            form_definition=form_definition,
            submitter=User.objects.create_user("trueu", password="pass"),
            form_data={"agree": True},
            status="submitted",
        )
        action = PostSubmissionAction.objects.create(
            form_definition=form_definition,
            name="True Check",
            action_type="email",
            trigger="on_approve",
            condition_field="agree",
            condition_operator="is_true",
            condition_value="",
        )
        assert action.should_execute(sub) is True

    def test_is_locked_prevents_reexecution(self, form_definition, submission):
        action = PostSubmissionAction.objects.create(
            form_definition=form_definition,
            name="Locked Action",
            action_type="email",
            trigger="on_approve",
            is_locked=True,
        )
        # First execution should succeed
        assert action.should_execute(submission) is True
        # Log a successful execution
        ActionExecutionLog.objects.create(
            action=action,
            submission=submission,
            trigger="on_approve",
            success=True,
        )
        # Now should_execute returns False
        assert action.should_execute(submission) is False

    def test_date_conditions(self, form_definition):
        tomorrow = (date.today().replace(year=date.today().year + 1)).isoformat()
        sub = FormSubmission.objects.create(
            form_definition=form_definition,
            submitter=User.objects.create_user("dateu", password="pass"),
            form_data={"due_date": tomorrow},
            status="submitted",
        )
        action = PostSubmissionAction.objects.create(
            form_definition=form_definition,
            name="Future Date",
            action_type="email",
            trigger="on_approve",
            condition_field="due_date",
            condition_operator="greater_than_today",
            condition_value="",
        )
        assert action.should_execute(sub) is True


# ── FormSubmission ────────────────────────────────────────────────────────


class TestFormSubmission:
    def test_create(self, submission):
        assert submission.status == "submitted"
        assert submission.form_data["full_name"] == "Test User"
        assert str(submission) == "Test Form - testuser - Submitted"

    def test_status_choices(self, form_with_fields, user):
        for status, _ in FormSubmission.STATUS_CHOICES:
            sub = FormSubmission.objects.create(
                form_definition=form_with_fields,
                submitter=user,
                form_data={"full_name": "Test"},
                status=status,
            )
            assert sub.status == status


# ── ApprovalTask ──────────────────────────────────────────────────────────


class TestApprovalTask:
    def test_create(self, submission, approval_group):
        task = ApprovalTask.objects.create(
            submission=submission,
            assigned_group=approval_group,
            step_name="Group Approval",
            status="pending",
        )
        assert task.status == "pending"
        assert str(task) == f"Group Approval for {submission}"


# ── AuditLog ──────────────────────────────────────────────────────────────


class TestAuditLog:
    def test_create(self, user):
        log = AuditLog.objects.create(
            action="submit",
            object_type="FormSubmission",
            object_id=1,
            user=user,
        )
        assert "submit" in str(log).lower() or "Submitted" in str(log)


# ── UserProfile ───────────────────────────────────────────────────────────


class TestUserProfile:
    def test_auto_creation(self, user):
        # Signal creates profile on user creation
        profile = UserProfile.objects.get(user=user)
        assert profile is not None
        assert str(profile) == "Profile for testuser"

    def test_properties(self, user):
        profile = UserProfile.objects.get(user=user)
        profile.employee_id = "EMP001"
        profile.title = "Engineer"
        profile.save()
        assert profile.full_name == "Test User"
        assert profile.display_name == "Test User (Engineer)"
        assert profile.id_number == "EMP001"

    def test_id_number_setter(self, user):
        profile = UserProfile.objects.get(user=user)
        profile.id_number = "EMP999"
        assert profile.employee_id == "EMP999"


# ── LDAPGroupProfile ─────────────────────────────────────────────────────


class TestLDAPGroupProfile:
    def test_create(self, db):
        group = Group.objects.create(name="LDAP Group")
        ldap_profile = LDAPGroupProfile.objects.create(
            group=group,
            ldap_dn="CN=LDAPGroup,OU=Groups,DC=example,DC=com",
        )
        assert str(ldap_profile) == "LDAP: LDAP Group"


# ── ManagedFile ───────────────────────────────────────────────────────────


class TestManagedFile:
    def test_status_methods(self, submission, user):
        mf = ManagedFile.objects.create(
            submission=submission,
            original_filename="test.pdf",
            stored_filename="test_001.pdf",
            file_path="/uploads/test_001.pdf",
            file_size=1024,
            uploaded_by=user,
        )
        assert mf.status == "pending"

        mf.mark_approved(user=user, notes="OK")
        mf.refresh_from_db()
        assert mf.status == "approved"

        mf2 = ManagedFile.objects.create(
            submission=submission,
            original_filename="test2.pdf",
            stored_filename="test_002.pdf",
            file_path="/uploads/test_002.pdf",
            file_size=2048,
            uploaded_by=user,
        )
        mf2.mark_rejected(user=user, notes="Not acceptable")
        mf2.refresh_from_db()
        assert mf2.status == "rejected"

    def test_supersede(self, submission, user):
        mf = ManagedFile.objects.create(
            submission=submission,
            original_filename="v1.pdf",
            stored_filename="v1.pdf",
            file_path="/uploads/v1.pdf",
            file_size=100,
            uploaded_by=user,
        )
        mf.mark_superseded(notes="Replaced by v2")
        mf.refresh_from_db()
        assert mf.status == "superseded"
        assert mf.is_current is False


# ── FormTemplate ──────────────────────────────────────────────────────────


class TestFormTemplate:
    def test_create_and_increment(self, db):
        t = FormTemplate.objects.create(
            name="Contact Form",
            slug="contact-form",
            description="Basic contact",
            template_data={"fields": []},
        )
        assert t.usage_count == 0
        t.increment_usage()
        t.refresh_from_db()
        assert t.usage_count == 1


# ── SubWorkflowDefinition ────────────────────────────────────────────────


class TestSubWorkflowModels:
    def test_sub_workflow_definition(self, db, form_definition):
        parent_wf = WorkflowDefinition.objects.create(
            form_definition=form_definition, requires_approval=True
        )
        sub_form = FormDefinition.objects.create(
            name="Sub Form", slug="sub-form", description="sub"
        )
        sub_wf = WorkflowDefinition.objects.create(
            form_definition=sub_form, requires_approval=True
        )
        config = SubWorkflowDefinition.objects.create(
            parent_workflow=parent_wf,
            sub_workflow=sub_wf,
            count_field="num_payments",
            label_template="Payment {index}",
            trigger="on_approval",
        )
        assert str(config) == f"Sub-WF config for: {form_definition}"

    def test_sub_workflow_instance_form_data_slice(self, db, form_definition):
        parent_wf = WorkflowDefinition.objects.create(
            form_definition=form_definition, requires_approval=True
        )
        sub_form = FormDefinition.objects.create(
            name="Sub2", slug="sub2", description="sub"
        )
        sub_wf = WorkflowDefinition.objects.create(
            form_definition=sub_form, requires_approval=True
        )
        config = SubWorkflowDefinition.objects.create(
            parent_workflow=parent_wf,
            sub_workflow=sub_wf,
            count_field="cnt",
            data_prefix="payment",
        )
        user = User.objects.create_user("subwfu", password="pass")
        sub = FormSubmission.objects.create(
            form_definition=form_definition,
            submitter=user,
            form_data={
                "cnt": 2,
                "payment_type_1": "credit",
                "payment_amount_1": "100",
                "payment_type_2": "debit",
                "payment_amount_2": "200",
                "other_field": "ignored",
            },
            status="submitted",
        )
        instance = SubWorkflowInstance.objects.create(
            parent_submission=sub, definition=config, index=1
        )
        data = instance.form_data_slice
        assert "payment_type_1" in data
        assert "payment_amount_1" in data
        assert "other_field" not in data
        assert "payment_type_2" not in data  # wrong index
