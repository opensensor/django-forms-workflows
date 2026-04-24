from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from django_forms_workflows.models import (
    ApprovalTask,
    FormSubmission,
    NotificationRule,
    StageApprovalGroup,
    WorkflowDefinition,
    WorkflowStage,
)
from django_forms_workflows.tasks import send_notification_rules


@pytest.mark.parametrize(
    "event,task_status",
    [
        ("workflow_approved", "approved"),
        ("workflow_denied", "rejected"),
    ],
)
def test_final_decision_notifications_include_dynamic_assignee(
    event,
    task_status,
    form_definition,
    user,
    approver_user,
):
    workflow = WorkflowDefinition.objects.create(
        form_definition=form_definition,
        requires_approval=True,
    )
    stage = WorkflowStage.objects.create(
        workflow=workflow,
        name="Advisor Review",
        order=1,
        approval_logic="all",
        assignee_form_field="advisor_email",
        assignee_lookup_type="email",
    )
    NotificationRule.objects.create(
        workflow=workflow,
        event=event,
        notify_submitter=True,
        notify_stage_assignees=True,
    )
    submission = FormSubmission.objects.create(
        form_definition=form_definition,
        submitter=user,
        form_data={"advisor_email": approver_user.email},
        status="approved" if event == "workflow_approved" else "rejected",
    )
    ApprovalTask.objects.create(
        submission=submission,
        step_name="Advisor Review",
        status=task_status,
        assigned_to=approver_user,
        workflow_stage=stage,
        stage_number=1,
    )

    with patch("django_forms_workflows.tasks._send_html_email") as mock_send:
        send_notification_rules(submission.id, event)

    recipients = [call.args[1][0] for call in mock_send.call_args_list]
    assert recipients == [user.email, approver_user.email]


# ── Answer piping in notification subjects ─────────────────────────────────


def _make_workflow_with_rule(form_definition, event="workflow_approved", **rule_kwargs):
    """Helper: creates a WorkflowDefinition + NotificationRule for tests."""
    workflow = WorkflowDefinition.objects.create(
        form_definition=form_definition,
        requires_approval=False,
    )
    rule = NotificationRule.objects.create(
        workflow=workflow,
        event=event,
        notify_submitter=True,
        **rule_kwargs,
    )
    return workflow, rule


def test_notification_subject_pipes_form_data_field(form_definition, user):
    """A {field_name} token in subject_template is replaced from form_data."""
    _make_workflow_with_rule(
        form_definition,
        subject_template="Application from {full_name} received",
    )
    submission = FormSubmission.objects.create(
        form_definition=form_definition,
        submitter=user,
        form_data={"full_name": "Alice Smith"},
        status="approved",
    )
    with patch("django_forms_workflows.tasks._send_html_email") as mock_send:
        send_notification_rules(submission.id, "workflow_approved")

    assert mock_send.called
    subject = mock_send.call_args[0][0]
    assert "Alice Smith" in subject


def test_notification_subject_unknown_field_becomes_empty(form_definition, user):
    """An unrecognised {token} is replaced with an empty string (defaultdict)."""
    _make_workflow_with_rule(
        form_definition,
        subject_template="Hi {ghost_field}, your form is done",
    )
    submission = FormSubmission.objects.create(
        form_definition=form_definition,
        submitter=user,
        form_data={"full_name": "Bob"},
        status="approved",
    )
    with patch("django_forms_workflows.tasks._send_html_email") as mock_send:
        send_notification_rules(submission.id, "workflow_approved")

    subject = mock_send.call_args[0][0]
    # {ghost_field} → "" so the subject should not contain a literal brace token
    assert "{ghost_field}" not in subject
    assert "Hi " in subject


def test_notification_subject_builtin_placeholders_still_work(form_definition, user):
    """{form_name} and {submission_id} continue to resolve as before."""
    _make_workflow_with_rule(
        form_definition,
        subject_template="{form_name} submission #{submission_id} approved",
    )
    submission = FormSubmission.objects.create(
        form_definition=form_definition,
        submitter=user,
        form_data={},
        status="approved",
    )
    with patch("django_forms_workflows.tasks._send_html_email") as mock_send:
        send_notification_rules(submission.id, "workflow_approved")

    subject = mock_send.call_args[0][0]
    assert form_definition.name in subject
    assert str(submission.id) in subject


