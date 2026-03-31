"""
Tests for django_forms_workflows.workflow_engine.
"""

from unittest.mock import patch

from django.contrib.auth.models import Group, User

from django_forms_workflows.models import (
    ApprovalTask,
    FormDefinition,
    FormSubmission,
    SubWorkflowDefinition,
    SubWorkflowInstance,
    WorkflowDefinition,
    WorkflowStage,
)
from django_forms_workflows.workflow_engine import (
    _dispatch_notification_rules,
    create_workflow_tasks,
    handle_approval,
    handle_rejection,
    handle_sub_workflow_approval,
    handle_sub_workflow_rejection,
)

# ── Helper ────────────────────────────────────────────────────────────────


def _make_submission(form_def, user, **overrides):
    defaults = {
        "form_definition": form_def,
        "submitter": user,
        "form_data": {"full_name": "Test User"},
        "status": "submitted",
    }
    defaults.update(overrides)
    return FormSubmission.objects.create(**defaults)


# ── No-workflow (auto-approve) ────────────────────────────────────────────


class TestAutoApprove:
    @patch("django_forms_workflows.workflow_engine._notify_submission_created")
    @patch("django_forms_workflows.workflow_engine._notify_final_approval")
    def test_no_workflow_auto_approves(
        self, mock_final, mock_created, form_definition, user
    ):
        sub = _make_submission(form_definition, user)
        create_workflow_tasks(sub)
        sub.refresh_from_db()
        assert sub.status == "approved"
        mock_created.assert_called_once()
        mock_final.assert_called_once()

    @patch("django_forms_workflows.workflow_engine._notify_submission_created")
    @patch("django_forms_workflows.workflow_engine._notify_final_approval")
    def test_workflow_no_approval_required(
        self, mock_final, mock_created, form_definition, user
    ):
        WorkflowDefinition.objects.create(
            form_definition=form_definition, requires_approval=False
        )
        sub = _make_submission(form_definition, user)
        create_workflow_tasks(sub)
        sub.refresh_from_db()
        assert sub.status == "approved"


class TestNotificationDispatch:
    @patch(
        "django_forms_workflows.workflow_engine.transaction.on_commit",
        side_effect=lambda fn: fn(),
    )
    @patch("django_forms_workflows.tasks.send_notification_rules.delay")
    def test_notification_rules_dispatch_on_commit(
        self, mock_delay, mock_on_commit, submission
    ):
        _dispatch_notification_rules(submission, "submission_received")

        mock_on_commit.assert_called()
        mock_delay.assert_any_call(submission.id, "submission_received", None)


# ── Legacy flat mode (all) ────────────────────────────────────────────────


class TestLegacyFlatAll:
    @patch("django_forms_workflows.workflow_engine._notify_task_request")
    @patch("django_forms_workflows.workflow_engine._notify_submission_created")
    def test_creates_parallel_tasks(self, mock_created, mock_task_req, workflow, user):
        sub = _make_submission(workflow.form_definition, user)
        create_workflow_tasks(sub)
        sub.refresh_from_db()
        assert sub.status == "pending_approval"
        tasks = sub.approval_tasks.all()
        assert tasks.count() == 1  # one group = one task

    @patch("django_forms_workflows.workflow_engine._notify_final_approval")
    @patch("django_forms_workflows.workflow_engine._notify_task_request")
    @patch("django_forms_workflows.workflow_engine._notify_submission_created")
    def test_all_approve_finalizes(
        self, mock_created, mock_task, mock_final, workflow, user, approver_user
    ):
        # The workflow fixture already has a stage with "any" logic;
        # update it to "all" for this test.
        stage = workflow.stages.first()
        stage.approval_logic = "all"
        stage.save()
        sub = _make_submission(workflow.form_definition, user)
        create_workflow_tasks(sub)
        task = sub.approval_tasks.first()
        task.status = "approved"
        task.approved_by = approver_user
        task.save()
        handle_approval(sub, task, workflow)
        sub.refresh_from_db()
        assert sub.status == "approved"


# ── Staged mode (any) ─────────────────────────────────────────────────────


class TestStagedAny:
    @patch("django_forms_workflows.workflow_engine._notify_final_approval")
    @patch("django_forms_workflows.workflow_engine._notify_task_request")
    @patch("django_forms_workflows.workflow_engine._notify_submission_created")
    def test_any_approve_finalizes(
        self, mock_created, mock_task, mock_final, form_definition, user, approver_user
    ):
        g1 = Group.objects.create(name="Group A")
        g2 = Group.objects.create(name="Group B")
        wf = WorkflowDefinition.objects.create(
            form_definition=form_definition,
            requires_approval=True,
        )
        stage = WorkflowStage.objects.create(
            workflow=wf, name="Review", order=1, approval_logic="any"
        )
        stage.approval_groups.add(g1, g2)
        sub = _make_submission(form_definition, user)
        create_workflow_tasks(sub)
        assert sub.approval_tasks.count() == 2
        # Approve just one
        task = sub.approval_tasks.filter(assigned_group=g1).first()
        task.status = "approved"
        task.approved_by = approver_user
        task.save()
        handle_approval(sub, task, wf)
        sub.refresh_from_db()
        assert sub.status == "approved"


