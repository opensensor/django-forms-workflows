# Payment System

`django-forms-workflows` includes a pluggable payment system that lets you collect payments as part of a form submission flow. Payments are processed after form validation but before the submission enters the approval workflow.

## Architecture

The payment system uses three layers:

| Layer | File | Purpose |
|---|---|---|
| **Abstract base** | `payments/base.py` | `PaymentProvider` ABC, enums, `PaymentResult` dataclass |
| **Registry** | `payments/registry.py` | Provider registration, lookup, and discovery |
| **Providers** | `payments/stripe_provider.py` | Concrete implementations (Stripe ships built-in) |

### Provider interface

Every provider implements `PaymentProvider`:

- `get_name()` — human-readable name (e.g. "Stripe")
- `get_flow_type()` — `PaymentFlow.INLINE` or `PaymentFlow.REDIRECT`
- `is_available()` — whether the provider is configured and ready
- `create_payment(amount, currency, description, metadata, idempotency_key)` — initiate a payment; returns a `PaymentResult`
- `confirm_payment(transaction_id, request)` — confirm an INLINE payment after client-side completion
- `handle_webhook(request)` — process provider webhook callbacks
- `get_client_config(payment_result)` — return config needed by the client-side JS (e.g. publishable key, client secret)
- `get_receipt_data(transaction_id)` — fetch receipt information
- `refund_payment(transaction_id, amount, reason)` — issue a full or partial refund

### Payment flows

| Flow | How it works | Example |
|---|---|---|
| `INLINE` | Payment form is rendered on your site using the provider's JS SDK. The user never leaves. | Stripe Elements |
| `REDIRECT` | User is redirected to the provider's hosted payment page, then returned to your site. | PayPal, external portals |

### PaymentResult

Returned by `create_payment()` and `confirm_payment()`:

```python
@dataclass
class PaymentResult:
    success: bool
    status: PaymentStatus          # pending, completed, failed, cancelled, refunded
    transaction_id: str = ""
    redirect_url: str = ""         # For REDIRECT flow
    client_secret: str = ""        # For INLINE flow (e.g. Stripe client_secret)
    error_message: str = ""
    provider_data: dict = field(default_factory=dict)
```

## Models

### PaymentRecord

Tracks the lifecycle of a single payment attempt:

| Field | Type | Purpose |
|---|---|---|
| `submission` | FK → FormSubmission | The submission this payment belongs to |
| `form_definition` | FK → FormDefinition | The form (protected on delete) |
| `provider_name` | CharField | Registry key of the provider used |
| `transaction_id` | CharField | Provider's transaction/payment intent ID |
| `amount` | DecimalField | Payment amount |
| `currency` | CharField | ISO 4217 currency code |
| `status` | CharField | `pending`, `completed`, `failed`, `cancelled`, `refunded` |
| `error_message` | TextField | Error details on failure |
| `idempotency_key` | CharField (unique) | Prevents duplicate charges |
| `provider_data` | JSONField | Raw provider response data |
| `created_at` / `completed_at` | DateTimeField | Timestamps |

### FormDefinition payment fields

Seven fields on `FormDefinition` configure payment collection:

| Field | Default | Purpose |
|---|---|---|
| `payment_enabled` | `False` | Master toggle |
| `payment_provider` | `""` | Registry key (e.g. `"stripe"`) |
| `payment_amount_type` | `"fixed"` | `"fixed"` or `"field"` |
| `payment_fixed_amount` | `None` | Amount when type is fixed |
| `payment_amount_field` | `""` | Form field name when type is field |
| `payment_currency` | `"usd"` | ISO 4217 currency code |
| `payment_description_template` | `""` | Description with `{form_name}`, `{submission_id}` tokens |

### FormSubmission status

A new `pending_payment` status is added to the submission lifecycle:

```
draft → pending_payment → submitted → pending_approval → approved
                       ↘ cancelled (if user cancels payment)
```

## Submission flow