def test_notification_subject_list_field_comma_joined(form_definition, user):
    """List-valued form fields are joined with ', ' in the subject."""
    _make_workflow_with_rule(
        form_definition,
        subject_template="Courses: {courses}",
    )
    submission = FormSubmission.objects.create(
        form_definition=form_definition,
        submitter=user,
        form_data={"courses": ["Math", "Science", "History"]},
        status="approved",
    )
    with patch("django_forms_workflows.tasks._send_html_email") as mock_send:
        send_notification_rules(submission.id, "workflow_approved")

    subject = mock_send.call_args[0][0]
    assert "Math, Science, History" in subject


def test_notification_context_includes_form_data(form_definition, user):
    """form_data is passed into the email template context."""
    _make_workflow_with_rule(form_definition)
    submission = FormSubmission.objects.create(
        form_definition=form_definition,
        submitter=user,
        form_data={"dept": "Engineering"},
        status="approved",
    )
    with patch("django_forms_workflows.tasks._send_html_email") as mock_send:
        send_notification_rules(submission.id, "workflow_approved")

    context = mock_send.call_args[0][3]  # 4th positional arg is the context dict
    assert "form_data" in context
    assert context["form_data"]["dept"] == "Engineering"


# ── use_triggering_stage tests ─────────────────────────────────────────────


class TestNotificationRuleUseTriggieringStageValidation:
    """Model-level validation for use_triggering_stage."""

    def test_use_triggering_stage_and_stage_raises(self, form_definition):
        """Cannot set both use_triggering_stage=True and an explicit stage FK."""
        wf = WorkflowDefinition.objects.create(
            form_definition=form_definition, requires_approval=True
        )
        stage = WorkflowStage.objects.create(
            workflow=wf, name="Stage 1", order=1, approval_logic="all"
        )
        rule = NotificationRule(
            workflow=wf,
            event="approval_request",
            stage=stage,
            use_triggering_stage=True,
            notify_submitter=True,
        )
        with pytest.raises(ValidationError, match="mutually exclusive"):
            rule.clean()

    def test_use_triggering_stage_without_stage_ok(self, form_definition):
        """use_triggering_stage=True with no stage FK is valid."""
        wf = WorkflowDefinition.objects.create(
            form_definition=form_definition, requires_approval=True
        )
        rule = NotificationRule(
            workflow=wf,
            event="approval_request",
            use_triggering_stage=True,
            notify_submitter=True,
        )
        # Should not raise
        rule.clean()

    def test_str_shows_triggering_stage(self, form_definition):
        """__str__ includes [triggering stage] when flag is set."""
        wf = WorkflowDefinition.objects.create(
            form_definition=form_definition, requires_approval=True
        )
        rule = NotificationRule(
            workflow=wf,
            event="approval_request",
            use_triggering_stage=True,
            notify_submitter=True,
        )
        assert "[triggering stage]" in str(rule)

    def test_str_shows_explicit_stage_name(self, form_definition):
        """__str__ includes [StageName] when an explicit stage is set."""
        wf = WorkflowDefinition.objects.create(
            form_definition=form_definition, requires_approval=True
        )
        stage = WorkflowStage.objects.create(
            workflow=wf, name="Director Review", order=1, approval_logic="all"
        )
        rule = NotificationRule(
            workflow=wf,
            event="approval_request",
            stage=stage,
            notify_submitter=True,
        )
        assert "[Director Review]" in str(rule)

    def test_str_no_stage_label_when_neither_set(self, form_definition):
        """__str__ has no stage bracket when neither flag nor FK is set."""
        wf = WorkflowDefinition.objects.create(
            form_definition=form_definition, requires_approval=True
        )
        rule = NotificationRule(
            workflow=wf,
            event="approval_request",
            notify_submitter=True,
        )
        assert "[" not in str(rule)


# ── use_triggering_stage recipient resolution ──────────────────────────────


