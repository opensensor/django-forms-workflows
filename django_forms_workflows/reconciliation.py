"""Delivery reconciliation against the Google Workspace Gmail log (BigQuery).

Why this exists
---------------
The Gmail API ``messages().send()`` call returns success synchronously even when
the message is subsequently dropped and never relayed. ``NotificationLog.status``
therefore records only "the send call did not raise", not "the recipient got it".
The single authoritative source of *delivery* truth for Gmail-sent mail is the
Workspace Gmail log, exported to BigQuery, which records the real relay outcome
per message (``gmail.event_info.success``, SMTP reply codes, etc.).

This module joins our ``NotificationLog`` rows to that log on the RFC 2822
Message-ID we stamp at send time (``NotificationLog.rfc2822_message_id`` ↔
``gmail.message_info.rfc2822_message_id``), classifies each send's real fate,
and then:

  * marks confirmed deliveries ``delivery_state='delivered'``;
  * auto-retries soft failures and silent drops (re-dispatching
    ``send_notification_rules`` — the same idempotent path the admin "Retry"
    action uses) up to a per-recipient attempt cap;
  * alerts on hard bounces (no retry) and on retry exhaustion.

It is invoked on a schedule by the ``reconcile_email_delivery`` Celery task.

Configuration (``settings.EMAIL_RECONCILIATION``)::

    EMAIL_RECONCILIATION = {
        "enabled": True,
        "bigquery_project": "your-gcp-project",
        "bigquery_table": "your-gcp-project.workspace_logs.activity",
        "service_account_json": "/path/to/key.json",   # or:
        "service_account_base64": "<base64 json>",
        "grace_minutes": 45,      # don't judge a send before mail can settle
        "lookback_hours": 72,     # how far back to reconcile
        "max_attempts": 3,        # total sends per (submission, event, recipient)
        "batch_limit": 1000,      # max log rows examined per run
        "alert_recipients": ["alerts@example.com"],
    }
"""

from __future__ import annotations

import base64
import json
import logging
from collections import defaultdict
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils import timezone

from .models import NotificationLog

logger = logging.getLogger(__name__)

# Generic fallbacks. Every deployment-specific value (GCP project, BigQuery
# table, service-account credentials, alert recipients) MUST be supplied by the
# consuming project via settings.EMAIL_RECONCILIATION — nothing institution-
# specific belongs in this reusable package.
_DEFAULTS = {
    "enabled": False,
    "bigquery_project": "",
    "bigquery_table": "",
    "service_account_json": "",
    "service_account_base64": "",
    "grace_minutes": 45,
    "lookback_hours": 72,
    "max_attempts": 3,
    "batch_limit": 1000,
    "alert_recipients": [],
}

_BQ_READONLY_SCOPE = "https://www.googleapis.com/auth/bigquery.readonly"


def _config() -> dict:
    cfg = dict(_DEFAULTS)
    cfg.update(getattr(settings, "EMAIL_RECONCILIATION", {}) or {})
    return cfg


def _get_bq_client(cfg: dict):
    """Build a BigQuery client authenticated with the configured service account.

    Imports are local so the package still imports where google-cloud-bigquery
    is not installed (e.g. the web pods, which never reconcile).
    """
    from google.cloud import bigquery
    from google.oauth2 import service_account

    project = cfg["bigquery_project"]
    if cfg.get("service_account_json"):
        creds = service_account.Credentials.from_service_account_file(
            cfg["service_account_json"], scopes=[_BQ_READONLY_SCOPE]
        )
    elif cfg.get("service_account_base64"):
        info = json.loads(base64.b64decode(cfg["service_account_base64"]).decode("utf-8"))
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=[_BQ_READONLY_SCOPE]
        )
    else:
        creds = None  # fall back to Application Default Credentials
    return bigquery.Client(project=project, credentials=creds)


