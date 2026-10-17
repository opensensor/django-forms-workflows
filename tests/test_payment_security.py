"""
Regression tests for payment endpoint authorization and state transitions
(issue #27).

Covers the payment access policy (owner / anonymous session-bound checkout
credential), idempotent initiation, lifecycle-restricted confirm/return/
cancel, fail-closed webhook signature verification, and replay/out-of-order
webhook handling.
"""

from types import SimpleNamespace
from unittest import mock

import pytest
from django.test import Client
from django.urls import reverse

from django_forms_workflows.models import (
    ApprovalTask,
    FormDefinition,
    FormField,
    FormSubmission,
    PaymentRecord,
)
from django_forms_workflows.payments.base import (
    PaymentFlow,
    PaymentProvider,
    PaymentResult,
    PaymentStatus,
    WebhookVerificationError,
)
from django_forms_workflows.payments.checkout import SESSION_KEY
from django_forms_workflows.payments.registry import (
    _instances,
    _registry,
    register_provider,
)

pytestmark = pytest.mark.django_db

PROVIDER_NAME = "testpay_security"


# ── Fixtures ─────────────────────────────────────────────────────────


class FakeProvider(PaymentProvider):
    """Controllable in-memory provider used to drive the payment views."""

    def __init__(self):
        self.flow = PaymentFlow.INLINE
        self.create_calls = []
        self.confirm_results = []
        self.webhook_result = None
        self.webhook_error = None
        self.next_create_result = None
        self.tx_counter = 0

    # PaymentProvider interface ───────────────────────────────────────
    def get_name(self):
        return "Fake"

    def get_flow_type(self):
        return self.flow

    def is_available(self):
        return True

    def create_payment(
        self,
        amount,
        currency,
        submission_id,
        description="",
        metadata=None,
        idempotency_key=None,
    ):
        self.create_calls.append(
            {
                "amount": amount,
                "currency": currency,
                "submission_id": submission_id,
                "idempotency_key": idempotency_key,
            }
        )
        if self.next_create_result is not None:
            result = self.next_create_result
            self.next_create_result = None
            return result
        self.tx_counter += 1
        return PaymentResult(
            success=True,
            status=PaymentStatus.PENDING,
            transaction_id=f"txn_{self.tx_counter}",
            client_secret=f"cs_{self.tx_counter}",
            provider_data={"intent_id": f"txn_{self.tx_counter}"},
        )

    def confirm_payment(self, transaction_id, **kwargs):
        if self.confirm_results:
            return self.confirm_results.pop(0)
        return PaymentResult(
            success=True,
            status=PaymentStatus.COMPLETED,
            transaction_id=transaction_id,
            provider_data={"status": "succeeded"},
        )

    def handle_webhook(self, request):
        if self.webhook_error is not None:
            raise self.webhook_error
        return self.webhook_result

    def get_client_config(self, payment_result):
        return {"provider": "fake", "client_secret": payment_result.client_secret}


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def auth_client(client, user):
    client.force_login(user)
    return client


@pytest.fixture
def fake_provider():
    provider = FakeProvider()
    register_provider(PROVIDER_NAME, provider)
    try:
        yield provider
    finally:
        _registry.pop(PROVIDER_NAME, None)
        _instances.pop(PROVIDER_NAME, None)


@pytest.fixture
def paid_form(db, category, user):
    return FormDefinition.objects.create(
        name="Paid Security Form",
        slug="paid-security-form",
        category=category,
        is_active=True,
        payment_enabled=True,
        payment_provider=PROVIDER_NAME,
        payment_amount_type="fixed",
        payment_fixed_amount="25.00",
        payment_currency="usd",
        created_by=user,
    )


@pytest.fixture
def paid_public_form(db, category, user):
    form_def = FormDefinition.objects.create(
        name="Paid Public Form",
        slug="paid-public-form",
        category=category,
        is_active=True,
        requires_login=False,
        payment_enabled=True,
        payment_provider=PROVIDER_NAME,
        payment_amount_type="fixed",
        payment_fixed_amount="25.00",
        payment_currency="usd",
        created_by=user,
    )
    FormField.objects.create(
        form_definition=form_def,
        field_name="full_name",
        field_label="Full Name",
        field_type="text",
        order=1,
        required=True,
    )
    return form_def


@pytest.fixture
def pending_submission(paid_form, user):
    return FormSubmission.objects.create(
        form_definition=paid_form,
        submitter=user,
        form_data={"full_name": "Owner"},
        status="pending_payment",
    )