def test_triggering_stage_scopes_assignees(form_definition, user, approver_user):
    """When use_triggering_stage=True, only the triggering stage's assignee is notified."""
    wf = WorkflowDefinition.objects.create(
        form_definition=form_definition, requires_approval=True
    )
    stage1 = WorkflowStage.objects.create(
        workflow=wf,
        name="Stage 1",
        order=1,
        approval_logic="all",
        assignee_form_field="advisor_email",
        assignee_lookup_type="email",
    )
    stage2 = WorkflowStage.objects.create(
        workflow=wf,
        name="Stage 2",
        order=2,
        approval_logic="all",
        assignee_form_field="manager_email",
        assignee_lookup_type="email",
    )
    # Rule with use_triggering_stage — should only notify stage1's assignee
    NotificationRule.objects.create(
        workflow=wf,
        event="approval_request",
        use_triggering_stage=True,
        notify_stage_assignees=True,
    )
    manager = User.objects.create_user(
        username="manager", email="manager@example.com", password="pass"
    )
    submission = FormSubmission.objects.create(
        form_definition=form_definition,
        submitter=user,
        form_data={
            "advisor_email": approver_user.email,
            "manager_email": manager.email,
        },
        status="pending_approval",
    )
    # Create tasks for both stages; approver on stage1, manager on stage2
    task1 = ApprovalTask.objects.create(
        submission=submission,
        step_name="Stage 1",
        status="pending",
        assigned_to=approver_user,
        workflow_stage=stage1,
        stage_number=1,
    )
    ApprovalTask.objects.create(
        submission=submission,
        step_name="Stage 2",
        status="pending",
        assigned_to=manager,
        workflow_stage=stage2,
        stage_number=2,
    )

    with patch("django_forms_workflows.tasks._send_html_email") as mock_send:
        send_notification_rules(submission.id, "approval_request", task_id=task1.id)

    # Only approver (stage1's assignee) should be notified, not manager
    recipients = [call.args[1][0] for call in mock_send.call_args_list]
    assert approver_user.email in recipients
    assert manager.email not in recipients


def test_triggering_stage_scopes_groups(
    form_definition, user, approval_group, second_approval_group
):
    """When use_triggering_stage=True, only the triggering stage's groups are notified."""
    from django.contrib.auth.models import User as AuthUser

    wf = WorkflowDefinition.objects.create(
        form_definition=form_definition, requires_approval=True
    )
    stage1 = WorkflowStage.objects.create(
        workflow=wf,
        name="Stage 1",
        order=1,
        approval_logic="all",
    )
    StageApprovalGroup.objects.create(stage=stage1, group=approval_group)
    stage2 = WorkflowStage.objects.create(
        workflow=wf,
        name="Stage 2",
        order=2,
        approval_logic="all",
    )
    StageApprovalGroup.objects.create(stage=stage2, group=second_approval_group)

    # Users in each group
    user_g1 = AuthUser.objects.create_user(
        username="g1user", email="g1@example.com", password="pass"
    )
    user_g1.groups.add(approval_group)
    user_g2 = AuthUser.objects.create_user(
        username="g2user", email="g2@example.com", password="pass"
    )
    user_g2.groups.add(second_approval_group)

    NotificationRule.objects.create(
        workflow=wf,
        event="approval_request",
        use_triggering_stage=True,
        notify_stage_groups=True,
    )
    submission = FormSubmission.objects.create(
        form_definition=form_definition,
        submitter=user,
        form_data={},
        status="pending_approval",
    )
    task1 = ApprovalTask.objects.create(
        submission=submission,
        step_name="Stage 1",
        status="pending",
        workflow_stage=stage1,
        stage_number=1,
    )

    with patch("django_forms_workflows.tasks._send_html_email") as mock_send:
        send_notification_rules(submission.id, "approval_request", task_id=task1.id)

    recipients = [call.args[1][0] for call in mock_send.call_args_list]
    assert "g1@example.com" in recipients
    assert "g2@example.com" not in recipients


# ── Workflow scoping tests ─────────────────────────────────────────────────


