"""
Payment views: initiate payment, handle return callbacks, process webhooks.

Every endpoint that touches a submission or payment record enforces the
single access policy in :mod:`django_forms_workflows.payments.checkout`:

* an authenticated submitter may act only on their own submission;
* an anonymous public-form submitter needs a short-lived, unguessable,
  session-bound checkout credential.

Callers that fail the policy get a non-disclosing 404 — identical to a
nonexistent object — and no payment details, client secrets, provider
calls, or record changes are performed.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import transaction
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from ..models import AuditLog, FormSubmission, PaymentRecord
from .base import PaymentFlow, PaymentStatus, WebhookVerificationError
from .checkout import has_checkout_access, revoke_checkout_access
from .registry import get_provider

logger = logging.getLogger(__name__)

# Payment-record states in which an attempt is still open and may be
# confirmed, returned to, retried against the provider, or cancelled.
ACTIVE_PAYMENT_STATUSES = ("pending", "requires_action", "processing")

# Payment-record states that must never be left by a later event.
# `completed -> refunded` is the only permitted forward transition.
_LOCKED_PAYMENT_STATUSES = ("completed", "refunded")


def _require_checkout_access(request, submission):
    """Enforce the payment access policy or raise a non-disclosing 404."""
    if not has_checkout_access(request, submission):
        raise Http404("Not found")


def _apply_payment_result(payment_record, result) -> bool:
    """
    Apply a provider result to ``payment_record`` without rolling state
    backward.

    Returns True if the record changed.  Events arriving for a record in a
    locked state (``completed``/``refunded``) are ignored — except the
    forward ``completed -> refunded`` transition — so replayed or
    out-of-order events cannot revert a finished payment.
    """
    new_status = result.status.value
    if payment_record.status in _LOCKED_PAYMENT_STATUSES and not (
        payment_record.status == "completed" and new_status == "refunded"
    ):
        logger.info(
            "Ignoring out-of-order payment event: record %s is %r, event says %r",
            payment_record.pk,
            payment_record.status,
            new_status,
        )
        return False

    payment_record.status = new_status
    payment_record.provider_data = result.provider_data
    if new_status == PaymentStatus.COMPLETED.value:
        payment_record.completed_at = timezone.now()
        payment_record.error_message = ""
    else:
        payment_record.error_message = result.error_message or ""
    payment_record.save()
    return True


def initiate_payment(request, submission_id):
    """
    Called after form validation.  Creates or resumes a PaymentRecord and
    either:
    - Returns the inline payment page for INLINE providers (Stripe)
    - Redirects to the external portal for REDIRECT providers (ECSI, PayPal)

    Initiation is idempotent per attempt: repeated navigation reuses the
    existing open PaymentRecord (and its stable idempotency key) instead of
    creating new provider-side payment intents.  A legitimate retry — after
    the previous attempt was cancelled or failed — gets a fresh record and
    idempotency key.
    """
    submission = get_object_or_404(
        FormSubmission, id=submission_id, status="pending_payment"
    )
    _require_checkout_access(request, submission)

    form_def = submission.form_definition

    if not form_def.payment_enabled or not form_def.payment_provider:
        return redirect(
            "forms_workflows:submission_detail", submission_id=submission.id
        )

    provider = get_provider(form_def.payment_provider)
    if not provider or not provider.is_available():
        logger.error("Payment provider %r not available", form_def.payment_provider)
        return render(
            request,
            "django_forms_workflows/payment_error.html",
            {
                "error": "Payment provider is not available. Please contact support.",
                "submission": submission,
            },
        )

    amount = _resolve_payment_amount(form_def, submission)
    if amount is None or amount <= 0:
        return render(
            request,
            "django_forms_workflows/payment_error.html",
            {
                "error": "Could not determine payment amount.",
                "submission": submission,
            },
        )

    currency = form_def.payment_currency or "usd"
    description = _resolve_description(form_def, submission)

    with transaction.atomic():
        # Lock the submission row so concurrent/repeated requests cannot
        # create duplicate payment attempts.
        FormSubmission.objects.select_for_update().get(pk=submission.pk)

        payment_record = (
            submission.payment_records.filter(status__in=ACTIVE_PAYMENT_STATUSES)
            .order_by("-created_at")
            .first()
        )
        if payment_record is None:
            payment_record = PaymentRecord.objects.create(
                submission=submission,
                form_definition=form_def,
                provider_name=form_def.payment_provider,
                amount=amount,
                currency=currency,
                description=description,
                status="pending",
                idempotency_key=f"sub_{submission.id}_{uuid.uuid4().hex[:12]}",
            )

        # (Re)issue the provider call with the attempt's stable idempotency
        # key.  Providers that support idempotency dedupe this to the
        # original intent/session instead of creating a duplicate charge.
        result = provider.create_payment(
            amount=payment_record.amount,
            currency=payment_record.currency,
            submission_id=submission.id,
            description=payment_record.description,
            metadata={
                "form_slug": form_def.slug,
                "submission_id": str(submission.id),
                "payment_record_id": str(payment_record.id),
            },
            idempotency_key=payment_record.idempotency_key,
        )

        payment_record.transaction_id = (
            result.transaction_id or payment_record.transaction_id
        )
        payment_record.provider_data = result.provider_data
        if result.success:
            # Never let a (re)issued initiation leave a locked state.
            if payment_record.status not in _LOCKED_PAYMENT_STATUSES:
                payment_record.status = result.status.value
        elif payment_record.status not in _LOCKED_PAYMENT_STATUSES:
            # Likewise, a transient re-issue failure must not stomp an
            # attempt that was already completed by a concurrent webhook.
            payment_record.status = "failed"
            payment_record.error_message = result.error_message
        payment_record.save()

    if not result.success:
        return render(
            request,
            "django_forms_workflows/payment_error.html",
            {
                "error": result.error_message or "Payment initialization failed.",
                "submission": submission,
            },
        )

    if provider.get_flow_type() == PaymentFlow.REDIRECT:
        return redirect(result.redirect_url)

    # INLINE flow: render payment collection page
    client_config = provider.get_client_config(result)
    return render(
        request,
        "django_forms_workflows/payment_collect.html",
        {
            "submission": submission,
            "form_def": form_def,
            "payment_record": payment_record,
            "provider_name": form_def.payment_provider,
            "client_config_json": json.dumps(client_config),
            "amount": payment_record.amount,
            "currency": payment_record.currency,
        },
    )


@require_POST
def confirm_payment(request, payment_record_id):
    """
    AJAX endpoint called by client-side JS after inline payment succeeds.
    Verifies with the provider and finalizes the submission.
    """
    payment_record = get_object_or_404(PaymentRecord, id=payment_record_id)
    submission = payment_record.submission
    _require_checkout_access(request, submission)

    provider = get_provider(payment_record.provider_name)
    if not provider:
        return JsonResponse(
            {"success": False, "error": "Provider not found"}, status=500
        )

    # Idempotent replay: this attempt already finished.
    if payment_record.status == PaymentStatus.COMPLETED.value:
        _finalize_submission(submission)
        return JsonResponse(
            {
                "success": True,
                "redirect_url": _get_success_redirect(submission),
            }
        )

    # Only an open attempt on a submission still awaiting payment may be
    # confirmed; anything else is a lifecycle violation.
    if (
        payment_record.status not in ACTIVE_PAYMENT_STATUSES
        or submission.status != "pending_payment"
    ):
        return JsonResponse(
            {"success": False, "error": "This payment can no longer be confirmed."},
            status=409,
        )

    result = provider.confirm_payment(transaction_id=payment_record.transaction_id)

    _apply_payment_result(payment_record, result)
    if payment_record.status == PaymentStatus.COMPLETED.value:
        _finalize_submission(submission)
        return JsonResponse(
            {
                "success": True,
                "redirect_url": _get_success_redirect(submission),
            }
        )
    return JsonResponse(
        {
            "success": False,
            "error": result.error_message or "Payment could not be confirmed.",
        }
    )


def payment_return(request, submission_id):
    """
    Return URL for REDIRECT flow providers.
    Provider-specific query params are forwarded to confirm_payment().
    """
    submission = get_object_or_404(FormSubmission, id=submission_id)
    _require_checkout_access(request, submission)

    # The checkout was already finalized (e.g. by a webhook racing this
    # browser return) — send the user on without changing anything.
    if submission.status != "pending_payment":
        return redirect(_get_success_redirect(submission))

    # Bind the return to the originating checkout: the one open attempt
    # for this submission, verified server-side with the provider.
    payment_record = (
        submission.payment_records.filter(status__in=ACTIVE_PAYMENT_STATUSES)
        .order_by("-created_at")
        .first()
    )

    if not payment_record:
        return render(
            request,
            "django_forms_workflows/payment_error.html",
            {
                "error": "No pending payment found for this submission.",
                "submission": submission,
            },
        )

    provider = get_provider(payment_record.provider_name)
    if not provider:
        return render(
            request,
            "django_forms_workflows/payment_error.html",
            {
                "error": "Payment provider not available.",
                "submission": submission,
            },
        )

    result = provider.confirm_payment(
        transaction_id=payment_record.transaction_id,
        **request.GET.dict(),
    )

    _apply_payment_result(payment_record, result)
    if payment_record.status == PaymentStatus.COMPLETED.value:
        _finalize_submission(submission)
        return redirect(_get_success_redirect(submission))
    return render(
        request,
        "django_forms_workflows/payment_error.html",
        {
            "error": result.error_message or "Payment was not completed.",
            "submission": submission,
        },
    )


@require_POST
def payment_cancel(request, submission_id):
    """
    User cancelled payment.  CSRF-protected POST only; a plain GET (e.g. an
    unauthenticated provider redirect) can no longer change state, and a
    verified provider callback arrives via the webhook endpoint instead.
    """
    submission = get_object_or_404(
        FormSubmission, id=submission_id, status="pending_payment"
    )
    _require_checkout_access(request, submission)

    # Cancel only open attempts — never a completed or refunded payment.
    for payment_record in submission.payment_records.filter(
        status__in=ACTIVE_PAYMENT_STATUSES
    ):
        payment_record.status = "cancelled"
        payment_record.save(update_fields=["status", "updated_at"])

    # The status guard above scopes this to pending_payment submissions,
    # so a completed/submitted/approved submission can never be reverted.
    submission.status = "draft"
    submission.save(update_fields=["status"])

    revoke_checkout_access(request, submission)

    messages.warning(
        request, "Payment was cancelled. Your form has been saved as a draft."
    )
    if request.user.is_authenticated:
        return redirect("forms_workflows:my_submissions")
    return redirect("forms_workflows:form_list")


@csrf_exempt
@require_POST
def payment_webhook(request, provider_name):
    """
    Generic webhook endpoint: /forms/payments/webhook/<provider_name>/

    Delegates to the provider's handle_webhook() method.  Events are
    applied only when the provider authenticates them (e.g. a verified
    Stripe signature); unverifiable events fail closed with HTTP 400.
    Replayed or out-of-order events never roll a payment's state backward
    or create duplicate workflow tasks.
    """
    provider = get_provider(provider_name)
    if not provider:
        return HttpResponse(status=404)

    try:
        result = provider.handle_webhook(request)
    except WebhookVerificationError:
        logger.warning(
            "Rejected unauthenticated webhook event for provider %s", provider_name
        )
        return HttpResponse(status=400)
    except Exception:
        logger.exception("Webhook processing error for provider %s", provider_name)
        return HttpResponse(status=500)

    if result is None:
        return HttpResponse(status=200)

    if result.transaction_id:
        try:
            payment_record = PaymentRecord.objects.get(
                transaction_id=result.transaction_id,
                provider_name=provider_name,
            )
        except PaymentRecord.DoesNotExist:
            logger.warning("Webhook for unknown transaction %s", result.transaction_id)
            return HttpResponse(status=200)

        _apply_payment_result(payment_record, result)
        if payment_record.status == PaymentStatus.COMPLETED.value:
            _finalize_submission(payment_record.submission)

    return HttpResponse(status=200)


# ── Helpers ──────────────────────────────────────────────────────────


def _resolve_payment_amount(form_def, submission) -> Decimal | None:
    if form_def.payment_amount_type == "fixed":
        return form_def.payment_fixed_amount
    elif form_def.payment_amount_type == "field":
        raw = (submission.form_data or {}).get(form_def.payment_amount_field)
        if raw is not None:
            try:
                return Decimal(str(raw))
            except (InvalidOperation, ValueError):
                return None
    return None


def _resolve_description(form_def, submission) -> str:
    template = form_def.payment_description_template or form_def.name
    form_data = submission.form_data or {}
    form_data["form_name"] = form_def.name

    def _repl(m):
        val = form_data.get(m.group(1), "")
        if isinstance(val, list):
            return ", ".join(str(v) for v in val)
        return str(val)

    return re.sub(r"\{(\w+)\}", _repl, template)


def _finalize_submission(submission):
    """Move submission from pending_payment to submitted and trigger workflow."""
    if submission.status != "pending_payment":
        return  # Already finalized (idempotent for webhooks)

    submission.status = "submitted"
    submission.submitted_at = timezone.now()
    submission.save()

    AuditLog.objects.create(
        action="submit",
        object_type="FormSubmission",
        object_id=submission.id,
        user=submission.submitter,
        comments="Payment completed, form submitted",
    )

    # A stale checkout credential cannot be reused after finalization:
    # every endpoint requires the submission to still be pending_payment.

    from ..views import create_approval_tasks

    create_approval_tasks(submission)


def _get_success_redirect(submission):
    form_def = submission.form_definition
    if form_def.success_message:
        return reverse(
            "forms_workflows:submission_success",
            kwargs={"submission_id": submission.id},
        )
    if submission.submitter_id:
        return reverse("forms_workflows:my_submissions")
    return reverse("forms_workflows:public_submission_confirmation")
