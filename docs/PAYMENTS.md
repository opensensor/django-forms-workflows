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
                        ↘ draft (only via an authorized cancellation)
```

## Payment access policy

Payment endpoints (`initiate`, `confirm`, `return`, `cancel`) enforce a
single access policy before rendering payment details, exposing client
secrets, calling providers, or changing records:

- **Authenticated submissions** — only the authenticated submitter may act
  on their own submission.
- **Anonymous (public-form) submissions** — the submitter's browser
  receives an unguessable, **session-bound checkout credential** when the
  form post creates the payment checkout. The credential is valid for
  `FORMS_WORKFLOWS_PAYMENT_CHECKOUT_TTL` seconds (default **3600**).

A numeric submission or payment-record ID alone grants **no** access;
callers that fail the policy receive a non-disclosing `404`, identical to
a nonexistent object. The credential is revoked on cancellation and cannot
be used once the submission has left `pending_payment`.

## Initiation idempotency and retries

Initiation is **idempotent per payment attempt**:

- The first authorized request creates one `PaymentRecord` with a stable
  `idempotency_key`; the row is locked while the attempt is created, so
  concurrent or repeated requests cannot create duplicate attempts.
- Repeated navigation to the initiate URL **reuses the open attempt**
  (`pending` / `requires_action` / `processing`) and re-issues the
  provider call with the **same idempotency key**, so providers that
  support request idempotency (e.g. Stripe) dedupe instead of creating
  duplicate provider-side charges.
- A **legitimate retry** starts a new attempt with a fresh idempotency
  key: cancel the open attempt (`POST …/payments/<submission_id>/cancel/`)
  or let a failed attempt be retried — the next initiation creates the
  new `PaymentRecord` then.

Cancellation is a CSRF-protected `POST` only. It is restricted to
`pending_payment` submissions and cancels only open attempts — it can
never revert a completed, submitted, or approved submission to `draft`.

## Submission flow

1. User fills out the form and submits.
2. If `payment_enabled`, the submission is saved with `status="pending_payment"`, a checkout credential is bound to the user's session, and the user is redirected to the payment initiation endpoint.
3. The view resolves the payment amount (fixed or from a form field), creates (or resumes) a `PaymentRecord`, and calls the provider's `create_payment()` with the attempt's stable idempotency key.
4. **INLINE flow**: renders `payment_collect.html` with the provider's JS SDK (e.g. Stripe Elements). The user completes payment without leaving the site.
5. **REDIRECT flow**: redirects the user to the provider's hosted payment page. The return URL is bound to the originating (single open) attempt and the provider's result is verified server-side.
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

Webhooks **require signing**. Add the webhook signing secret to Django settings:

```python
STRIPE_WEBHOOK_SECRET = "whsec_..."   # REQUIRED — events are rejected without it
```

Set up a Stripe webhook in your Stripe Dashboard pointing to:

```
https://your-domain.com/forms/payments/webhook/stripe/
```

Subscribe to `payment_intent.succeeded` and `payment_intent.payment_failed` events.

The provider verifies the `Stripe-Signature` header against
`STRIPE_WEBHOOK_SECRET` before any event is applied. Verification **fails
closed**: if the secret is missing or the signature is invalid, the
endpoint answers HTTP 400 and no payment or submission state changes.

Replayed and out-of-order events are safe: a completed payment is never
rolled backward by a late or duplicate event, `_finalize_submission()` is
idempotent (no duplicate workflow tasks), and the only permitted
transition out of `completed` is `completed → refunded`.

### Provider webhook requirement (all providers)

Every provider's `handle_webhook(request)` MUST authenticate the event
(signature, shared secret, or provider-verified fetch) before returning a
`PaymentResult`, and raise
`django_forms_workflows.payments.base.WebhookVerificationError` when
verification fails or its verification secret is not configured. The
generic webhook endpoint turns that exception into HTTP 400 without
applying any state change.

## Writing a custom provider

Third-party providers self-register in their Django app's `ready()` method:

```python
# myapp/providers.py
from django_forms_workflows.payments.base import (
    PaymentFlow,
    PaymentProvider,
    PaymentResult,
    PaymentStatus,
    WebhookVerificationError,
)

class MyProvider(PaymentProvider):
    def get_name(self):
        return "My Gateway"

    def get_flow_type(self):
        return PaymentFlow.REDIRECT

    def is_available(self):
        return bool(getattr(settings, "MY_GATEWAY_KEY", ""))

    def create_payment(self, amount, currency, description, metadata, idempotency_key):
        # Call your gateway API to create a checkout session. Forward the
        # idempotency key if your gateway supports it, so a retried
        # initiation of the same attempt cannot double-charge.
        session = my_gateway.create_session(
            amount=amount, currency=currency, idempotency_key=idempotency_key
        )
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
        # Authenticate the event first — raise to reject unverified payloads.
        if not my_gateway.verify_signature(request):
            raise WebhookVerificationError("invalid webhook signature")
        event = my_gateway.parse_event(request)
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