def test_notification_rules_scoped_to_task_workflow(form_definition, user):
    """When task_id is provided, only rules from the task's workflow fire."""
    wf1 = WorkflowDefinition.objects.create(
        form_definition=form_definition, requires_approval=True
    )
    stage1 = WorkflowStage.objects.create(
        workflow=wf1,
        name="WF1 Stage",
        order=1,
        approval_logic="all",
    )
    wf2 = WorkflowDefinition.objects.create(
        form_definition=form_definition, requires_approval=True
    )
    WorkflowStage.objects.create(
        workflow=wf2,
        name="WF2 Stage",
        order=1,
        approval_logic="all",
    )

    # Rule on wf1 — should fire
    NotificationRule.objects.create(
        workflow=wf1,
        event="approval_request",
        notify_submitter=True,
        static_emails="wf1@example.com",
    )
    # Rule on wf2 — should NOT fire when task belongs to wf1
    NotificationRule.objects.create(
        workflow=wf2,
        event="approval_request",
        notify_submitter=True,
        static_emails="wf2@example.com",
    )

    submission = FormSubmission.objects.create(
        form_definition=form_definition,
        submitter=user,
        form_data={},
        status="pending_approval",
    )
    task = ApprovalTask.objects.create(
        submission=submission,
        step_name="WF1 Stage",
        status="pending",
        workflow_stage=stage1,
        stage_number=1,
    )

    with patch("django_forms_workflows.tasks._send_html_email") as mock_send:
        send_notification_rules(submission.id, "approval_request", task_id=task.id)

    all_recipients = [call.args[1][0] for call in mock_send.call_args_list]
    assert "wf1@example.com" in all_recipients
    assert "wf2@example.com" not in all_recipients


def test_no_task_id_fires_all_workflow_rules(form_definition, user):
    """When no task_id is given, rules from all workflows on the form fire."""
    wf1 = WorkflowDefinition.objects.create(
        form_definition=form_definition, requires_approval=False
    )
    wf2 = WorkflowDefinition.objects.create(
        form_definition=form_definition, requires_approval=False
    )
    NotificationRule.objects.create(
        workflow=wf1,
        event="submission_received",
        static_emails="wf1@example.com",
    )
    NotificationRule.objects.create(
        workflow=wf2,
        event="submission_received",
        static_emails="wf2@example.com",
    )

    submission = FormSubmission.objects.create(
        form_definition=form_definition,
        submitter=user,
        form_data={},
        status="submitted",
    )

    with patch("django_forms_workflows.tasks._send_html_email") as mock_send:
        send_notification_rules(submission.id, "submission_received")

    all_recipients = [call.args[1][0] for call in mock_send.call_args_list]
    assert "wf1@example.com" in all_recipients
    assert "wf2@example.com" in all_recipients


# ── approver context in template rendering ─────────────────────────────


def test_approval_request_includes_approver_in_context(
    form_definition, user, approver_user
):
    """send_notification_rules passes 'approver' (User) in the template context."""
    wf = WorkflowDefinition.objects.create(
        form_definition=form_definition, requires_approval=True
    )
    stage = WorkflowStage.objects.create(
        workflow=wf,
        name="Stage 1",
        order=1,
        approval_logic="all",
        assignee_form_field="advisor_email",
        assignee_lookup_type="email",
    )
    NotificationRule.objects.create(
        workflow=wf,
        event="approval_request",
        use_triggering_stage=True,
        notify_stage_assignees=True,
    )
    submission = FormSubmission.objects.create(
        form_definition=form_definition,
        submitter=user,
        form_data={"advisor_email": approver_user.email},
        status="pending_approval",
    )
    task = ApprovalTask.objects.create(
        submission=submission,
        step_name="Stage 1",
        status="pending",
        assigned_to=approver_user,
        workflow_stage=stage,
        stage_number=1,
    )

    with patch("django_forms_workflows.tasks._send_html_email") as mock_send:
        send_notification_rules(submission.id, "approval_request", task_id=task.id)

    assert mock_send.call_count >= 1
    # The context dict is the 4th positional arg (index 3)
    ctx = mock_send.call_args_list[0].args[3]
    assert "approver" in ctx
    assert ctx["approver"].pk == approver_user.pk


# ── body_template rendering ───────────────────────────────────────────