# ── Staged mode (sequence across stages) ─────────────────────────────────


class TestStagedSequence:
    @patch("django_forms_workflows.workflow_engine._notify_final_approval")
    @patch("django_forms_workflows.workflow_engine._notify_task_request")
    @patch("django_forms_workflows.workflow_engine._notify_submission_created")
    def test_sequence_creates_one_at_a_time(
        self, mock_created, mock_task, mock_final, form_definition, user, approver_user
    ):
        g1 = Group.objects.create(name="Step1")
        g2 = Group.objects.create(name="Step2")
        wf = WorkflowDefinition.objects.create(
            form_definition=form_definition,
            requires_approval=True,
        )
        stage1 = WorkflowStage.objects.create(
            workflow=wf, name="Stage 1", order=1, approval_logic="all"
        )
        stage1.approval_groups.add(g1)
        stage2 = WorkflowStage.objects.create(
            workflow=wf, name="Stage 2", order=2, approval_logic="all"
        )
        stage2.approval_groups.add(g2)
        sub = _make_submission(form_definition, user)
        create_workflow_tasks(sub)
        # Only stage 1 task initially
        assert sub.approval_tasks.filter(status="pending").count() == 1
        task1 = sub.approval_tasks.first()
        assert task1.assigned_group == g1

        # Approve first; stage 2 task should be created
        task1.status = "approved"
        task1.approved_by = approver_user
        task1.save()
        handle_approval(sub, task1, wf)
        assert sub.approval_tasks.filter(status="pending").count() == 1
        task2 = sub.approval_tasks.filter(status="pending").first()
        assert task2.assigned_group == g2

        # Approve second => finalized
        task2.status = "approved"
        task2.approved_by = approver_user
        task2.save()
        handle_approval(sub, task2, wf)
        sub.refresh_from_db()
        assert sub.status == "approved"


# ── Staged workflow ───────────────────────────────────────────────────────


class TestStagedWorkflow:
    @patch("django_forms_workflows.workflow_engine._notify_task_request")
    @patch("django_forms_workflows.workflow_engine._notify_submission_created")
    def test_creates_first_stage_only(
        self, mock_created, mock_task, staged_workflow, user
    ):
        sub = _make_submission(staged_workflow.form_definition, user)
        create_workflow_tasks(sub)
        sub.refresh_from_db()
        assert sub.status == "pending_approval"
        # Only Stage 1 tasks should be created
        tasks = sub.approval_tasks.filter(status="pending")
        stages_in_tasks = set(tasks.values_list("stage_number", flat=True))
        assert 1 in stages_in_tasks
        assert 2 not in stages_in_tasks

    @patch("django_forms_workflows.workflow_engine._notify_final_approval")
    @patch("django_forms_workflows.workflow_engine._notify_task_request")
    @patch("django_forms_workflows.workflow_engine._notify_submission_created")
    def test_stage_advance(
        self, mock_created, mock_task, mock_final, staged_workflow, user, approver_user
    ):
        sub = _make_submission(staged_workflow.form_definition, user)
        create_workflow_tasks(sub)
        # Approve all stage 1 tasks
        for t in sub.approval_tasks.filter(status="pending"):
            t.status = "approved"
            t.approved_by = approver_user
            t.save()
            handle_approval(sub, t, staged_workflow)
        # Now stage 2 tasks should exist
        stage2_tasks = sub.approval_tasks.filter(stage_number=2, status="pending")
        assert stage2_tasks.count() >= 1

        # Approve stage 2
        for t in stage2_tasks:
            t.status = "approved"
            t.approved_by = approver_user
            t.save()
            handle_approval(sub, t, staged_workflow)
        sub.refresh_from_db()
        assert sub.status == "approved"


# ── Rejection tests ──────────────────────────────────────────────────────


