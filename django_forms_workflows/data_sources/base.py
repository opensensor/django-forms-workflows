"""
Base classes for data source abstraction
"""

import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class DataSource(ABC):
    """
    Abstract base class for data sources.

    All data sources must implement the get_value method.
    """

    @abstractmethod
    def get_value(self, user, field_name: str, **kwargs) -> Any | None:
        """
        Get a value from the data source.

        Args:
            user: Django User object
            field_name: Name of the field to retrieve
            **kwargs: Additional parameters (e.g., schema, table, column)

        Returns:
            The field value, or None if not found
        """
        pass

    def is_available(self) -> bool:
        """
        Check if this data source is available/configured.

        Returns:
            True if the data source can be used, False otherwise
        """
        return True

    def get_display_name(self) -> str:
        """
        Get a human-readable name for this data source.

        Returns:
            Display name
        """
        return self.__class__.__name__


class DataSourceRegistry:
    """
    Registry for data sources.

    Allows registration and retrieval of data source implementations.
    """

    def __init__(self):
        self._sources: dict[str, type] = {}

    def register(self, source_type: str, source_class: type):
        """
        Register a data source.

        Args:
            source_type: Unique identifier for the source
            source_class: DataSource subclass
        """
        if not issubclass(source_class, DataSource):
            raise ValueError(f"{source_class} must be a subclass of DataSource")

        self._sources[source_type] = source_class
        logger.info(f"Registered data source: {source_type} -> {source_class.__name__}")

    def get(self, source_type: str) -> DataSource:
        """
        Get a data source instance by type.

        Args:
            source_type: Type of data source

        Returns:
            DataSource instance

        Raises:
            ValueError: If source type is not registered
        """
        if source_type not in self._sources:
            raise ValueError(
                f"Unknown data source type: {source_type}. "
                f"Available types: {', '.join(self._sources.keys())}"
            )

        source_class = self._sources[source_type]
        return source_class()

    def list_sources(self) -> list:
        """
        List all registered data source types.

        Returns:
            List of source type names
        """
        return list(self._sources.keys())

    def is_registered(self, source_type: str) -> bool:
        """
        Check if a source type is registered.

        Args:
            source_type: Type to check

        Returns:
            True if registered, False otherwise
        """
        return source_type in self._sources