def test_body_template_renders_inline_html(form_definition, user, approver_user):
    """When body_template is set, it renders as a Django template string."""
    wf = WorkflowDefinition.objects.create(
        form_definition=form_definition, requires_approval=True
    )
    stage = WorkflowStage.objects.create(
        workflow=wf,
        name="Stage 1",
        order=1,
        approval_logic="all",
        assignee_form_field="advisor_email",
        assignee_lookup_type="email",
    )
    NotificationRule.objects.create(
        workflow=wf,
        event="approval_request",
        use_triggering_stage=True,
        notify_stage_assignees=True,
        body_template="<p>Hello {{ approver.username }}, please review.</p>",
    )
    submission = FormSubmission.objects.create(
        form_definition=form_definition,
        submitter=user,
        form_data={"advisor_email": approver_user.email},
        status="pending_approval",
    )
    task = ApprovalTask.objects.create(
        submission=submission,
        step_name="Stage 1",
        status="pending",
        assigned_to=approver_user,
        workflow_stage=stage,
        stage_number=1,
    )

    with (
        patch(
            "django_forms_workflows.tasks._send_html_email_from_string"
        ) as mock_send_str,
        patch("django_forms_workflows.tasks._send_html_email") as mock_send_file,
    ):
        send_notification_rules(submission.id, "approval_request", task_id=task.id)

    # Should use the string renderer, not the file renderer
    assert mock_send_str.call_count >= 1
    assert mock_send_file.call_count == 0
    # Verify the body_template was passed
    body_arg = mock_send_str.call_args_list[0].args[2]
    assert "Hello {{ approver.username }}" in body_arg


def test_empty_body_template_uses_file_template(form_definition, user, approver_user):
    """When body_template is empty, falls back to the file-based template."""
    wf = WorkflowDefinition.objects.create(
        form_definition=form_definition, requires_approval=True
    )
    stage = WorkflowStage.objects.create(
        workflow=wf,
        name="Stage 1",
        order=1,
        approval_logic="all",
        assignee_form_field="advisor_email",
        assignee_lookup_type="email",
    )
    NotificationRule.objects.create(
        workflow=wf,
        event="approval_request",
        use_triggering_stage=True,
        notify_stage_assignees=True,
        body_template="",  # empty → use file
    )
    submission = FormSubmission.objects.create(
        form_definition=form_definition,
        submitter=user,
        form_data={"advisor_email": approver_user.email},
        status="pending_approval",
    )
    task = ApprovalTask.objects.create(
        submission=submission,
        step_name="Stage 1",
        status="pending",
        assigned_to=approver_user,
        workflow_stage=stage,
        stage_number=1,
    )

    with (
        patch(
            "django_forms_workflows.tasks._send_html_email_from_string"
        ) as mock_send_str,
        patch("django_forms_workflows.tasks._send_html_email") as mock_send_file,
    ):
        send_notification_rules(submission.id, "approval_request", task_id=task.id)

    assert mock_send_file.call_count >= 1
    assert mock_send_str.call_count == 0


# ── Built-in send_approval_request no longer dispatched ────────────────


def test_notify_task_request_does_not_call_send_approval_request(
    form_definition, user, approver_user
):
    """_notify_task_request no longer dispatches the built-in send_approval_request."""
    wf = WorkflowDefinition.objects.create(
        form_definition=form_definition, requires_approval=True
    )
    stage = WorkflowStage.objects.create(
        workflow=wf,
        name="Stage 1",
        order=1,
        approval_logic="all",
        assignee_form_field="advisor_email",
        assignee_lookup_type="email",
    )
    NotificationRule.objects.create(
        workflow=wf,
        event="approval_request",
        use_triggering_stage=True,
        notify_stage_assignees=True,
    )
    submission = FormSubmission.objects.create(
        form_definition=form_definition,
        submitter=user,
        form_data={"advisor_email": approver_user.email},
        status="pending_approval",
    )
    task = ApprovalTask.objects.create(
        submission=submission,
        step_name="Stage 1",
        status="pending",
        assigned_to=approver_user,
        workflow_stage=stage,
        stage_number=1,
    )

    from django_forms_workflows.workflow_engine import _notify_task_request

    with (
        patch(
            "django_forms_workflows.workflow_engine._dispatch_notification_rules"
        ) as mock_dispatch,
        patch("django_forms_workflows.tasks.send_approval_request") as mock_builtin,
    ):
        _notify_task_request(task)

    # NotificationRule dispatch was called
    mock_dispatch.assert_called_once()
    # Built-in was NOT called
    mock_builtin.delay.assert_not_called()


