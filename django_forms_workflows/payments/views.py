"""
Payment views: initiate payment, handle return callbacks, process webhooks.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from decimal import Decimal, InvalidOperation

from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from ..models import AuditLog, FormSubmission, PaymentRecord
from .base import PaymentFlow, PaymentStatus
from .registry import get_provider

logger = logging.getLogger(__name__)


def initiate_payment(request, submission_id):
    """
    Called after form validation.  Creates a PaymentRecord and either:
    - Returns the inline payment page for INLINE providers (Stripe)
    - Redirects to the external portal for REDIRECT providers (ECSI, PayPal)
    """
    submission = get_object_or_404(
        FormSubmission, id=submission_id, status="pending_payment"
    )
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
    idempotency_key = f"sub_{submission.id}_{uuid.uuid4().hex[:12]}"

    payment_record = PaymentRecord.objects.create(
        submission=submission,
        form_definition=form_def,
        provider_name=form_def.payment_provider,
        amount=amount,
        currency=currency,
        description=description,
        status="pending",
        idempotency_key=idempotency_key,
    )

    result = provider.create_payment(
        amount=amount,
        currency=currency,
        submission_id=submission.id,
        description=description,
        metadata={
            "form_slug": form_def.slug,
            "submission_id": str(submission.id),
            "payment_record_id": str(payment_record.id),
        },
    )

    payment_record.transaction_id = result.transaction_id
    payment_record.provider_data = result.provider_data
    if result.success:
        payment_record.status = result.status.value
    else:
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
            "amount": amount,
            "currency": currency,
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

    provider = get_provider(payment_record.provider_name)
    if not provider:
        return JsonResponse(
            {"success": False, "error": "Provider not found"}, status=500
        )

    result = provider.confirm_payment(transaction_id=payment_record.transaction_id)

    payment_record.status = result.status.value
    payment_record.provider_data = result.provider_data
    if result.status == PaymentStatus.COMPLETED:
        payment_record.completed_at = timezone.now()
        payment_record.save()
        _finalize_submission(submission)
        return JsonResponse(
            {
                "success": True,
                "redirect_url": _get_success_redirect(submission),
            }
        )
    else:
        payment_record.error_message = result.error_message
        payment_record.save()
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
    payment_record = (
        submission.payment_records.filter(
            status__in=["pending", "processing", "requires_action"]
        )
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

    payment_record.status = result.status.value
    payment_record.provider_data = result.provider_data
    if result.status == PaymentStatus.COMPLETED:
        payment_record.completed_at = timezone.now()
        payment_record.save()
        _finalize_submission(submission)
        return redirect(_get_success_redirect(submission))
    else:
        payment_record.error_message = result.error_message
        payment_record.save()
        return render(
            request,
            "django_forms_workflows/payment_error.html",
            {
                "error": result.error_message or "Payment was not completed.",
                "submission": submission,
            },
        )


def payment_cancel(request, submission_id):
    """User cancelled payment on external portal."""
    from django.contrib import messages

    submission = get_object_or_404(FormSubmission, id=submission_id)
    payment_record = (
        submission.payment_records.filter(status="pending")
        .order_by("-created_at")
        .first()
    )

    if payment_record:
        payment_record.status = "cancelled"
        payment_record.save()

    submission.status = "draft"
    submission.save()

    messages.warning(
        request, "Payment was cancelled. Your form has been saved as a draft."
    )
    return redirect("forms_workflows:my_submissions")


@csrf_exempt
@require_POST
def payment_webhook(request, provider_name):
    """
    Generic webhook endpoint: /forms/payments/webhook/<provider_name>/

    Delegates to the provider's handle_webhook() method.
    """
    provider = get_provider(provider_name)
    if not provider:
        return HttpResponse(status=404)

    try:
        result = provider.handle_webhook(request)
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

        payment_record.status = result.status.value
        payment_record.provider_data = result.provider_data
        if result.status == PaymentStatus.COMPLETED:
            payment_record.completed_at = timezone.now()
            _finalize_submission(payment_record.submission)
        payment_record.save()

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
