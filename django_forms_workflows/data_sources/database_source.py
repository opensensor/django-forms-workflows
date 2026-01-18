"""
Database Data Source

Provides access to external databases configured in Django's DATABASES setting.
Supports querying any database with syntax: {{ db.schema.table.column }}
"""

import logging
import re
from typing import Any

from django.conf import settings
from django.db import connections

from .base import DataSource

logger = logging.getLogger(__name__)


class DatabaseDataSource(DataSource):
    """
    Data source for external database queries.

    Supports syntax:
    - {{ db.schema.table.column }}
    - {{ schema.table.column }}
    - db.schema.table.column

    Requires:
    - Database configured in Django's DATABASES setting
    - User profile with external_id field for lookups

    Configuration in settings.py:
        FORMS_WORKFLOWS = {
            'DATABASE_SOURCE': {
                'database_alias': 'external_db',  # Django database alias
                'user_id_field': 'external_id',   # UserProfile field for lookups
                'default_schema': 'dbo',          # Default schema if not specified
            }
        }
    """

    def get_value(self, user, field_name: str, **kwargs) -> Any | None:
        """
        Get a value from an external database.

        Args:
            user: Django User object
            field_name: Database query in format: schema.table.column or {{ schema.table.column }}
            **kwargs: Optional overrides:
                - database_alias: Django database alias to use
                - user_id_field: UserProfile field to use for lookup
                - lookup_field: Database column to match against (default: ID_NUMBER)
                - schema: Database schema
                - table: Table name
                - column: Column name

        Returns:
            The column value, or None if not found
        """
        if not user or not user.is_authenticated:
            return None

        if not self.is_available():
            logger.warning(
                "Database data source is not available (no external database configured)"
            )
            return None

        try:
            # Get configuration
            config = self._get_config()
            database_alias = kwargs.get("database_alias", config.get("database_alias"))
            user_id_field = kwargs.get(
                "user_id_field", config.get("user_id_field", "external_id")
            )
            lookup_field = kwargs.get(
                "lookup_field", config.get("lookup_field", "ID_NUMBER")
            )
            default_schema = kwargs.get(
                "default_schema", config.get("default_schema", "dbo")
            )

            # Get user's external ID
            user_id = self._get_user_id(user, user_id_field)
            if not user_id:
                logger.debug(f"User {user.username} has no {user_id_field}")
                return None

            # Parse the field_name to extract schema, table, column
            schema, table, column = self._parse_field_name(field_name, default_schema)

            if not all([schema, table, column]):
                logger.error(f"Invalid database field format: {field_name}")
                return None

            # Validate identifiers to prevent SQL injection
            if not all(
                self._is_safe_identifier(x)
                for x in [schema, table, column, lookup_field]
            ):
                logger.error(
                    f"Invalid identifier in: {field_name} or lookup_field: {lookup_field}"
                )
                return None

            # Query the database
            value = self._query_database(
                database_alias=database_alias,
                schema=schema,
                table=table,
                column=column,
                user_id=user_id,
                lookup_field=lookup_field,
            )

            return value

        except Exception as e:
            logger.error(f"Error getting database value for {field_name}: {e}")
            return None

    def _get_config(self) -> dict:
        """Get configuration from settings."""
        return getattr(settings, "FORMS_WORKFLOWS", {}).get("DATABASE_SOURCE", {})

    def _get_user_id(self, user, user_id_field: str) -> str | None:
        """Get user's external ID from profile or user object."""
        try:
            # First check if it's a direct user attribute (e.g., 'username', 'email')
            if hasattr(user, user_id_field):
                value = getattr(user, user_id_field)
                if value:
                    return value

            # Then check the user's profile
            if hasattr(user, "forms_profile"):
                profile = user.forms_profile
                if hasattr(profile, user_id_field):
                    return getattr(profile, user_id_field)
            return None
        except Exception as e:
            logger.error(f"Error getting user ID field {user_id_field}: {e}")
            return None

    def _parse_field_name(self, field_name: str, default_schema: str) -> tuple:
        """
        Parse field_name to extract schema, table, column.

        Supports:
        - {{ db.schema.table.column }}
        - {{ schema.table.column }}
        - db.schema.table.column
        - schema.table.column

        Returns:
            (schema, table, column) tuple
        """
        # Remove {{ }} if present
        field_name = field_name.strip()
        if field_name.startswith("{{") and field_name.endswith("}}"):
            field_name = field_name[2:-2].strip()

        # Remove 'db.' prefix if present
        if field_name.startswith("db."):
            field_name = field_name[3:]

        # Split by dots
        parts = field_name.split(".")

        if len(parts) == 3:
            return parts[0], parts[1], parts[2]
        elif len(parts) == 2:
            # Assume default schema
            return default_schema, parts[0], parts[1]
        else:
            return None, None, None

    def _is_safe_identifier(self, identifier: str) -> bool:
        """
        Validate that an identifier is safe to use in SQL.

        Prevents SQL injection by ensuring identifier contains only:
        - Alphanumeric characters
        - Underscores
        - Does not start with a number
        """
        if not identifier:
            return False

        # Allow alphanumeric and underscore only
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", identifier):
            return False

        return True

    def _query_database(
        self,
        database_alias: str,
        schema: str,
        table: str,
        column: str,
        user_id: str,
        lookup_field: str = "ID_NUMBER",
    ) -> Any | None:
        """
        Execute database query.

        Args:
            database_alias: Django database alias
            schema: Database schema
            table: Table name
            column: Column name
            user_id: User's external ID for lookup
            lookup_field: Database column to match against (default: ID_NUMBER)

        Returns:
            Column value or None
        """
        try:
            # Build parameterized query
            # Note: Schema and table names cannot be parameterized in most databases
            # We've already validated them with _is_safe_identifier
            query = f"""
                SELECT TOP 1 [{column}]
                FROM [{schema}].[{table}]
                WHERE [{lookup_field}] = %s
            """

            # Execute query
            with connections[database_alias].cursor() as cursor:
                cursor.execute(query, [user_id])
                row = cursor.fetchone()

                if row:
                    # Strip whitespace for fixed-width NCHAR columns
                    value = row[0]
                    if isinstance(value, str):
                        value = value.strip()
                    return value

                logger.debug(
                    f"No data found for user {user_id} in {schema}.{table}.{column} (lookup: {lookup_field})"
                )
                return None

        except Exception as e:
            logger.error(f"Database query error: {e}")
            return None

    def _query_database_template(
        self,
        database_alias: str,
        schema: str,
        table: str,
        columns: list[str],
        template: str,
        user_id: str,
        lookup_field: str = "ID_NUMBER",
    ) -> str | None:
        """
        Execute database query for multiple columns and apply template.

        Args:
            database_alias: Django database alias
            schema: Database schema
            table: Table name
            columns: List of column names to fetch
            template: Template string with {COLUMN_NAME} placeholders
            user_id: User's external ID for lookup
            lookup_field: Database column to match against

        Returns:
            Formatted string with template applied, or None if not found
        """
        try:
            # Validate all column identifiers
            if not all(self._is_safe_identifier(col) for col in columns):
                logger.error(f"Invalid column identifiers in: {columns}")
                return None

            # Build column list for SELECT
            column_list = ", ".join(f"[{col}]" for col in columns)

            # Build parameterized query
            query = f"""
                SELECT TOP 1 {column_list}
                FROM [{schema}].[{table}]
                WHERE [{lookup_field}] = %s
            """

            # Execute query
            with connections[database_alias].cursor() as cursor:
                cursor.execute(query, [user_id])
                row = cursor.fetchone()

                if row:
                    # Build dictionary of column values, stripping whitespace
                    # (handles fixed-width NCHAR columns with trailing spaces)
                    values = {
                        col: str(row[i] or "").strip() for i, col in enumerate(columns)
                    }

                    # Apply template
                    result = template
                    for col, val in values.items():
                        result = result.replace(f"{{{col}}}", val)

                    return result.strip()

                logger.debug(
                    f"No data found for user {user_id} in {schema}.{table} (lookup: {lookup_field})"
                )
                return None

        except Exception as e:
            logger.error(f"Database template query error: {e}")
            return None

    def get_template_value(
        self,
        user,
        schema: str,
        table: str,
        columns: list[str],
        template: str,
        **kwargs,
    ) -> str | None:
        """
        Get a templated value from multiple database columns.

        Args:
            user: Django User object
            schema: Database schema
            table: Table name
            columns: List of column names to fetch
            template: Template string with {COLUMN_NAME} placeholders
            **kwargs: Optional overrides (database_alias, user_id_field, lookup_field)

        Returns:
            Formatted string with template applied, or None
        """
        if not user or not user.is_authenticated:
            return None

        if not self.is_available():
            logger.warning("Database data source is not available")
            return None

        try:
            config = self._get_config()
            database_alias = kwargs.get("database_alias", config.get("database_alias"))
            user_id_field = kwargs.get(
                "user_id_field", config.get("user_id_field", "external_id")
            )
            lookup_field = kwargs.get(
                "lookup_field", config.get("lookup_field", "ID_NUMBER")
            )

            # Get user's external ID
            user_id = self._get_user_id(user, user_id_field)
            if not user_id:
                logger.debug(f"User {user.username} has no {user_id_field}")
                return None

            # Validate identifiers
            if not self._is_safe_identifier(schema) or not self._is_safe_identifier(
                table
            ):
                logger.error(f"Invalid schema or table: {schema}.{table}")
                return None

            return self._query_database_template(
                database_alias=database_alias,
                schema=schema,
                table=table,
                columns=columns,
                template=template,
                user_id=user_id,
                lookup_field=lookup_field,
            )

        except Exception as e:
            logger.error(f"Error getting template value: {e}")
            return None

    def is_available(self) -> bool:
        """
        Check if database source is configured.

        Returns:
            True if external database is configured
        """
        config = self._get_config()
        database_alias = config.get("database_alias")

        if not database_alias:
            return False

        # Check if database alias exists in settings
        databases = getattr(settings, "DATABASES", {})
        return database_alias in databases

    def get_display_name(self) -> str:
        return "External Database"

    def test_connection(self, database_alias: str = None) -> bool:
        """
        Test the database connection.

        Args:
            database_alias: Database alias to test (uses config default if not provided)

        Returns:
            True if connection successful, False otherwise
        """
        if database_alias is None:
            config = self._get_config()
            database_alias = config.get("database_alias")

        if not database_alias:
            logger.error("No database alias configured")
            return False

        try:
            with connections[database_alias].cursor() as cursor:
                # Try to get database version
                engine = connections[database_alias].settings_dict.get("ENGINE", "")

                if "mssql" in engine or "sql_server" in engine:
                    cursor.execute("SELECT @@VERSION")
                elif "postgresql" in engine or "postgis" in engine:
                    cursor.execute("SELECT version()")
                elif "mysql" in engine:
                    cursor.execute("SELECT VERSION()")
                elif "sqlite" in engine:
                    cursor.execute("SELECT sqlite_version()")
                else:
                    cursor.execute("SELECT 1")

                result = cursor.fetchone()
                if result:
                    logger.info(
                        f"Database connection successful for '{database_alias}'"
                    )
                    return True

            return False

        except Exception as e:
            logger.error(f"Database connection test failed for '{database_alias}': {e}")
            return False

    def get_available_tables(
        self, schema: str = None, database_alias: str = None
    ) -> list:
        """
        Get list of available tables in a schema.

        Args:
            schema: Schema name (uses config default if not provided)
            database_alias: Database alias (uses config default if not provided)

        Returns:
            List of table names
        """
        config = self._get_config()

        if schema is None:
            schema = config.get("default_schema", "dbo")

        if database_alias is None:
            database_alias = config.get("database_alias")

        if not database_alias:
            logger.error("No database alias configured")
            return []

        if not self._is_safe_identifier(schema):
            logger.error(f"Invalid schema name: {schema}")
            return []

        try:
            query = """
                SELECT TABLE_NAME
                FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_SCHEMA = %s
                AND TABLE_TYPE = 'BASE TABLE'
                ORDER BY TABLE_NAME
            """

            with connections[database_alias].cursor() as cursor:
                cursor.execute(query, [schema])
                rows = cursor.fetchall()
                return [row[0] for row in rows]

        except Exception as e:
            logger.error(f"Error getting tables from {schema}: {e}")
            return []

    def get_table_columns(
        self, table: str, schema: str = None, database_alias: str = None
    ) -> list:
        """
        Get list of columns in a table.

        Args:
            table: Table name
            schema: Schema name (uses config default if not provided)
            database_alias: Database alias (uses config default if not provided)

        Returns:
            List of dictionaries with column information:
            [
                {
                    'name': 'COLUMN_NAME',
                    'type': 'DATA_TYPE',
                    'max_length': 100,
                    'nullable': True
                },
                ...
            ]
        """
        config = self._get_config()

        if schema is None:
            schema = config.get("default_schema", "dbo")

        if database_alias is None:
            database_alias = config.get("database_alias")

        if not database_alias:
            logger.error("No database alias configured")
            return []

        if not self._is_safe_identifier(schema) or not self._is_safe_identifier(table):
            logger.error(f"Invalid schema or table name: {schema}.{table}")
            return []

        try:
            query = """
                SELECT
                    COLUMN_NAME,
                    DATA_TYPE,
                    CHARACTER_MAXIMUM_LENGTH,
                    IS_NULLABLE
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = %s
                AND TABLE_NAME = %s
                ORDER BY ORDINAL_POSITION
            """

            with connections[database_alias].cursor() as cursor:
                cursor.execute(query, [schema, table])
                rows = cursor.fetchall()

                columns = []
                for row in rows:
                    columns.append(
                        {
                            "name": row[0],
                            "type": row[1],
                            "max_length": row[2],
                            "nullable": row[3] == "YES",
                        }
                    )

                return columns

        except Exception as e:
            logger.error(f"Error getting columns from {schema}.{table}: {e}")
            return []