# ── approval_reminder + escalation event types ─────────────────────────


def test_approval_reminder_event_type_works(form_definition, user, approver_user):
    """approval_reminder event type fires via send_notification_rules."""
    wf = WorkflowDefinition.objects.create(
        form_definition=form_definition, requires_approval=True
    )
    stage = WorkflowStage.objects.create(
        workflow=wf,
        name="Stage 1",
        order=1,
        approval_logic="all",
        assignee_form_field="advisor_email",
        assignee_lookup_type="email",
    )
    NotificationRule.objects.create(
        workflow=wf,
        event="approval_reminder",
        use_triggering_stage=True,
        notify_stage_assignees=True,
    )
    submission = FormSubmission.objects.create(
        form_definition=form_definition,
        submitter=user,
        form_data={"advisor_email": approver_user.email},
        status="pending_approval",
    )
    task = ApprovalTask.objects.create(
        submission=submission,
        step_name="Stage 1",
        status="pending",
        assigned_to=approver_user,
        workflow_stage=stage,
        stage_number=1,
    )

    with patch("django_forms_workflows.tasks._send_html_email") as mock_send:
        send_notification_rules(submission.id, "approval_reminder", task_id=task.id)

    assert mock_send.call_count >= 1
    recipients = [call.args[1][0] for call in mock_send.call_args_list]
    assert approver_user.email in recipients


# ── notify_stage_groups skipped when assigned_to is resolved ───────────


def test_stage_groups_skipped_when_assigned_to_resolved(
    form_definition, user, approver_user, approval_group
):
    """When use_triggering_stage and the task has assigned_to, stage groups are skipped."""
    from django.contrib.auth.models import User as AuthUser

    wf = WorkflowDefinition.objects.create(
        form_definition=form_definition, requires_approval=True
    )
    stage = WorkflowStage.objects.create(
        workflow=wf,
        name="Stage 1",
        order=1,
        approval_logic="all",
        assignee_form_field="advisor_email",
        assignee_lookup_type="email",
    )
    StageApprovalGroup.objects.create(stage=stage, group=approval_group)

    # Group member who should NOT be notified
    group_user = AuthUser.objects.create_user(
        username="groupmember", email="groupmember@example.com", password="pass"
    )
    group_user.groups.add(approval_group)

    NotificationRule.objects.create(
        workflow=wf,
        event="approval_request",
        use_triggering_stage=True,
        notify_stage_assignees=True,
        notify_stage_groups=True,
    )
    submission = FormSubmission.objects.create(
        form_definition=form_definition,
        submitter=user,
        form_data={"advisor_email": approver_user.email},
        status="pending_approval",
    )
    # Task has assigned_to set — groups should be skipped
    task = ApprovalTask.objects.create(
        submission=submission,
        step_name="Stage 1",
        status="pending",
        assigned_to=approver_user,
        workflow_stage=stage,
        stage_number=1,
    )

    with patch("django_forms_workflows.tasks._send_html_email") as mock_send:
        send_notification_rules(submission.id, "approval_request", task_id=task.id)

    recipients = [call.args[1][0] for call in mock_send.call_args_list]
    assert approver_user.email in recipients
    assert "groupmember@example.com" not in recipients


