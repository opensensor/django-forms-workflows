"""
Views for diffing FormDefinition objects side-by-side.
"""

import json

from django.http import HttpResponseBadRequest
from django.shortcuts import render

from .models import FormDefinition
from .sync_api import build_export_payload


def _payload_workflows(payload):
    """Return every workflow in a serialized payload, primary first.

    ``serialize_form`` splits a form's workflows across two keys — ``workflow``
    holds the first one by id, ``additional_workflows`` holds the rest — so
    anything reading only ``workflow`` is blind to sub-workflows.
    """
    workflows = []
    primary = payload.get("workflow")
    if primary:
        workflows.append(primary)
    workflows.extend(wf for wf in (payload.get("additional_workflows") or []) if wf)
    return workflows


def _pair_workflows(b_wfs, o_wfs):
    """Pair base/other workflows, yielding ``(index, base_wf, other_wf)`` tuples.

    Matched on ``uuid`` first, because creation order — and therefore position
    in the list — is not guaranteed to agree between environments. Whatever
    uuid matching leaves over is paired by position, which covers payloads
    predating the uuid field and the standalone diff view, where two *different*
    forms are compared and no uuid will ever match. Anything still unpaired is
    reported as added or removed.
    """
    o_by_uuid = {}
    for idx, wf in enumerate(o_wfs):
        uid = wf.get("uuid")
        if uid:
            o_by_uuid.setdefault(uid, []).append(idx)

    pairs = []
    matched_o = set()
    unmatched_b = []
    for idx, wf in enumerate(b_wfs):
        candidates = o_by_uuid.get(wf.get("uuid")) or []
        match = next((c for c in candidates if c not in matched_o), None)
        if match is None:
            unmatched_b.append(idx)
        else:
            matched_o.add(match)
            pairs.append((idx, wf, o_wfs[match]))

    leftover_o = [i for i in range(len(o_wfs)) if i not in matched_o]
    for b_idx, o_idx in zip(unmatched_b, leftover_o, strict=False):
        pairs.append((b_idx, b_wfs[b_idx], o_wfs[o_idx]))
    overlap = min(len(unmatched_b), len(leftover_o))
    for b_idx in unmatched_b[overlap:]:
        pairs.append((b_idx, b_wfs[b_idx], None))
    for o_idx in leftover_o[overlap:]:
        pairs.append((o_idx, None, o_wfs[o_idx]))

    pairs.sort(key=lambda p: p[0])
    return pairs