class TestRejection:
    @patch("django_forms_workflows.workflow_engine._notify_rejection")
    @patch("django_forms_workflows.workflow_engine._notify_task_request")
    @patch("django_forms_workflows.workflow_engine._notify_submission_created")
    def test_staged_all_reject(
        self, mock_created, mock_task, mock_reject, workflow, user, approver_user
    ):
        # The workflow fixture has a stage with "any" logic; change to "all"
        stage = workflow.stages.first()
        stage.approval_logic = "all"
        stage.save()
        sub = _make_submission(workflow.form_definition, user)
        create_workflow_tasks(sub)
        task = sub.approval_tasks.first()
        task.status = "rejected"
        task.approved_by = approver_user
        task.rejection_reason = "Not acceptable"
        task.save()
        handle_rejection(sub, task, workflow)
        sub.refresh_from_db()
        assert sub.status == "rejected"
        mock_reject.assert_called_once()

    @patch("django_forms_workflows.workflow_engine._notify_rejection")
    @patch("django_forms_workflows.workflow_engine._notify_task_request")
    @patch("django_forms_workflows.workflow_engine._notify_submission_created")
    def test_any_single_reject_not_final(
        self, mock_created, mock_task, mock_reject, form_definition, user, approver_user
    ):
        g1 = Group.objects.create(name="Grp1")
        g2 = Group.objects.create(name="Grp2")
        wf = WorkflowDefinition.objects.create(
            form_definition=form_definition,
            requires_approval=True,
        )
        stage = WorkflowStage.objects.create(
            workflow=wf, name="Review", order=1, approval_logic="any"
        )
        stage.approval_groups.add(g1, g2)
        sub = _make_submission(form_definition, user)
        create_workflow_tasks(sub)
        # Reject one — submission should survive
        task1 = sub.approval_tasks.filter(assigned_group=g1).first()
        task1.status = "rejected"
        task1.approved_by = approver_user
        task1.save()
        handle_rejection(sub, task1, wf)
        sub.refresh_from_db()
        assert sub.status == "pending_approval"

    @patch("django_forms_workflows.workflow_engine._notify_rejection")
    @patch("django_forms_workflows.workflow_engine._notify_task_request")
    @patch("django_forms_workflows.workflow_engine._notify_submission_created")
    def test_staged_reject(
        self, mock_created, mock_task, mock_reject, staged_workflow, user, approver_user
    ):
        sub = _make_submission(staged_workflow.form_definition, user)
        create_workflow_tasks(sub)
        task = sub.approval_tasks.filter(status="pending").first()
        task.status = "rejected"
        task.approved_by = approver_user
        task.rejection_reason = "Not appropriate"
        task.save()
        # Staged workflow with "all" logic => single rejection vetoes
        handle_rejection(sub, task, staged_workflow)
        sub.refresh_from_db()
        assert sub.status == "rejected"


# ── Empty workflow edges ──────────────────────────────────────────────────


class TestEdgeCases:
    @patch("django_forms_workflows.workflow_engine._notify_final_approval")
    @patch("django_forms_workflows.workflow_engine._notify_submission_created")
    def test_workflow_with_no_groups_auto_approves(
        self, mock_created, mock_final, form_definition, user
    ):
        WorkflowDefinition.objects.create(
            form_definition=form_definition, requires_approval=True
        )
        sub = _make_submission(form_definition, user)
        create_workflow_tasks(sub)
        sub.refresh_from_db()
        assert sub.status == "approved"

    @patch("django_forms_workflows.workflow_engine._notify_final_approval")
    @patch("django_forms_workflows.workflow_engine._notify_submission_created")
    def test_staged_empty_stage_auto_approves(
        self, mock_created, mock_final, form_definition, user
    ):
        wf = WorkflowDefinition.objects.create(
            form_definition=form_definition, requires_approval=True
        )
        # Stage with no groups
        WorkflowStage.objects.create(workflow=wf, name="Empty Stage", order=1)
        sub = _make_submission(form_definition, user)
        create_workflow_tasks(sub)
        sub.refresh_from_db()
        assert sub.status == "approved"


class TestSendBack:
    @patch("django_forms_workflows.workflow_engine._notify_task_request")
    @patch("django_forms_workflows.workflow_engine._notify_submission_created")
    def test_send_back_creates_new_tasks(
        self, mock_created, mock_task_req, staged_workflow, user, approval_group
    ):
        from django_forms_workflows.models import ApprovalTask
        from django_forms_workflows.workflow_engine import handle_send_back

        sub = _make_submission(staged_workflow.form_definition, user)

        stages = list(staged_workflow.stages.order_by("order"))
        stage1 = stages[0]
        stage2 = stages[1]

        # Simulate: stage1 approved, now at stage2
        ApprovalTask.objects.create(
            submission=sub,
            assigned_group=approval_group,
            step_name="Manager Review",
            status="approved",
            stage_number=1,
            workflow_stage=stage1,
        )
        t2 = ApprovalTask.objects.create(
            submission=sub,
            assigned_group=Group.objects.get(name="Finance Approvers"),
            step_name="Finance Review",
            status="returned",
            stage_number=2,
            workflow_stage=stage2,
        )
        sub.status = "pending_approval"
        sub.save()

        handle_send_back(sub, t2, stage1)

        # New task(s) should be created for stage1
        new_tasks = ApprovalTask.objects.filter(
            submission=sub, workflow_stage=stage1, status="pending"
        )
        assert new_tasks.count() >= 1