1. User fills out the form and submits.
2. If `payment_enabled`, the submission is saved with `status="pending_payment"` and the user is redirected to the payment initiation endpoint.
3. The view resolves the payment amount (fixed or from a form field), creates a `PaymentRecord`, and calls the provider's `create_payment()`.
4. **INLINE flow**: renders `payment_collect.html` with the provider's JS SDK (e.g. Stripe Elements). The user completes payment without leaving the site.
5. **REDIRECT flow**: redirects the user to the provider's hosted payment page.
6. On successful payment confirmation, the submission transitions to `submitted` and enters the normal workflow engine (`_finalize_submission()`).

## Built-in Stripe provider

The library ships with a Stripe provider that auto-registers in `AppConfig.ready()`.

### Setup

1. Install the Stripe Python SDK:

   ```bash
   pip install stripe
   ```

2. Add your Stripe API keys to Django settings:

   ```python
   STRIPE_SECRET_KEY = "sk_test_..."
   STRIPE_PUBLISHABLE_KEY = "pk_test_..."
   ```

3. In the form's admin or form builder, enable payment and select "Stripe" as the provider.

The Stripe provider uses **PaymentIntents** with `automatic_payment_methods` enabled, which supports cards, Apple Pay, Google Pay, and other methods Stripe enables on your account.

### Webhook configuration

Set up a Stripe webhook in your Stripe Dashboard pointing to:

```
https://your-domain.com/forms/payments/webhook/stripe/
```

Subscribe to `payment_intent.succeeded` and `payment_intent.payment_failed` events.

## Writing a custom provider

Third-party providers self-register in their Django app's `ready()` method:

```python
# myapp/providers.py
from django_forms_workflows.payments.base import (
    PaymentFlow,
    PaymentProvider,
    PaymentResult,
    PaymentStatus,
)

class MyProvider(PaymentProvider):
    def get_name(self):
        return "My Gateway"

    def get_flow_type(self):
        return PaymentFlow.REDIRECT

    def is_available(self):
        return bool(getattr(settings, "MY_GATEWAY_KEY", ""))

    def create_payment(self, amount, currency, description, metadata, idempotency_key):
        # Call your gateway API to create a checkout session
        session = my_gateway.create_session(amount=amount, currency=currency)
        return PaymentResult(
            success=True,
            status=PaymentStatus.PENDING,
            transaction_id=session.id,
            redirect_url=session.checkout_url,
        )

    def confirm_payment(self, transaction_id, request):
        result = my_gateway.get_payment(transaction_id)
        return PaymentResult(
            success=result.paid,
            status=PaymentStatus.COMPLETED if result.paid else PaymentStatus.FAILED,
            transaction_id=transaction_id,
        )

    def handle_webhook(self, request):
        # Verify and process webhook
        return PaymentResult(...)

    def refund_payment(self, transaction_id, amount=None, reason=None):
        my_gateway.refund(transaction_id, amount=amount)
        return PaymentResult(
            success=True,
            status=PaymentStatus.REFUNDED,
            transaction_id=transaction_id,
        )
```

```python
# myapp/apps.py
from django.apps import AppConfig

class MyAppConfig(AppConfig):
    name = "myapp"

    def ready(self):
        from django_forms_workflows.payments import register_provider
        from .providers import MyProvider
        register_provider("my_gateway", MyProvider)
```

The provider will appear in the admin and form builder dropdowns automatically.

## Admin integration

- **FormDefinition**: A collapsible "Payment" fieldset exposes all seven payment configuration fields.
- **FormSubmission**: A `PaymentRecordInline` shows all payment attempts for a submission (read-only).
- **PaymentRecord**: A standalone read-only admin with search by transaction ID, status filtering, and date hierarchy.

## Form builder integration

The form builder's settings panel includes a "Payment" section with:

- Payment enabled toggle
- Provider dropdown (populated from registry)
- Amount type (fixed / from field)
- Fixed amount input
- Amount field selector
- Currency input
- Description template input

## Sync and cloning

- **Clone forms** action copies all seven payment fields to the cloned form.
- **Sync export/import** serializes and restores payment configuration. `PaymentRecord` instances are not synced (they are runtime data).

## Related docs

- [Workflows](WORKFLOWS.md)
- [Shared Option Lists](SHARED_OPTION_LISTS.md)
- [Post-Submission Actions](POST_SUBMISSION_ACTIONS.md)