def test_stage_groups_fire_when_no_assigned_to(form_definition, user, approval_group):
    """When the task has no assigned_to (group-only), stage groups DO fire."""
    from django.contrib.auth.models import User as AuthUser

    wf = WorkflowDefinition.objects.create(
        form_definition=form_definition, requires_approval=True
    )
    stage = WorkflowStage.objects.create(
        workflow=wf,
        name="Stage 1",
        order=1,
        approval_logic="all",
    )
    StageApprovalGroup.objects.create(stage=stage, group=approval_group)

    group_user = AuthUser.objects.create_user(
        username="groupmember2", email="groupmember2@example.com", password="pass"
    )
    group_user.groups.add(approval_group)

    NotificationRule.objects.create(
        workflow=wf,
        event="approval_request",
        use_triggering_stage=True,
        notify_stage_groups=True,
    )
    submission = FormSubmission.objects.create(
        form_definition=form_definition,
        submitter=user,
        form_data={},
        status="pending_approval",
    )
    # Task with NO assigned_to — groups should fire
    task = ApprovalTask.objects.create(
        submission=submission,
        step_name="Stage 1",
        status="pending",
        assigned_group=approval_group,
        workflow_stage=stage,
        stage_number=1,
    )

    with patch("django_forms_workflows.tasks._send_html_email") as mock_send:
        send_notification_rules(submission.id, "approval_request", task_id=task.id)

    recipients = [call.args[1][0] for call in mock_send.call_args_list]
    assert "groupmember2@example.com" in recipients


# ── CC recipients (static and dynamic) ─────────────────────────────────


def test_cc_static_and_dynamic_attached_to_first_email(
    form_definition, user, approver_user
):
    """Static and dynamic CC addresses are attached to the first outgoing email."""
    wf = WorkflowDefinition.objects.create(
        form_definition=form_definition, requires_approval=False
    )
    NotificationRule.objects.create(
        workflow=wf,
        event="workflow_approved",
        notify_submitter=True,
        static_emails=approver_user.email,
        cc_static_emails="auditor@example.com, supervisor@example.com",
        cc_email_field="copy_email",
    )
    submission = FormSubmission.objects.create(
        form_definition=form_definition,
        submitter=user,
        form_data={"copy_email": "dynamic_cc@example.com"},
        status="approved",
    )

    with patch("django_forms_workflows.tasks._send_html_email") as mock_send:
        send_notification_rules(submission.id, "workflow_approved")

    assert mock_send.call_count == 2
    first_cc = mock_send.call_args_list[0].kwargs.get("cc") or []
    second_cc = mock_send.call_args_list[1].kwargs.get("cc") or []
    assert "auditor@example.com" in first_cc
    assert "supervisor@example.com" in first_cc
    assert "dynamic_cc@example.com" in first_cc
    assert second_cc == []


def test_cc_duplicate_of_to_is_dropped(form_definition, user):
    """A CC address that already appears in the TO list is removed from CC."""
    wf = WorkflowDefinition.objects.create(
        form_definition=form_definition, requires_approval=False
    )
    NotificationRule.objects.create(
        workflow=wf,
        event="workflow_approved",
        notify_submitter=True,
        cc_static_emails=f"{user.email}, other@example.com",
    )
    submission = FormSubmission.objects.create(
        form_definition=form_definition,
        submitter=user,
        form_data={},
        status="approved",
    )

    with patch("django_forms_workflows.tasks._send_html_email") as mock_send:
        send_notification_rules(submission.id, "workflow_approved")

    cc = mock_send.call_args_list[0].kwargs.get("cc") or []
    assert user.email not in cc
    assert "other@example.com" in cc


def test_cc_passed_to_email_message(form_definition, user):
    """The CC list propagates all the way to the underlying EmailMultiAlternatives."""
    from unittest.mock import MagicMock

    wf = WorkflowDefinition.objects.create(
        form_definition=form_definition, requires_approval=False
    )
    NotificationRule.objects.create(
        workflow=wf,
        event="workflow_approved",
        notify_submitter=True,
        cc_static_emails="cc1@example.com",
    )
    submission = FormSubmission.objects.create(
        form_definition=form_definition,
        submitter=user,
        form_data={},
        status="approved",
    )

    with patch("django_forms_workflows.tasks.EmailMultiAlternatives") as mock_msg_cls:
        mock_msg_cls.return_value = MagicMock()
        send_notification_rules(submission.id, "workflow_approved")

    assert mock_msg_cls.call_count == 1
    kwargs = mock_msg_cls.call_args.kwargs
    assert kwargs["to"] == [user.email]
    assert kwargs["cc"] == ["cc1@example.com"]