class TestTwoStageFullCycle:
    """End-to-end: submit → stage 1 approve → stage 2 approve → approved."""

    @patch("django_forms_workflows.workflow_engine._notify_final_approval")
    @patch("django_forms_workflows.workflow_engine._notify_task_request")
    @patch("django_forms_workflows.workflow_engine._notify_submission_created")
    def test_full_two_stage_approval(
        self,
        mock_created,
        mock_task_req,
        mock_final,
        staged_workflow,
        user,
        approval_group,
        second_approval_group,
    ):
        from django_forms_workflows.models import ApprovalTask

        sub = _make_submission(staged_workflow.form_definition, user)
        create_workflow_tasks(sub)

        # Stage 1 task should be pending
        s1_tasks = ApprovalTask.objects.filter(
            submission=sub, stage_number=1, status="pending"
        )
        assert s1_tasks.count() >= 1

        # Approve stage 1
        for task in s1_tasks:
            task.status = "approved"
            task.save()
            handle_approval(sub, task, staged_workflow)

        sub.refresh_from_db()
        # Should not be final approved yet (stage 2 pending)
        assert sub.status == "pending_approval"

        # Stage 2 task should now exist
        s2_tasks = ApprovalTask.objects.filter(
            submission=sub, stage_number=2, status="pending"
        )
        assert s2_tasks.count() >= 1

        # Approve stage 2
        for task in s2_tasks:
            task.status = "approved"
            task.save()
            handle_approval(sub, task, staged_workflow)

        sub.refresh_from_db()
        assert sub.status == "approved"


# ── Dynamic assignee: email lookup ────────────────────────────────────────


class TestDynamicAssigneeByEmail:
    @patch("django_forms_workflows.workflow_engine._notify_task_request")
    @patch("django_forms_workflows.workflow_engine._notify_submission_created")
    def test_email_assignee_creates_personal_task(
        self, mock_created, mock_task, form_definition, user
    ):
        """When a stage has assignee_form_field set to an email field, the engine
        resolves it to a Django User and creates an assigned_to task.

        Note: the stage must have at least one approval group so that the
        pre-check in ``create_workflow_tasks`` considers it a non-empty stage.
        The assignee is placed in that group so the optional group-validation
        check (validate_assignee_group=True) also passes.
        """
        approval_group = Group.objects.create(name="Assignee Group Email")
        assignee = User.objects.create_user(
            "assignee_e", email="assignee@example.com", password="pass"
        )
        assignee.groups.add(approval_group)

        wf = WorkflowDefinition.objects.create(
            form_definition=form_definition, requires_approval=True
        )
        stage = WorkflowStage.objects.create(
            workflow=wf,
            name="Personal Review",
            order=1,
            approval_logic="all",
            assignee_form_field="reviewer_email",
            assignee_lookup_type="email",
        )
        # A group is required so the stage is not silently skipped as "empty".
        stage.approval_groups.add(approval_group)

        sub = FormSubmission.objects.create(
            form_definition=form_definition,
            submitter=user,
            form_data={"reviewer_email": "assignee@example.com"},
            status="submitted",
        )
        create_workflow_tasks(sub)
        sub.refresh_from_db()
        assert sub.status == "pending_approval"
        tasks = sub.approval_tasks.filter(assigned_to=assignee)
        assert tasks.count() == 1

    @patch("django_forms_workflows.workflow_engine._notify_final_approval")
    @patch("django_forms_workflows.workflow_engine._notify_task_request")
    @patch("django_forms_workflows.workflow_engine._notify_submission_created")
    def test_missing_email_falls_back_to_group_task(
        self, mock_created, mock_task, mock_final, form_definition, user
    ):
        """An email value with no '@' returns None from _lookup_by_email.
        The engine falls back to the stage's approval groups and creates
        a standard group task.
        """
        g = Group.objects.create(name="Fallback Group")
        wf = WorkflowDefinition.objects.create(
            form_definition=form_definition, requires_approval=True
        )
        stage = WorkflowStage.objects.create(
            workflow=wf,
            name="Personal Review",
            order=1,
            approval_logic="all",
            assignee_form_field="reviewer_email",
            assignee_lookup_type="email",
        )
        stage.approval_groups.add(g)
        sub = FormSubmission.objects.create(
            form_definition=form_definition,
            submitter=user,
            form_data={"reviewer_email": "not-an-email"},
            status="submitted",
        )
        create_workflow_tasks(sub)
        sub.refresh_from_db()
        # Bad email → fallback to group task; submission stays pending
        assert sub.status == "pending_approval"
        assert (
            sub.approval_tasks.filter(assigned_group=g, status="pending").count() == 1
        )


