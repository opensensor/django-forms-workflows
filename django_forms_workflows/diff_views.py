"""
Views for diffing FormDefinition objects side-by-side.
"""

import json

from django.http import HttpResponseBadRequest
from django.shortcuts import render

from .models import FormDefinition
from .sync_api import build_export_payload


def _build_summary(forms_data):
    """Build a supplemental summary of key differences between serialized forms."""
    if len(forms_data) < 2:
        return []

    summaries = []
    base = forms_data[0]
    for other in forms_data[1:]:
        diffs = []
        b_form, o_form = base.get("form", {}), other.get("form", {})

        # Field count
        b_fields = base.get("fields", [])
        o_fields = other.get("fields", [])
        if len(b_fields) != len(o_fields):
            diffs.append(f"Field count: {len(b_fields)} → {len(o_fields)}")

        # Fields added/removed
        b_names = {f["field_name"] for f in b_fields}
        o_names = {f["field_name"] for f in o_fields}
        added = o_names - b_names
        removed = b_names - o_names
        if added:
            diffs.append(f"Fields added: {', '.join(sorted(added))}")
        if removed:
            diffs.append(f"Fields removed: {', '.join(sorted(removed))}")

        # Changed fields
        common = b_names & o_names
        b_field_map = {f["field_name"]: f for f in b_fields}
        o_field_map = {f["field_name"]: f for f in o_fields}
        changed_fields = []
        for name in sorted(common):
            if b_field_map[name] != o_field_map[name]:
                changed_fields.append(name)
        if changed_fields:
            diffs.append(f"Fields modified: {', '.join(changed_fields)}")

        # Workflow differences
        b_wf = base.get("workflow")
        o_wf = other.get("workflow")
        if (b_wf is None) != (o_wf is None):
            diffs.append(
                f"Workflow: {'present' if b_wf else 'absent'}"
                f" → {'present' if o_wf else 'absent'}"
            )
        elif b_wf and o_wf:
            b_stages = b_wf.get("stages", [])
            o_stages = o_wf.get("stages", [])
            if len(b_stages) != len(o_stages):
                diffs.append(f"Workflow stages: {len(b_stages)} → {len(o_stages)}")
            wf_setting_keys = [
                "requires_approval",
                "notify_on_submission",
                "notify_on_approval",
                "notify_on_rejection",
                "hide_approval_history",
                "approval_deadline_days",
            ]
            for key in wf_setting_keys:
                if b_wf.get(key) != o_wf.get(key):
                    diffs.append(f"Workflow {key}: {b_wf.get(key)} → {o_wf.get(key)}")

        # Form metadata
        meta_keys = [
            "name",
            "is_active",
            "allow_save_draft",
            "allow_withdrawal",
            "requires_login",
            "enable_multi_step",
            "pdf_generation",
        ]
        for key in meta_keys:
            if b_form.get(key) != o_form.get(key):
                diffs.append(f"{key}: {b_form.get(key)!r} → {o_form.get(key)!r}")

        # Permission groups
        for g in ("submit_groups", "view_groups", "admin_groups"):
            bg = set(b_form.get(g, []))
            og = set(o_form.get(g, []))
            if bg != og:
                added_g = og - bg
                removed_g = bg - og
                parts = []
                if added_g:
                    parts.append(f"+{', '.join(sorted(added_g))}")
                if removed_g:
                    parts.append(f"-{', '.join(sorted(removed_g))}")
                diffs.append(f"{g}: {'; '.join(parts)}")

        # Post actions
        b_actions = base.get("post_actions", [])
        o_actions = other.get("post_actions", [])
        if len(b_actions) != len(o_actions):
            diffs.append(f"Post actions: {len(b_actions)} → {len(o_actions)}")

        summaries.append(
            {
                "left": b_form.get("name", "Form A"),
                "right": o_form.get("name", "Form B"),
                "diffs": diffs,
                "identical": len(diffs) == 0,
            }
        )

    return summaries


def diff_forms_view(request):
    """Render a side-by-side JSON diff of selected FormDefinitions."""
    pks = request.GET.get("pks", "")
    if not pks:
        return HttpResponseBadRequest("No form IDs provided.")

    pk_list = [int(pk) for pk in pks.split(",") if pk.strip().isdigit()]
    if len(pk_list) < 2:
        return HttpResponseBadRequest("Select at least 2 forms to diff.")

    qs = FormDefinition.objects.filter(pk__in=pk_list)
    payload = build_export_payload(qs)
    forms_data = payload.get("forms", [])

    # Build per-form JSON strings for the diff viewer
    forms_json = []
    for fd in forms_data:
        # Remove schema_version from each form (it's the same for all)
        fd.pop("schema_version", None)
        forms_json.append(
            {
                "name": fd.get("form", {}).get("name", "Unknown"),
                "slug": fd.get("form", {}).get("slug", ""),
                "json": json.dumps(fd, indent=2, default=str),
            }
        )

    summary = _build_summary(forms_data)

    return render(
        request,
        "admin/django_forms_workflows/diff_forms.html",
        {
            "title": "Form Definition Diff",
            "forms_json": forms_json,
            "forms_json_escaped": json.dumps(
                [f["json"] for f in forms_json], default=str
            ),
            "form_names": json.dumps([f["name"] for f in forms_json]),
            "summary": summary,
        },
    )