def _query_delivery_outcomes(cfg: dict, message_ids: list[str], since_usec: int):
    """Query the Workspace Gmail log for the given Message-IDs.

    Returns ``(outcomes, seen_msgids)`` where ``outcomes`` is keyed by
    ``(msgid, recipient_lower)`` → dict(any_success, max_smtp_code, reason) and
    ``seen_msgids`` is the set of Message-IDs that appeared in the log at all
    (so a recipient absent from a *seen* message is distinguishable from a
    message that never relayed at all).
    """
    from google.cloud import bigquery

    table = cfg["bigquery_table"]
    sql = f"""
        SELECT
          g.message_info.rfc2822_message_id AS msgid,
          LOWER(dest.address) AS recipient,
          LOGICAL_OR(g.event_info.success) AS any_success,
          MAX(g.message_info.connection_info.smtp_reply_code) AS max_smtp_code,
          -- smtp_response_reason is an INT64 enum in this schema, not text.
          STRING_AGG(
            DISTINCT CAST(
              NULLIF(g.message_info.connection_info.smtp_response_reason, 0) AS STRING
            )
          ) AS smtp_reasons
        FROM `{table}` t,
          UNNEST([t.gmail]) g,
          UNNEST(g.message_info.destination) dest
        WHERE t.record_type = 'gmail'
          AND t.event_name = 'delivery'
          AND t.time_usec >= @since_usec
          AND g.message_info.rfc2822_message_id IN UNNEST(@msgids)
        GROUP BY msgid, recipient
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("since_usec", "INT64", since_usec),
            bigquery.ArrayQueryParameter("msgids", "STRING", message_ids),
        ]
    )
    outcomes: dict[tuple[str, str], dict] = {}
    seen_msgids: set[str] = set()
    for row in _get_bq_client(cfg).query(sql, job_config=job_config).result():
        seen_msgids.add(row["msgid"])
        outcomes[(row["msgid"], (row["recipient"] or "").lower())] = {
            "any_success": bool(row["any_success"]),
            "max_smtp_code": row["max_smtp_code"],
            "reason": row["smtp_reasons"] or "",
        }
    return outcomes, seen_msgids


def _classify(msgid: str, recipient: str, outcomes: dict, seen_msgids: set):
    """Return ``(state, detail)`` for one send.

    state ∈ {"delivered", "bounced", "soft"}:
      * delivered — log shows a successful relay to this recipient
      * bounced   — permanent failure (SMTP 5xx); do NOT auto-retry
      * soft      — transient failure, or no relay record at all (silent drop)
    """
    rec = outcomes.get((msgid, recipient))
    if rec is None:
        if msgid in seen_msgids:
            return "soft", "message relayed but no record for this recipient"
        return "soft", "no delivery record in Workspace log (possible silent drop)"

    code = rec["max_smtp_code"]
    reason = rec["reason"]
    # A confirmed successful relay wins over a stale high SMTP code: the log
    # records every hop, so a recipient can show a transient 451 deferral on
    # one event and a 250 success on a later one (any_success=True). Only treat
    # it as a bounce when there is NO success and the code is permanent (5xx).
    if rec["any_success"]:
        return "delivered", f"relayed{(' (reason ' + reason + ')') if reason else ''}"
    if code is not None and code >= 500:
        return "bounced", f"smtp {code}{(' reason ' + reason) if reason else ''}"
    if code is not None and 400 <= code < 500:
        return "soft", f"smtp {code} transient{(' reason ' + reason) if reason else ''}"
    return "soft", f"not relayed{(' (reason ' + reason + ')') if reason else ''}"


def run_reconciliation() -> str:
    """Reconcile recently-sent notifications against the Workspace Gmail log.

    Safe to run repeatedly: rows advance from ``unconfirmed`` to a terminal
    delivery_state, so each run only does work for the latest grace window plus
    anything still in flight. Returns a human-readable summary string.
    """
    cfg = _config()
    if not cfg["enabled"]:
        return "email reconciliation disabled (EMAIL_RECONCILIATION['enabled'] is False)"
    if not cfg["bigquery_project"] or not cfg["bigquery_table"]:
        logger.warning(
            "email reconciliation enabled but bigquery_project/table not "
            "configured; nothing to do"
        )
        return "email reconciliation not configured (missing bigquery_project/table)"

    now = timezone.now()
    grace_cutoff = now - timedelta(minutes=cfg["grace_minutes"])
    lookback_cutoff = now - timedelta(hours=cfg["lookback_hours"])

    candidates = list(
        NotificationLog.objects.filter(
            status="sent",
            delivery_state="unconfirmed",
            created_at__lt=grace_cutoff,
            created_at__gte=lookback_cutoff,
        )
        .exclude(rfc2822_message_id="")
        .order_by("created_at")[: cfg["batch_limit"]]
    )
    if not candidates:
        return "reconciliation: no unconfirmed sends in window"

    msgids = sorted({c.rfc2822_message_id for c in candidates})
    # Give the log query a little extra lookback margin (mail can be logged a
    # few minutes after our created_at) — 6h cushion before the oldest row.
    since_usec = int((lookback_cutoff - timedelta(hours=6)).timestamp() * 1_000_000)

    try:
        outcomes, seen_msgids = _query_delivery_outcomes(cfg, msgids, since_usec)
    except Exception:
        logger.exception("reconciliation: BigQuery query failed; aborting run")
        return "reconciliation: BigQuery query failed (see logs)"

    counters: dict[str, int] = defaultdict(int)
    retries: dict[tuple[int, str], set[str]] = {}
    alerts: list[dict] = []
    updated: list[NotificationLog] = []

    for row in candidates:
        recipient = (row.recipient_email or "").lower()
        state, detail = _classify(row.rfc2822_message_id, recipient, outcomes, seen_msgids)
        row.delivery_checked_at = now
        row.delivery_detail = detail[:500]

        if state == "delivered":
            row.delivery_state = "delivered"
            counters["delivered"] += 1
        elif state == "bounced":
            row.delivery_state = "bounced"
            counters["bounced"] += 1
            alerts.append(_alert_entry(row, "hard bounce", detail))
        else:  # soft — retry if we can and the cap allows
            attempts = (
                NotificationLog.objects.filter(
                    submission_id=row.submission_id,
                    notification_type=row.notification_type,
                    recipient_email=row.recipient_email,
                ).count()
                if row.submission_id
                else None
            )
            can_retry = (
                row.submission_id is not None
                and row.notification_type
                and attempts is not None
                and attempts < cfg["max_attempts"]
            )
            if can_retry:
                row.delivery_state = "retried"
                retries.setdefault(
                    (row.submission_id, row.notification_type), set()
                ).add(row.recipient_email)
                counters["retried"] += 1
            else:
                row.delivery_state = "exhausted"
                counters["exhausted"] += 1
                why = (
                    "no submission/event to retry"
                    if not (row.submission_id and row.notification_type)
                    else f"retry cap reached ({attempts}/{cfg['max_attempts']})"
                )
                alerts.append(_alert_entry(row, f"undelivered — {why}", detail))
        updated.append(row)

    if updated:
        NotificationLog.objects.bulk_update(
            updated, ["delivery_state", "delivery_checked_at", "delivery_detail"]
        )

    # Dispatch retries once per (submission, event) — send_notification_rules
    # re-resolves recipients and its idempotency guard now lets the rows we
    # marked 'retried' through while still skipping confirmed/in-flight ones.
    dispatched = 0
    if retries:
        from .tasks import send_notification_rules

        for (submission_id, event) in retries:
            try:
                send_notification_rules.delay(submission_id, event)
            except Exception:
                try:
                    send_notification_rules(submission_id, event)
                except Exception:
                    logger.exception(
                        "reconciliation: retry dispatch failed for submission %s "
                        "event %s",
                        submission_id,
                        event,
                    )
                    continue
            dispatched += 1

    if alerts:
        _send_alert(cfg, alerts, dict(counters))

    summary = (
        f"reconciliation: examined {len(candidates)} send(s) — "
        f"delivered={counters['delivered']}, retried={counters['retried']} "
        f"({dispatched} dispatch task(s)), bounced={counters['bounced']}, "
        f"exhausted={counters['exhausted']}"
    )
    logger.info(summary)
    return summary


def _alert_entry(row: NotificationLog, kind: str, detail: str) -> dict:
    return {
        "kind": kind,
        "recipient": row.recipient_email,
        "subject": row.subject,
        "notification_type": row.notification_type,
        "submission_id": row.submission_id,
        "created_at": row.created_at,
        "detail": detail,
    }


def _send_alert(cfg: dict, alerts: list[dict], counters: dict) -> None:
    """Email the configured staff list about undelivered/bounced notifications.

    Sent directly (no NotificationLog row) so the alert itself is never
    reconciled or retried into a loop. Failures are swallowed — the summary is
    also logged at WARNING for the k8s log trail.
    """
    recipients = [e for e in cfg.get("alert_recipients", []) if e]
    if not recipients:
        return

    lines = [
        "Email delivery reconciliation found notifications that were NOT delivered.",
        "",
        f"Hard bounces (no retry): {counters.get('bounced', 0)}",
        f"Undelivered, retries exhausted: {counters.get('exhausted', 0)}",
        f"Auto-retried this run: {counters.get('retried', 0)}",
        f"Confirmed delivered this run: {counters.get('delivered', 0)}",
        "",
        "Affected messages:",
    ]
    for a in alerts[:50]:
        when = a["created_at"].strftime("%Y-%m-%d %H:%M") if a["created_at"] else "?"
        lines.append(
            f"  • [{a['kind']}] {a['recipient']} — \"{a['subject']}\" "
            f"(type={a['notification_type']}, submission={a['submission_id']}, "
            f"sent {when}) :: {a['detail']}"
        )
    if len(alerts) > 50:
        lines.append(f"  … and {len(alerts) - 50} more.")
    body = "\n".join(lines)

    from_addr = getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@localhost")
    subject = (
        f"[forms] Email delivery alert: "
        f"{counters.get('bounced', 0) + counters.get('exhausted', 0)} undelivered"
    )
    try:
        EmailMultiAlternatives(
            subject=subject, body=body, from_email=from_addr, to=recipients
        ).send(fail_silently=True)
    except Exception:
        logger.exception("reconciliation: failed to send alert email")
    logger.warning("reconciliation alert:\n%s", body)
