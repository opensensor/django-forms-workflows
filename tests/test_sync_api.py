"""
Tests for django_forms_workflows.sync_api.
"""

import pytest
from django.contrib.auth.models import Group

from django_forms_workflows.models import (
    FormCategory,
    FormDefinition,
    FormField,
    PostSubmissionAction,
    PrefillSource,
    WebhookEndpoint,
    WorkflowDefinition,
    WorkflowStage,
)
from django_forms_workflows.sync_api import (
    SYNC_SCHEMA_VERSION,
    build_export_payload,
    import_payload,
)


@pytest.fixture
def export_form(db):
    """Create a full form with fields, workflow, stages, and prefill for export."""
    cat = FormCategory.objects.create(name="Sync Cat", slug="sync-cat")
    fd = FormDefinition.objects.create(
        name="Sync Form",
        slug="sync-form",
        description="For testing sync",
        category=cat,
        is_active=True,
    )
    ps = PrefillSource.objects.create(
        name="User Email",
        source_type="user",
        source_key="user.email",
    )
    FormField.objects.create(
        form_definition=fd,
        field_name="name",
        field_label="Name",
        field_type="text",
        order=1,
    )
    FormField.objects.create(
        form_definition=fd,
        field_name="email",
        field_label="Email",
        field_type="email",
        order=2,
        prefill_source_config=ps,
    )
    g = Group.objects.create(name="Sync Approvers")
    wf = WorkflowDefinition.objects.create(
        form_definition=fd,
        requires_approval=True,
    )
    stage = WorkflowStage.objects.create(
        workflow=wf, name="Review", order=1, approval_logic="all"
    )
    stage.approval_groups.add(g)
    WebhookEndpoint.objects.create(
        workflow=wf,
        name="ERP Callback",
        url="https://example.com/hooks/workflows",
        events=["submission.created", "submission.approved"],
        custom_headers={"Authorization": "Bearer sync-token"},
    )
    PostSubmissionAction.objects.create(
        form_definition=fd,
        name="Notify Admin",
        action_type="email",
        trigger="on_approve",
        email_to="admin@example.com",
    )
    return fd


class TestExportPayload:
    def test_basic_structure(self, export_form):
        qs = FormDefinition.objects.filter(pk=export_form.pk)
        payload = build_export_payload(qs)
        assert payload["schema_version"] == SYNC_SCHEMA_VERSION
        assert len(payload["forms"]) == 1

    def test_fields_included(self, export_form):
        qs = FormDefinition.objects.filter(pk=export_form.pk)
        payload = build_export_payload(qs)
        form_data = payload["forms"][0]
        assert len(form_data["fields"]) == 2
        names = [f["field_name"] for f in form_data["fields"]]
        assert "name" in names
        assert "email" in names

    def test_workflow_included(self, export_form):
        qs = FormDefinition.objects.filter(pk=export_form.pk)
        payload = build_export_payload(qs)
        form_data = payload["forms"][0]
        assert form_data["workflow"] is not None
        assert form_data["workflow"]["requires_approval"] is True

    def test_stages_included(self, export_form):
        qs = FormDefinition.objects.filter(pk=export_form.pk)
        payload = build_export_payload(qs)
        form_data = payload["forms"][0]
        stages = form_data["workflow"].get("stages", [])
        assert len(stages) == 1
        assert stages[0]["name"] == "Review"

    def test_webhooks_included(self, export_form):
        qs = FormDefinition.objects.filter(pk=export_form.pk)
        payload = build_export_payload(qs)
        form_data = payload["forms"][0]
        webhooks = form_data["workflow"].get("webhook_endpoints", [])
        assert len(webhooks) == 1
        assert webhooks[0]["name"] == "ERP Callback"
        assert webhooks[0]["events"] == ["submission.created", "submission.approved"]

    def test_post_actions_included(self, export_form):
        qs = FormDefinition.objects.filter(pk=export_form.pk)
        payload = build_export_payload(qs)
        form_data = payload["forms"][0]
        assert len(form_data.get("post_actions", [])) == 1

    def test_prefill_config_included(self, export_form):
        qs = FormDefinition.objects.filter(pk=export_form.pk)
        payload = build_export_payload(qs)
        form_data = payload["forms"][0]
        email_field = [f for f in form_data["fields"] if f["field_name"] == "email"][0]
        assert email_field["prefill_source_config"] is not None
        assert email_field["prefill_source_config"]["source_type"] == "user"

    def test_category_included(self, export_form):
        qs = FormDefinition.objects.filter(pk=export_form.pk)
        payload = build_export_payload(qs)
        form_data = payload["forms"][0]
        assert form_data["category"] is not None
        assert form_data["category"]["slug"] == "sync-cat"