# ── Dynamic assignee: username lookup ─────────────────────────────────────


class TestDynamicAssigneeByUsername:
    @patch("django_forms_workflows.workflow_engine._notify_task_request")
    @patch("django_forms_workflows.workflow_engine._notify_submission_created")
    def test_username_assignee_creates_personal_task(
        self, mock_created, mock_task, form_definition, user
    ):
        """Stage with assignee_lookup_type='username' resolves by Django username."""
        approval_group = Group.objects.create(name="Assignee Group Username")
        assignee = User.objects.create_user(
            "jsmith", email="jsmith@example.com", password="pass"
        )
        assignee.groups.add(approval_group)

        wf = WorkflowDefinition.objects.create(
            form_definition=form_definition, requires_approval=True
        )
        stage = WorkflowStage.objects.create(
            workflow=wf,
            name="Username Review",
            order=1,
            approval_logic="all",
            assignee_form_field="manager_username",
            assignee_lookup_type="username",
        )
        stage.approval_groups.add(approval_group)
        sub = FormSubmission.objects.create(
            form_definition=form_definition,
            submitter=user,
            form_data={"manager_username": "jsmith"},
            status="submitted",
        )
        create_workflow_tasks(sub)
        tasks = sub.approval_tasks.filter(assigned_to=assignee)
        assert tasks.count() == 1


# ── Dynamic assignee: full_name lookup ────────────────────────────────────


class TestDynamicAssigneeByFullName:
    @patch("django_forms_workflows.workflow_engine._notify_task_request")
    @patch("django_forms_workflows.workflow_engine._notify_submission_created")
    def test_full_name_assignee_resolves(
        self, mock_created, mock_task, form_definition, user
    ):
        """Stage with assignee_lookup_type='full_name' resolves by first+last name."""
        approval_group = Group.objects.create(name="Assignee Group FullName")
        assignee = User.objects.create_user(
            "jdoe",
            email="j.doe@example.com",
            password="pass",
            first_name="Jane",
            last_name="Doe",
        )
        assignee.groups.add(approval_group)

        wf = WorkflowDefinition.objects.create(
            form_definition=form_definition, requires_approval=True
        )
        stage = WorkflowStage.objects.create(
            workflow=wf,
            name="Full Name Review",
            order=1,
            approval_logic="all",
            assignee_form_field="manager_name",
            assignee_lookup_type="full_name",
        )
        stage.approval_groups.add(approval_group)
        sub = FormSubmission.objects.create(
            form_definition=form_definition,
            submitter=user,
            form_data={"manager_name": "Jane Doe"},
            status="submitted",
        )
        create_workflow_tasks(sub)
        tasks = sub.approval_tasks.filter(assigned_to=assignee)
        assert tasks.count() == 1


# ── Due date calculation ──────────────────────────────────────────────────


class TestDueDateCalculation:
    @patch("django_forms_workflows.workflow_engine._notify_task_request")
    @patch("django_forms_workflows.workflow_engine._notify_submission_created")
    def test_due_date_set_when_configured(
        self, mock_created, mock_task, form_definition, user, approval_group
    ):
        """When approval_deadline_days is set, tasks should receive a due_date."""
        wf = WorkflowDefinition.objects.create(
            form_definition=form_definition,
            requires_approval=True,
            approval_deadline_days=5,
        )
        stage = WorkflowStage.objects.create(
            workflow=wf, name="Deadline Stage", order=1, approval_logic="all"
        )
        stage.approval_groups.add(approval_group)
        sub = FormSubmission.objects.create(
            form_definition=form_definition,
            submitter=user,
            form_data={},
            status="submitted",
        )
        create_workflow_tasks(sub)
        task = sub.approval_tasks.first()
        assert task is not None
        assert task.due_date is not None

    @patch("django_forms_workflows.workflow_engine._notify_task_request")
    @patch("django_forms_workflows.workflow_engine._notify_submission_created")
    def test_no_due_date_when_not_configured(
        self, mock_created, mock_task, form_definition, user, approval_group
    ):
        """Without approval_deadline_days, tasks should have no due_date."""
        wf = WorkflowDefinition.objects.create(
            form_definition=form_definition,
            requires_approval=True,
            # approval_deadline_days not set (None)
        )
        stage = WorkflowStage.objects.create(
            workflow=wf, name="No Deadline Stage", order=1, approval_logic="all"
        )
        stage.approval_groups.add(approval_group)
        sub = FormSubmission.objects.create(
            form_definition=form_definition,
            submitter=user,
            form_data={},
            status="submitted",
        )
        create_workflow_tasks(sub)
        task = sub.approval_tasks.first()
        assert task is not None
        assert task.due_date is None


