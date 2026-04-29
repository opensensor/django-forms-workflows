"""
Tests for django_forms_workflows.sync_api.
"""

import pytest
from django.contrib.auth.models import Group

from django_forms_workflows.models import (
    FormCategory,
    FormDefinition,
    FormField,
    NotificationRule,
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


class TestUUIDSync:
    """Tests for UUID-based cross-instance sync identity."""

    def test_schema_version_is_2(self, export_form):
        qs = FormDefinition.objects.filter(pk=export_form.pk)
        payload = build_export_payload(qs)
        assert payload["schema_version"] == 2

    def test_export_includes_uuids(self, export_form):
        """All serialized levels must include a uuid field."""
        qs = FormDefinition.objects.filter(pk=export_form.pk)
        payload = build_export_payload(qs)
        form_data = payload["forms"][0]

        # Form-level UUID
        assert "uuid" in form_data["form"]
        assert form_data["form"]["uuid"] == str(export_form.uuid)

        # Workflow-level UUID
        wf = export_form.workflows.first()
        assert form_data["workflow"]["uuid"] == str(wf.uuid)

        # Stage-level UUID
        stage = wf.stages.first()
        assert form_data["workflow"]["stages"][0]["uuid"] == str(stage.uuid)

    def test_uuid_roundtrip(self, export_form):
        """UUIDs should survive an export → delete → import cycle."""
        original_uuid = str(export_form.uuid)
        wf = export_form.workflows.first()
        wf_uuid = str(wf.uuid)
        stage = wf.stages.first()
        stage_uuid = str(stage.uuid)

        qs = FormDefinition.objects.filter(pk=export_form.pk)
        payload = build_export_payload(qs)
        export_form.delete()

        results = import_payload(payload, conflict="skip")
        new_fd, action = results[0]
        assert action == "created"
        assert str(new_fd.uuid) == original_uuid

        new_wf = new_fd.workflows.first()
        assert str(new_wf.uuid) == wf_uuid

        new_stage = new_wf.stages.first()
        assert str(new_stage.uuid) == stage_uuid

    def test_import_matches_by_uuid(self, export_form):
        """UUID match should find existing form even if slug differs."""
        qs = FormDefinition.objects.filter(pk=export_form.pk)
        payload = build_export_payload(qs)
        # Change the slug in the payload — UUID should still match
        payload["forms"][0]["form"]["slug"] = "totally-different-slug"
        payload["forms"][0]["form"]["description"] = "UUID-matched update"

        results = import_payload(payload, conflict="update")
        fd, action = results[0]
        assert action == "updated"
        assert fd.pk == export_form.pk
        export_form.refresh_from_db()
        assert export_form.description == "UUID-matched update"

    def test_backward_compat_no_uuid(self, export_form):
        """Payloads without UUIDs should fall back to slug/heuristic matching."""
        qs = FormDefinition.objects.filter(pk=export_form.pk)
        payload = build_export_payload(qs)

        # Strip all UUIDs from the payload
        form_data = payload["forms"][0]
        form_data["form"].pop("uuid", None)
        if form_data.get("workflow"):
            form_data["workflow"].pop("uuid", None)
            for stage in form_data["workflow"].get("stages", []):
                stage.pop("uuid", None)
        for field in form_data.get("fields", []):
            field.pop("workflow_stage_uuid", None)

        # Delete and re-import — should still work via slug matching
        export_form.delete()
        results = import_payload(payload, conflict="skip")
        fd, action = results[0]
        assert action == "created"
        assert fd.slug == "sync-form"

    def test_uuid_survives_stage_rename(self, db):
        """UUID matching should find existing stage even if name changes."""
        fd = FormDefinition.objects.create(
            name="Rename Test", slug="rename-test", is_active=True
        )
        wf = WorkflowDefinition.objects.create(
            form_definition=fd, requires_approval=True
        )
        stage = WorkflowStage.objects.create(workflow=wf, name="Old Name", order=1)
        original_stage_uuid = str(stage.uuid)

        qs = FormDefinition.objects.filter(pk=fd.pk)
        payload = build_export_payload(qs)

        # Rename the stage in the payload
        payload["forms"][0]["workflow"]["stages"][0]["name"] = "New Name"

        results = import_payload(payload, conflict="update")
        updated_fd, _ = results[0]

        updated_stage = updated_fd.workflows.first().stages.first()
        assert updated_stage.name == "New Name"
        # Same UUID, same DB record
        assert str(updated_stage.uuid) == original_stage_uuid
        assert updated_stage.pk == stage.pk

    def test_field_stage_uuid_resolution(self, db):
        """workflow_stage_uuid should resolve fields to the correct stage."""
        fd = FormDefinition.objects.create(
            name="UUID Stage Test", slug="uuid-stage-test", is_active=True
        )
        wf1 = WorkflowDefinition.objects.create(
            form_definition=fd, requires_approval=True
        )
        WorkflowStage.objects.create(workflow=wf1, name="Approve", order=1)
        wf2 = WorkflowDefinition.objects.create(
            form_definition=fd, requires_approval=True
        )
        target_stage = WorkflowStage.objects.create(
            workflow=wf2, name="Process", order=1
        )
        FormField.objects.create(
            form_definition=fd,
            field_name="stage_field",
            field_label="Stage Field",
            field_type="text",
            order=1,
            workflow_stage=target_stage,
        )

        qs = FormDefinition.objects.filter(pk=fd.pk)
        payload = build_export_payload(qs)
        fd.delete()

        results = import_payload(payload, conflict="skip")
        new_fd, _ = results[0]
        field = new_fd.fields.get(field_name="stage_field")
        assert field.workflow_stage is not None
        assert field.workflow_stage.name == "Process"


class TestReviewerGroupsSync:
    """reviewer_groups is a FormDefinition M2M (distinct from view/admin
    groups) — it must round-trip through push/pull."""

    def test_reviewer_groups_exported(self, db):
        fd = FormDefinition.objects.create(
            name="Reviewer Form", slug="reviewer-form", is_active=True
        )
        g1 = Group.objects.create(name="Auditors")
        g2 = Group.objects.create(name="Compliance")
        fd.reviewer_groups.set([g1, g2])

        qs = FormDefinition.objects.filter(pk=fd.pk)
        payload = build_export_payload(qs)
        form_data = payload["forms"][0]
        assert set(form_data["form"]["reviewer_groups"]) == {"Auditors", "Compliance"}

    def test_reviewer_groups_imported(self, db):
        fd = FormDefinition.objects.create(
            name="Reviewer Form", slug="reviewer-form", is_active=True
        )
        g = Group.objects.create(name="Auditors")
        fd.reviewer_groups.add(g)

        qs = FormDefinition.objects.filter(pk=fd.pk)
        payload = build_export_payload(qs)
        fd.delete()
        Group.objects.filter(name="Auditors").delete()

        results = import_payload(payload, conflict="skip")
        new_fd, _ = results[0]
        assert list(new_fd.reviewer_groups.values_list("name", flat=True)) == [
            "Auditors"
        ]

    def test_reviewer_groups_updated_on_existing_form(self, db):
        fd = FormDefinition.objects.create(
            name="Reviewer Form", slug="reviewer-form", is_active=True
        )
        fd.reviewer_groups.add(Group.objects.create(name="Old Reviewers"))
        qs = FormDefinition.objects.filter(pk=fd.pk)
        payload = build_export_payload(qs)
        # Swap reviewer_groups in the payload
        payload["forms"][0]["form"]["reviewer_groups"] = ["New Reviewers"]

        results = import_payload(payload, conflict="update")
        _, action = results[0]
        assert action == "updated"
        fd.refresh_from_db()
        assert list(fd.reviewer_groups.values_list("name", flat=True)) == [
            "New Reviewers"
        ]


class TestShowHelpTextInDetailSync:
    """FormField.show_help_text_in_detail must round-trip through push/pull
    — without it, toggling the flag in one environment can't propagate."""

    def test_show_help_text_in_detail_round_trips(self, db):
        fd = FormDefinition.objects.create(
            name="HT Form", slug="ht-form", is_active=True
        )
        FormField.objects.create(
            form_definition=fd,
            field_name="initials",
            field_label="I Agree",
            field_type="text",
            help_text="I have read and agree to the statement above.",
            show_help_text_in_detail=True,
            order=1,
        )
        qs = FormDefinition.objects.filter(pk=fd.pk)
        payload = build_export_payload(qs)
        form_data = payload["forms"][0]
        exported_field = [
            f for f in form_data["fields"] if f["field_name"] == "initials"
        ][0]
        assert exported_field["show_help_text_in_detail"] is True

        fd.delete()
        results = import_payload(payload, conflict="skip")
        new_fd, _ = results[0]
        assert new_fd.fields.get(field_name="initials").show_help_text_in_detail


class TestNotificationRuleSync:
    """Round-trip every NotificationRule field through export → import.

    Regression: use_triggering_stage, body_template, cc_email_field, and
    cc_static_emails were missing from sync_api serialization, so they did not
    appear in the diff checker and were lost on push/pull between environments.
    """

    @pytest.fixture
    def form_with_notification_rules(self, db):
        cat = FormCategory.objects.create(name="Notif Cat", slug="notif-cat")
        fd = FormDefinition.objects.create(
            name="Notif Form",
            slug="notif-form",
            category=cat,
        )
        wf = WorkflowDefinition.objects.create(
            form_definition=fd,
            requires_approval=True,
        )
        stage = WorkflowStage.objects.create(
            workflow=wf, name="Review", order=1, approval_logic="all"
        )
        notify_group = Group.objects.create(name="Notif Group")

        # Workflow-level rule (stage=null) using all the previously-dropped fields
        wf_rule = NotificationRule.objects.create(
            workflow=wf,
            stage=None,
            event="workflow_approved",
            use_triggering_stage=False,
            notify_submitter=True,
            email_field="contact_email",
            static_emails="ops@example.com",
            cc_email_field="manager_email",
            cc_static_emails="audit@example.com,records@example.com",
            notify_stage_assignees=False,
            notify_stage_groups=False,
            subject_template="Approved: {form_name}",
            body_template="<p>Hello {{ submitter }}</p>",
            conditions={"field": "amount", "operator": ">", "value": 100},
        )
        wf_rule.notify_groups.add(notify_group)

        # Stage-level rule using use_triggering_stage = False with explicit stage
        stage_rule = NotificationRule.objects.create(
            workflow=wf,
            stage=stage,
            event="approval_request",
            use_triggering_stage=False,
            notify_submitter=False,
            email_field="",
            static_emails="",
            cc_email_field="cc_field",
            cc_static_emails="cc-static@example.com",
            notify_stage_assignees=True,
            notify_stage_groups=True,
            subject_template="Action needed",
            body_template="<p>Please review</p>",
        )
        stage_rule.notify_groups.add(notify_group)
        return fd

    def test_export_includes_all_notification_rule_fields(
        self, form_with_notification_rules
    ):
        qs = FormDefinition.objects.filter(pk=form_with_notification_rules.pk)
        payload = build_export_payload(qs)
        wf_data = payload["forms"][0]["workflow"]

        wf_rules = wf_data["notification_rules"]
        assert len(wf_rules) == 1
        wf_rule = wf_rules[0]
        for key in (
            "use_triggering_stage",
            "body_template",
            "cc_email_field",
            "cc_static_emails",
        ):
            assert key in wf_rule, f"workflow-level rule missing {key}"
        assert wf_rule["body_template"] == "<p>Hello {{ submitter }}</p>"
        assert wf_rule["cc_email_field"] == "manager_email"
        assert wf_rule["cc_static_emails"] == "audit@example.com,records@example.com"

        stage_rules = wf_data["stages"][0]["notification_rules"]
        assert len(stage_rules) == 1
        stage_rule = stage_rules[0]
        for key in (
            "use_triggering_stage",
            "body_template",
            "cc_email_field",
            "cc_static_emails",
        ):
            assert key in stage_rule, f"stage-level rule missing {key}"
        assert stage_rule["cc_static_emails"] == "cc-static@example.com"

    def test_round_trip_preserves_all_notification_rule_fields(
        self, form_with_notification_rules
    ):
        qs = FormDefinition.objects.filter(pk=form_with_notification_rules.pk)
        payload = build_export_payload(qs)
        form_with_notification_rules.delete()

        results = import_payload(payload, conflict="update")
        new_fd, _ = results[0]
        new_wf = new_fd.workflows.first()

        wf_rule = new_wf.notification_rules.get(stage__isnull=True)
        assert wf_rule.event == "workflow_approved"
        assert wf_rule.use_triggering_stage is False
        assert wf_rule.body_template == "<p>Hello {{ submitter }}</p>"
        assert wf_rule.cc_email_field == "manager_email"
        assert wf_rule.cc_static_emails == "audit@example.com,records@example.com"
        assert wf_rule.subject_template == "Approved: {form_name}"
        assert wf_rule.notify_groups.filter(name="Notif Group").exists()

        stage_rule = new_wf.notification_rules.get(stage__isnull=False)
        assert stage_rule.event == "approval_request"
        assert stage_rule.cc_email_field == "cc_field"
        assert stage_rule.cc_static_emails == "cc-static@example.com"
        assert stage_rule.body_template == "<p>Please review</p>"
        assert stage_rule.notify_stage_assignees is True
        assert stage_rule.notify_stage_groups is True

    def test_serialized_rule_order_is_deterministic_across_envs(self, db):
        """Same rules created in different DB-row orders must serialize identically.

        Regression: when two workflow-level rules share an event, the model's
        Meta ordering doesn't disambiguate them, so DB row order leaks into
        the export payload. The diff viewer compared lists with == which
        produced false-positive 'Workflow notification rules: 6 → 6' diffs.
        """
        cat = FormCategory.objects.create(name="Order Cat", slug="order-cat")

        def build_form(slug, group_order_a, group_order_b):
            fd = FormDefinition.objects.create(
                name=f"Order {slug}", slug=slug, category=cat
            )
            wf = WorkflowDefinition.objects.create(
                form_definition=fd, requires_approval=True
            )
            # Two rules sharing the same event — Meta ordering can't tell
            # them apart, so the second-key (id) decides DB row order.
            r1 = NotificationRule.objects.create(
                workflow=wf,
                stage=None,
                event="approval_request",
                notify_submitter=True,
                static_emails="a@example.com",
            )
            r2 = NotificationRule.objects.create(
                workflow=wf,
                stage=None,
                event="approval_request",
                notify_submitter=True,
                static_emails="b@example.com",
            )
            # Vary the M2M attach order between the two forms.
            for gname in group_order_a:
                r1.notify_groups.add(Group.objects.get_or_create(name=gname)[0])
            for gname in group_order_b:
                r2.notify_groups.add(Group.objects.get_or_create(name=gname)[0])
            return fd

        fd_a = build_form("order-a", ["GroupX", "GroupY"], ["GroupZ"])
        fd_b = build_form("order-b", ["GroupY", "GroupX"], ["GroupZ"])

        payload_a = build_export_payload(FormDefinition.objects.filter(pk=fd_a.pk))
        payload_b = build_export_payload(FormDefinition.objects.filter(pk=fd_b.pk))
        rules_a = payload_a["forms"][0]["workflow"]["notification_rules"]
        rules_b = payload_b["forms"][0]["workflow"]["notification_rules"]
        # Lists of dicts must be equal regardless of how rows / M2M attaches
        # were ordered in the DB.
        assert rules_a == rules_b
