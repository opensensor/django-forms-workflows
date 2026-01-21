"""
LDAP Data Source

Provides access to LDAP/Active Directory attributes.
Requires django-auth-ldap to be installed and configured.
"""

import logging
from typing import Any

from django.conf import settings

from .base import DataSource

logger = logging.getLogger(__name__)


class LDAPDataSource(DataSource):
    """
    Data source for LDAP/Active Directory attributes.

    Supports common AD attributes:
    - ldap.department
    - ldap.title
    - ldap.manager
    - ldap.manager_email
    - ldap.phone
    - ldap.employee_id
    - ldap.office_location
    - ldap.company

    Requires django-auth-ldap to be installed and configured.
    """

    # Mapping of friendly names to LDAP attribute names
    ATTRIBUTE_MAP = {
        "department": "department",
        "title": "title",
        "phone": "telephoneNumber",
        "mobile": "mobile",
        "email": "mail",
        "employee_id": "employeeID",
        "office_location": "physicalDeliveryOfficeName",
        "company": "company",
        "manager": "manager",
        "manager_email": "manager_email",  # Special handling
    }

    def get_value(self, user, field_name: str, **kwargs) -> Any | None:
        """
        Get a value from LDAP attributes.

        Args:
            user: Django User object
            field_name: LDAP attribute name (e.g., 'department', 'title', 'mail')
            **kwargs: Unused

        Returns:
            The attribute value, or None if not found
        """
        if not user or not user.is_authenticated:
            return None

        # Map friendly name to LDAP attribute
        ldap_attr = self.ATTRIBUTE_MAP.get(field_name, field_name)

        try:
            # For 'mail', try user.email first (usually synced from LDAP/SSO)
            if field_name == "mail" or ldap_attr == "mail":
                if user.email:
                    return user.email

            # Try to get from user profile first (cached LDAP data)
            if hasattr(user, "forms_profile"):
                profile = user.forms_profile
                if hasattr(profile, field_name):
                    value = getattr(profile, field_name)
                    if value:
                        return value

            # Try to get from LDAP backend directly (for LDAP-authenticated users)
            ldap_user = getattr(user, "ldap_user", None)
            if ldap_user:
                # Special handling for manager email
                if field_name == "manager_email":
                    return self._get_manager_email(ldap_user)

                # Get attribute from cached LDAP attrs
                if hasattr(ldap_user, "attrs") and ldap_attr in ldap_user.attrs:
                    value = ldap_user.attrs[ldap_attr]
                    # LDAP attributes are often lists
                    if isinstance(value, list) and value:
                        return value[0]
                    return value

            # For SSO users without ldap_user, query LDAP directly
            return self._query_ldap_attribute(user.username, ldap_attr)

        except Exception as e:
            logger.error(f"Error getting LDAP attribute {field_name}: {e}")
            return None

    def _query_ldap_attribute(self, username: str, ldap_attr: str) -> Any | None:
        """
        Query LDAP directly for a user attribute.

        This is used for SSO users who don't have a cached ldap_user object.
        """
        import os

        try:
            import ldap
            from ldap.filter import escape_filter_chars
        except ImportError:
            logger.debug("python-ldap not installed")
            return None

        ldap_server = getattr(settings, "AUTH_LDAP_SERVER_URI", None)
        if not ldap_server:
            return None

        bind_dn = getattr(settings, "AUTH_LDAP_BIND_DN", "")
        bind_password = getattr(settings, "AUTH_LDAP_BIND_PASSWORD", "")

        # Get search base
        user_search = getattr(settings, "AUTH_LDAP_USER_SEARCH", None)
        search_base = None
        if user_search and hasattr(user_search, "base_dn"):
            search_base = user_search.base_dn
        if not search_base:
            search_base = getattr(settings, "AUTH_LDAP_USER_SEARCH_BASE", None)
        if not search_base and bind_dn:
            parts = bind_dn.split(",")
            dc_parts = [p for p in parts if p.strip().upper().startswith("DC=")]
            if dc_parts:
                search_base = ",".join(dc_parts)

        if not search_base:
            logger.debug("Could not determine LDAP search base")
            return None

        try:
            conn = ldap.initialize(ldap_server)
            conn.set_option(ldap.OPT_REFERRALS, 0)
            conn.set_option(ldap.OPT_PROTOCOL_VERSION, ldap.VERSION3)

            # Configure TLS
            tls_require_cert = os.getenv("LDAP_TLS_REQUIRE_CERT", "demand").lower()
            if tls_require_cert == "never":
                conn.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)

            if bind_dn and bind_password:
                conn.simple_bind_s(bind_dn, bind_password)
            else:
                conn.simple_bind_s("", "")

            search_filter = f"(sAMAccountName={escape_filter_chars(username)})"
            result = conn.search_s(
                search_base, ldap.SCOPE_SUBTREE, search_filter, [ldap_attr]
            )

            if result and result[0][0]:
                attrs = result[0][1]
                if ldap_attr in attrs:
                    value = attrs[ldap_attr]
                    if isinstance(value, list) and value:
                        val = value[0]
                        if isinstance(val, bytes):
                            return val.decode("utf-8")
                        return val

            return None

        except ldap.LDAPError as e:
            logger.debug(f"LDAP query failed for {username}.{ldap_attr}: {e}")
            return None
        finally:
            try:
                conn.unbind_s()
            except Exception:
                pass

    def _get_manager_email(self, ldap_user) -> str | None:
        """
        Get manager's email from LDAP.

        This requires looking up the manager's DN and getting their email.
        """
        try:
            if not hasattr(ldap_user, "attrs") or "manager" not in ldap_user.attrs:
                return None

            manager_dn = ldap_user.attrs["manager"]
            if isinstance(manager_dn, list):
                manager_dn = manager_dn[0] if manager_dn else None

            if not manager_dn:
                return None

            # TODO: Implement manager lookup
            # This would require querying LDAP for the manager's record
            # For now, return None
            logger.debug(
                f"Manager DN found: {manager_dn}, but email lookup not implemented"
            )
            return None

        except Exception as e:
            logger.error(f"Error getting manager email: {e}")
            return None

    def is_available(self) -> bool:
        """
        Check if LDAP is configured.

        Returns:
            True if django-auth-ldap is installed and configured
        """
        import importlib.util

        # Check if django-auth-ldap is available
        if importlib.util.find_spec("django_auth_ldap") is None:
            return False

        # Check if LDAP is in authentication backends
        backends = getattr(settings, "AUTHENTICATION_BACKENDS", [])
        return any("ldap" in backend.lower() for backend in backends)

    def get_display_name(self) -> str:
        return "LDAP/Active Directory"