@pytest.fixture
def pending_record(paid_form, pending_submission):
    return PaymentRecord.objects.create(
        submission=pending_submission,
        form_definition=paid_form,
        provider_name=PROVIDER_NAME,
        amount="25.00",
        currency="usd",
        status="pending",
        transaction_id="txn_pending_1",
        idempotency_key="sub_sec_key_1",
    )


@pytest.fixture
def other_user(db):
    from django.contrib.auth.models import User

    return User.objects.create_user(
        username="other", email="other@example.com", password="pass123"
    )


@pytest.fixture
def other_client(other_user):
    client = Client()
    client.force_login(other_user)
    return client


@pytest.fixture
def anonymous_checkout(paid_public_form, fake_provider):
    """Anonymous browser that has just posted a public paid form.

    Returns (client, submission): the client session holds a valid
    checkout credential for the submission.
    """
    client = Client()
    resp = client.post(
        reverse("forms_workflows:form_submit", args=[paid_public_form.slug]),
        data={"full_name": "Anonymous Payer"},
    )
    assert resp.status_code == 302
    assert resp["Location"].endswith("/initiate/")
    submission = FormSubmission.objects.get(
        form_definition=paid_public_form, status="pending_payment"
    )
    return client, submission


def _initiate_url(submission):
    return reverse("forms_workflows:payment_initiate", args=[submission.id])


def _confirm_url(record):
    return reverse("forms_workflows:payment_confirm", args=[record.id])


def _return_url(submission):
    return reverse("forms_workflows:payment_return", args=[submission.id])


def _cancel_url(submission):
    return reverse("forms_workflows:payment_cancel", args=[submission.id])


# ── Access policy: authenticated owner / strangers / anonymous ───────


class TestPaymentAccessPolicy:
    def test_anonymous_gets_404_on_owned_submission(
        self, client, pending_submission, fake_provider
    ):
        resp = client.get(_initiate_url(pending_submission))
        assert resp.status_code == 404
        assert fake_provider.create_calls == []

    def test_different_signed_in_user_gets_404(
        self, other_client, pending_submission, fake_provider
    ):
        resp = other_client.get(_initiate_url(pending_submission))
        assert resp.status_code == 404
        assert fake_provider.create_calls == []

    def test_owner_can_initiate(self, auth_client, pending_submission, fake_provider):
        resp = auth_client.get(_initiate_url(pending_submission))
        assert resp.status_code == 200
        assert len(fake_provider.create_calls) == 1

    def test_confirm_denied_for_anonymous(self, client, pending_record, fake_provider):
        resp = client.post(_confirm_url(pending_record), {})
        assert resp.status_code == 404

    def test_confirm_denied_for_different_user(
        self, other_client, pending_record, fake_provider
    ):
        resp = other_client.post(_confirm_url(pending_record), {})
        assert resp.status_code == 404

    def test_return_denied_for_anonymous(
        self, client, pending_submission, pending_record, fake_provider
    ):
        resp = client.get(_return_url(pending_submission))
        assert resp.status_code == 404

    def test_return_denied_for_different_user(
        self, other_client, pending_submission, pending_record, fake_provider
    ):
        resp = other_client.get(_return_url(pending_submission))
        assert resp.status_code == 404
        pending_submission.refresh_from_db()
        assert pending_submission.status == "pending_payment"

    def test_cancel_denied_for_anonymous(
        self, client, pending_submission, fake_provider
    ):
        resp = client.post(_cancel_url(pending_submission))
        assert resp.status_code == 404
        pending_submission.refresh_from_db()
        assert pending_submission.status == "pending_payment"

    def test_cancel_denied_for_different_user(
        self, other_client, pending_submission, fake_provider
    ):
        resp = other_client.post(_cancel_url(pending_submission))
        assert resp.status_code == 404
        pending_submission.refresh_from_db()
        assert pending_submission.status == "pending_payment"


# ── Anonymous public-form checkout credential ────────────────────────


