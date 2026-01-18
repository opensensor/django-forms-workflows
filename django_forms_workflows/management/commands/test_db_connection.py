"""
Management command to test external database connections.
"""

from django.core.management.base import BaseCommand
from django.db import connections


class Command(BaseCommand):
    """Test external database connection."""

    help = "Test external database connection"

    def add_arguments(self, parser):
        parser.add_argument(
            "--database",
            type=str,
            default="default",
            help="Database alias to test (default: 'default')",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Show detailed output",
        )

    def handle(self, *args, **options):
        database_alias = options.get("database", "default")
        verbose = options.get("verbose", False)

        self.stdout.write(f"Testing connection to database: {database_alias}")
        self.stdout.write("=" * 50)

        # Check if database exists in settings
        if database_alias not in connections:
            self.stdout.write(
                self.style.ERROR(
                    f"Database '{database_alias}' not found in settings.DATABASES"
                )
            )
            return

        try:
            # Get database connection
            connection = connections[database_alias]

            if verbose:
                self.stdout.write(
                    f"Database engine: {connection.settings_dict['ENGINE']}"
                )
                self.stdout.write(f"Database name: {connection.settings_dict['NAME']}")
                self.stdout.write(
                    f"Database host: {connection.settings_dict.get('HOST', 'N/A')}"
                )
                self.stdout.write(
                    f"Database port: {connection.settings_dict.get('PORT', 'N/A')}"
                )
                self.stdout.write("")

            # Test connection
            with connection.cursor() as cursor:
                # Try to get database version
                engine = connection.settings_dict["ENGINE"]

                if "mssql" in engine or "sql_server" in engine:
                    # SQL Server
                    cursor.execute("SELECT @@VERSION")
                    version = cursor.fetchone()
                    self.stdout.write(self.style.SUCCESS("✓ Connection successful!"))
                    if verbose and version:
                        self.stdout.write(f"Version: {version[0][:100]}...")

                elif "postgresql" in engine or "postgis" in engine:
                    # PostgreSQL
                    cursor.execute("SELECT version()")
                    version = cursor.fetchone()
                    self.stdout.write(self.style.SUCCESS("✓ Connection successful!"))
                    if verbose and version:
                        self.stdout.write(f"Version: {version[0][:100]}...")

                elif "mysql" in engine:
                    # MySQL
                    cursor.execute("SELECT VERSION()")
                    version = cursor.fetchone()
                    self.stdout.write(self.style.SUCCESS("✓ Connection successful!"))
                    if verbose and version:
                        self.stdout.write(f"Version: {version[0]}")

                elif "sqlite" in engine:
                    # SQLite
                    cursor.execute("SELECT sqlite_version()")
                    version = cursor.fetchone()
                    self.stdout.write(self.style.SUCCESS("✓ Connection successful!"))
                    if verbose and version:
                        self.stdout.write(f"Version: {version[0]}")

                else:
                    # Generic test
                    cursor.execute("SELECT 1")
                    result = cursor.fetchone()
                    if result and result[0] == 1:
                        self.stdout.write(
                            self.style.SUCCESS("✓ Connection successful!")
                        )
                    else:
                        self.stdout.write(
                            self.style.WARNING(
                                "⚠ Connection test returned unexpected result"
                            )
                        )

                # Test a simple query
                if verbose:
                    self.stdout.write("\nTesting query execution...")
                    cursor.execute("SELECT 1 AS test")
                    result = cursor.fetchone()
                    if result and result[0] == 1:
                        self.stdout.write(
                            self.style.SUCCESS("✓ Query execution successful!")
                        )

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✗ Connection test failed: {e}"))
            if verbose:
                import traceback

                self.stdout.write("\nFull error:")
                self.stdout.write(traceback.format_exc())
            return

        self.stdout.write("=" * 50)
        self.stdout.write(
            self.style.SUCCESS(
                f"Database '{database_alias}' is accessible and working correctly."
            )
        )
