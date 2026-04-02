"""
Payment provider registry.

Providers register themselves in their ``AppConfig.ready()`` via
``register_provider()``.  The library auto-registers the bundled Stripe
provider; third-party apps register their own.

Example::

    from django_forms_workflows.payments import register_provider
    register_provider("ecsi", MyECSIProvider)
"""

from __future__ import annotations

import logging

from .base import PaymentProvider

logger = logging.getLogger(__name__)

_registry: dict[str, type[PaymentProvider] | PaymentProvider] = {}
_instances: dict[str, PaymentProvider] = {}


def register_provider(
    name: str, provider: type[PaymentProvider] | PaymentProvider
) -> None:
    """Register a payment provider under *name*."""
    _registry[name] = provider
    _instances.pop(name, None)  # Bust cache on re-register
    logger.debug("Registered payment provider %r", name)


def get_provider(name: str) -> PaymentProvider | None:
    """Return the provider instance for *name*, or None if not registered."""
    if name in _instances:
        return _instances[name]

    raw = _registry.get(name)
    if raw is None:
        return None

    # Instantiate class, or use instance directly
    if isinstance(raw, type) and issubclass(raw, PaymentProvider):
        instance = raw()
    elif isinstance(raw, PaymentProvider):
        instance = raw
    else:
        logger.error("Payment provider %r is not a PaymentProvider subclass", name)
        return None

    _instances[name] = instance
    return instance


def get_available_providers() -> dict[str, PaymentProvider]:
    """Return {name: provider} for all registered providers where is_available()."""
    result = {}
    for name in list(_registry):
        provider = get_provider(name)
        if provider and provider.is_available():
            result[name] = provider
    return result


def get_provider_choices() -> list[tuple[str, str]]:
    """Return choices suitable for a Django form/template dropdown."""
    choices = []
    for name in sorted(_registry):
        provider = get_provider(name)
        if provider:
            choices.append((name, provider.get_name()))
    return choices


def is_registered(name: str) -> bool:
    return name in _registry


def clear() -> None:
    """Remove all registrations (for tests)."""
    _registry.clear()
    _instances.clear()