# ── Conditional stage trigger_conditions ─────────────────────────────────


class TestConditionalStageTriggers:
    @patch("django_forms_workflows.workflow_engine._notify_final_approval")
    @patch("django_forms_workflows.workflow_engine._notify_task_request")
    @patch("django_forms_workflows.workflow_engine._notify_submission_created")
    def test_stage_skipped_when_condition_not_met(
        self, mock_created, mock_task, mock_final, form_definition, user, approval_group
    ):
        """A stage with trigger_conditions that don't match should be skipped;
        if it's the only stage the submission auto-approves."""
        wf = WorkflowDefinition.objects.create(
            form_definition=form_definition, requires_approval=True
        )
        stage = WorkflowStage.objects.create(
            workflow=wf,
            name="HR Only Stage",
            order=1,
            approval_logic="all",
            trigger_conditions={
                "operator": "AND",
                "conditions": [
                    {"field": "department", "operator": "equals", "value": "hr"}
                ],
            },
        )
        stage.approval_groups.add(approval_group)
        sub = FormSubmission.objects.create(
            form_definition=form_definition,
            submitter=user,
            form_data={"department": "it"},  # doesn't match "hr"
            status="submitted",
        )
        create_workflow_tasks(sub)
        sub.refresh_from_db()
        # Stage condition not met → no tasks created → remains pending so
        # admins can investigate the configuration (prevents silent
        # auto-approval when trigger conditions are misconfigured).
        assert sub.status == "pending_approval"
        assert sub.approval_tasks.count() == 0

    @patch("django_forms_workflows.workflow_engine._notify_task_request")
    @patch("django_forms_workflows.workflow_engine._notify_submission_created")
    def test_stage_created_when_condition_met(
        self, mock_created, mock_task, form_definition, user, approval_group
    ):
        """A stage whose trigger_conditions match the submission data is activated."""
        wf = WorkflowDefinition.objects.create(
            form_definition=form_definition, requires_approval=True
        )
        stage = WorkflowStage.objects.create(
            workflow=wf,
            name="HR Only Stage",
            order=1,
            approval_logic="all",
            trigger_conditions={
                "operator": "AND",
                "conditions": [
                    {"field": "department", "operator": "equals", "value": "hr"}
                ],
            },
        )
        stage.approval_groups.add(approval_group)
        sub = FormSubmission.objects.create(
            form_definition=form_definition,
            submitter=user,
            form_data={"department": "hr"},
            status="submitted",
        )
        create_workflow_tasks(sub)
        sub.refresh_from_db()
        assert sub.status == "pending_approval"
        assert sub.approval_tasks.filter(status="pending").count() == 1

    @patch("django_forms_workflows.workflow_engine._notify_final_approval")
    @patch("django_forms_workflows.workflow_engine._notify_task_request")
    @patch("django_forms_workflows.workflow_engine._notify_submission_created")
    def test_conditional_next_stage_skipped_and_finalized(
        self,
        mock_created,
        mock_task,
        mock_final,
        form_definition,
        user,
        approver_user,
        approval_group,
    ):
        """After stage 1 completes, stage 2 is skipped (condition unmet) → final."""
        wf = WorkflowDefinition.objects.create(
            form_definition=form_definition, requires_approval=True
        )
        stage1 = WorkflowStage.objects.create(
            workflow=wf, name="Stage 1", order=1, approval_logic="all"
        )
        stage1.approval_groups.add(approval_group)
        stage2 = WorkflowStage.objects.create(
            workflow=wf,
            name="Stage 2 (HR only)",
            order=2,
            approval_logic="all",
            trigger_conditions={
                "operator": "AND",
                "conditions": [
                    {"field": "department", "operator": "equals", "value": "hr"}
                ],
            },
        )
        stage2.approval_groups.add(approval_group)
        sub = FormSubmission.objects.create(
            form_definition=form_definition,
            submitter=user,
            form_data={"department": "it"},
            status="submitted",
        )
        create_workflow_tasks(sub)
        sub.refresh_from_db()
        assert sub.status == "pending_approval"

        # Approve stage 1
        task = sub.approval_tasks.filter(status="pending").first()
        task.status = "approved"
        task.approved_by = approver_user
        task.save()
        handle_approval(sub, task, wf)
        sub.refresh_from_db()
        # Stage 2 condition unmet → directly finalized
        assert sub.status == "approved"


# ── Multi-workflow parallel tracks ────────────────────────────────────────