class TestAnonymousCheckoutCredential:
    def test_form_post_grants_session_credential(self, anonymous_checkout):
        client, submission = anonymous_checkout
        session = client.session
        assert str(submission.id) in session.get(SESSION_KEY, {})

    def test_anonymous_with_credential_can_initiate(self, anonymous_checkout):
        client, submission = anonymous_checkout
        resp = client.get(_initiate_url(submission))
        assert resp.status_code == 200

    def test_guessed_id_without_credential(self, paid_public_form, fake_provider):
        stranger = Client()
        submission = FormSubmission.objects.create(
            form_definition=paid_public_form,
            submitter=None,
            form_data={"full_name": "Victim"},
            status="pending_payment",
        )
        for url in (
            _initiate_url(submission),
            _return_url(submission),
        ):
            assert stranger.get(url).status_code == 404
        assert stranger.post(_cancel_url(submission)).status_code == 404
        assert PaymentRecord.objects.count() == 0
        submission.refresh_from_db()
        assert submission.status == "pending_payment"

    def test_credential_does_not_transfer_across_submissions(
        self, paid_public_form, anonymous_checkout
    ):
        client, own_submission = anonymous_checkout
        other_submission = FormSubmission.objects.create(
            form_definition=paid_public_form,
            submitter=None,
            form_data={"full_name": "Someone Else"},
            status="pending_payment",
        )
        resp = client.get(_initiate_url(other_submission))
        assert resp.status_code == 404
        resp = client.post(_cancel_url(other_submission))
        assert resp.status_code == 404

    def test_expired_credential_is_rejected(self, anonymous_checkout, settings):
        client, submission = anonymous_checkout
        # Forge an already-expired credential.
        session = client.session
        session[SESSION_KEY][str(submission.id)]["exp"] = 1
        session.save()
        resp = client.get(_initiate_url(submission))
        assert resp.status_code == 404

    def test_anonymous_checkout_full_payment_cycle(
        self, anonymous_checkout, fake_provider
    ):
        client, submission = anonymous_checkout
        resp = client.get(_initiate_url(submission))
        assert resp.status_code == 200
        record = PaymentRecord.objects.get(submission=submission)

        resp = client.post(_confirm_url(record), {})
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        submission.refresh_from_db()
        # No approval workflow on this form — the engine auto-approves.
        assert submission.status == "approved"


# ── GET vs POST ──────────────────────────────────────────────────────


class TestHttpMethods:
    def test_cancel_rejects_get(self, auth_client, pending_submission):
        resp = auth_client.get(_cancel_url(pending_submission))
        assert resp.status_code == 405
        pending_submission.refresh_from_db()
        assert pending_submission.status == "pending_payment"

    def test_confirm_rejects_get(self, auth_client, pending_record):
        resp = auth_client.get(_confirm_url(pending_record))
        assert resp.status_code == 405

    def test_webhook_rejects_get(self, client):
        resp = client.get(reverse("forms_workflows:payment_webhook", args=["stripe"]))
        assert resp.status_code == 405


# ── Idempotent initiation / repeated requests ────────────────────────


class TestIdempotentInitiation:
    def test_repeated_gets_reuse_single_attempt(
        self, auth_client, pending_submission, fake_provider
    ):
        for _ in range(3):
            resp = auth_client.get(_initiate_url(pending_submission))
            assert resp.status_code == 200

        records = PaymentRecord.objects.filter(submission=pending_submission)
        assert records.count() == 1
        record = records.first()
        # The provider was re-invoked with the SAME stable idempotency key,
        # so an idempotency-aware provider dedupes instead of re-charging.
        keys = [c["idempotency_key"] for c in fake_provider.create_calls]
        assert keys == [record.idempotency_key] * 3

    def test_retry_after_cancel_starts_new_attempt(
        self, auth_client, pending_submission, fake_provider
    ):
        resp = auth_client.get(_initiate_url(pending_submission))
        assert resp.status_code == 200
        PaymentRecord.objects.get(submission=pending_submission)

        resp = auth_client.post(_cancel_url(pending_submission))
        assert resp.status_code == 302
        pending_submission.refresh_from_db()
        assert pending_submission.status == "draft"

        # A legitimate retry: move the submission back to pending_payment
        # (as a resubmission of the draft would) and re-initiate.
        pending_submission.status = "pending_payment"
        pending_submission.save(update_fields=["status"])
        resp = auth_client.get(_initiate_url(pending_submission))
        assert resp.status_code == 200

        records = PaymentRecord.objects.filter(submission=pending_submission).order_by(
            "created_at"
        )
        assert records.count() == 2
        assert records[0].status == "cancelled"
        assert records[1].status == "pending"
        assert records[0].idempotency_key != records[1].idempotency_key


# ── Confirm: lifecycle restrictions ─────────────────────────────────


