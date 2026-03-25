"""
Tests for django_forms_workflows.utils.
"""

from unittest.mock import MagicMock

from django.contrib.auth.models import Group, User

from django_forms_workflows.models import (
    ApprovalTask,
    FormCategory,
    FormSubmission,
    UserProfile,
    WorkflowDefinition,
    WorkflowStage,
)
from django_forms_workflows.utils import (
    check_escalation_needed,
    get_ldap_attribute,
    get_user_manager,
    user_can_access_category,
    user_can_approve,
    user_can_submit_form,
    user_can_view_form,
    user_can_view_submission,
)


class TestCheckEscalation:
    def test_escalation_not_triggered_no_config(
        self, form_definition, user, approval_group
    ):
        wf = WorkflowDefinition.objects.create(
            form_definition=form_definition,
            requires_approval=True,
        )
        stage = WorkflowStage.objects.create(
            workflow=wf, name="Review", order=1, approval_logic="all"
        )
        stage.approval_groups.add(approval_group)
        sub = FormSubmission.objects.create(
            form_definition=form_definition,
            submitter=user,
            form_data={"amount": "500.00"},
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

    def test_approver_can_view(
        self, form_definition, user, approver_user, approval_group
    ):
        """A user with an active approval task for the submission can view it."""
        approver_user.groups.add(approval_group)
        sub = FormSubmission.objects.create(
            form_definition=form_definition,
            submitter=user,
            form_data={},
            status="pending_approval",
        )
        ApprovalTask.objects.create(
            submission=sub,
            assigned_group=approval_group,
            step_name="Review",
            status="pending",
        )
        assert user_can_view_submission(approver_user, sub) is True

    def test_unauthenticated_cannot_view(self, form_definition, user):
        sub = FormSubmission.objects.create(
            form_definition=form_definition,
            submitter=user,
            form_data={},
            status="submitted",
        )
        anon = MagicMock()
        anon.is_authenticated = False
        assert user_can_view_submission(anon, sub) is False


# ── user_can_access_category ──────────────────────────────────────────────


class TestUserCanAccessCategory:
    def test_no_groups_open_to_all(self, category, user):
        """A category with no allowed_groups is accessible to any authenticated user."""
        assert user_can_access_category(user, category) is True

    def test_restricted_category_user_not_in_group(self, category, user):
        g = Group.objects.create(name="HR Only")
        category.allowed_groups.add(g)
        assert user_can_access_category(user, category) is False

    def test_restricted_category_user_in_group(self, category, user):
        g = Group.objects.create(name="HR Only 2")
        category.allowed_groups.add(g)
        user.groups.add(g)
        assert user_can_access_category(user, category) is True

    def test_parent_restriction_blocks_child_access(self, category, user):
        """User blocked from parent category cannot access child categories."""
        g = Group.objects.create(name="Parent Group")
        category.allowed_groups.add(g)
        child = FormCategory.objects.create(
            name="Child Cat", slug="child-cat", parent=category
        )
        assert user_can_access_category(user, child) is False

    def test_parent_restriction_grants_child_when_in_group(self, category, user):
        """User in parent's group can access child category with no own groups."""
        g = Group.objects.create(name="Parent Group 2")
        category.allowed_groups.add(g)
        user.groups.add(g)
        child = FormCategory.objects.create(
            name="Child Cat 2", slug="child-cat-2", parent=category
        )
        assert user_can_access_category(user, child) is True


# ── user_can_view_form ─────────────────────────────────────────────────────


class TestUserCanViewForm:
    def test_public_form_accessible_without_auth(self, form_definition):
        """A form with requires_login=False is open to everyone, even unauthenticated."""
        form_definition.requires_login = False
        form_definition.save()
        anon = MagicMock()
        anon.is_authenticated = False
        assert user_can_view_form(anon, form_definition) is True

    def test_login_required_anonymous_denied(self, form_definition):
        form_definition.requires_login = True
        form_definition.save()
        anon = MagicMock()
        anon.is_authenticated = False
        assert user_can_view_form(anon, form_definition) is False

    def test_superuser_can_view_restricted_form(self, form_definition, superuser):
        form_definition.requires_login = True
        form_definition.save()
        g = Group.objects.create(name="View Only Group")
        form_definition.view_groups.add(g)
        assert user_can_view_form(superuser, form_definition) is True

    def test_view_groups_restriction_blocks_non_member(self, form_definition, user):
        form_definition.requires_login = True
        form_definition.save()
        g = Group.objects.create(name="Restricted Viewers")
        form_definition.view_groups.add(g)
        assert user_can_view_form(user, form_definition) is False

    def test_view_groups_grants_access_to_member(self, form_definition, user):
        form_definition.requires_login = True
        form_definition.save()
        g = Group.objects.create(name="Allowed Viewers")
        form_definition.view_groups.add(g)
        user.groups.add(g)
        assert user_can_view_form(user, form_definition) is True

    def test_no_view_groups_any_authenticated_user_can_view(
        self, form_definition, user
    ):
        """No view_groups restriction means any authenticated user may view."""
        form_definition.requires_login = True
        form_definition.save()
        assert user_can_view_form(user, form_definition) is True


# ── get_ldap_attribute (utils) ─────────────────────────────────────────────


class TestGetLDAPAttributeUtils:
    def test_none_user_returns_empty(self):
        assert get_ldap_attribute(None, "department") == ""

    def test_user_without_ldap_returns_empty(self, user):
        assert get_ldap_attribute(user, "title") == ""

    def test_list_attribute_decoded(self, user):
        ldap_user = MagicMock()
        ldap_user.attrs = {"department": ["Engineering"]}
        user.ldap_user = ldap_user
        assert get_ldap_attribute(user, "department") == "Engineering"

    def test_bytes_attribute_decoded(self, user):
        ldap_user = MagicMock()
        ldap_user.attrs = {"department": [b"Accounting"]}
        user.ldap_user = ldap_user
        assert get_ldap_attribute(user, "department") == "Accounting"

    def test_attr_map_applied(self, user):
        """Built-in attr_map translates 'email' → 'mail'."""
        ldap_user = MagicMock()
        ldap_user.attrs = {"mail": ["alice@example.com"]}
        user.ldap_user = ldap_user
        assert get_ldap_attribute(user, "email") == "alice@example.com"

    def test_custom_ldap_attr_name(self, user):
        ldap_user = MagicMock()
        ldap_user.attrs = {"extensionAttribute7": ["EMP007"]}
        user.ldap_user = ldap_user
        result = get_ldap_attribute(user, "employee_id", "extensionAttribute7")
        assert result == "EMP007"


# ── get_user_manager ──────────────────────────────────────────────────────


class TestGetUserManagerFromProfile:
    def test_returns_manager_from_profile(self, user, db):
        manager = User.objects.create_user("manager_u", password="pass")
        profile = UserProfile.objects.get(user=user)
        profile.manager = manager
        profile.save()
        result = get_user_manager(user)
        assert result == manager

    def test_returns_none_when_no_manager_set(self, user):
        result = get_user_manager(user)
        assert result is None

    def test_returns_none_for_none_user(self):
        assert get_user_manager(None) is None