class TestMultiWorkflowParallelTracks:
    @patch("django_forms_workflows.workflow_engine._notify_final_approval")
    @patch("django_forms_workflows.workflow_engine._notify_task_request")
    @patch("django_forms_workflows.workflow_engine._notify_submission_created")
    def test_two_workflows_both_must_complete(
        self,
        mock_created,
        mock_task,
        mock_final,
        form_definition,
        user,
        approver_user,
        approval_group,
        second_approval_group,
    ):
        """With two parallel workflows, the submission stays pending_approval
        until both tracks complete."""
        # Track A
        wf_a = WorkflowDefinition.objects.create(
            form_definition=form_definition,
            requires_approval=True,
            name_label="Track A",
        )
        stage_a = WorkflowStage.objects.create(
            workflow=wf_a, name="A Review", order=1, approval_logic="all"
        )
        stage_a.approval_groups.add(approval_group)

        # Track B
        wf_b = WorkflowDefinition.objects.create(
            form_definition=form_definition,
            requires_approval=True,
            name_label="Track B",
        )
        stage_b = WorkflowStage.objects.create(
            workflow=wf_b, name="B Review", order=1, approval_logic="all"
        )
        stage_b.approval_groups.add(second_approval_group)

        sub = FormSubmission.objects.create(
            form_definition=form_definition,
            submitter=user,
            form_data={},
            status="submitted",
        )
        create_workflow_tasks(sub)
        sub.refresh_from_db()
        assert sub.status == "pending_approval"
        # Tasks created for both tracks
        assert sub.approval_tasks.filter(status="pending").count() == 2

        # Approve track A only
        task_a = sub.approval_tasks.filter(workflow_stage=stage_a).first()
        task_a.status = "approved"
        task_a.approved_by = approver_user
        task_a.save()
        handle_approval(sub, task_a, wf_a)
        sub.refresh_from_db()
        # Track B still pending — submission should not be finalized
        assert sub.status == "pending_approval"

        # Approve track B
        task_b = sub.approval_tasks.filter(workflow_stage=stage_b).first()
        task_b.status = "approved"
        task_b.approved_by = approver_user
        task_b.save()
        handle_approval(sub, task_b, wf_b)
        sub.refresh_from_db()
        assert sub.status == "approved"

    @patch("django_forms_workflows.workflow_engine._notify_final_approval")
    @patch("django_forms_workflows.workflow_engine._notify_task_request")
    @patch("django_forms_workflows.workflow_engine._notify_submission_created")
    def test_workflow_trigger_condition_skips_track(
        self,
        mock_created,
        mock_task,
        mock_final,
        form_definition,
        user,
        approver_user,
        approval_group,
        second_approval_group,
    ):
        """A workflow whose trigger_conditions don't match is never started,
        so only the other track needs to complete."""
        # Track A — always runs
        wf_a = WorkflowDefinition.objects.create(
            form_definition=form_definition,
            requires_approval=True,
            name_label="Always Track",
        )
        stage_a = WorkflowStage.objects.create(
            workflow=wf_a, name="A Review", order=1, approval_logic="all"
        )
        stage_a.approval_groups.add(approval_group)

        # Track B — only runs when amount > 1000
        wf_b = WorkflowDefinition.objects.create(
            form_definition=form_definition,
            requires_approval=True,
            name_label="High-Value Track",
            trigger_conditions={
                "operator": "AND",
                "conditions": [{"field": "amount", "operator": "gt", "value": "1000"}],
            },
        )
        stage_b = WorkflowStage.objects.create(
            workflow=wf_b, name="B Review", order=1, approval_logic="all"
        )
        stage_b.approval_groups.add(second_approval_group)

        sub = FormSubmission.objects.create(
            form_definition=form_definition,
            submitter=user,
            form_data={"amount": "100"},  # ≤ 1000 → skip Track B
            status="submitted",
        )
        create_workflow_tasks(sub)
        sub.refresh_from_db()
        assert sub.status == "pending_approval"
        # Only Track A task
        assert sub.approval_tasks.filter(status="pending").count() == 1

        task_a = sub.approval_tasks.filter(status="pending").first()
        task_a.status = "approved"
        task_a.approved_by = approver_user
        task_a.save()
        handle_approval(sub, task_a, wf_a)
        sub.refresh_from_db()
        assert sub.status == "approved"


# ── Sub-workflow engine ───────────────────────────────────────────────────