class TestConfirmLifecycle:
    def test_confirm_completes_and_finalizes(
        self, auth_client, pending_record, fake_provider
    ):
        resp = auth_client.post(_confirm_url(pending_record), {})
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        pending_record.refresh_from_db()
        assert pending_record.status == "completed"
        assert pending_record.completed_at is not None
        pending_record.submission.refresh_from_db()
        # No approval workflow on this form — the engine auto-approves.
        assert pending_record.submission.status == "approved"

    def test_confirm_is_idempotent_replay(
        self, auth_client, pending_record, fake_provider
    ):
        for _ in range(2):
            resp = auth_client.post(_confirm_url(pending_record), {})
            assert resp.status_code == 200
            assert resp.json()["success"] is True
        pending_record.refresh_from_db()
        assert pending_record.status == "completed"

    def test_confirm_rejects_cancelled_record(
        self, auth_client, pending_record, fake_provider
    ):
        pending_record.status = "cancelled"
        pending_record.save(update_fields=["status"])
        resp = auth_client.post(_confirm_url(pending_record), {})
        assert resp.status_code == 409
        assert resp.json()["success"] is False

    def test_confirm_rejects_when_submission_not_pending(
        self, auth_client, pending_record, fake_provider, user
    ):
        submission = pending_record.submission
        submission.status = "submitted"
        submission.save(update_fields=["status"])
        pending_record.status = "failed"
        pending_record.save(update_fields=["status"])
        resp = auth_client.post(_confirm_url(pending_record), {})
        assert resp.status_code == 409


# ── Return: provider redirect binding ───────────────────────────────


class TestPaymentReturn:
    def test_return_completes_checkout(
        self, auth_client, pending_submission, pending_record, fake_provider
    ):
        resp = auth_client.get(_return_url(pending_submission))
        assert resp.status_code == 302
        pending_record.refresh_from_db()
        assert pending_record.status == "completed"
        pending_submission.refresh_from_db()
        # No approval workflow on this form — the engine auto-approves.
        assert pending_submission.status == "approved"

    def test_return_after_finalization_is_safe(
        self, auth_client, pending_submission, pending_record, fake_provider
    ):
        # Simulate a webhook finalizing before the browser returns.
        pending_submission.status = "submitted"
        pending_submission.save(update_fields=["status"])
        pending_record.status = "completed"
        pending_record.save(update_fields=["status"])

        resp = auth_client.get(_return_url(pending_submission))
        assert resp.status_code == 302
        pending_submission.refresh_from_db()
        assert pending_submission.status == "submitted"

    def test_return_failed_payment_does_not_finalize(
        self, auth_client, pending_submission, pending_record, fake_provider
    ):
        fake_provider.confirm_results.append(
            PaymentResult(
                success=False,
                status=PaymentStatus.FAILED,
                transaction_id="txn_pending_1",
                error_message="card declined",
            )
        )
        resp = auth_client.get(_return_url(pending_submission))
        assert resp.status_code == 200  # error page
        pending_submission.refresh_from_db()
        assert pending_submission.status == "pending_payment"
        pending_record.refresh_from_db()
        assert pending_record.status == "failed"


# ── Cancel: state transition safety ─────────────────────────────────


class TestCancelTransitions:
    def test_cancel_reverts_pending_payment_to_draft(
        self, auth_client, pending_submission, pending_record
    ):
        resp = auth_client.post(_cancel_url(pending_submission))
        assert resp.status_code == 302
        pending_submission.refresh_from_db()
        assert pending_submission.status == "draft"
        pending_record.refresh_from_db()
        assert pending_record.status == "cancelled"

    def test_cancel_never_reverts_submitted(
        self, auth_client, pending_submission, user
    ):
        pending_submission.status = "submitted"
        pending_submission.save(update_fields=["status"])
        resp = auth_client.post(_cancel_url(pending_submission))
        assert resp.status_code == 404
        pending_submission.refresh_from_db()
        assert pending_submission.status == "submitted"

    @pytest.mark.parametrize("status", ["approved", "pending_approval"])
    def test_cancel_never_reverts_later_states(
        self, auth_client, pending_submission, status
    ):
        pending_submission.status = status
        pending_submission.save(update_fields=["status"])
        resp = auth_client.post(_cancel_url(pending_submission))
        assert resp.status_code == 404
        pending_submission.refresh_from_db()
        assert pending_submission.status == status

    def test_cancel_does_not_touch_completed_record(
        self, auth_client, pending_submission, pending_record
    ):
        pending_record.status = "completed"
        pending_record.save(update_fields=["status"])
        auth_client.post(_cancel_url(pending_submission))
        pending_record.refresh_from_db()
        assert pending_record.status == "completed"
        pending_submission.refresh_from_db()
        assert pending_submission.status == "draft"

    def test_anonymous_cancel_revokes_credential(
        self, anonymous_checkout, fake_provider
    ):
        client, submission = anonymous_checkout
        resp = client.post(_cancel_url(submission))
        assert resp.status_code == 302
        submission.refresh_from_db()
        assert submission.status == "draft"
        assert str(submission.id) not in client.session.get(SESSION_KEY, {})


