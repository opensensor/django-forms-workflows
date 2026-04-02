"""
Payment Processing Plugin System.

Providers register themselves in ``AppConfig.ready()``::

    from django_forms_workflows.payments import register_provider
    from .my_provider import MyProvider
    register_provider("myprovider", MyProvider)

The library auto-registers the bundled Stripe provider.  Third-party
apps can add ECSI, PayPal, Authorize.Net, or any other provider
without modifying the library itself.
"""

from .base import PaymentFlow, PaymentProvider, PaymentResult, PaymentStatus
from .registry import (
    clear,
    get_available_providers,
    get_provider,
    get_provider_choices,
    is_registered,
    register_provider,
)

__all__ = [
    "PaymentFlow",
    "PaymentProvider",
    "PaymentResult",
    "PaymentStatus",
    "clear",
    "get_available_providers",
    "get_provider",
    "get_provider_choices",
    "is_registered",
    "register_provider",
]
