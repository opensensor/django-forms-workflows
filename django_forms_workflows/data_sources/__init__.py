"""
Data Source Abstraction Layer

Pluggable system for prefilling form fields from external sources:
- LDAP/Active Directory
- External databases
- REST APIs
- Custom sources

Usage:
    from django_forms_workflows.data_sources import get_data_source

    source = get_data_source('ldap')
    value = source.get_value(user, 'department')
"""

from .base import DataSource, DataSourceRegistry
from .database_source import DatabaseDataSource
from .ldap_source import LDAPDataSource
from .user_source import UserDataSource

# Global registry
registry = DataSourceRegistry()

# Register built-in sources
registry.register("user", UserDataSource)
registry.register("ldap", LDAPDataSource)
registry.register("database", DatabaseDataSource)
registry.register("db", DatabaseDataSource)  # Alias


def get_data_source(source_type):
    """
    Get a data source instance by type.

    Args:
        source_type: Type of data source ('user', 'ldap', 'database', etc.)

    Returns:
        DataSource instance

    Raises:
        ValueError: If source type is not registered
    """
    return registry.get(source_type)


def register_data_source(source_type, source_class):
    """
    Register a custom data source.

    Args:
        source_type: Unique identifier for the source
        source_class: DataSource subclass

    Example:
        from django_forms_workflows.data_sources import register_data_source, DataSource

        class SalesforceSource(DataSource):
            def get_value(self, user, field_name, **kwargs):
                # Query Salesforce API
                pass

        register_data_source('salesforce', SalesforceSource)
    """
    registry.register(source_type, source_class)


__all__ = [
    "DataSource",
    "DataSourceRegistry",
    "UserDataSource",
    "LDAPDataSource",
    "DatabaseDataSource",
    "get_data_source",
    "register_data_source",
    "registry",
]
