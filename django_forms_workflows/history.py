"""
Lightweight change-history tracking for configuration models.

Call ``track_model_changes(ModelClass)`` for each model you want to track.
This wires up ``pre_save`` / ``post_save`` / ``post_delete`` signals that
record field-level diffs into :class:`~django_forms_workflows.models.ChangeHistory`.

The current user is obtained from a thread-local that the included
``ChangeHistoryMiddleware`` populates on each request.
"""

import logging
import threading

from django.db.models.signals import post_delete, post_save, pre_save

logger = logging.getLogger(__name__)

# ── Thread-local for current user ───────────────────────────────────────

_thread_locals = threading.local()


def get_current_user():
    """Return the user stored on this thread, or *None*."""
    return getattr(_thread_locals, "user", None)


def set_current_user(user):
    """Store *user* on the current thread (called by middleware)."""
    _thread_locals.user = user


class ChangeHistoryMiddleware:
    """
    Django middleware that stores ``request.user`` in a thread-local so
    signal handlers can attribute changes to the right user.

    Add ``'django_forms_workflows.history.ChangeHistoryMiddleware'``
    to ``MIDDLEWARE`` **after** ``AuthenticationMiddleware``.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user and getattr(user, "is_authenticated", False):
            set_current_user(user)
        else:
            set_current_user(None)
        try:
            return self.get_response(request)
        finally:
            set_current_user(None)


# ── Field diffing helpers ───────────────────────────────────────────────

# Fields that should never show up in diffs (noisy / internal)
_SKIP_FIELDS = frozenset({"id", "pk", "created_at", "updated_at", "change_history"})


def _snapshot(instance):
    """Return a dict of {field_name: value} for concrete DB fields."""
    data = {}
    for field in instance._meta.concrete_fields:
        if field.name in _SKIP_FIELDS:
            continue
        value = field.value_from_object(instance)
        # Convert non-JSON-serialisable types to str
        if hasattr(value, "isoformat"):
            value = value.isoformat()
        elif isinstance(value, bytes):
            value = value.decode("utf-8", errors="replace")
        data[field.name] = value
    return data


def _diff(old, new):
    """Return {field: {old, new}} for fields that differ between two snapshots."""
    changes = {}
    all_keys = set(old.keys()) | set(new.keys())
    for key in sorted(all_keys):
        old_v = old.get(key)
        new_v = new.get(key)
        if old_v != new_v:
            changes[key] = {"old": old_v, "new": new_v}
    return changes


# ── Signal handlers ─────────────────────────────────────────────────────


def _pre_save_handler(sender, instance, **kwargs):
    """Snapshot the *current* DB state before the save overwrites it."""
    # Allow callers to opt out (e.g. auto-save, bulk imports)
    if getattr(instance, "_skip_change_history", False):
        return
    if not instance.pk:
        return  # new object — nothing to diff against
    try:
        old = sender.objects.get(pk=instance.pk)
        instance._change_history_old_snapshot = _snapshot(old)
    except sender.DoesNotExist:
        pass  # race condition or bulk-create — treat as new


def _post_save_handler(sender, instance, created, **kwargs):
    """Compare old → new and log any changes."""
    # Allow callers to opt out (e.g. auto-save, bulk imports)
    if getattr(instance, "_skip_change_history", False):
        return

    from .models import ChangeHistory

    user = get_current_user()
    if created:
        ChangeHistory.log_create(instance, user=user)
        return

    old_snap = getattr(instance, "_change_history_old_snapshot", None)
    if old_snap is None:
        return
    new_snap = _snapshot(instance)
    changes = _diff(old_snap, new_snap)
    if changes:
        ChangeHistory.log_update(instance, changes, user=user)
    # Clean up
    del instance._change_history_old_snapshot


def _post_delete_handler(sender, instance, **kwargs):
    from .models import ChangeHistory

    user = get_current_user()
    ChangeHistory.log_delete(instance, user=user)


# ── Public registration API ────────────────────────────────────────────

_tracked_models = set()


def track_model_changes(model_class):
    """
    Register *model_class* for automatic change-history tracking.

    Safe to call multiple times for the same model.
    """
    if model_class in _tracked_models:
        return
    _tracked_models.add(model_class)

    pre_save.connect(_pre_save_handler, sender=model_class, weak=False)
    post_save.connect(_post_save_handler, sender=model_class, weak=False)
    post_delete.connect(_post_delete_handler, sender=model_class, weak=False)

    logger.debug("Change-history tracking enabled for %s", model_class.__name__)
