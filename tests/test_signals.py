"""
Tests for django_forms_workflows.signals.
"""

from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import RequestFactory, override_settings

from django_forms_workflows.models import UserProfile
from django_forms_workflows.signals import (
    get_ldap_attribute,
    is_sso_authentication,
    sync_ldap_attributes,
    sync_sso_attributes_to_profile,
)


class TestUserProfileAutoCreation:
    def test_profile_created_on_user_create(self, db):
        user = User.objects.create_user("signal_test", password="pass")
        assert UserProfile.objects.filter(user=user).exists()

    def test_profile_not_duplicated(self, user):
        # Creating user again shouldn't duplicate profile
        count = UserProfile.objects.filter(user=user).count()
        assert count == 1


class TestGetLDAPAttribute:
    def test_no_user(self):
        assert get_ldap_attribute(None, "department") == ""

    def test_user_without_ldap(self, user):
        assert get_ldap_attribute(user, "department") == ""

    def test_user_with_ldap_list_attr(self, user):
        ldap_user = MagicMock()
        ldap_user.attrs = {"department": ["Engineering"]}
        user.ldap_user = ldap_user
        assert get_ldap_attribute(user, "department") == "Engineering"

    def test_user_with_ldap_bytes_attr(self, user):
        ldap_user = MagicMock()
        ldap_user.attrs = {"department": [b"Engineering"]}
        user.ldap_user = ldap_user
        assert get_ldap_attribute(user, "department") == "Engineering"

    def test_custom_ldap_attr_name(self, user):
        ldap_user = MagicMock()
        ldap_user.attrs = {"extensionAttribute1": ["EMP001"]}
        user.ldap_user = ldap_user
        result = get_ldap_attribute(user, "employee_id", "extensionAttribute1")
        assert result == "EMP001"


class TestSyncLDAPAttributes:
    @override_settings(FORMS_WORKFLOWS={"LDAP_SYNC": {"enabled": False}})
    def test_sync_disabled(self, user):
        profile = sync_ldap_attributes(user)
        assert profile is not None  # Returns profile, just doesn't sync

    @override_settings(
        FORMS_WORKFLOWS={
            "LDAP_SYNC": {
                "enabled": True,
                "attributes": {
                    "department": "department",
                    "title": "title",
                },
            }
        }
    )
    def test_sync_enabled_with_ldap_data(self, user):
        ldap_user = MagicMock()
        ldap_user.attrs = {
            "department": ["Engineering"],
            "title": ["Staff Engineer"],
        }
        user.ldap_user = ldap_user
        profile = sync_ldap_attributes(user)
        assert profile.department == "Engineering"
        assert profile.title == "Staff Engineer"
        assert profile.ldap_last_sync is not None


class TestSSOSync:
    def test_sync_sso_attributes(self, user):
        with patch(
            "django_forms_workflows.sso_backends.get_sso_settings",
            return_value={
                "update_user_on_login": True,
                "attr_map": {
                    "profile.department": "dept",
                    "profile.title": "job_title",
                },
            },
        ):
            details = {"dept": "Marketing", "job_title": "Manager"}
            profile = sync_sso_attributes_to_profile(user, details)
            assert profile.department == "Marketing"
            assert profile.title == "Manager"

    def test_sync_sso_disabled(self, user):
        with patch(
            "django_forms_workflows.sso_backends.get_sso_settings",
            return_value={"update_user_on_login": False},
        ):
            result = sync_sso_attributes_to_profile(user, {})
            assert result is None


class TestIsSSO:
    def test_sso_detected(self):
        factory = RequestFactory()
        request = factory.get("/")
        request.session = {"social_auth_last_login_backend": "azure-ad"}
        assert is_sso_authentication(request) is True

    def test_non_sso(self):
        factory = RequestFactory()
        request = factory.get("/")
        request.session = {}
        assert is_sso_authentication(request) is False

    def test_no_session(self):
        factory = RequestFactory()
        request = factory.get("/")
        # Remove session attribute
        if hasattr(request, "session"):
            delattr(request, "session")
        assert is_sso_authentication(request) is False