def _make_sub_workflow_setup(form_definition, approval_group, second_approval_group):
    """Helper: create parent + sub workflows and a SubWorkflowDefinition config."""
    parent_wf = WorkflowDefinition.objects.create(
        form_definition=form_definition, requires_approval=True
    )
    sub_form = FormDefinition.objects.create(
        name="Sub Workflow Form", slug="sub-wf-form", description="sub"
    )
    sub_wf = WorkflowDefinition.objects.create(
        form_definition=sub_form, requires_approval=True
    )
    sub_stage = WorkflowStage.objects.create(
        workflow=sub_wf, name="Sub Review", order=1, approval_logic="all"
    )
    sub_stage.approval_groups.add(second_approval_group)
    config = SubWorkflowDefinition.objects.create(
        parent_workflow=parent_wf,
        sub_workflow=sub_wf,
        count_field="num_items",
        label_template="Item {index}",
        trigger="on_approval",
        detached=True,
    )
    return parent_wf, sub_wf, sub_stage, config


class TestSubWorkflowEngine:
    @patch("django_forms_workflows.workflow_engine._notify_task_request")
    @patch("django_forms_workflows.workflow_engine._notify_submission_created")
    def test_sub_workflow_spawned_on_approval(
        self,
        mock_created,
        mock_task,
        form_definition,
        user,
        approver_user,
        approval_group,
        second_approval_group,
    ):
        """Sub-workflows should be spawned when the parent is approved."""
        parent_wf, sub_wf, sub_stage, config = _make_sub_workflow_setup(
            form_definition, approval_group, second_approval_group
        )
        stage = WorkflowStage.objects.create(
            workflow=parent_wf, name="Main Review", order=1, approval_logic="all"
        )
        stage.approval_groups.add(approval_group)

        sub = FormSubmission.objects.create(
            form_definition=form_definition,
            submitter=user,
            form_data={"num_items": 2},
            status="submitted",
        )
        create_workflow_tasks(sub)

        # Approve parent
        task = sub.approval_tasks.filter(status="pending").first()
        task.status = "approved"
        task.approved_by = approver_user
        task.save()
        with patch("django_forms_workflows.workflow_engine._notify_final_approval"):
            handle_approval(sub, task, parent_wf)

        # 2 sub-workflow instances should have been spawned
        instances = SubWorkflowInstance.objects.filter(parent_submission=sub)
        assert instances.count() == 2

    @patch("django_forms_workflows.workflow_engine._notify_task_request")
    @patch("django_forms_workflows.workflow_engine._notify_submission_created")
    def test_sub_workflow_approval_advances_instance(
        self,
        mock_created,
        mock_task,
        form_definition,
        user,
        approver_user,
        approval_group,
        second_approval_group,
    ):
        """Approving a sub-workflow task should finalize the instance."""
        parent_wf, sub_wf, sub_stage, config = _make_sub_workflow_setup(
            form_definition, approval_group, second_approval_group
        )

        sub = FormSubmission.objects.create(
            form_definition=form_definition,
            submitter=user,
            form_data={"num_items": 1},
            status="approved",
        )
        # Manually spawn a sub-workflow instance (as the engine would after approval)
        instance = SubWorkflowInstance.objects.create(
            parent_submission=sub, definition=config, index=1, status="in_progress"
        )
        task = ApprovalTask.objects.create(
            submission=sub,
            sub_workflow_instance=instance,
            assigned_group=second_approval_group,
            workflow_stage=sub_stage,
            stage_number=1,
            step_name="Sub Review",
            status="pending",
        )
        task.status = "approved"
        task.approved_by = approver_user
        task.save()
        handle_sub_workflow_approval(task)
        instance.refresh_from_db()
        assert instance.status == "approved"

    @patch("django_forms_workflows.workflow_engine._notify_task_request")
    @patch("django_forms_workflows.workflow_engine._notify_submission_created")
    def test_sub_workflow_rejection_marks_instance_rejected(
        self,
        mock_created,
        mock_task,
        form_definition,
        user,
        approver_user,
        approval_group,
        second_approval_group,
    ):
        """Rejecting a sub-workflow task (logic=all) should mark the instance rejected."""
        parent_wf, sub_wf, sub_stage, config = _make_sub_workflow_setup(
            form_definition, approval_group, second_approval_group
        )
        sub_stage.approval_logic = "all"
        sub_stage.save()

        sub = FormSubmission.objects.create(
            form_definition=form_definition,
            submitter=user,
            form_data={"num_items": 1},
            status="approved",
        )
        instance = SubWorkflowInstance.objects.create(
            parent_submission=sub, definition=config, index=1, status="in_progress"
        )
        task = ApprovalTask.objects.create(
            submission=sub,
            sub_workflow_instance=instance,
            assigned_group=second_approval_group,
            workflow_stage=sub_stage,
            stage_number=1,
            step_name="Sub Review",
            status="rejected",
        )
        handle_sub_workflow_rejection(task)
        instance.refresh_from_db()
        assert instance.status == "rejected"
