"""
Stripe payment provider — ships as the bundled reference implementation.

Requires::

    pip install stripe

Configuration via standard Django settings::

    STRIPE_SECRET_KEY = "sk_test_..."
    STRIPE_PUBLISHABLE_KEY = "pk_test_..."
    STRIPE_WEBHOOK_SECRET = "whsec_..."   # optional, for webhook verification
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Any

from django.conf import settings

from .base import PaymentFlow, PaymentProvider, PaymentResult, PaymentStatus

logger = logging.getLogger(__name__)


def _get_stripe():
    """Lazy import stripe to allow the library to work without it installed."""
    try:
        import stripe

        return stripe
    except ImportError as err:
        raise ImportError(
            "The Stripe payment provider requires the 'stripe' package. "
            "Install it with: pip install stripe"
        ) from err


class StripePaymentProvider(PaymentProvider):
    def get_name(self) -> str:
        return "Stripe"

    def get_flow_type(self) -> PaymentFlow:
        return PaymentFlow.INLINE

    def is_available(self) -> bool:
        return bool(
            getattr(settings, "STRIPE_SECRET_KEY", "")
            and getattr(settings, "STRIPE_PUBLISHABLE_KEY", "")
        )

    def create_payment(
        self,
        amount: Decimal,
        currency: str,
        submission_id: int,
        description: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> PaymentResult:
        stripe = _get_stripe()
        stripe.api_key = settings.STRIPE_SECRET_KEY

        amount_cents = int(amount * 100)

        try:
            intent = stripe.PaymentIntent.create(
                amount=amount_cents,
                currency=currency.lower(),
                description=description or f"Form submission #{submission_id}",
                metadata=metadata or {},
                automatic_payment_methods={"enabled": True},
            )
            return PaymentResult(
                success=True,
                status=PaymentStatus.PENDING,
                transaction_id=intent.id,
                client_secret=intent.client_secret,
                provider_data={"intent_id": intent.id, "status": intent.status},
            )
        except Exception as e:
            logger.exception("Stripe create_payment failed")
            return PaymentResult(
                success=False,
                status=PaymentStatus.FAILED,
                error_message=str(e),
            )

    def confirm_payment(self, transaction_id: str, **kwargs: Any) -> PaymentResult:
        stripe = _get_stripe()
        stripe.api_key = settings.STRIPE_SECRET_KEY

        try:
            intent = stripe.PaymentIntent.retrieve(transaction_id)
            if intent.status == "succeeded":
                return PaymentResult(
                    success=True,
                    status=PaymentStatus.COMPLETED,
                    transaction_id=intent.id,
                    provider_data={
                        "intent_id": intent.id,
                        "status": intent.status,
                        "amount_received": intent.amount_received,
                    },
                )
            elif intent.status == "requires_action":
                return PaymentResult(
                    success=False,
                    status=PaymentStatus.REQUIRES_ACTION,
                    transaction_id=intent.id,
                    error_message="Additional authentication required.",
                )
            else:
                return PaymentResult(
                    success=False,
                    status=PaymentStatus.PROCESSING,
                    transaction_id=intent.id,
                    error_message=f"Payment status: {intent.status}",
                )
        except Exception as e:
            logger.exception("Stripe confirm_payment failed")
            return PaymentResult(
                success=False,
                status=PaymentStatus.FAILED,
                error_message=str(e),
            )

    def handle_webhook(self, request: Any) -> PaymentResult | None:
        stripe = _get_stripe()
        webhook_secret = getattr(settings, "STRIPE_WEBHOOK_SECRET", "")

        payload = request.body
        sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")

        if webhook_secret:
            try:
                event = stripe.Webhook.construct_event(
                    payload, sig_header, webhook_secret
                )
            except (ValueError, stripe.error.SignatureVerificationError) as e:
                logger.warning("Stripe webhook verification failed: %s", e)
                return None
        else:
            event = stripe.Event.construct_from(json.loads(payload), stripe.api_key)

        if event.type == "payment_intent.succeeded":
            intent = event.data.object
            return PaymentResult(
                success=True,
                status=PaymentStatus.COMPLETED,
                transaction_id=intent.id,
                provider_data={"event_type": event.type},
            )
        elif event.type == "payment_intent.payment_failed":
            intent = event.data.object
            return PaymentResult(
                success=False,
                status=PaymentStatus.FAILED,
                transaction_id=intent.id,
                error_message=(
                    intent.last_payment_error.message
                    if intent.last_payment_error
                    else "Payment failed"
                ),
            )

        return None

    def get_client_config(self, payment_result: PaymentResult) -> dict:
        return {
            "provider": "stripe",
            "publishable_key": getattr(settings, "STRIPE_PUBLISHABLE_KEY", ""),
            "client_secret": payment_result.client_secret,
        }

    def get_receipt_data(self, transaction_id: str) -> dict:
        stripe = _get_stripe()
        stripe.api_key = settings.STRIPE_SECRET_KEY

        try:
            intent = stripe.PaymentIntent.retrieve(
                transaction_id, expand=["latest_charge"]
            )
            charge = intent.latest_charge
            return {
                "amount": Decimal(str(intent.amount / 100)),
                "currency": intent.currency.upper(),
                "last4": (charge.payment_method_details.card.last4 if charge else ""),
                "brand": (charge.payment_method_details.card.brand if charge else ""),
                "receipt_url": charge.receipt_url if charge else "",
            }
        except Exception:
            return {}

    def refund_payment(
        self, transaction_id: str, amount: Decimal | None = None
    ) -> PaymentResult:
        stripe = _get_stripe()
        stripe.api_key = settings.STRIPE_SECRET_KEY

        try:
            params: dict[str, Any] = {"payment_intent": transaction_id}
            if amount is not None:
                params["amount"] = int(amount * 100)
            refund = stripe.Refund.create(**params)
            return PaymentResult(
                success=True,
                status=PaymentStatus.REFUNDED,
                transaction_id=refund.id,
                provider_data={"refund_id": refund.id, "status": refund.status},
            )
        except Exception as e:
            return PaymentResult(
                success=False,
                status=PaymentStatus.FAILED,
                error_message=str(e),
            )
