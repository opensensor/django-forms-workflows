"""
Configurable LDAP Authentication Backend for Django Form Workflows

This module provides LDAP authentication integration with Active Directory,
including user attribute mapping, group synchronization, and manager hierarchy lookup.

All LDAP attribute mappings are configurable via Django settings.
"""

import logging
import os

import ldap
from django.conf import settings
from django.contrib.auth.models import Group
from django_auth_ldap.backend import LDAPBackend
from ldap.filter import escape_filter_chars

logger = logging.getLogger(__name__)


def configure_ldap_connection(conn):
    """
    Configure LDAP connection with TLS settings from environment variables.

    This function applies TLS certificate verification settings based on the
    LDAP_TLS_REQUIRE_CERT environment variable.

    Args:
        conn: LDAP connection object

    Environment Variables:
        LDAP_TLS_REQUIRE_CERT: TLS certificate verification level
            - 'never': Don't require or verify certificates (ldap.OPT_X_TLS_NEVER)
            - 'allow': Allow connection without cert verification (ldap.OPT_X_TLS_ALLOW)
            - 'try': Try to verify but proceed if verification fails (ldap.OPT_X_TLS_TRY)
            - 'demand' or 'hard': Require valid certificate (ldap.OPT_X_TLS_DEMAND)
            - Default: 'demand'
    """
    # Configure TLS settings based on environment variable
    tls_require_cert = os.getenv("LDAP_TLS_REQUIRE_CERT", "demand").lower()

    if tls_require_cert == "never":
        conn.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)
        logger.debug("LDAP TLS certificate verification: NEVER")
    elif tls_require_cert == "allow":
        conn.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_ALLOW)
        logger.debug("LDAP TLS certificate verification: ALLOW")
    elif tls_require_cert == "try":
        conn.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_TRY)
        logger.debug("LDAP TLS certificate verification: TRY")
    else:  # 'demand' or 'hard' or any other value
        conn.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_DEMAND)
        logger.debug("LDAP TLS certificate verification: DEMAND")

    # Set other standard options
    conn.set_option(ldap.OPT_REFERRALS, 0)


