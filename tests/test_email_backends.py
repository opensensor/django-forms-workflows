"""Tests for django_forms_workflows.email_backends.gmail_api.

Focus: the retry-with-exponential-backoff loop wrapped around the Gmail
``messages.send`` call. Catches ``HttpError`` 429 and 403-with-rate-limit
reasons, sleeps with jittered exponential backoff, and re-fires up to a
small cap. Non-retryable errors (auth failures, dailyLimitExceeded,
non-HttpError exceptions) propagate immediately.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from django.core.mail import EmailMultiAlternatives

from django_forms_workflows.email_backends.gmail_api import (
    GmailAPIBackend,
    _is_retryable_gmail_error,
)

# googleapiclient is an optional dep (only required when GMAIL_API is wired
# up in production settings). Skip these tests in environments where it
# isn't installed rather than failing collection.
googleapiclient = pytest.importorskip("googleapiclient")


def _http_error(status: int, reason: str | None = None):
    """Construct a real googleapiclient HttpError mimicking a Gmail response."""
    from googleapiclient.errors import HttpError

    resp = MagicMock(status=status, reason="rate")
    if reason:
        body = json.dumps(
            {
                "error": {
                    "code": status,
                    "message": reason,
                    "errors": [{"reason": reason}],
                }
            }
        ).encode("utf-8")
    else:
        body = json.dumps({"error": {"code": status, "message": "blah"}}).encode(
            "utf-8"
        )
    return HttpError(resp, body)


class TestIsRetryableGmailError:
    """Unit cover the predicate so the retry loop's policy is explicit."""

    def test_429_is_retryable(self):
        assert _is_retryable_gmail_error(_http_error(429)) is True

    def test_403_rate_limit_exceeded_is_retryable(self):
        assert _is_retryable_gmail_error(_http_error(403, "rateLimitExceeded")) is True

    def test_403_user_rate_limit_exceeded_is_retryable(self):
        assert (
            _is_retryable_gmail_error(_http_error(403, "userRateLimitExceeded")) is True
        )

    def test_403_backend_error_is_retryable(self):
        assert _is_retryable_gmail_error(_http_error(403, "backendError")) is True

    def test_403_daily_limit_exceeded_is_not_retryable(self):
        """Daily cap doesn't reset until midnight Pacific — retrying within a
        Celery task is pointless."""
        assert (
            _is_retryable_gmail_error(_http_error(403, "dailyLimitExceeded")) is False
        )

    def test_403_permission_denied_is_not_retryable(self):
        assert _is_retryable_gmail_error(_http_error(403, "forbidden")) is False

    def test_404_is_not_retryable(self):
        assert _is_retryable_gmail_error(_http_error(404, "notFound")) is False

    def test_non_httperror_is_not_retryable(self):
        assert _is_retryable_gmail_error(ValueError("oops")) is False


class TestGmailBackendRetry:
    """Functional cover the retry loop in ``_send``."""

    def _make_backend_with_send(self, send_side_effects):
        """Return a backend whose service.send().execute() yields the supplied
        side-effects across successive calls."""
        backend = GmailAPIBackend()
        send_call = MagicMock()
        send_call.execute.side_effect = send_side_effects
        # users().messages().send(...) chain
        chain = MagicMock()
        chain.users.return_value.messages.return_value.send.return_value = send_call
        backend._service = chain
        return backend, send_call

    def _msg(self):
        return EmailMultiAlternatives(
            subject="hi", body="b", from_email="a@x", to=["b@x"]
        )

    def test_succeeds_first_try_no_retry(self):
        backend, send = self._make_backend_with_send([None])
        backend._send(self._msg())
        assert send.execute.call_count == 1

    def test_retries_then_succeeds_on_429(self):
        backend, send = self._make_backend_with_send(
            [_http_error(429), _http_error(429), None]
        )
        with patch("django_forms_workflows.email_backends.gmail_api.time.sleep"):
            backend._send(self._msg())
        assert send.execute.call_count == 3

    def test_retries_then_succeeds_on_403_rate_limit(self):
        backend, send = self._make_backend_with_send(
            [_http_error(403, "rateLimitExceeded"), None]
        )
        with patch("django_forms_workflows.email_backends.gmail_api.time.sleep"):
            backend._send(self._msg())
        assert send.execute.call_count == 2

    def test_gives_up_after_max_retries(self):
        from django_forms_workflows.email_backends.gmail_api import _MAX_RETRIES

        # _MAX_RETRIES + 1 attempts fail (initial + retries) then exception
        # propagates so the caller can write a NotificationLog 'failed' row.
        backend, send = self._make_backend_with_send(
            [_http_error(429)] * (_MAX_RETRIES + 1)
        )
        from googleapiclient.errors import HttpError

        with patch("django_forms_workflows.email_backends.gmail_api.time.sleep"):
            with pytest.raises(HttpError):
                backend._send(self._msg())
        assert send.execute.call_count == _MAX_RETRIES + 1

    def test_non_retryable_propagates_immediately(self):
        """A 403 with non-rate-limit reason (e.g. dailyLimitExceeded) is not
        retried — it propagates on the first try."""
        from googleapiclient.errors import HttpError

        backend, send = self._make_backend_with_send(
            [_http_error(403, "dailyLimitExceeded")]
        )
        with pytest.raises(HttpError):
            backend._send(self._msg())
        assert send.execute.call_count == 1

    def test_backoff_grows_exponentially(self):
        """Each retry sleeps for roughly 2x the previous (with jitter)."""
        from django_forms_workflows.email_backends.gmail_api import (
            _BACKOFF_BASE_SECONDS,
            _BACKOFF_CAP_SECONDS,
        )

        backend, send = self._make_backend_with_send(
            [_http_error(429), _http_error(429), _http_error(429), None]
        )
        sleeps: list[float] = []
        with patch(
            "django_forms_workflows.email_backends.gmail_api.time.sleep",
            side_effect=lambda s: sleeps.append(s),
        ):
            backend._send(self._msg())

        assert len(sleeps) == 3
        # Bounds: base * 2^attempt, with jitter in [0.75, 1.25]
        for attempt, slept in enumerate(sleeps):
            ideal = min(_BACKOFF_BASE_SECONDS * (2**attempt), _BACKOFF_CAP_SECONDS)
            lo, hi = ideal * 0.75 - 1e-6, ideal * 1.25 + 1e-6
            assert lo <= slept <= hi, (
                f"sleep #{attempt} = {slept!r}, expected within [{lo}, {hi}]"
            )
