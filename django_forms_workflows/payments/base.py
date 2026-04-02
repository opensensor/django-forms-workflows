"""
Abstract base class for payment providers.

All payment providers — whether bundled (Stripe) or third-party
(ECSI, PayPal, Authorize.Net) — implement this interface.  The library
discovers providers via ``register_provider()`` calls in each app's
``AppConfig.ready()`` method.

Third-party example::

    # myapp/apps.py
    class MyPaymentsConfig(AppConfig):
        def ready(self):
            from django_forms_workflows.payments import register_provider
            from .ecsi_provider import ECSIPaymentProvider
            register_provider("ecsi", ECSIPaymentProvider)
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class PaymentFlow(Enum):
    """How the provider collects payment."""

    INLINE = "inline"  # Payment collected on the same page (Stripe Elements)
    REDIRECT = "redirect"  # User sent to an external portal (ECSI, PayPal)


class PaymentStatus(Enum):
    """Canonical payment statuses across all providers."""

    PENDING = "pending"
    REQUIRES_ACTION = "requires_action"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


@dataclass
class PaymentResult:
    """Returned by create_payment() and confirm_payment()."""

    success: bool
    status: PaymentStatus
    transaction_id: str = ""
    redirect_url: str = ""  # For REDIRECT flow providers
    client_secret: str = ""  # For INLINE flow (e.g. Stripe client_secret)
    error_message: str = ""
    provider_data: dict = field(default_factory=dict)


class PaymentProvider(ABC):
    """
    Abstract interface that all payment providers implement.

    Lifecycle:
        1. ``get_flow_type()`` — tells the view layer which UI to render
        2. ``create_payment()`` — initiates the payment (server-side)
        3. ``get_client_config()`` — returns JS config for inline providers
        4. ``confirm_payment()`` — finalizes after client interaction or webhook
        5. ``handle_webhook()`` — processes async callbacks from the provider
        6. ``get_receipt_data()`` — returns receipt info for confirmation display
    """

    @abstractmethod
    def get_name(self) -> str:
        """Human-readable provider name (e.g., 'Stripe', 'ECSI')."""

    @abstractmethod
    def get_flow_type(self) -> PaymentFlow:
        """Whether this provider uses inline or redirect payment collection."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the provider is properly configured."""

    @abstractmethod
    def create_payment(
        self,
        amount: Decimal,
        currency: str,
        submission_id: int,
        description: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> PaymentResult:
        """
        Initiate a payment.

        For INLINE providers: creates a payment intent, returns client_secret.
        For REDIRECT providers: creates a session, returns redirect_url.
        """

    @abstractmethod
    def confirm_payment(
        self,
        transaction_id: str,
        **kwargs: Any,
    ) -> PaymentResult:
        """
        Confirm/finalize a payment after client interaction.

        Called when:
        - INLINE flow: after client-side confirms (server verification)
        - REDIRECT flow: on the return-URL callback
        """

    def handle_webhook(self, request: Any) -> PaymentResult | None:
        """
        Process an asynchronous webhook from the payment provider.

        Override if the provider sends server-to-server callbacks.
        Returns None if the event is not relevant.
        """
        return None

    def get_client_config(self, payment_result: PaymentResult) -> dict:
        """
        Return configuration for the client-side payment UI.

        INLINE providers return keys needed by their JS SDK
        (e.g., publishable_key, client_secret for Stripe).
        REDIRECT providers typically return an empty dict.
        """
        return {}

    def get_receipt_data(self, transaction_id: str) -> dict:
        """Return data for rendering a payment receipt/confirmation."""
        return {}

    def refund_payment(
        self, transaction_id: str, amount: Decimal | None = None
    ) -> PaymentResult:
        """Issue a full or partial refund. Not all providers support this."""
        raise NotImplementedError(
            f"{self.get_name()} does not support programmatic refunds."
        )
