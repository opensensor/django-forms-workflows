"""
Django Forms Workflows - Cross-Instance Sync API

Provides serialization/deserialization of FormDefinition (with all related
objects) so that form + workflow + config definitions can be pushed or pulled
between multiple instances (e.g. test → prod).

Settings
--------
FORMS_SYNC_API_TOKEN : str
    Shared secret token that protects the export/import HTTP endpoints.
    If unset, the sync API endpoints are disabled.

Usage examples
--------------
Management commands (bundled)::

    # Pull all forms from a test instance
    python manage.py pull_forms --source-url=https://test.example.com --token=SECRET

    # Push selected forms to a prod instance
    python manage.py push_forms --dest-url=https://prod.example.com --token=SECRET --slugs=time-off,onboarding
"""

import logging
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import Group
from django.db import transaction
from django.utils import timezone as django_tz

from .models import (
    ApprovalTask,
    FormCategory,
    FormDefinition,
    FormField,
    NotificationRule,
    PostSubmissionAction,
    PrefillSource,
    StageApprovalGroup,
    SubWorkflowDefinition,
    WebhookEndpoint,
    WorkflowDefinition,
    WorkflowStage,
)

logger = logging.getLogger(__name__)

SYNC_SCHEMA_VERSION = 1


# ── Auth helpers ──────────────────────────────────────────────────────────────


def get_sync_token():
    """Return the configured sync API token, or None if not configured."""
    return getattr(settings, "FORMS_SYNC_API_TOKEN", None)


def verify_sync_token(request):
    """Return True if the Bearer token in the request matches the configured token."""
    token = get_sync_token()
    if not token:
        return False  # No token configured → sync disabled
    auth_header = request.META.get("HTTP_AUTHORIZATION", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:] == token
    return False


# ── Remote helpers ────────────────────────────────────────────────────────────


def get_sync_remotes():
    """Return configured remote instances from the FORMS_SYNC_REMOTES setting.

    Each entry should be a dict::

        {"name": "Test Site", "url": "https://test.example.com", "token": "secret"}

    Returns an empty list if the setting is not configured.
    """
    return getattr(settings, "FORMS_SYNC_REMOTES", [])


