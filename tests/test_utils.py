"""
Tests for django_forms_workflows.utils.
"""

from decimal import Decimal

from django.contrib.auth.models import Group, User

from django_forms_workflows.models import (
    ApprovalTask,
    FormSubmission,
    WorkflowDefinition,
)
from django_forms_workflows.utils import (
    check_escalation_needed,
    user_can_approve,
    user_can_submit_form,
    user_can_view_submission,
)


class TestCheckEscalation:
    def test_escalation_not_triggered_below_threshold(
        self, form_definition, user, approval_group
    ):
        wf = WorkflowDefinition.objects.create(
            form_definition=form_definition,
            requires_approval=True,
            escalation_field="amount",
            escalation_threshold=Decimal("1000.00"),
        )
        wf.approval_groups.add(approval_group)
        sub = FormSubmission.objects.create(
            form_definition=form_definition,
            submitter=user,
            form_data={"amount": "500.00"},
            status="submitted",
        )
        result = check_escalation_needed(sub)
        assert result is False

    def test_escalation_triggered_above_threshold(
        self, form_definition, user, approval_group
    ):
        esc_group = Group.objects.create(name="Escalation Group")
        wf = WorkflowDefinition.objects.create(
            form_definition=form_definition,
            requires_approval=True,
            escalation_field="amount",
            escalation_threshold=Decimal("1000.00"),
        )
        wf.approval_groups.add(approval_group)
        wf.escalation_groups.add(esc_group)
        sub = FormSubmission.objects.create(
            form_definition=form_definition,
            submitter=user,
            form_data={"amount": "5000.00"},
            status="submitted",
        )
        result = check_escalation_needed(sub)
        assert result is True

    def test_escalation_no_field_configured(
        self, form_definition, user, approval_group
    ):
        wf = WorkflowDefinition.objects.create(
            form_definition=form_definition,
            requires_approval=True,
        )
        wf.approval_groups.add(approval_group)
        sub = FormSubmission.objects.create(
            form_definition=form_definition,
            submitter=user,
            form_data={"amount": "5000.00"},
            status="submitted",
        )
        result = check_escalation_needed(sub)
        assert result is False


class TestUserCanApprove:
    def test_user_in_approval_group(self, form_definition, user, approval_group):
        user.groups.add(approval_group)
        sub = FormSubmission.objects.create(
            form_definition=form_definition,
            submitter=User.objects.create_user("other", password="pass"),
            form_data={},
            status="pending_approval",
        )
        ApprovalTask.objects.create(
            submission=sub,
            assigned_group=approval_group,
            step_name="Test",
            status="pending",
        )
        assert user_can_approve(user, sub) is True

    def test_user_not_in_group(self, form_definition, user, approval_group):
        sub = FormSubmission.objects.create(
            form_definition=form_definition,
            submitter=User.objects.create_user("other2", password="pass"),
            form_data={},
            status="pending_approval",
        )
        ApprovalTask.objects.create(
            submission=sub,
            assigned_group=approval_group,
            step_name="Test",
            status="pending",
        )
        assert user_can_approve(user, sub) is False

    def test_superuser_can_approve(self, form_definition, superuser, approval_group):
        sub = FormSubmission.objects.create(
            form_definition=form_definition,
            submitter=User.objects.create_user("other3", password="pass"),
            form_data={},
            status="pending_approval",
        )
        ApprovalTask.objects.create(
            submission=sub,
            assigned_group=approval_group,
            step_name="Test",
            status="pending",
        )
        assert user_can_approve(superuser, sub) is True


class TestUserCanSubmitForm:
    def test_anyone_can_submit_no_groups(self, form_definition, user):
        assert user_can_submit_form(user, form_definition) is True

    def test_restricted_form(self, form_definition, user):
        g = Group.objects.create(name="Submitters")
        form_definition.submit_groups.add(g)
        assert user_can_submit_form(user, form_definition) is False
        user.groups.add(g)
        assert user_can_submit_form(user, form_definition) is True

    def test_staff_bypass(self, form_definition, staff_user):
        g = Group.objects.create(name="Submitters Only")
        form_definition.submit_groups.add(g)
        assert user_can_submit_form(staff_user, form_definition) is True


class TestUserCanViewSubmission:
    def test_owner_can_view(self, form_definition, user):
        sub = FormSubmission.objects.create(
            form_definition=form_definition,
            submitter=user,
            form_data={},
            status="submitted",
        )
        assert user_can_view_submission(user, sub) is True

    def test_other_user_cannot_view(self, form_definition, user):
        other = User.objects.create_user("nonowner", password="pass")
        sub = FormSubmission.objects.create(
            form_definition=form_definition,
            submitter=user,
            form_data={},
            status="submitted",
        )
        assert user_can_view_submission(other, sub) is False

    def test_superuser_can_view(self, form_definition, superuser, user):
        sub = FormSubmission.objects.create(
            form_definition=form_definition,
            submitter=user,
            form_data={},
            status="submitted",
        )
        assert user_can_view_submission(superuser, sub) is True
