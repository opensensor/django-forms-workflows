"""
Normalize FormField.conditional_rules: rewrite the client-only ``is_not_empty``
operator to the canonical ``not_empty`` recognised by
``django_forms_workflows.conditions.evaluate_conditions``.

Prior to this migration, the form builder UI wrote ``is_not_empty`` into each
field's ``conditional_rules`` JSON, but the server-side evaluator only knew
about ``not_empty``. On submission ``clean()`` treated ``show``-gated fields as
hidden and dropped their values, so they never reached ``form_data`` and did
not render in the submission detail view.
"""

from django.db import migrations


def _rewrite_rules(rules):
    """Recursively swap ``is_not_empty`` → ``not_empty`` in a rules blob."""
    if isinstance(rules, list):
        return [_rewrite_rules(r) for r in rules]
    if isinstance(rules, dict):
        out = {}
        for k, v in rules.items():
            if k == "operator" and v == "is_not_empty":
                out[k] = "not_empty"
            elif k == "conditions":
                out[k] = [_rewrite_rules(c) for c in (v or [])]
            else:
                out[k] = _rewrite_rules(v) if isinstance(v, list | dict) else v
        return out
    return rules


def forwards(apps, schema_editor):
    FormField = apps.get_model("django_forms_workflows", "FormField")
    for field in FormField.objects.exclude(conditional_rules__isnull=True):
        original = field.conditional_rules
        rewritten = _rewrite_rules(original)
        if rewritten != original:
            field.conditional_rules = rewritten
            field.save(update_fields=["conditional_rules"])


class Migration(migrations.Migration):

    dependencies = [
        ("django_forms_workflows", "0092_add_user_notification_preference"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
