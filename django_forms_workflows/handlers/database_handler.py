"""
Database update handler for post-submission actions.

Updates external databases with form data after submission or approval.
"""

import logging
import re

from django.db import connections

from .base import BaseActionHandler

logger = logging.getLogger(__name__)


class DatabaseUpdateHandler(BaseActionHandler):
    """
    Handler for updating external databases with form data.

    Supports:
    - Configurable database connections
    - Field mapping from form fields to database columns
    - User-based record lookup
    - SQL injection protection
    """

    def execute(self):
        """
        Execute the database update.

        Returns:
            dict: Result with 'success', 'message', and optional 'data'
        """
        try:
            # Validate configuration
            if not self.action.db_alias:
                return {"success": False, "message": "Database alias not configured"}

            if not self.action.db_table:
                return {"success": False, "message": "Database table not configured"}

            if not self.action.db_field_mappings:
                return {"success": False, "message": "Field mappings not configured"}

            # Get user identifier for lookup
            user_id_field = self.action.db_user_field or "employee_id"
            user_id = self.get_user_profile_value(user_id_field)

            if not user_id:
                return {
                    "success": False,
                    "message": f"User profile field {user_id_field} not found or empty",
                }

            # Build and execute update query
            result = self._update_database(user_id)

            if result["success"]:
                self.log_success(result["message"])
            else:
                self.log_error(result["message"])

            return result

        except Exception as e:
            error_msg = f"Database update failed: {str(e)}"
            self.log_error(error_msg, exc_info=True)
            return {"success": False, "message": error_msg}

    def _update_database(self, user_id):
        """
        Execute the database update query.

        Args:
            user_id: User identifier for WHERE clause

        Returns:
            dict: Result with success status and message
        """
        database_alias = self.action.db_alias
        schema = self.action.db_schema or "dbo"
        table = self.action.db_table
        lookup_field = self.action.db_lookup_field or "ID_NUMBER"

        # Validate identifiers to prevent SQL injection
        if not self._is_valid_identifier(schema):
            return {"success": False, "message": f"Invalid schema name: {schema}"}

        if not self._is_valid_identifier(table):
            return {"success": False, "message": f"Invalid table name: {table}"}

        if not self._is_valid_identifier(lookup_field):
            return {
                "success": False,
                "message": f"Invalid lookup field: {lookup_field}",
            }

        # Build SET clause from field mappings
        set_clauses = []
        params = []

        for mapping in self.action.db_field_mappings:
            form_field = mapping.get("form_field")
            db_column = mapping.get("db_column")

            if not form_field or not db_column:
                continue

            # Validate column name
            if not self._is_valid_identifier(db_column):
                self.log_warning(f"Skipping invalid column name: {db_column}")
                continue

            # Get form field value
            value = self.get_form_field_value(form_field)

            # Skip if value is None or empty string (unless explicitly configured to update nulls)
            if value is None or value == "":
                continue

            set_clauses.append(f"[{db_column}] = %s")
            params.append(value)

        if not set_clauses:
            return {"success": False, "message": "No valid field mappings to update"}

        # Add user_id for WHERE clause
        params.append(user_id)

        # Build UPDATE query
        # Handle schema - SQLite doesn't use schemas
        if schema and schema.lower() not in ("", "public", "dbo"):
            table_ref = f"[{schema}].[{table}]"
        else:
            table_ref = f"[{table}]"

        query = f"""
            UPDATE {table_ref}
            SET {", ".join(set_clauses)}
            WHERE [{lookup_field}] = %s
        """

        # Execute query
        try:
            with connections[database_alias].cursor() as cursor:
                cursor.execute(query, params)
                rows_affected = cursor.rowcount

                if rows_affected == 0:
                    return {
                        "success": False,
                        "message": f"No records found for {lookup_field}={user_id}",
                    }

                return {
                    "success": True,
                    "message": f"Updated {rows_affected} record(s) in {schema}.{table}",
                    "data": {
                        "rows_affected": rows_affected,
                        "table": f"{schema}.{table}",
                        "lookup_value": user_id,
                    },
                }

        except Exception as e:
            return {"success": False, "message": f"Database query failed: {str(e)}"}

    def _is_valid_identifier(self, identifier):
        """
        Validate SQL identifier to prevent SQL injection.

        Args:
            identifier: SQL identifier (table, column, schema name)

        Returns:
            bool: True if valid, False otherwise
        """
        if not identifier:
            return False

        # Allow only alphanumeric characters, underscores, and dots
        # This prevents SQL injection while allowing schema.table notation
        pattern = r"^[a-zA-Z0-9_\.]+$"
        return bool(re.match(pattern, identifier))
