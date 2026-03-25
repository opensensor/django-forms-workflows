"""
Tests for django_forms_workflows.workflow_engine.
"""

from unittest.mock import patch

from django.contrib.auth.models import Group

from django_forms_workflows.models import (
    FormSubmission,
    WorkflowDefinition,
    WorkflowStage,
)
from django_forms_workflows.workflow_engine import (
    create_workflow_tasks,
    handle_approval,
    handle_rejection,
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
