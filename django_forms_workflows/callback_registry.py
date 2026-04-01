"""
Callback handler registry for Django Forms Workflows.

Provides a central registry for custom post-submission action handlers.
Handlers can be registered programmatically or via the
``FORMS_WORKFLOWS_CALLBACKS`` Django setting.

Usage in settings.py::

    FORMS_WORKFLOWS_CALLBACKS = {
        "id_photo_copy": "workflows.handlers.id_photo_handler.IDPhotoApprovalHandler",
        "sync_to_erp": "myapp.handlers.ERPSyncHandler",
    }

Handlers are resolved lazily on first use and cached for the process lifetime.
Both ``BaseActionHandler`` subclasses and plain ``(action, submission) -> dict``
callables are supported — the executor wraps callables automatically.

Programmatic registration (e.g. in ``AppConfig.ready()``)::

    from django_forms_workflows.callback_registry import register_handler

    register_handler("my_handler", "myapp.handlers.MyHandler")
    # or pass the class/function directly:
    register_handler("my_handler", MyHandler)
"""

import logging
from importlib import import_module

logger = logging.getLogger(__name__)

# ── internal state ────────────────────────────────────────────────────────────
_registry: dict[str, object] = {}  # name -> class/function or dotted path str
_resolved: dict[str, object] = {}  # name -> resolved class/function (cache)


# ── public API ────────────────────────────────────────────────────────────────


def register_handler(name: str, handler) -> None:
    """
    Register a handler under *name*.

    *handler* can be:
    - A dotted Python path string (resolved lazily on first lookup).
    - A ``BaseActionHandler`` subclass.
    - A callable ``(action, submission) -> dict``.

    Re-registering a name silently overwrites the previous entry.
    """
    _registry[name] = handler
    _resolved.pop(name, None)  # bust cache on re-register
    logger.debug("Registered callback handler %r", name)


def get_handler(name: str):
    """
    Return the resolved handler for *name*, or ``None`` if not registered.

    The first call for a given name resolves a dotted-path string to the
    actual class/function and caches the result.
    """
    if name in _resolved:
        return _resolved[name]

    raw = _registry.get(name)
    if raw is None:
        return None

    resolved = _resolve(raw, name)
    if resolved is not None:
        _resolved[name] = resolved
    return resolved


def get_registered_names() -> list[str]:
    """Return a sorted list of all registered handler names."""
    return sorted(_registry)


def is_registered(name: str) -> bool:
    """Return ``True`` if *name* has been registered."""
    return name in _registry


def clear() -> None:
    """Remove all registrations (useful in tests)."""
    _registry.clear()
    _resolved.clear()


def load_from_settings() -> None:
    """
    Bulk-register handlers from ``settings.FORMS_WORKFLOWS_CALLBACKS``.

    Called automatically from ``DjangoFormsWorkflowsConfig.ready()``.
    Safe to call multiple times — existing entries are overwritten.
    """
    from django.conf import settings

    callbacks = getattr(settings, "FORMS_WORKFLOWS_CALLBACKS", None)
    if not callbacks:
        return

    if not isinstance(callbacks, dict):
        logger.error(
            "FORMS_WORKFLOWS_CALLBACKS must be a dict mapping names to "
            "dotted Python paths; got %s",
            type(callbacks).__name__,
        )
        return

    for name, path in callbacks.items():
        register_handler(name, path)

    logger.info(
        "Loaded %d callback handler(s) from FORMS_WORKFLOWS_CALLBACKS: %s",
        len(callbacks),
        ", ".join(sorted(callbacks)),
    )


# ── internal helpers ──────────────────────────────────────────────────────────


def _resolve(raw, name: str):
    """Resolve *raw* (string or object) to a class/function."""
    if isinstance(raw, str):
        try:
            module_path, attr_name = raw.rsplit(".", 1)
            module = import_module(module_path)
            return getattr(module, attr_name)
        except Exception as exc:
            logger.error(
                "Could not resolve callback handler %r (%s): %s",
                name,
                raw,
                exc,
            )
            return None
    # Already a class or callable — use as-is.
    return raw