def fetch_remote_payload(remote_url, token, slugs=None, timeout=15):
    """Fetch an export payload from a remote instance via HTTP GET.

    Args:
        remote_url: Base URL of the remote instance (e.g. ``https://test.example.com``).
        token: Bearer token matching the remote's ``FORMS_SYNC_API_TOKEN``.
        slugs: Optional list of form slugs to filter. If ``None`` all forms are returned.
        timeout: Request timeout in seconds.

    Returns:
        Parsed JSON payload dict from the remote export endpoint.

    Raises:
        requests.HTTPError: If the remote returns a non-2xx response.
        requests.RequestException: For connection / timeout errors.
    """
    import requests

    url = remote_url.rstrip("/") + "/forms-sync/export/"
    params = {"slugs": ",".join(slugs)} if slugs else {}
    response = requests.get(
        url,
        params=params,
        headers={"Authorization": f"Bearer {token}"},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def push_to_remote(remote_url, token, queryset, conflict="update", timeout=30):
    """Push a local form queryset to a remote instance via HTTP POST.

    Args:
        remote_url: Base URL of the remote instance.
        token: Bearer token matching the remote's ``FORMS_SYNC_API_TOKEN``.
        queryset: ``FormDefinition`` queryset to export and push.
        conflict: Conflict resolution mode (``update``, ``skip``, or ``new_slug``).
        timeout: Request timeout in seconds.

    Returns:
        Parsed JSON response dict from the remote import endpoint.

    Raises:
        requests.HTTPError: If the remote returns a non-2xx response.
        requests.RequestException: For connection / timeout errors.
    """
    import requests

    payload = build_export_payload(queryset)
    url = remote_url.rstrip("/") + f"/forms-sync/import/?conflict={conflict}"
    response = requests.post(
        url,
        json=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


# ── Serializers ───────────────────────────────────────────────────────────────


def _group_names(qs):
    return list(qs.values_list("name", flat=True))


def _serialize_prefill_source(ps):
    if ps is None:
        return None
    return {
        "name": ps.name,
        "source_type": ps.source_type,
        "source_key": ps.source_key,
        "description": ps.description,
        "is_active": ps.is_active,
        "db_alias": ps.db_alias,
        "db_schema": ps.db_schema,
        "db_table": ps.db_table,
        "db_column": ps.db_column,
        "db_columns": ps.db_columns,
        "db_template": ps.db_template,
        "db_lookup_field": ps.db_lookup_field,
        "db_user_field": ps.db_user_field,
        "ldap_attribute": ps.ldap_attribute,
        "api_endpoint": ps.api_endpoint,
        "api_field": ps.api_field,
        "custom_config": ps.custom_config,
        "database_query_key": ps.database_query_key,
        "order": ps.order,
    }


def _serialize_category(cat):
    if cat is None:
        return None
    return {
        "name": cat.name,
        "slug": cat.slug,
        "description": cat.description,
        "order": cat.order,
        "is_collapsed_by_default": cat.is_collapsed_by_default,
        "icon": cat.icon,
        "allowed_groups": _group_names(cat.allowed_groups),
        "parent_slug": cat.parent.slug if cat.parent else None,
    }


def _serialize_field(field):
    return {
        "field_name": field.field_name,
        "field_label": field.field_label,
        "field_type": field.field_type,
        "order": field.order,
        "help_text": field.help_text,
        "placeholder": field.placeholder,
        "css_class": field.css_class,
        "width": field.width,
        "required": field.required,
        "readonly": field.readonly,
        "min_value": str(field.min_value) if field.min_value is not None else None,
        "max_value": str(field.max_value) if field.max_value is not None else None,
        "min_length": field.min_length,
        "max_length": field.max_length,
        "regex_validation": field.regex_validation,
        "regex_error_message": field.regex_error_message,
        "choices": field.choices,
        "shared_option_list_slug": field.shared_option_list.slug
        if field.shared_option_list_id
        else None,
        "prefill_source_config": _serialize_prefill_source(field.prefill_source_config),
        "default_value": field.default_value,
        "formula": field.formula,
        "conditional_rules": field.conditional_rules,
        "validation_rules": field.validation_rules,
        "field_dependencies": field.field_dependencies,
        "step_number": field.step_number,
        "allowed_extensions": field.allowed_extensions,
        "max_file_size_mb": field.max_file_size_mb,
        "workflow_stage_order": field.workflow_stage.order
        if field.workflow_stage_id
        else None,
    }


def _serialize_workflow_stage(stage):
    # Serialize approval groups with their sequence position so that
    # "sequence" stages are restored in the correct order on import.
    approval_groups = [
        {"name": sag.group.name, "position": sag.position}
        for sag in stage.stageapprovalgroup_set.select_related("group").order_by(
            "position"
        )
    ]
    return {
        "name": stage.name,
        "order": stage.order,
        "approval_logic": stage.approval_logic,
        "approval_groups": approval_groups,
        "requires_manager_approval": stage.requires_manager_approval,
        "approve_label": stage.approve_label,
        "trigger_conditions": stage.trigger_conditions,
        "assignee_form_field": stage.assignee_form_field,
        "assignee_lookup_type": stage.assignee_lookup_type,
        "validate_assignee_group": stage.validate_assignee_group,
        "allow_reassign": stage.allow_reassign,
        "allow_send_back": stage.allow_send_back,
        "allow_edit_form_data": stage.allow_edit_form_data,
        "notification_rules": [
            {
                "event": r.event,
                "notify_submitter": r.notify_submitter,
                "email_field": r.email_field,
                "static_emails": r.static_emails,
                "notify_stage_assignees": r.notify_stage_assignees,
                "notify_stage_groups": r.notify_stage_groups,
                "subject_template": r.subject_template,
                "conditions": r.conditions,
                "notify_groups": [g.name for g in r.notify_groups.all()],
            }
            for r in stage.notification_rules.all()
        ],
    }


def _serialize_sub_workflow_config(swc):
    if swc is None:
        return None
    # Include sub-workflow stage names so the importer can disambiguate when
    # the parent and sub workflows belong to the same FormDefinition.
    sub_wf_stage_names = list(
        swc.sub_workflow.stages.order_by("order").values_list("name", flat=True)
    )
    return {
        "sub_workflow_form_slug": swc.sub_workflow.form_definition.slug,
        "sub_workflow_stage_names": sub_wf_stage_names,
        "section_label": swc.section_label,
        "count_field": swc.count_field,
        "label_template": swc.label_template,
        "trigger": swc.trigger,
        "data_prefix": swc.data_prefix,
        "detached": swc.detached,
        "reject_parent": swc.reject_parent,
    }


def _serialize_webhook_endpoint(endpoint):
    return {
        "name": endpoint.name,
        "url": endpoint.url,
        "secret": endpoint.secret,
        "events": endpoint.events,
        "custom_headers": endpoint.custom_headers,
        "is_active": endpoint.is_active,
        "timeout_seconds": endpoint.timeout_seconds,
        "retry_on_failure": endpoint.retry_on_failure,
        "max_retries": endpoint.max_retries,
        "description": endpoint.description,
    }


def _serialize_workflow(wf):
    if wf is None:
        return None
    return {
        # Identity / display
        "name_label": wf.name_label,
        # Start trigger
        "start_trigger": wf.start_trigger,
        # Core approval settings
        "requires_approval": wf.requires_approval,
        "trigger_conditions": wf.trigger_conditions,
        "approval_deadline_days": wf.approval_deadline_days,
        "send_reminder_after_days": wf.send_reminder_after_days,
        "auto_approve_after_days": wf.auto_approve_after_days,
        # Notification cadence
        "notification_cadence": wf.notification_cadence,
        "notification_cadence_day": wf.notification_cadence_day,
        "notification_cadence_time": wf.notification_cadence_time.isoformat()
        if wf.notification_cadence_time
        else None,
        "notification_cadence_form_field": wf.notification_cadence_form_field,
        # Privacy / display options
        "hide_approval_history": wf.hide_approval_history,
        "collapse_parallel_stages": wf.collapse_parallel_stages,
        # Bulk export options
        "allow_bulk_export": wf.allow_bulk_export,
        "allow_bulk_pdf_export": wf.allow_bulk_pdf_export,
        # Visual editor data
        "visual_workflow_data": wf.visual_workflow_data,
        # Workflow-level notification rules (stage=null)
        "notification_rules": [
            {
                "event": r.event,
                "notify_submitter": r.notify_submitter,
                "email_field": r.email_field,
                "static_emails": r.static_emails,
                "notify_stage_assignees": r.notify_stage_assignees,
                "notify_stage_groups": r.notify_stage_groups,
                "subject_template": r.subject_template,
                "conditions": r.conditions,
                "notify_groups": [g.name for g in r.notify_groups.all()],
            }
            for r in wf.notification_rules.filter(stage__isnull=True)
        ],
        "webhook_endpoints": [
            _serialize_webhook_endpoint(endpoint)
            for endpoint in wf.webhook_endpoints.all().order_by("name")
        ],
        # Stages and sub-workflows
        "stages": [
            _serialize_workflow_stage(s) for s in wf.stages.all().order_by("order")
        ],
        "sub_workflow_config": _serialize_sub_workflow_config(
            getattr(wf, "sub_workflow_config", None)
        ),
    }


def _serialize_post_action(action):
    return {
        "name": action.name,
        "action_type": action.action_type,
        "trigger": action.trigger,
        "is_active": action.is_active,
        "order": action.order,
        "db_alias": action.db_alias,
        "db_schema": action.db_schema,
        "db_table": action.db_table,
        "db_lookup_field": action.db_lookup_field,
        "db_user_field": action.db_user_field,
        "db_field_mappings": action.db_field_mappings,
        "ldap_dn_template": action.ldap_dn_template,
        "ldap_field_mappings": action.ldap_field_mappings,
        "api_endpoint": action.api_endpoint,
        "api_method": action.api_method,
        "api_headers": action.api_headers,
        "api_body_template": action.api_body_template,
        "custom_handler_path": action.custom_handler_path,
        "custom_handler_config": action.custom_handler_config,
        "email_to": action.email_to,
        "email_to_field": action.email_to_field,
        "email_cc": action.email_cc,
        "email_cc_field": action.email_cc_field,
        "email_subject_template": action.email_subject_template,
        "email_body_template": action.email_body_template,
        "email_template_name": action.email_template_name,
        "is_locked": action.is_locked,
        "condition_field": action.condition_field,
        "condition_operator": action.condition_operator,
        "condition_value": action.condition_value,
        "fail_silently": action.fail_silently,
        "retry_on_failure": action.retry_on_failure,
        "max_retries": action.max_retries,
        "description": action.description,
    }


def serialize_form(form_definition):
    """Serialize a FormDefinition (with all related objects) to a plain dict."""
    all_workflows = list(form_definition.workflows.all().order_by("id"))

    # Primary workflow (backward compat: always stored as "workflow")
    primary_workflow = all_workflows[0] if all_workflows else None
    # Additional workflows (new: stored in "additional_workflows")
    extra_workflows = all_workflows[1:] if len(all_workflows) > 1 else []

    result = {
        "schema_version": SYNC_SCHEMA_VERSION,
        "category": _serialize_category(form_definition.category),
        "form": {
            "name": form_definition.name,
            "slug": form_definition.slug,
            "description": form_definition.description,
            "instructions": form_definition.instructions,
            "is_active": form_definition.is_active,
            "is_listed": form_definition.is_listed,
            "version": form_definition.version,
            "submit_groups": _group_names(form_definition.submit_groups),
            "view_groups": _group_names(form_definition.view_groups),
            "admin_groups": _group_names(form_definition.admin_groups),
            "allow_save_draft": form_definition.allow_save_draft,
            "allow_withdrawal": form_definition.allow_withdrawal,
            "allow_resubmit": form_definition.allow_resubmit,
            "allow_batch_import": form_definition.allow_batch_import,
            "requires_login": form_definition.requires_login,
            "enable_multi_step": form_definition.enable_multi_step,
            "form_steps": form_definition.form_steps,
            "enable_auto_save": form_definition.enable_auto_save,
            "auto_save_interval": form_definition.auto_save_interval,
            "pdf_generation": form_definition.pdf_generation,
            "api_enabled": form_definition.api_enabled,
            "embed_enabled": form_definition.embed_enabled,
            "payment_enabled": form_definition.payment_enabled,
            "payment_provider": form_definition.payment_provider,
            "payment_amount_type": form_definition.payment_amount_type,
            "payment_fixed_amount": str(form_definition.payment_fixed_amount)
            if form_definition.payment_fixed_amount is not None
            else None,
            "payment_amount_field": form_definition.payment_amount_field,
            "payment_currency": form_definition.payment_currency,
            "payment_description_template": form_definition.payment_description_template,
        },
        "fields": [
            _serialize_field(f) for f in form_definition.fields.all().order_by("order")
        ],
        "workflow": _serialize_workflow(primary_workflow),
        "post_actions": [
            _serialize_post_action(a)
            for a in form_definition.post_actions.all().order_by("order")
        ],
    }

    if extra_workflows:
        result["additional_workflows"] = [
            _serialize_workflow(wf) for wf in extra_workflows
        ]

    return result


def _topo_sort_categories(cat_data_list):
    """Return *cat_data_list* sorted so parent categories precede their children.

    Uses a simple repeated-pass approach — sufficient for the typical shallow
    category hierarchy (1-2 levels).
    """
    sorted_cats = []
    remaining = list(cat_data_list)
    seen_slugs = set()
    max_passes = len(remaining) + 1  # guard against circular refs
    while remaining and max_passes:
        max_passes -= 1
        next_remaining = []
        for cat in remaining:
            parent_slug = cat.get("parent_slug")
            if parent_slug is None or parent_slug in seen_slugs:
                sorted_cats.append(cat)
                seen_slugs.add(cat["slug"])
            else:
                next_remaining.append(cat)
        remaining = next_remaining
    # Append any unresolved (circular / missing parent) at the end
    sorted_cats.extend(remaining)
    return sorted_cats


def build_export_payload(queryset):
    """Build the full export payload dict for a queryset of FormDefinitions.

    The payload includes a top-level ``"categories"`` list containing *all*
    ``FormCategory`` objects so that:

    * Newly created categories (with no forms yet) are always exported.
    * Category renames, re-ordering, icon changes, and group-permission
      changes propagate independently of whether any form in that category
      was modified.
    """
    qs = queryset.prefetch_related(
        "fields",
        "fields__prefill_source_config",
        "fields__shared_option_list",
        "fields__workflow_stage",
        "workflows",
        "workflows__stages",
        "workflows__stages__stageapprovalgroup_set",
        "workflows__stages__stageapprovalgroup_set__group",
        "workflows__notification_rules",
        "workflows__notification_rules__notify_groups",
        "workflows__webhook_endpoints",
        "workflows__stages__notification_rules",
        "workflows__stages__notification_rules__notify_groups",
        "workflows__sub_workflow_config",
        "workflows__sub_workflow_config__sub_workflow__form_definition",
        "post_actions",
        "submit_groups",
        "view_groups",
        "admin_groups",
        "category",
        "category__allowed_groups",
    )

    # Export all categories (topologically sorted) so category-only changes
    # propagate even when no form in that category was touched.
    all_categories = (
        FormCategory.objects.prefetch_related("allowed_groups")
        .select_related("parent")
        .order_by("order", "name")
    )
    categories_payload = _topo_sort_categories(
        [_serialize_category(c) for c in all_categories]
    )

    # Export all prefill sources so standalone sources and config changes
    # propagate independently of whether any form field referencing them was
    # included in the push/pull.
    prefill_sources_payload = [
        _serialize_prefill_source(ps)
        for ps in PrefillSource.objects.order_by("order", "name")
    ]

    return {
        "schema_version": SYNC_SCHEMA_VERSION,
        "exported_at": django_tz.now().isoformat(),
        "form_count": qs.count(),
        "categories": categories_payload,
        "prefill_sources": prefill_sources_payload,
        "forms": [serialize_form(f) for f in qs],
    }


# ── Deserializers / Import logic ───────────────────────────────────────────────


def _get_or_create_group(name):
    """Return a Group with the given name, creating it if necessary."""
    group, _ = Group.objects.get_or_create(name=name)
    return group


def _get_or_create_prefill_source(data):
    """Find or create a PrefillSource by name, updating its fields."""
    if data is None:
        return None
    ps, _ = PrefillSource.objects.update_or_create(
        name=data["name"],
        defaults={k: v for k, v in data.items() if k != "name"},
    )
    return ps


def _get_or_create_category(data, category_cache=None):
    """Find or create a FormCategory by slug, updating its fields."""
    if data is None:
        return None
    if category_cache is not None and data["slug"] in category_cache:
        return category_cache[data["slug"]]

    parent = None
    if data.get("parent_slug"):
        parent = FormCategory.objects.filter(slug=data["parent_slug"]).first()

    cat, _ = FormCategory.objects.update_or_create(
        slug=data["slug"],
        defaults={
            "name": data["name"],
            "description": data.get("description", ""),
            "order": data.get("order", 0),
            "is_collapsed_by_default": data.get("is_collapsed_by_default", False),
            "icon": data.get("icon", ""),
            "parent": parent,
        },
    )
    # Sync allowed_groups
    cat.allowed_groups.set(
        [_get_or_create_group(n) for n in data.get("allowed_groups", [])]
    )

    if category_cache is not None:
        category_cache[data["slug"]] = cat
    return cat


def _resolve_sub_workflow(sub_wf_form, sub_wf_data, parent_workflow):
    """Resolve the correct WorkflowDefinition for a sub-workflow reference.

    When the parent and sub workflows belong to the **same** FormDefinition
    (e.g. Course Development Request has both a "Contract Approval" parent
    workflow and a "Payment" sub-workflow on the same form), the naïve
    ``sub_wf_form.workflow`` (which returns ``.workflows.first()``) will
    return the parent workflow — producing a self-referencing
    SubWorkflowDefinition.

    To disambiguate, we:
    1. Exclude the parent workflow from the candidate set.
    2. If ``sub_workflow_stage_names`` was serialised, match on the workflow
       whose stages (by name + order) match the exported data.
    3. Fall back to the first remaining workflow on the form.
    """
    if sub_wf_form is None:
        return None

    candidates = sub_wf_form.workflows.all()

    # If the parent belongs to the same form, exclude it so we don't
    # accidentally self-reference.
    if parent_workflow.form_definition_id == sub_wf_form.id:
        candidates = candidates.exclude(pk=parent_workflow.pk)

    # Try matching by stage names if available in the serialised payload.
    expected_stages = sub_wf_data.get("sub_workflow_stage_names")
    if expected_stages:
        for candidate in candidates:
            actual_stages = list(
                candidate.stages.order_by("order").values_list("name", flat=True)
            )
            if actual_stages == expected_stages:
                return candidate

    # Fall back to the first remaining candidate.
    return candidates.first()


def _import_single_workflow(
    form_obj,
    wf_payload,
    existing_wfs,
    wf_idx,
    imported_wf_ids,
):
    """Import one workflow definition for *form_obj*.

    Matches the incoming payload to an existing WorkflowDefinition by stage
    fingerprint (ordered list of stage names) so that forms with multiple
    workflows don't collide.  Falls back to positional matching (wf_idx) when
    stage-based matching fails.

    Returns ``(workflow_obj, stage_order_map)`` where *stage_order_map* maps
    stage ``order`` → ``WorkflowStage`` for field FK resolution.
    """
    from datetime import time as _time

    wf_data = dict(wf_payload)  # don't mutate caller's dict
    nc_time_str = wf_data.pop("notification_cadence_time", None)
    nc_time = _time.fromisoformat(nc_time_str) if nc_time_str else None
    stages_data = wf_data.pop("stages", [])
    wf_data.pop("sub_workflow_config", None)  # handled separately

    wf_notif_data = wf_data.pop("notification_rules", [])
    wf_webhook_data = wf_data.pop("webhook_endpoints", [])

    # Silently discard legacy keys
    for legacy_key in (
        "escalation_threshold",
        "approval_groups",
        "escalation_groups",
        "approval_logic",
        "requires_manager_approval",
        "manager_can_override_group",
        "escalation_field",
        "enable_db_updates",
        "db_update_mappings",
    ):
        wf_data.pop(legacy_key, None)

    # ── Find or create the right WorkflowDefinition ───────────────────────
    incoming_stage_names = [sd.get("name", "") for sd in stages_data]
    wf = None

    # Try to match by stage fingerprint among existing workflows
    for existing_wf in existing_wfs:
        if existing_wf.pk in imported_wf_ids:
            continue  # already claimed by a previous payload
        existing_stage_names = list(
            existing_wf.stages.order_by("order").values_list("name", flat=True)
        )
        if existing_stage_names == incoming_stage_names:
            wf = existing_wf
            break

    # Fallback: positional matching (first unclaimed existing workflow)
    if wf is None:
        unclaimed = [ew for ew in existing_wfs if ew.pk not in imported_wf_ids]
        if unclaimed:
            wf = unclaimed[0]

    if wf:
        # Update existing workflow
        for k, v in wf_data.items():
            setattr(wf, k, v)
        wf.notification_cadence_time = nc_time
        wf.save()
    else:
        # Create new workflow
        wf = WorkflowDefinition.objects.create(
            form_definition=form_obj,
            **wf_data,
            notification_cadence_time=nc_time,
        )

    # Sync workflow-level notification rules (stage=null)
    wf.notification_rules.filter(stage__isnull=True).delete()
    for notif in wf_notif_data:
        notif = dict(notif)
        group_names = notif.pop("notify_groups", [])
        if "notification_type" in notif and "event" not in notif:
            notif["event"] = notif.pop("notification_type")
        rule = NotificationRule.objects.create(workflow=wf, stage=None, **notif)
        for gname in group_names:
            rule.notify_groups.add(_get_or_create_group(gname))

    wf.webhook_endpoints.all().delete()
    for endpoint_data in wf_webhook_data:
        WebhookEndpoint.objects.create(workflow=wf, **endpoint_data)

    # Update stages in-place (matched by order + name) so that existing
    # ApprovalTask records — which hold a PROTECT FK to WorkflowStage —
    # are not broken.
    existing_by_key = {(s.order, s.name): s for s in wf.stages.all()}
    incoming_keys = {
        (sd.get("order", idx + 1), sd.get("name", ""))
        for idx, sd in enumerate(stages_data)
    }

    # Nullify task references then delete stages absent from incoming data
    removed = [s for k, s in existing_by_key.items() if k not in incoming_keys]
    if removed:
        ApprovalTask.objects.filter(workflow_stage__in=removed).update(
            workflow_stage=None
        )
        for s in removed:
            s.delete()

    stage_order_map = {}
    for idx, stage_data in enumerate(stages_data):
        stage_data = dict(stage_data)
        # Backwards compat: old exports used assignee_email_field
        if (
            "assignee_email_field" in stage_data
            and "assignee_form_field" not in stage_data
        ):
            stage_data["assignee_form_field"] = stage_data.pop("assignee_email_field")
        else:
            stage_data.pop("assignee_email_field", None)
        stage_group_data = stage_data.pop("approval_groups", [])
        stage_notif_data = stage_data.pop("notification_rules", [])
        if not stage_notif_data:
            stage_notif_data = stage_data.pop("form_field_notifications", [])
        order = stage_data.get("order", idx + 1)
        name = stage_data.get("name", "")
        key = (order, name)
        if key in existing_by_key:
            stage = existing_by_key[key]
            for k, v in stage_data.items():
                setattr(stage, k, v)
            stage.save()
        else:
            stage = WorkflowStage.objects.create(workflow=wf, **stage_data)

        StageApprovalGroup.objects.filter(stage=stage).delete()
        for pos, entry in enumerate(stage_group_data):
            if isinstance(entry, dict):
                group = _get_or_create_group(entry["name"])
                position = entry.get("position", pos)
            else:
                group = _get_or_create_group(entry)
                position = pos
            StageApprovalGroup.objects.create(
                stage=stage, group=group, position=position
            )

        stage.notification_rules.all().delete()
        for notif in stage_notif_data:
            notif = dict(notif)
            group_names = notif.pop("notify_groups", [])
            if "notification_type" in notif and "event" not in notif:
                notif["event"] = notif.pop("notification_type")
            rule = NotificationRule.objects.create(workflow=wf, stage=stage, **notif)
            for gname in group_names:
                rule.notify_groups.add(_get_or_create_group(gname))

        stage_order_map[order] = stage

    return wf, stage_order_map


@transaction.atomic
def import_form(form_data, conflict="update", category_cache=None):
    """
    Import a single serialized form dict.

    Parameters
    ----------
    form_data : dict
        A single form entry as returned by ``serialize_form()``.
    conflict : str
        How to handle an existing form with the same slug.
        ``'update'``    — overwrite the existing form (default).
        ``'skip'``      — leave the existing form untouched and return it.
        ``'new_slug'``  — append ``_imported`` to the slug and create a copy.
    category_cache : dict or None
        Pass a dict to cache ``FormCategory`` objects across multiple calls.

    Returns
    -------
    tuple[FormDefinition, str]
        ``(form_definition, action)`` where *action* is one of
        ``'created'``, ``'updated'``, or ``'skipped'``.
    """
    if category_cache is None:
        category_cache = {}

    fd = form_data.get("form", form_data)  # tolerate bare-form dicts
    slug = fd["slug"]

    category = _get_or_create_category(form_data.get("category"), category_cache)

    existing = FormDefinition.objects.filter(slug=slug).first()
    if existing:
        if conflict == "skip":
            return existing, "skipped"
        if conflict == "new_slug":
            slug = slug + "_imported"
            existing = FormDefinition.objects.filter(slug=slug).first()

    form_defaults = {
        "name": fd["name"],
        "description": fd.get("description", ""),
        "instructions": fd.get("instructions", ""),
        "is_active": fd.get("is_active", True),
        "is_listed": fd.get("is_listed", True),
        "version": fd.get("version", 1),
        "category": category,
        "allow_save_draft": fd.get("allow_save_draft", False),
        "allow_withdrawal": fd.get("allow_withdrawal", False),
        "allow_resubmit": fd.get("allow_resubmit", False),
        "allow_batch_import": fd.get("allow_batch_import", False),
        "requires_login": fd.get("requires_login", True),
        "enable_multi_step": fd.get("enable_multi_step", False),
        "form_steps": fd.get("form_steps"),
        "enable_auto_save": fd.get("enable_auto_save", False),
        "auto_save_interval": fd.get("auto_save_interval", 30),
        "pdf_generation": fd.get("pdf_generation", False),
        "api_enabled": fd.get("api_enabled", False),
        "embed_enabled": fd.get("embed_enabled", False),
        "payment_enabled": fd.get("payment_enabled", False),
        "payment_provider": fd.get("payment_provider", ""),
        "payment_amount_type": fd.get("payment_amount_type", "fixed"),
        "payment_fixed_amount": Decimal(fd["payment_fixed_amount"])
        if fd.get("payment_fixed_amount")
        else None,
        "payment_amount_field": fd.get("payment_amount_field", ""),
        "payment_currency": fd.get("payment_currency", "usd"),
        "payment_description_template": fd.get("payment_description_template", ""),
    }

    form_obj, created = FormDefinition.objects.update_or_create(
        slug=slug,
        defaults=form_defaults,
    )
    action = "created" if created else "updated"

    # Sync M2M groups
    form_obj.submit_groups.set(
        [_get_or_create_group(n) for n in fd.get("submit_groups", [])]
    )
    form_obj.view_groups.set(
        [_get_or_create_group(n) for n in fd.get("view_groups", [])]
    )
    form_obj.admin_groups.set(
        [_get_or_create_group(n) for n in fd.get("admin_groups", [])]
    )

    # ── Workflows (created BEFORE fields so stage FKs can be resolved) ─────────
    stage_order_map = {}  # order → WorkflowStage, used when creating fields
    wf_data = form_data.get("workflow")
    additional_wf_data = form_data.get("additional_workflows", [])

    # Collect all workflow data payloads to import
    all_wf_payloads = []
    if wf_data is not None:
        all_wf_payloads.append(wf_data)
    all_wf_payloads.extend(additional_wf_data)

    if all_wf_payloads:
        # Get existing workflows for this form, ordered by id.
        existing_wfs = list(
            WorkflowDefinition.objects.filter(form_definition=form_obj).order_by("id")
        )

        imported_wf_ids = set()
        for wf_idx, wf_payload in enumerate(all_wf_payloads):
            wf_obj, s_map = _import_single_workflow(
                form_obj,
                wf_payload,
                existing_wfs,
                wf_idx,
                imported_wf_ids,
            )
            imported_wf_ids.add(wf_obj.pk)
            # Use the primary workflow's stage map for field FK resolution
            if wf_idx == 0:
                stage_order_map = s_map

        # Now resolve sub-workflow configs (must be done after ALL workflows
        # exist so cross-references can be resolved).
        all_imported_wfs = list(
            WorkflowDefinition.objects.filter(form_definition=form_obj).order_by("id")
        )
        for wf_idx, wf_payload in enumerate(all_wf_payloads):
            wf_obj = (
                all_imported_wfs[wf_idx] if wf_idx < len(all_imported_wfs) else None
            )
            if wf_obj is None:
                continue
            sub_wf_data = dict(wf_payload).get("sub_workflow_config")
            if sub_wf_data:
                sub_form_slug = sub_wf_data.get("sub_workflow_form_slug")
                sub_wf_form = FormDefinition.objects.filter(slug=sub_form_slug).first()
                sub_wf = _resolve_sub_workflow(
                    sub_wf_form, sub_wf_data, parent_workflow=wf_obj
                )
                if sub_wf:
                    SubWorkflowDefinition.objects.update_or_create(
                        parent_workflow=wf_obj,
                        defaults={
                            "sub_workflow": sub_wf,
                            "section_label": sub_wf_data.get("section_label", ""),
                            "count_field": sub_wf_data.get("count_field", ""),
                            "label_template": sub_wf_data.get(
                                "label_template", "Sub-workflow {index}"
                            ),
                            "trigger": sub_wf_data.get("trigger", "on_approval"),
                            "data_prefix": sub_wf_data.get("data_prefix", ""),
                            "detached": sub_wf_data.get("detached", False),
                            "reject_parent": sub_wf_data.get("reject_parent", False),
                        },
                    )
                else:
                    logger.warning(
                        "Sync import: sub-workflow form not found for parent form;"
                        " sub_workflow_config skipped."
                    )
            else:
                SubWorkflowDefinition.objects.filter(parent_workflow=wf_obj).delete()
    else:
        # Remove all workflows if source had none
        WorkflowDefinition.objects.filter(form_definition=form_obj).delete()

    # ── Fields ─────────────────────────────────────────────────────────────────
    # Delete existing fields so we get a clean ordered set
    form_obj.fields.all().delete()
    for field_data in form_data.get("fields", []):
        field_data = dict(field_data)
        ps_config = _get_or_create_prefill_source(
            field_data.pop("prefill_source_config", None)
        )
        field_data.pop("prefill_source_config", None)
        # Remove legacy fields no longer on the model (may exist in older payloads)
        field_data.pop("prefill_source", None)
        field_data.pop("approval_step", None)
        field_data.pop("show_if_field", None)
        field_data.pop("show_if_value", None)
        min_val = field_data.pop("min_value", None)
        max_val = field_data.pop("max_value", None)
        stage_order = field_data.pop("workflow_stage_order", None)
        workflow_stage = (
            stage_order_map.get(stage_order) if stage_order is not None else None
        )
        # Resolve shared option list by slug (if present)
        sol_slug = field_data.pop("shared_option_list_slug", None)
        shared_option_list = None
        if sol_slug:
            from .models import SharedOptionList

            shared_option_list = SharedOptionList.objects.filter(slug=sol_slug).first()
        FormField.objects.create(
            form_definition=form_obj,
            prefill_source_config=ps_config,
            shared_option_list=shared_option_list,
            min_value=Decimal(min_val) if min_val is not None else None,
            max_value=Decimal(max_val) if max_val is not None else None,
            workflow_stage=workflow_stage,
            **field_data,
        )

    # ── Post-submission actions ────────────────────────────────────────────────
    form_obj.post_actions.all().delete()
    for action_data in form_data.get("post_actions", []):
        PostSubmissionAction.objects.create(form_definition=form_obj, **action_data)

    logger.info("Sync import: form %s.", action)
    return form_obj, action


def import_payload(payload, conflict="update"):
    """
    Import a full export payload (as returned by ``build_export_payload()``).

    Categories in the top-level ``"categories"`` key are upserted first
    (topologically, so parents precede children) so that:

    * Standalone categories with no forms are created/updated.
    * Category renames, ordering, icons, and group-permissions are applied
      even when none of the category's forms are in the payload.

    Returns a list of ``(FormDefinition, action)`` tuples.
    """
    category_cache = {}

    # ── 1. Upsert all categories (parents before children) ────────────────────
    for cat_data in _topo_sort_categories(payload.get("categories", [])):
        _get_or_create_category(cat_data, category_cache)

    # ── 2. Upsert all prefill sources ─────────────────────────────────────────
    for ps_data in payload.get("prefill_sources", []):
        _get_or_create_prefill_source(ps_data)

    # ── 3. Import forms (category / prefill-source lookups are now cache hits) ─
    results = []
    for form_data in payload.get("forms", []):
        result = import_form(
            form_data, conflict=conflict, category_cache=category_cache
        )
        results.append(result)

    # ── 4. Reset PostgreSQL sequences ─────────────────────────────────────────
    # Sync deletes and re-creates rows (e.g. NotificationRule, StageApprovalGroup,
    # PostSubmissionAction) which can leave auto-increment sequences behind the
    # actual max ID in the table, causing IntegrityError on the next insert.
    _reset_sequences()

    return results


def _reset_sequences():
    """Reset PostgreSQL sequences for all models that sync may delete/recreate.

    Safe to call on any database backend — silently skips non-PostgreSQL.
    """
    from django.db import connection

    if connection.vendor != "postgresql":
        return

    models_to_reset = [
        FormDefinition,
        NotificationRule,
        StageApprovalGroup,
        PostSubmissionAction,
        WebhookEndpoint,
        WorkflowStage,
        FormField,
    ]
    with connection.cursor() as cursor:
        for model in models_to_reset:
            table = model._meta.db_table
            pk_col = model._meta.pk.column
            cursor.execute(
                f"SELECT setval("
                f"pg_get_serial_sequence('{table}', '{pk_col}'), "
                f"COALESCE(MAX({pk_col}), 1)) "
                f"FROM {table}"
            )