class ConfigurableLDAPBackend(LDAPBackend):
    """
    Configurable LDAP backend for Active Directory integration.

    Features:
    - Automatic user creation from LDAP
    - Configurable user attribute synchronization
    - Group membership synchronization
    - Manager hierarchy lookup

    Configuration via Django settings:

    FORMS_WORKFLOWS_LDAP_ATTR_MAP = {
        'first_name': 'givenName',
        'last_name': 'sn',
        'email': 'mail',
        'profile.employee_id': 'employeeID',
        'profile.department': 'department',
        'profile.title': 'title',
        'profile.phone_number': 'telephoneNumber',
        'profile.office_location': 'physicalDeliveryOfficeName',
        'profile.manager_dn': 'manager',
    }

    FORMS_WORKFLOWS_LDAP_SYNC_GROUPS = True  # Default: True
    FORMS_WORKFLOWS_LDAP_PROFILE_MODEL = 'workflows.UserProfile'  # Default: None
    """

    def authenticate_ldap_user(self, ldap_user, password):
        """
        Authenticate user against LDAP and populate Django user attributes.
        """
        try:
            user = super().authenticate_ldap_user(ldap_user, password)

            if user:
                # Sync LDAP attributes based on configuration
                self._sync_user_attributes(user, ldap_user)

                # Sync group memberships if enabled
                if self._should_sync_groups():
                    self._sync_groups(user, ldap_user)

                logger.info(f"Successfully authenticated LDAP user: {user.username}")

            return user
        except ldap.SERVER_DOWN as e:
            logger.warning(f"LDAP server unavailable: {e}")
            return None
        except ldap.TIMEOUT as e:
            logger.warning(f"LDAP connection timeout: {e}")
            return None
        except Exception as e:
            logger.error(f"LDAP authentication error: {e}")
            return None

    def _sync_user_attributes(self, user, ldap_user):
        """
        Synchronize LDAP attributes to Django user model and profile.

        Uses FORMS_WORKFLOWS_LDAP_ATTR_MAP setting to map LDAP attributes
        to Django model fields.
        """
        try:
            ldap_attrs = ldap_user.attrs
            attr_map = self._get_attribute_map()

            # Separate user fields from profile fields
            user_fields = {}
            profile_fields = {}

            for django_field, ldap_attr in attr_map.items():
                if ldap_attr not in ldap_attrs or not ldap_attrs[ldap_attr]:
                    continue

                # Get the first value (LDAP attributes are lists)
                value = ldap_attrs[ldap_attr][0]

                # Check if this is a profile field (contains '.')
                if "." in django_field:
                    prefix, field_name = django_field.split(".", 1)
                    if prefix == "profile":
                        profile_fields[field_name] = value
                else:
                    user_fields[django_field] = value

            # Update user fields
            for field_name, value in user_fields.items():
                if hasattr(user, field_name):
                    setattr(user, field_name, value)

            if user_fields:
                user.save()

            # Update profile fields if profile model is configured
            if profile_fields:
                self._sync_profile_attributes(user, profile_fields)

            logger.debug(f"Synced attributes for user: {user.username}")

        except Exception as e:
            logger.error(f"Error syncing user attributes for {user.username}: {str(e)}")

    def _sync_profile_attributes(self, user, profile_fields):
        """
        Sync attributes to user profile model.

        Uses FORMS_WORKFLOWS_LDAP_PROFILE_MODEL setting to determine
        which profile model to use.
        """
        try:
            profile_model_path = getattr(
                settings, "FORMS_WORKFLOWS_LDAP_PROFILE_MODEL", None
            )

            if not profile_model_path:
                logger.debug("No profile model configured, skipping profile sync")
                return

            # Import the profile model
            from django.apps import apps

            app_label, model_name = profile_model_path.rsplit(".", 1)
            ProfileModel = apps.get_model(app_label, model_name)

            # Get or create profile
            profile, created = ProfileModel.objects.get_or_create(user=user)

            # Update profile fields
            for field_name, value in profile_fields.items():
                if hasattr(profile, field_name):
                    setattr(profile, field_name, value)
                    if field_name == "id_number":
                        logger.info(f"Synced ID number for {user.username}: {value}")

            profile.save()

        except Exception as e:
            logger.error(
                f"Error syncing profile attributes for {user.username}: {str(e)}"
            )

    def _sync_groups(self, user, ldap_user):
        """
        Synchronize LDAP group memberships to Django groups.

        Creates Django groups if they don't exist and adds user to them.
        """
        try:
            ldap_attrs = ldap_user.attrs

            if "memberOf" in ldap_attrs:
                for group_dn in ldap_attrs["memberOf"]:
                    # Extract CN from DN (e.g., "CN=Managers,OU=Groups,DC=example,DC=com" -> "Managers")
                    group_name = self._extract_cn_from_dn(group_dn)

                    if group_name:
                        # Create group if it doesn't exist
                        group, created = Group.objects.get_or_create(name=group_name)

                        # Add user to group
                        user.groups.add(group)

                        if created:
                            logger.info(f"Created new group from LDAP: {group_name}")

                logger.debug(f"Synced groups for user: {user.username}")

        except Exception as e:
            logger.error(f"Error syncing groups for {user.username}: {str(e)}")

    def _extract_cn_from_dn(self, dn):
        """
        Extract CN (Common Name) from LDAP Distinguished Name.

        Example: "CN=Managers,OU=Groups,DC=example,DC=com" -> "Managers"
        """
        if isinstance(dn, bytes):
            dn = dn.decode("utf-8")

        parts = dn.split(",")
        for part in parts:
            if part.strip().upper().startswith("CN="):
                return part.strip()[3:]  # Remove "CN=" prefix

        return None

    def _get_attribute_map(self):
        """
        Get the LDAP attribute mapping from settings.

        Returns default mapping if not configured.
        """
        default_map = {
            "first_name": "givenName",
            "last_name": "sn",
            "email": "mail",
        }

        return getattr(settings, "FORMS_WORKFLOWS_LDAP_ATTR_MAP", default_map)

    def _should_sync_groups(self):
        """
        Check if group synchronization is enabled.
        """
        return getattr(settings, "FORMS_WORKFLOWS_LDAP_SYNC_GROUPS", True)


def get_user_manager(user):
    """
    Get the manager of a user from LDAP.

    Args:
        user: Django User object

    Returns:
        Django User object of the manager, or None if not found
    """
    try:
        # Initialize LDAP connection
        conn = ldap.initialize(settings.AUTH_LDAP_SERVER_URI)
        configure_ldap_connection(conn)

        # Bind with service account
        conn.simple_bind_s(settings.AUTH_LDAP_BIND_DN, settings.AUTH_LDAP_BIND_PASSWORD)

        # Get username attribute from settings (default: sAMAccountName for AD)
        username_attr = getattr(
            settings, "FORMS_WORKFLOWS_LDAP_USERNAME_ATTR", "sAMAccountName"
        )

        # Search for user
        search_filter = f"({username_attr}={escape_filter_chars(user.username)})"
        result = conn.search_s(
            settings.AUTH_LDAP_USER_SEARCH.base_dn,
            ldap.SCOPE_SUBTREE,
            search_filter,
            ["manager"],
        )

        if result and len(result) > 0:
            user_dn, user_attrs = result[0]

            if "manager" in user_attrs and user_attrs["manager"]:
                manager_dn = user_attrs["manager"][0]

                if isinstance(manager_dn, bytes):
                    manager_dn = manager_dn.decode("utf-8")

                # Get manager's username from DN
                manager_result = conn.search_s(
                    manager_dn, ldap.SCOPE_BASE, "(objectClass=*)", [username_attr]
                )

                if manager_result and len(manager_result) > 0:
                    _, manager_attrs = manager_result[0]

                    if username_attr in manager_attrs:
                        manager_username = manager_attrs[username_attr][0]

                        if isinstance(manager_username, bytes):
                            manager_username = manager_username.decode("utf-8")

                        # Get or create Django user for manager
                        from django.contrib.auth import get_user_model

                        User = get_user_model()

                        try:
                            manager_user = User.objects.get(username=manager_username)
                            return manager_user
                        except User.DoesNotExist:
                            logger.warning(
                                f"Manager {manager_username} not found in Django database"
                            )
                            return None

        conn.unbind_s()
        return None

    except Exception as e:
        logger.error(f"Error getting manager for user {user.username}: {str(e)}")
        return None


