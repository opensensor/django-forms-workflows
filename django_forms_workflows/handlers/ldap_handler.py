"""
LDAP update handler for post-submission actions.

Updates LDAP/Active Directory attributes with form data after submission or approval.
"""

import logging

from django.conf import settings

from .base import BaseActionHandler

logger = logging.getLogger(__name__)


def _configure_ldap_connection(conn):
    """
    Configure LDAP connection with TLS settings from environment variables.

    This is a local helper that imports and uses the configure_ldap_connection
    function from ldap_backend module.

    Args:
        conn: LDAP connection object
    """
    try:
        from django_forms_workflows.ldap_backend import configure_ldap_connection

        configure_ldap_connection(conn)
    except ImportError:
        # Fallback if ldap_backend is not available
        import os

        import ldap

        tls_require_cert = os.getenv("LDAP_TLS_REQUIRE_CERT", "demand").lower()

        if tls_require_cert == "never":
            conn.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)
        elif tls_require_cert == "allow":
            conn.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_ALLOW)
        elif tls_require_cert == "try":
            conn.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_TRY)
        else:
            conn.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_DEMAND)

        conn.set_option(ldap.OPT_REFERRALS, 0)


class LDAPUpdateHandler(BaseActionHandler):
    """
    Handler for updating LDAP attributes with form data.

    Supports:
    - Configurable DN templates
    - Field mapping from form fields to LDAP attributes
    - Multiple LDAP backends
    """

    def execute(self):
        """
        Execute the LDAP update.

        Returns:
            dict: Result with 'success', 'message', and optional 'data'
        """
        try:
            # Check if LDAP is available
            if not self._is_ldap_available():
                return {
                    "success": False,
                    "message": "LDAP is not configured or available",
                }

            # Validate configuration
            if not self.action.ldap_dn_template:
                return {"success": False, "message": "LDAP DN template not configured"}

            if not self.action.ldap_field_mappings:
                return {
                    "success": False,
                    "message": "LDAP field mappings not configured",
                }

            # Build DN from template
            dn = self._build_dn()
            if not dn:
                return {
                    "success": False,
                    "message": "Could not build LDAP DN from template",
                }

            # Build attribute updates
            attributes = self._build_attributes()
            if not attributes:
                return {"success": False, "message": "No valid attributes to update"}

            # Execute LDAP update
            result = self._update_ldap(dn, attributes)

            if result["success"]:
                self.log_success(result["message"])
            else:
                self.log_error(result["message"])

            return result

        except Exception as e:
            error_msg = f"LDAP update failed: {str(e)}"
            self.log_error(error_msg, exc_info=True)
            return {"success": False, "message": error_msg}

    def _is_ldap_available(self):
        """
        Check if LDAP is configured and available.

        Returns:
            bool: True if LDAP is available
        """
        import importlib.util

        # Check if python-ldap is available
        if importlib.util.find_spec("ldap") is None:
            return False

        ldap_settings = getattr(settings, "LDAP_CONFIG", None)
        return ldap_settings is not None

    def _build_dn(self):
        """
        Build LDAP DN from template.

        Template can use placeholders like {username}, {email}, etc.

        Returns:
            str: Built DN or None if failed
        """
        template = self.action.ldap_dn_template

        # Available placeholders
        placeholders = {
            "username": self.user.username,
            "email": self.user.email,
            "first_name": self.user.first_name,
            "last_name": self.user.last_name,
        }

        # Add user profile fields
        try:
            profile = self.user.profile
            for field in ["employee_id", "department", "external_id"]:
                value = getattr(profile, field, None)
                if value:
                    placeholders[field] = value
        except Exception:
            pass

        # Replace placeholders
        try:
            dn = template.format(**placeholders)
            return dn
        except KeyError as e:
            self.log_error(f"Missing placeholder in DN template: {e}")
            return None

    def _build_attributes(self):
        """
        Build LDAP attributes from field mappings.

        Returns:
            dict: Attribute name -> value mapping
        """
        attributes = {}

        for mapping in self.action.ldap_field_mappings:
            form_field = mapping.get("form_field")
            ldap_attribute = mapping.get("ldap_attribute")

            if not form_field or not ldap_attribute:
                continue

            # Get form field value
            value = self.get_form_field_value(form_field)

            # Skip if value is None or empty string
            if value is None or value == "":
                continue

            # Convert value to string for LDAP
            attributes[ldap_attribute] = str(value)

        return attributes

    def _update_ldap(self, dn, attributes):
        """
        Execute the LDAP update.

        Args:
            dn: Distinguished Name of the LDAP entry
            attributes: Dict of attribute name -> value

        Returns:
            dict: Result with success status and message
        """
        try:
            import ldap

            # Get LDAP configuration
            ldap_config = getattr(settings, "LDAP_CONFIG", {})
            server_uri = ldap_config.get("SERVER_URI")
            bind_dn = ldap_config.get("BIND_DN")
            bind_password = ldap_config.get("BIND_PASSWORD")

            if not all([server_uri, bind_dn, bind_password]):
                return {"success": False, "message": "LDAP configuration incomplete"}

            # Connect to LDAP
            conn = ldap.initialize(server_uri)
            _configure_ldap_connection(conn)
            conn.simple_bind_s(bind_dn, bind_password)

            # Build modification list
            mod_attrs = []
            for attr_name, attr_value in attributes.items():
                # Encode value as bytes for LDAP
                if isinstance(attr_value, str):
                    attr_value = attr_value.encode("utf-8")

                mod_attrs.append((ldap.MOD_REPLACE, attr_name, attr_value))

            # Execute modification
            conn.modify_s(dn, mod_attrs)
            conn.unbind_s()

            return {
                "success": True,
                "message": f"Updated LDAP entry: {dn}",
                "data": {"dn": dn, "attributes": list(attributes.keys())},
            }

        except ImportError:
            return {"success": False, "message": "python-ldap library not installed"}
        except Exception as e:
            return {"success": False, "message": f"LDAP update failed: {str(e)}"}