def _workflow_label(wf, index):
    """Label a workflow in the summary bullets.

    ``name_label`` is what distinguishes a parent workflow from its
    sub-workflows on the same form, so it is preferred when set.
    """
    name_label = (wf or {}).get("name_label")
    if name_label:
        return f"Workflow '{name_label}'"
    return "Workflow" if index == 0 else f"Workflow #{index + 1}"


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

        # Workflow differences — every workflow, not only the primary one.
        for wf_index, b_wf, o_wf in _pair_workflows(
            _payload_workflows(base), _payload_workflows(other)
        ):
            wf_label = _workflow_label(b_wf or o_wf, wf_index)
            if b_wf is None or o_wf is None:
                diffs.append(
                    f"{wf_label}: {'present' if b_wf else 'absent'}"
                    f" → {'present' if o_wf else 'absent'}"
                )
                continue
            b_stages = b_wf.get("stages", [])
            o_stages = o_wf.get("stages", [])
            if len(b_stages) != len(o_stages):
                diffs.append(f"{wf_label} stages: {len(b_stages)} → {len(o_stages)}")

            # Per-stage comparison keyed on (order, name) to handle parallel stages
            b_stage_map = {(s.get("order"), s.get("name")): s for s in b_stages}
            o_stage_map = {(s.get("order"), s.get("name")): s for s in o_stages}
            added_stages = sorted(o_stage_map.keys() - b_stage_map.keys())
            removed_stages = sorted(b_stage_map.keys() - o_stage_map.keys())
            if added_stages:
                diffs.append(
                    f"{wf_label} stages added: {', '.join(n for _, n in added_stages)}"
                )
            if removed_stages:
                diffs.append(
                    f"{wf_label} stages removed: "
                    f"{', '.join(n for _, n in removed_stages)}"
                )
            stage_field_keys = [
                "assignee_form_field",
                "assignee_lookup_type",
                "validate_assignee_group",
                "allow_reassign",
                "allow_send_back",
                "allow_edit_form_data",
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
                            f"{wf_label} stage '{key[1]}' {sk}: "
                            f"{bs.get(sk)!r} → {os_.get(sk)!r}"
                        )
                b_notifs = bs.get(
                    "notification_rules", bs.get("form_field_notifications", [])
                )
                o_notifs = os_.get(
                    "notification_rules", os_.get("form_field_notifications", [])
                )
                if len(b_notifs) != len(o_notifs):
                    diffs.append(
                        f"{wf_label} stage '{key[1]}' notifications: "
                        f"{len(b_notifs)} → {len(o_notifs)}"
                    )
                elif b_notifs != o_notifs:
                    for idx, (bn, on) in enumerate(
                        zip(b_notifs, o_notifs, strict=False)
                    ):
                        if bn == on:
                            continue
                        changed_keys = sorted(
                            k for k in set(bn) | set(on) if bn.get(k) != on.get(k)
                        )
                        label = bn.get("event") or on.get("event") or f"#{idx}"
                        diffs.append(
                            f"{wf_label} stage '{key[1]}' notification "
                            f"'{label}' changed: {', '.join(changed_keys)}"
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
                        f"{wf_label} stage '{key[1]}' approval_groups: "
                        f"{'; '.join(parts)}"
                    )

            wf_setting_keys = [
                "requires_approval",
                "name_label",
                "start_trigger",
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
                    diffs.append(f"{wf_label} {key}: {b_wf.get(key)} → {o_wf.get(key)}")

            # Sub-workflow wiring. Compared by changed key rather than dumped
            # whole — the config is a nested dict and printing both sides makes
            # the summary unreadable.
            b_swc = b_wf.get("sub_workflow_config")
            o_swc = o_wf.get("sub_workflow_config")
            if (b_swc is None) != (o_swc is None):
                diffs.append(
                    f"{wf_label} sub_workflow_config: "
                    f"{'present' if b_swc else 'absent'}"
                    f" → {'present' if o_swc else 'absent'}"
                )
            elif b_swc and o_swc and b_swc != o_swc:
                swc_keys = sorted(
                    k for k in set(b_swc) | set(o_swc) if b_swc.get(k) != o_swc.get(k)
                )
                diffs.append(
                    f"{wf_label} sub_workflow_config changed: {', '.join(swc_keys)}"
                )

            # Workflow-level notification rules (stage=null)
            b_wf_notifs = b_wf.get("notification_rules", [])
            o_wf_notifs = o_wf.get("notification_rules", [])
            if len(b_wf_notifs) != len(o_wf_notifs):
                diffs.append(
                    f"{wf_label} notification rules: "
                    f"{len(b_wf_notifs)} → {len(o_wf_notifs)}"
                )
            elif b_wf_notifs != o_wf_notifs:
                # Same count but content differs — surface what changed.
                changed = []
                for idx, (br, or_) in enumerate(
                    zip(b_wf_notifs, o_wf_notifs, strict=False)
                ):
                    if br == or_:
                        continue
                    changed_keys = sorted(
                        k for k in set(br) | set(or_) if br.get(k) != or_.get(k)
                    )
                    label = br.get("event") or or_.get("event") or f"#{idx}"
                    diffs.append(
                        f"{wf_label} notification rule '{label}' changed: "
                        f"{', '.join(changed_keys)}"
                    )
                    changed.append(label)
                if not changed:
                    diffs.append(f"{wf_label} notification rules: order changed")

        # Form metadata
        meta_keys = [
            "name",
            "description",
            "instructions",
            "is_active",
            "is_listed",
            "allow_save_draft",
            "allow_withdrawal",
            "allow_resubmit",
            "allow_batch_import",
            "requires_login",
            "enable_multi_step",
            "enable_auto_save",
            "auto_save_interval",
            "pdf_generation",
            "api_enabled",
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
        for g in ("submit_groups", "view_groups", "admin_groups", "reviewer_groups"):
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
            # Keep in sync with sync_api._serialize_post_action so every
            # field that round-trips through push/pull also shows up here.
            action_check_keys = [
                "action_type",
                "trigger",
                "is_active",
                "order",
                "is_locked",
                "description",
                # Database action
                "db_alias",
                "db_schema",
                "db_table",
                "db_lookup_field",
                "db_user_field",
                "db_field_mappings",
                # LDAP action
                "ldap_dn_template",
                "ldap_field_mappings",
                # API action
                "api_endpoint",
                "api_method",
                "api_headers",
                "api_body_template",
                # Custom handler
                "custom_handler_path",
                "custom_handler_config",
                # Email action
                "email_to",
                "email_to_field",
                "email_cc",
                "email_cc_field",
                "email_subject_template",
                "email_body_template",
                "email_template_name",
                # Conditional execution
                "condition_field",
                "condition_operator",
                "condition_value",
                # Retry / failure handling
                "fail_silently",
                "retry_on_failure",
                "max_retries",
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