def search_ldap_users(search_term, max_results=10):
    """
    Search for users in LDAP by name or username.

    Args:
        search_term: String to search for (name or username)
        max_results: Maximum number of results to return

    Returns:
        List of dictionaries with user information
    """
    try:
        # Initialize LDAP connection
        conn = ldap.initialize(settings.AUTH_LDAP_SERVER_URI)
        configure_ldap_connection(conn)

        # Bind with service account
        conn.simple_bind_s(settings.AUTH_LDAP_BIND_DN, settings.AUTH_LDAP_BIND_PASSWORD)

        # Get username attribute from settings
        username_attr = getattr(
            settings, "FORMS_WORKFLOWS_LDAP_USERNAME_ATTR", "sAMAccountName"
        )

        # Build search filter (search by username, first name, or last name)
        if search_term:
            escaped_term = escape_filter_chars(search_term)
            search_filter = f"(&(objectClass=user)(|({username_attr}=*{escaped_term}*)(givenName=*{escaped_term}*)(sn=*{escaped_term}*)))"
        else:
            search_filter = "(objectClass=user)"

        # Search for users
        conn.set_option(ldap.OPT_SIZELIMIT, max_results)
        result = conn.search_s(
            settings.AUTH_LDAP_USER_SEARCH.base_dn,
            ldap.SCOPE_SUBTREE,
            search_filter,
            [username_attr, "givenName", "sn", "mail", "department", "title"],
        )

        users = []
        for dn, attrs in result:
            if dn:  # Skip referrals
                user_info = {
                    "username": (
                        attrs.get(username_attr, [b""])[0].decode("utf-8")
                        if attrs.get(username_attr)
                        else ""
                    ),
                    "first_name": (
                        attrs.get("givenName", [b""])[0].decode("utf-8")
                        if attrs.get("givenName")
                        else ""
                    ),
                    "last_name": (
                        attrs.get("sn", [b""])[0].decode("utf-8")
                        if attrs.get("sn")
                        else ""
                    ),
                    "email": (
                        attrs.get("mail", [b""])[0].decode("utf-8")
                        if attrs.get("mail")
                        else ""
                    ),
                    "department": (
                        attrs.get("department", [b""])[0].decode("utf-8")
                        if attrs.get("department")
                        else ""
                    ),
                    "title": (
                        attrs.get("title", [b""])[0].decode("utf-8")
                        if attrs.get("title")
                        else ""
                    ),
                }
                users.append(user_info)

        conn.unbind_s()
        return users

    except Exception as e:
        logger.error(f"Error searching LDAP users: {str(e)}")
        return []


def get_ldap_user_attributes(username):
    """
    Get all LDAP attributes for a specific user.

    Args:
        username: Username to look up

    Returns:
        Dictionary of LDAP attributes, or None if user not found
    """
    try:
        # Initialize LDAP connection
        conn = ldap.initialize(settings.AUTH_LDAP_SERVER_URI)
        configure_ldap_connection(conn)

        # Bind with service account
        conn.simple_bind_s(settings.AUTH_LDAP_BIND_DN, settings.AUTH_LDAP_BIND_PASSWORD)

        # Get username attribute from settings
        username_attr = getattr(
            settings, "FORMS_WORKFLOWS_LDAP_USERNAME_ATTR", "sAMAccountName"
        )

        # Search for user
        search_filter = f"({username_attr}={escape_filter_chars(username)})"
        result = conn.search_s(
            settings.AUTH_LDAP_USER_SEARCH.base_dn, ldap.SCOPE_SUBTREE, search_filter
        )

        if result and len(result) > 0:
            dn, attrs = result[0]

            # Convert bytes to strings
            decoded_attrs = {}
            for key, values in attrs.items():
                decoded_attrs[key] = [
                    v.decode("utf-8") if isinstance(v, bytes) else v for v in values
                ]

            conn.unbind_s()
            return decoded_attrs

        conn.unbind_s()
        return None

    except Exception as e:
        logger.error(f"Error getting LDAP attributes for {username}: {str(e)}")
        return None
