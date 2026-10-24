"""Recover validated uploads from the submitting session, never from POST metadata."""

import time
from functools import wraps

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import HttpResponseBadRequest

from .forms import MaxFileSizeValidator, _build_file_validators

FILE_TYPES = ("file", "multifile", "spreadsheet")


def _key(request, form_definition):
    return f"{request.user.pk or 'anonymous'}:{form_definition.pk}"


def reject_invalid_uploads(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        try:
            return view(*args, **kwargs)
        except ValidationError:
            return HttpResponseBadRequest(
                "Invalid file upload. Check the file type and size."
            )

    return wrapped


def prepare_uploads(request, form_definition):
    """Validate every new file before writing any of them to storage."""
    from .views import _serialize_single_file

    now = time.time()
    entries = {
        k: v
        for k, v in request.session.get("dfw_uploads", {}).items()
        if v["expires"] > now
    }
    key = _key(request, form_definition)
    metadata = dict(entries.get(key, {}).get("files", {}))
    fields = {
        f.field_name: f
        for f in form_definition.fields.filter(
            field_type__in=FILE_TYPES, workflow_stage__isnull=True
        )
    }
    validated = {}
    for name in request.FILES:
        if name not in fields:
            raise ValidationError("Unknown upload field")
        field = fields[name]
        validators = _build_file_validators(field)
        validators.append(
            MaxFileSizeValidator(getattr(settings, "FORMS_WORKFLOWS_MAX_UPLOAD_MB", 32))
        )
        cleaner = forms.FileField(validators=validators)
        files = request.FILES.getlist(name)
        if field.field_type != "multifile" and len(files) != 1:
            raise ValidationError("Only one file is allowed")
        validated[name] = [cleaner.clean(file) for file in files]
    for name, files in validated.items():
        values = [_serialize_single_file(file, name, "pending") for file in files]
        if any(value.get("upload_failed") for value in values):
            raise ValidationError("Upload storage unavailable")
        metadata[name] = values if fields[name].field_type == "multifile" else values[0]
    # Keep only fields still present in this form definition.
    metadata = {name: value for name, value in metadata.items() if name in fields}
    if metadata:
        entries[key] = {"expires": now + 3600, "files": metadata}
    request.session["dfw_uploads"] = dict(list(entries.items())[-20:])
    return metadata


def clear_uploads(request, form_definition):
    entries = dict(request.session.get("dfw_uploads", {}))
    entries.pop(_key(request, form_definition), None)
    request.session["dfw_uploads"] = entries


def draft_data(form_definition, raw, previous=None):
    """Accept scalar answers only; retain upload metadata from the owned draft."""
    fields = list(form_definition.fields.filter(workflow_stage__isnull=True))
    names = {f.field_name for f in fields if f.field_type not in FILE_TYPES}
    for field in fields:
        if field.field_type == "matrix" and isinstance(field.choices, dict):
            names.update(
                f"{field.field_name}__{row}" for row in field.choices.get("rows", [])
            )
    result = {}
    for name, value in raw.items():
        if name not in names or name == "_stashed_files":
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            result[name] = value
        elif isinstance(value, list) and all(isinstance(v, str) for v in value):
            result[name] = value
    for field in fields:
        if field.field_type in FILE_TYPES and field.field_name in (previous or {}):
            result[field.field_name] = previous[field.field_name]
    return result