class TestImportPayload:
    def test_import_new_form(self, export_form):
        qs = FormDefinition.objects.filter(pk=export_form.pk)
        payload = build_export_payload(qs)
        # Delete the original
        export_form.delete()
        assert FormDefinition.objects.filter(slug="sync-form").count() == 0
        results = import_payload(payload, conflict="skip")
        # results is list of (FormDefinition, action) tuples
        assert len(results) == 1
        fd, action = results[0]
        assert action == "created"
        assert FormDefinition.objects.filter(slug="sync-form").count() == 1
        assert fd.fields.count() == 2
        assert fd.workflows.first().webhook_endpoints.count() == 1

    def test_import_skip_existing(self, export_form):
        qs = FormDefinition.objects.filter(pk=export_form.pk)
        payload = build_export_payload(qs)
        results = import_payload(payload, conflict="skip")
        assert len(results) == 1
        _, action = results[0]
        assert action == "skipped"

    def test_import_update_existing(self, export_form):
        qs = FormDefinition.objects.filter(pk=export_form.pk)
        payload = build_export_payload(qs)
        # Modify the payload (nested under "form")
        payload["forms"][0]["form"]["description"] = "Updated description"
        results = import_payload(payload, conflict="update")
        assert len(results) == 1
        _, action = results[0]
        assert action == "updated"
        export_form.refresh_from_db()
        assert export_form.description == "Updated description"
        webhook = export_form.workflows.first().webhook_endpoints.first()
        assert webhook is not None
        assert webhook.url == "https://example.com/hooks/workflows"

    def test_multi_workflow_field_stage_resolution(self, db):
        """Fields assigned to stages in additional workflows must retain
        their workflow_stage FK after export → import round-trip."""
        fd = FormDefinition.objects.create(
            name="Multi WF Form", slug="multi-wf-form", is_active=True
        )
        # Primary workflow with one stage
        wf1 = WorkflowDefinition.objects.create(
            form_definition=fd, requires_approval=True
        )
        WorkflowStage.objects.create(workflow=wf1, name="Contract Approval", order=1)
        # Additional workflow with multiple stages
        wf2 = WorkflowDefinition.objects.create(
            form_definition=fd, requires_approval=True
        )
        WorkflowStage.objects.create(workflow=wf2, name="Payment Request", order=1)
        hr_stage = WorkflowStage.objects.create(
            workflow=wf2, name="HR Processing", order=2
        )
        WorkflowStage.objects.create(workflow=wf2, name="Payroll Processing", order=3)
        # Field on primary workflow stage (order=1, wf_idx=0)
        FormField.objects.create(
            form_definition=fd,
            field_name="contract_doc",
            field_label="Contract",
            field_type="file",
            order=1,
            workflow_stage=WorkflowStage.objects.get(workflow=wf1, order=1),
        )
        # Fields on additional workflow stage (order=2, wf_idx=1)
        FormField.objects.create(
            form_definition=fd,
            field_name="payment_dept_code",
            field_label="Department Code",
            field_type="text",
            order=2,
            workflow_stage=hr_stage,
        )
        FormField.objects.create(
            form_definition=fd,
            field_name="employee_ssn_last4",
            field_label="Last 4 SSN",
            field_type="text",
            order=3,
            workflow_stage=hr_stage,
        )

        # Export and re-import into a fresh form
        qs = FormDefinition.objects.filter(pk=fd.pk)
        payload = build_export_payload(qs)
        fd.delete()

        results = import_payload(payload, conflict="skip")
        assert len(results) == 1
        new_fd, action = results[0]
        assert action == "created"

        # Verify field on primary workflow stage
        contract_field = new_fd.fields.get(field_name="contract_doc")
        assert contract_field.workflow_stage is not None
        assert contract_field.workflow_stage.name == "Contract Approval"

        # Verify fields on additional workflow stage are NOT null
        dept_field = new_fd.fields.get(field_name="payment_dept_code")
        assert dept_field.workflow_stage is not None, (
            "payment_dept_code lost its workflow_stage FK during sync"
        )
        assert dept_field.workflow_stage.name == "HR Processing"

        ssn_field = new_fd.fields.get(field_name="employee_ssn_last4")
        assert ssn_field.workflow_stage is not None, (
            "employee_ssn_last4 lost its workflow_stage FK during sync"
        )
        assert ssn_field.workflow_stage.name == "HR Processing"
