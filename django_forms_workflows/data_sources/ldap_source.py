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
            field_name: LDAP attribute name (e.g., 'department', 'title')
            **kwargs: Unused

        Returns:
            The attribute value, or None if not found
        """
        if not user or not user.is_authenticated:
            return None

        if not self.is_available():
            logger.warning(
                "LDAP data source is not available (django-auth-ldap not configured)"
            )
            return None

        try:
            # Try to get from user profile first (cached LDAP data)
            if hasattr(user, "forms_profile"):
                profile = user.forms_profile
                if hasattr(profile, field_name):
                    value = getattr(profile, field_name)
                    if value:
                        return value

            # Try to get from LDAP backend directly
            ldap_user = getattr(user, "ldap_user", None)
            if not ldap_user:
                logger.debug(f"User {user.username} has no LDAP user object")
                return None

            # Map friendly name to LDAP attribute
            ldap_attr = self.ATTRIBUTE_MAP.get(field_name, field_name)

            # Special handling for manager email
            if field_name == "manager_email":
                return self._get_manager_email(ldap_user)

            # Get attribute from LDAP
            if hasattr(ldap_user, "attrs") and ldap_attr in ldap_user.attrs:
                value = ldap_user.attrs[ldap_attr]
                # LDAP attributes are often lists
                if isinstance(value, list) and value:
                    return value[0]
                return value

            logger.debug(f"LDAP attribute not found: {ldap_attr}")
            return None

        except Exception as e:
            logger.error(f"Error getting LDAP attribute {field_name}: {e}")
            return None

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
