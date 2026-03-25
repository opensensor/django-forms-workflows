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

            # Per-stage comparison keyed on (order, name) to handle parallel stages
            b_stage_map = {(s.get("order"), s.get("name")): s for s in b_stages}
            o_stage_map = {(s.get("order"), s.get("name")): s for s in o_stages}
            added_stages = sorted(o_stage_map.keys() - b_stage_map.keys())
            removed_stages = sorted(b_stage_map.keys() - o_stage_map.keys())
            if added_stages:
                diffs.append(f"Stages added: {', '.join(n for _, n in added_stages)}")
            if removed_stages:
                diffs.append(
                    f"Stages removed: {', '.join(n for _, n in removed_stages)}"
                )
            stage_field_keys = [
                "assignee_form_field",
                "assignee_lookup_type",
                "validate_assignee_group",
                "allow_reassign",
                "allow_send_back",
                "approve_label",
                "approval_logic",
                "requires_manager_approval",
                "trigger_conditions",
            ]
            for key in sorted(b_stage_map.keys() & o_stage_map.keys()):
                bs, os_ = b_stage_map[key], o_stage_map[key]
                for sk in stage_field_keys:
                    if bs.get(sk) != os_.get(sk):
                        diffs.append(
                            f"Stage '{key[1]}' {sk}: {bs.get(sk)!r} → {os_.get(sk)!r}"
                        )
                b_notifs = bs.get("form_field_notifications", [])
                o_notifs = os_.get("form_field_notifications", [])
                if len(b_notifs) != len(o_notifs):
                    diffs.append(
                        f"Stage '{key[1]}' notifications: {len(b_notifs)} → {len(o_notifs)}"
                    )
                # Approval groups: support both old string lists and new dict lists
                b_groups = {
                    g["name"] if isinstance(g, dict) else g
                    for g in bs.get("approval_groups", [])
                }
                o_groups = {
                    g["name"] if isinstance(g, dict) else g
                    for g in os_.get("approval_groups", [])
                }
                if b_groups != o_groups:
                    added_g = o_groups - b_groups
                    removed_g = b_groups - o_groups
                    parts = []
                    if added_g:
                        parts.append(f"+{', '.join(sorted(added_g))}")
                    if removed_g:
                        parts.append(f"-{', '.join(sorted(removed_g))}")
                    diffs.append(
                        f"Stage '{key[1]}' approval_groups: {'; '.join(parts)}"
                    )

            wf_setting_keys = [
                "requires_approval",
                "name_label",
                "notify_on_submission",
                "notify_on_approval",
                "notify_on_rejection",
                "notify_on_withdrawal",
                "additional_notify_emails",
                "hide_approval_history",
                "collapse_parallel_stages",
                "allow_bulk_export",
                "allow_bulk_pdf_export",
                "approval_deadline_days",
                "send_reminder_after_days",
                "auto_approve_after_days",
                "notification_cadence",
                "notification_cadence_day",
                "notification_cadence_time",
                "notification_cadence_form_field",
                "trigger_conditions",
            ]
            for key in wf_setting_keys:
                if b_wf.get(key) != o_wf.get(key):
                    diffs.append(f"Workflow {key}: {b_wf.get(key)} → {o_wf.get(key)}")

        # Form metadata
        meta_keys = [
            "name",
            "description",
            "instructions",
            "is_active",
            "allow_save_draft",
            "allow_withdrawal",
            "requires_login",
            "enable_multi_step",
            "enable_auto_save",
            "auto_save_interval",
            "pdf_generation",
        ]
        for key in meta_keys:
            if b_form.get(key) != o_form.get(key):
                diffs.append(f"{key}: {b_form.get(key)!r} → {o_form.get(key)!r}")

        # Category
        b_cat = base.get("category") or {}
        o_cat = other.get("category") or {}
        b_cat_slug = b_cat.get("slug") if b_cat else None
        o_cat_slug = o_cat.get("slug") if o_cat else None
        if b_cat_slug != o_cat_slug:
            diffs.append(f"category: {b_cat_slug!r} → {o_cat_slug!r}")

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
        else:
            b_action_names = {a.get("name") for a in b_actions}
            o_action_names = {a.get("name") for a in o_actions}
            added_a = o_action_names - b_action_names
            removed_a = b_action_names - o_action_names
            if added_a:
                diffs.append(
                    f"Post actions added: {', '.join(sorted(str(a) for a in added_a))}"
                )
            if removed_a:
                diffs.append(
                    f"Post actions removed: {', '.join(sorted(str(a) for a in removed_a))}"
                )
            b_action_map = {a.get("name"): a for a in b_actions}
            o_action_map = {a.get("name"): a for a in o_actions}
            action_check_keys = [
                "action_type",
                "trigger",
                "is_active",
                "order",
                "api_endpoint",
                "api_method",
                "email_to",
                "email_subject_template",
                "condition_field",
                "condition_operator",
                "condition_value",
            ]
            for name in sorted(b_action_names & o_action_names):
                ba, oa = b_action_map[name], o_action_map[name]
                for ak in action_check_keys:
                    if ba.get(ak) != oa.get(ak):
                        diffs.append(
                            f"Post action '{name}' {ak}: {ba.get(ak)!r} → {oa.get(ak)!r}"
                        )

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