# ── Webhooks: signature verification required ───────────────────────


def _make_payment_record(submission, transaction_id="txn_wh_1", status="pending"):
    return PaymentRecord.objects.create(
        submission=submission,
        form_definition=submission.form_definition,
        provider_name=PROVIDER_NAME,
        amount="25.00",
        currency="usd",
        status=status,
        transaction_id=transaction_id,
        idempotency_key=f"wh_key_{transaction_id}_{status}",
    )


def _webhook_url(provider=PROVIDER_NAME):
    return reverse("forms_workflows:payment_webhook", args=[provider])


class TestWebhookVerification:
    def test_unverifiable_event_rejected(
        self, client, pending_submission, fake_provider
    ):
        record = _make_payment_record(pending_submission)
        fake_provider.webhook_error = WebhookVerificationError("no secret")
        resp = client.post(_webhook_url(), data="{}", content_type="application/json")
        assert resp.status_code == 400
        record.refresh_from_db()
        assert record.status == "pending"
        pending_submission.refresh_from_db()
        assert pending_submission.status == "pending_payment"

    def test_verified_event_applies(self, client, pending_submission, fake_provider):
        record = _make_payment_record(pending_submission)
        fake_provider.webhook_result = PaymentResult(
            success=True,
            status=PaymentStatus.COMPLETED,
            transaction_id="txn_wh_1",
            provider_data={"event_type": "payment_intent.succeeded"},
        )
        resp = client.post(_webhook_url(), data="{}", content_type="application/json")
        assert resp.status_code == 200
        record.refresh_from_db()
        assert record.status == "completed"
        assert record.completed_at is not None
        pending_submission.refresh_from_db()
        # No approval workflow on this form — the engine auto-approves.
        assert pending_submission.status == "approved"

    def test_duplicate_event_creates_no_duplicate_tasks(
        self, client, paid_form, user, fake_provider, approval_group
    ):
        from django_forms_workflows.models import WorkflowDefinition, WorkflowStage

        wf = WorkflowDefinition.objects.create(
            form_definition=paid_form, requires_approval=True
        )
        stage = WorkflowStage.objects.create(
            workflow=wf, name="Approval", order=1, approval_logic="any"
        )
        stage.approval_groups.add(approval_group)

        submission = FormSubmission.objects.create(
            form_definition=paid_form,
            submitter=user,
            form_data={},
            status="pending_payment",
        )
        _make_payment_record(submission)
        fake_provider.webhook_result = PaymentResult(
            success=True,
            status=PaymentStatus.COMPLETED,
            transaction_id="txn_wh_1",
            provider_data={"event_type": "payment_intent.succeeded"},
        )
        for _ in range(3):
            resp = client.post(
                _webhook_url(), data="{}", content_type="application/json"
            )
            assert resp.status_code == 200
        submission.refresh_from_db()
        assert submission.status == "pending_approval"
        task_count = ApprovalTask.objects.filter(submission=submission).count()
        for _ in range(2):  # extra replays still change nothing
            client.post(_webhook_url(), data="{}", content_type="application/json")
        assert ApprovalTask.objects.filter(submission=submission).count() == task_count

    def test_out_of_order_failure_does_not_roll_back_completion(
        self, client, pending_submission, fake_provider
    ):
        record = _make_payment_record(pending_submission, status="completed")
        pending_submission.status = "submitted"
        pending_submission.save(update_fields=["status"])
        fake_provider.webhook_result = PaymentResult(
            success=False,
            status=PaymentStatus.FAILED,
            transaction_id="txn_wh_1",
            error_message="late failure event",
        )
        resp = client.post(_webhook_url(), data="{}", content_type="application/json")
        assert resp.status_code == 200
        record.refresh_from_db()
        assert record.status == "completed"
        pending_submission.refresh_from_db()
        assert pending_submission.status == "submitted"

    def test_failed_record_can_still_complete(
        self, client, pending_submission, fake_provider
    ):
        record = _make_payment_record(pending_submission, status="failed")
        fake_provider.webhook_result = PaymentResult(
            success=True,
            status=PaymentStatus.COMPLETED,
            transaction_id="txn_wh_1",
            provider_data={"event_type": "payment_intent.succeeded"},
        )
        resp = client.post(_webhook_url(), data="{}", content_type="application/json")
        assert resp.status_code == 200
        record.refresh_from_db()
        assert record.status == "completed"
        pending_submission.refresh_from_db()
        # No approval workflow on this form — the engine auto-approves.
        assert pending_submission.status == "approved"


