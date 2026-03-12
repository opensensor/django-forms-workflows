"""
Data migration: convert legacy ``FormField.prefill_source`` string values
to ``PrefillSource`` records and set the ``prefill_source_config`` FK.

For each unique ``prefill_source`` string that has no corresponding FK:
  1. Get-or-create a ``PrefillSource`` record matching the string pattern.
  2. Set ``prefill_source_config`` on the field.
  3. Clear the legacy ``prefill_source`` string.

Reverse migration restores the string from the FK's ``get_source_identifier()``.
"""

from django.db import migrations


# ── Mapping helpers ──────────────────────────────────────────────────────

_SOURCE_MAP = {
    # user.* pattern
    "user.email": {
        "name": "Current User - Email",
        "source_type": "user",
        "source_key": "user.email",
    },
    "user.first_name": {
        "name": "Current User - First Name",
        "source_type": "user",
        "source_key": "user.first_name",
    },
    "user.last_name": {
        "name": "Current User - Last Name",
        "source_type": "user",
        "source_key": "user.last_name",
    },
    "user.full_name": {
        "name": "Current User - Full Name",
        "source_type": "user",
        "source_key": "user.full_name",
    },
    "user.username": {
        "name": "Current User - Username",
        "source_type": "user",
        "source_key": "user.username",
    },
    # system values
    "current_date": {
        "name": "Current Date",
        "source_type": "system",
        "source_key": "current_date",
    },
    "current_datetime": {
        "name": "Current Date/Time",
        "source_type": "system",
        "source_key": "current_datetime",
    },
}


def _parse_ldap_key(key):
    """Parse 'ldap.xxx' → PrefillSource kwargs."""
    attr = key.replace("ldap.", "", 1)
    return {
        "name": f"LDAP - {attr}",
        "source_type": "ldap",
        "source_key": key,
        "ldap_attribute": attr,
    }


def forwards(apps, schema_editor):
    FormField = apps.get_model("django_forms_workflows", "FormField")
    PrefillSource = apps.get_model("django_forms_workflows", "PrefillSource")

    fields = FormField.objects.filter(
        prefill_source__isnull=False,
        prefill_source_config__isnull=True,
    ).exclude(prefill_source="")

    cache = {}  # prefill_source string → PrefillSource instance

    for field in fields.iterator():
        key = field.prefill_source.strip()
        if not key:
            continue

        if key not in cache:
            if key in _SOURCE_MAP:
                defaults = dict(_SOURCE_MAP[key])
            elif key.startswith("ldap."):
                defaults = _parse_ldap_key(key)
            elif key.startswith("user."):
                attr = key.replace("user.", "", 1)
                defaults = {
                    "name": f"Current User - {attr.replace('_', ' ').title()}",
                    "source_type": "user",
                    "source_key": key,
                }
            else:
                # Unknown pattern — create a generic source
                defaults = {
                    "name": f"Legacy: {key}",
                    "source_type": "custom",
                    "source_key": key,
                }

            source_key = defaults.pop("source_key")
            ps, _ = PrefillSource.objects.get_or_create(
                source_key=source_key,
                defaults={**defaults, "source_key": source_key},
            )
            cache[key] = ps

        field.prefill_source_config = cache[key]
        field.prefill_source = ""
        field.save(update_fields=["prefill_source_config", "prefill_source"])


def backwards(apps, schema_editor):
    FormField = apps.get_model("django_forms_workflows", "FormField")

    fields = FormField.objects.filter(
        prefill_source_config__isnull=False,
        prefill_source="",
    ).select_related("prefill_source_config")

    for field in fields.iterator():
        ps = field.prefill_source_config
        field.prefill_source = ps.source_key
        field.save(update_fields=["prefill_source"])


class Migration(migrations.Migration):
    dependencies = [
        ("django_forms_workflows", "0034_add_notificationlog"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]

