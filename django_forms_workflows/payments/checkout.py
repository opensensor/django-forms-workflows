"""
Checkout authorization for the payment flow.

Payment endpoints act on a :class:`~django_forms_workflows.models.FormSubmission`
that is in ``pending_payment``.  Access is governed by exactly one policy:

* **Owned submissions** — only the authenticated submitter may act on them.
  A numeric submission or payment-record ID alone grants nothing.
* **Anonymous (public-form) submissions** — the browser that just posted the
  public form is issued a *checkout credential*: an unguessable token stored
  in its session and bound to the submission ID, valid for a short time
  (``FORMS_WORKFLOWS_PAYMENT_CHECKOUT_TTL`` seconds, default one hour).

The credential is granted by the submit views when a submission enters
``pending_payment`` and is revoked when the checkout is cancelled.  It is
never exposed in a URL.  Callers that fail the policy receive a
non-disclosing 404, identical to a nonexistent submission.
"""

from __future__ import annotations

import secrets
import time

from django.conf import settings

SESSION_KEY = "payment_checkouts"
DEFAULT_CHECKOUT_TTL_SECONDS = 3600  # 1 hour


def _checkout_ttl() -> int:
    return int(
        getattr(
            settings,
            "FORMS_WORKFLOWS_PAYMENT_CHECKOUT_TTL",
            DEFAULT_CHECKOUT_TTL_SECONDS,
        )
    )


def grant_checkout_access(request, submission) -> None:
    """Bind a short-lived checkout credential for *submission* to the session.

    Called by the submit views right after a submission enters
    ``pending_payment`` so the same browser session can complete (confirm,
    return, or cancel) the checkout that belongs to it.
    """
    checkouts = dict(request.session.get(SESSION_KEY, {}))
    checkouts[str(submission.id)] = {
        "token": secrets.token_urlsafe(32),
        "exp": time.time() + _checkout_ttl(),
    }
    request.session[SESSION_KEY] = checkouts
    request.session.modified = True


def revoke_checkout_access(request, submission) -> None:
    """Drop any checkout credential for *submission* from the session."""
    checkouts = dict(request.session.get(SESSION_KEY, {}))
    if checkouts.pop(str(submission.id), None) is not None:
        request.session[SESSION_KEY] = checkouts
        request.session.modified = True


def has_checkout_access(request, submission) -> bool:
    """The single payment access policy used by every payment endpoint.

    * Authenticated submitter: may act only on their own submission.
    * Anonymous submission (``submitter`` is null): the caller's session
      must hold an unexpired checkout credential issued by
      :func:`grant_checkout_access`.
    """
    if submission.submitter_id is not None:
        return (
            request.user.is_authenticated and request.user.pk == submission.submitter_id
        )

    entry = request.session.get(SESSION_KEY, {}).get(str(submission.id))
    if not entry:
        return False
    try:
        return float(entry.get("exp", 0)) > time.time()
    except (TypeError, ValueError):
        return False