# ── Stripe provider: fail-closed webhook verification ───────────────


class _FakeStripeError:
    SignatureVerificationError = type("SignatureVerificationError", (Exception,), {})


def _fake_stripe(construct_event=None):
    return SimpleNamespace(
        Webhook=SimpleNamespace(construct_event=construct_event),
        error=_FakeStripeError,
        api_key=None,
    )


class TestStripeWebhookVerification:
    URL = reverse("forms_workflows:payment_webhook", args=["stripe"])

    def _post(self, client):
        return client.post(self.URL, data=b"{}", content_type="application/json")

    def test_missing_webhook_secret_fails_closed(self, client, settings):
        settings.STRIPE_WEBHOOK_SECRET = ""
        with mock.patch(
            "django_forms_workflows.payments.stripe_provider._get_stripe",
            return_value=_fake_stripe(),
        ):
            resp = self._post(client)
        assert resp.status_code == 400

    def test_invalid_signature_fails_closed(self, client, settings):
        settings.STRIPE_WEBHOOK_SECRET = "whsec_test"

        def _construct(payload, sig, secret):
            raise _FakeStripeError.SignatureVerificationError("bad signature")

        with mock.patch(
            "django_forms_workflows.payments.stripe_provider._get_stripe",
            return_value=_fake_stripe(construct_event=_construct),
        ):
            resp = self._post(client)
        assert resp.status_code == 400

    def test_valid_signature_applies_event(self, client, settings, paid_form, user):
        settings.STRIPE_WEBHOOK_SECRET = "whsec_test"
        settings.STRIPE_SECRET_KEY = "sk_test_x"
        submission = FormSubmission.objects.create(
            form_definition=paid_form,
            submitter=user,
            form_data={},
            status="pending_payment",
        )
        record = PaymentRecord.objects.create(
            submission=submission,
            form_definition=paid_form,
            provider_name="stripe",
            amount="25.00",
            currency="usd",
            status="pending",
            transaction_id="pi_123",
            idempotency_key="stripe_test_key",
        )

        event = SimpleNamespace(
            type="payment_intent.succeeded",
            data=SimpleNamespace(object=SimpleNamespace(id="pi_123")),
        )
        fake = _fake_stripe(construct_event=lambda p, s, k: event)
        with mock.patch(
            "django_forms_workflows.payments.stripe_provider._get_stripe",
            return_value=fake,
        ):
            resp = self._post(client)
        assert resp.status_code == 200
        record.refresh_from_db()
        assert record.status == "completed"
        submission.refresh_from_db()
        # No approval workflow on this form — the engine auto-approves.
        assert submission.status == "approved"

    def test_stripe_forwards_idempotency_key(self, settings):
        settings.STRIPE_SECRET_KEY = "sk_test_x"
        captured = {}

        class FakeIntent:
            id = "pi_test"
            client_secret = "cs_test"
            status = "requires_payment_method"

        def _create(**kwargs):
            captured.update(kwargs)
            return FakeIntent()

        fake = SimpleNamespace(
            PaymentIntent=SimpleNamespace(create=_create),
            api_key=None,
        )
        from django_forms_workflows.payments.stripe_provider import (
            StripePaymentProvider,
        )

        with mock.patch(
            "django_forms_workflows.payments.stripe_provider._get_stripe",
            return_value=fake,
        ):
            result = StripePaymentProvider().create_payment(
                amount=10, currency="usd", submission_id=1, idempotency_key="k_1"
            )
        assert captured.get("idempotency_key") == "k_1"
        assert result.success is True
