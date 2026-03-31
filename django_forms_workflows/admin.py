"""
Django admin for Django Forms Workflows

Provides a friendly admin interface to build forms (with fields),
configure approval workflows, and review submissions and audit logs.
"""

import json
import logging

import nested_admin
from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin
from django.contrib.auth.models import Group
from django.db import transaction
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.urls import path, reverse
from django.utils.html import format_html, mark_safe

from .models import (
    ActionExecutionLog,
    APIToken,
    ApprovalTask,
    AuditLog,
    ChangeHistory,
    FileUploadConfig,
    FileWorkflowHook,
    FormCategory,
    FormDefinition,
    FormField,
    FormSubmission,
    FormTemplate,
    LDAPGroupProfile,
    ManagedFile,
    NotificationLog,
    NotificationRule,
    PostSubmissionAction,
    PrefillSource,
    StageApprovalGroup,
    SubWorkflowDefinition,
    SubWorkflowInstance,
    UserProfile,
    WorkflowDefinition,
    WorkflowStage,
)

logger = logging.getLogger(__name__)


# ── Change History inline (read-only, for tracked models) ───────────────


class ChangeHistoryInline(nested_admin.NestedGenericTabularInline):
    model = ChangeHistory
    ct_field = "content_type"
    ct_fk_field = "object_id"
    fields = ("timestamp", "action", "user", "summary", "changes_preview")
    readonly_fields = ("timestamp", "action", "user", "summary", "changes_preview")
    extra = 0
    max_num = 0  # prevent adding new rows
    ordering = ("-timestamp",)
    classes = ("collapse",)
    verbose_name = "Change History Entry"
    verbose_name_plural = "Change History"

    def changes_preview(self, obj):
        """Show a compact summary of changed fields."""
        if not obj.changes:
            return "—"
        parts = []
        for key, diff in list(obj.changes.items())[:8]:
            old = diff.get("old", "")
            new = diff.get("new", "")
            # Truncate long values (e.g. base64 signatures)
            old_s = str(old)[:60] + "…" if len(str(old)) > 60 else str(old)
            new_s = str(new)[:60] + "…" if len(str(new)) > 60 else str(new)
            parts.append(f"<b>{key}</b>: {old_s} → {new_s}")
        html = "<br>".join(parts)
        if len(obj.changes) > 8:
            html += f"<br><i>… and {len(obj.changes) - 8} more</i>"
        return mark_safe(html)

    changes_preview.short_description = "Changes"

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# Inline for form fields when editing a form definition
class FormFieldInline(nested_admin.NestedStackedInline):
    model = FormField
    extra = 0
    ordering = ("order",)
    fk_name = "form_definition"
    classes = ("collapse",)
    readonly_fields = ("conditional_rules_summary",)
    fieldsets = (
        (
            None,
            {
                "fields": (
                    ("order", "field_label", "field_name", "field_type"),
                    ("required", "readonly", "workflow_stage"),
                    ("help_text", "placeholder", "width", "css_class"),
                )
            },
        ),
        (
            "Validation",
            {
                "classes": ("collapse",),
                "fields": (
                    ("min_value", "max_value"),
                    ("min_length", "max_length"),
                    "regex_validation",
                    "regex_error_message",
                ),
            },
        ),
        (
            "Choices & Defaults",
            {
                "classes": ("collapse",),
                "fields": (
                    "choices",
                    "prefill_source_config",
                    "default_value",
                    "formula",
                ),
            },
        ),
        (
            "Conditional display",
            {
                "fields": ("conditional_rules_summary", "conditional_rules"),
                "description": (
                    "The summary shows the currently saved rules at a glance. "
                    "Edit the raw JSON below to add or modify rules."
                ),
            },
        ),
        (
            "File upload",
            {
                "classes": ("collapse",),
                "fields": ("allowed_extensions", "max_file_size_mb"),
            },
        ),
    )

    @admin.display(description="Conditional rules (summary)")
    def conditional_rules_summary(self, obj):
        result = _render_conditional_rules(obj.conditional_rules)
        return result or "No conditional rules configured."


def _render_conditional_rules(rules) -> str:
    """Return a colour-coded HTML summary of a ``conditional_rules`` value.

    Used as a read-only admin display for both the inline and the standalone
    ``FormFieldAdmin``.  Returns an empty string when there are no rules.

    Each rule is rendered as a coloured badge for its action followed by the
    human-readable condition expression:

        [SHOW]    when  ``first_enrollment`` equals ``Yes``
        [REQUIRE] when  ``first_enrollment`` equals ``Yes``
    """
    import json

    if not rules:
        return ""
    if isinstance(rules, str):
        try:
            rules = json.loads(rules)
        except (json.JSONDecodeError, TypeError):
            return format_html('<span style="color:#dc3545">⚠ Invalid JSON</span>')
    if isinstance(rules, dict):
        rules = [rules]
    if not isinstance(rules, list):
        return ""

    _badge_styles = {
        "show": "background:#198754;color:#fff",  # green
        "hide": "background:#dc3545;color:#fff",  # red
        "require": "background:#0d6efd;color:#fff",  # blue
        "enable": "background:#6c757d;color:#fff",  # grey
    }

    parts = []
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        action = rule.get("action", "show")
        badge_style = _badge_styles.get(action, "background:#6c757d;color:#fff")
        conditions = rule.get("conditions") or []
        op = rule.get("operator", "AND")
        if isinstance(conditions, list) and conditions:
            cond_strs = [
                f"<code>{c.get('field', '?')}</code> {c.get('operator', '=')} "
                f"<code>{c.get('value', '?')}</code>"
                for c in conditions
                if isinstance(c, dict)
            ]
            cond_html = f" <small style='color:#6c757d'>{op}</small> ".join(cond_strs)
        else:
            cond_html = "<em style='color:#999'>(no conditions — always applies)</em>"
        parts.append(
            f'<div style="margin:3px 0;line-height:1.6">'
            f'<span style="{badge_style};padding:1px 7px;border-radius:3px;'
            f'font-size:11px;font-weight:700;letter-spacing:.5px">'
            f"{action.upper()}</span>"
            f"&nbsp;&nbsp;when &nbsp;{cond_html}</div>"
        )

    from django.utils.safestring import mark_safe

    return mark_safe("".join(parts)) if parts else ""


@admin.register(FormField)
class FormFieldAdmin(admin.ModelAdmin):
    """Standalone admin for FormField — useful for searching/editing fields
    across all forms."""

    list_display = [
        "field_name",
        "field_label",
        "field_type",
        "form_definition",
        "required",
        "readonly",
        "conditional_rules_summary",
        "workflow_stage",
        "order",
    ]
    list_filter = [
        "form_definition",
        "field_type",
        "required",
        "readonly",
        "workflow_stage",
    ]
    search_fields = ["field_name", "field_label"]
    ordering = ["form_definition", "order"]
    autocomplete_fields = ["form_definition", "prefill_source_config", "workflow_stage"]
    readonly_fields = ["conditional_rules_summary"]

    fieldsets = (
        (
            "Basic Information",
            {"fields": ("form_definition", "field_name", "field_label", "field_type")},
        ),
        (
            "Field Configuration",
            {"fields": (("required", "readonly"), "width", "order", "workflow_stage")},
        ),
        (
            "Prefill / Default Value",
            {"fields": ("prefill_source_config", "default_value")},
        ),
        (
            "Choices (for select/radio/checkbox fields)",
            {"fields": ("choices",), "classes": ("collapse",)},
        ),
        (
            "Formula (for calculated fields)",
            {"fields": ("formula",), "classes": ("collapse",)},
        ),
        (
            "Validation",
            {
                "fields": (
                    "regex_validation",
                    "regex_error_message",
                    "min_value",
                    "max_value",
                    "min_length",
                    "max_length",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Display",
            {"fields": ("help_text", "placeholder"), "classes": ("collapse",)},
        ),
        (
            "Conditional Display",
            {
                "fields": ("conditional_rules_summary", "conditional_rules"),
                "description": (
                    "Rules control when this field is shown, hidden, or required. "
                    "The summary above reflects the current saved rules; "
                    "edit the raw JSON below to change them."
                ),
            },
        ),
        (
            "File Upload",
            {
                "fields": ("allowed_extensions", "max_file_size_mb"),
                "classes": ("collapse",),
            },
        ),
    )

    @admin.display(description="Conditional rules")
    def conditional_rules_summary(self, obj):
        result = _render_conditional_rules(obj.conditional_rules)
        return result or "—"

    conditional_rules_summary.allow_tags = True  # Django <4 compat guard


@admin.register(PrefillSource)
class PrefillSourceAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "source_type",
        "source_key",
        "is_active",
        "order",
    )
    list_filter = ("source_type", "is_active")
    search_fields = ("name", "source_key", "description")
    list_editable = ("order", "is_active")
    fieldsets = (
        (
            None,
            {
                "fields": (
                    ("name", "source_type"),
                    "source_key",
                    "description",
                    ("is_active", "order"),
                )
            },
        ),
        (
            "Database Configuration",
            {
                "classes": ("collapse",),
                "fields": (
                    "db_alias",
                    ("db_schema", "db_table", "db_column"),
                    ("db_lookup_field", "db_user_field"),
                ),
            },
        ),
        (
            "LDAP Configuration",
            {
                "classes": ("collapse",),
                "fields": ("ldap_attribute",),
            },
        ),
        (
            "API Configuration",
            {
                "classes": ("collapse",),
                "fields": ("api_endpoint", "api_field"),
            },
        ),
        (
            "Custom Configuration",
            {
                "classes": ("collapse",),
                "fields": ("custom_config",),
            },
        ),
    )


@admin.register(FormCategory)
class FormCategoryAdmin(admin.ModelAdmin):
    """Admin interface for FormCategory grouping primitives."""

    list_display = [
        "name",
        "parent",
        "slug",
        "order",
        "is_collapsed_by_default",
        "icon",
    ]
    list_editable = ["order", "is_collapsed_by_default"]
    list_filter = ["parent"]
    prepopulated_fields = {"slug": ("name",)}
    filter_horizontal = ["allowed_groups"]
    search_fields = ["name", "description"]
    autocomplete_fields = ["parent"]
    fieldsets = (
        (
            None,
            {
                "fields": ("name", "slug", "description", "icon"),
            },
        ),
        (
            "Hierarchy",
            {
                "fields": ("parent",),
                "description": (
                    "Optionally nest this category under a parent. "
                    "Leave empty to make this a top-level category."
                ),
            },
        ),
        (
            "Display Options",
            {
                "fields": ("order", "is_collapsed_by_default"),
            },
        ),
        (
            "Access Control",
            {
                "fields": ("allowed_groups",),
                "description": (
                    "Restrict this category to specific groups. "
                    "Leave empty to allow all authenticated users."
                ),
            },
        ),
    )


class StageApprovalGroupInline(nested_admin.NestedTabularInline):
    """Inline for ordering approval groups within a stage."""

    model = StageApprovalGroup
    extra = 1
    ordering = ("position",)
    autocomplete_fields = ("group",)


class WorkflowStageInline(nested_admin.NestedStackedInline):
    """Inline for defining ordered stages on a WorkflowDefinition."""

    model = WorkflowStage
    extra = 0
    ordering = ("order",)
    inlines = [StageApprovalGroupInline]
    fields = (
        ("order", "name"),
        "approval_logic",
        "approve_label",
        "requires_manager_approval",
        ("assignee_form_field", "assignee_lookup_type"),
        "validate_assignee_group",
        ("allow_reassign", "allow_send_back"),
        "allow_edit_form_data",
        "trigger_conditions",
    )


class NotificationRuleInline(nested_admin.NestedStackedInline):
    """Unified notification rule inline.

    Replaces WorkflowNotificationInline and StageFormFieldNotificationInline
    with a single, generic inline that supports all event types and all
    recipient sources.
    """

    model = NotificationRule
    extra = 0
    fieldsets = (
        (
            None,
            {
                "fields": (
                    ("event", "stage"),
                    (
                        "notify_submitter",
                        "notify_stage_assignees",
                        "notify_stage_groups",
                    ),
                    ("email_field", "static_emails"),
                    "notify_groups",
                    "subject_template",
                )
            },
        ),
        (
            "Conditions (optional)",
            {
                "classes": ("collapse",),
                "description": (
                    "Leave blank to always send. "
                    "Use the same JSON format as stage trigger_conditions — "
                    'e.g. <code>{"operator":"AND","conditions":[{"field":"department","operator":"equals","value":"Graduate"}]}</code>'
                ),
                "fields": ("conditions",),
            },
        ),
    )


class WorkflowDefinitionInline(nested_admin.NestedStackedInline):
    """Inline for editing a WorkflowDefinition directly from the FormDefinition
    change page."""

    model = WorkflowDefinition
    extra = 0
    inlines = [WorkflowStageInline, NotificationRuleInline]
    fields = [
        "name_label",
        "requires_approval",
        "hide_approval_history",
        "collapse_parallel_stages",
        "trigger_conditions",
        "notification_cadence",
        (
            "notification_cadence_day",
            "notification_cadence_time",
            "notification_cadence_form_field",
        ),
        (
            "approval_deadline_days",
            "send_reminder_after_days",
            "auto_approve_after_days",
        ),
        ("allow_bulk_export", "allow_bulk_pdf_export"),
    ]


@admin.register(FormDefinition)
class FormDefinitionAdmin(nested_admin.NestedModelAdmin):
    list_display = (
        "name",
        "slug",
        "category",
        "is_active",
        "is_listed",
        "form_builder_link",
        "workflow_builder_link",
        "submission_count",
        "last_submission",
        "created_at",
        "clone_link",
    )
    list_filter = (
        "is_active",
        "is_listed",
        "requires_login",
        "allow_batch_import",
        "category",
    )
    list_select_related = ["category"]
    search_fields = ("name", "slug", "description")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("created_at", "updated_at", "created_by")
    inlines = [FormFieldInline, WorkflowDefinitionInline, ChangeHistoryInline]
    filter_horizontal = (
        "submit_groups",
        "view_groups",
        "admin_groups",
        "reviewer_groups",
    )
    change_form_template = "admin/django_forms_workflows/formdef_change_form.html"
    actions = ["clone_forms", "diff_forms", "export_as_json"]

    fieldsets = (
        (
            None,
            {
                "fields": (
                    ("name", "slug"),
                    "category",
                    "description",
                    "instructions",
                    ("is_active", "is_listed", "version"),
                )
            },
        ),
        (
            "Access Control",
            {
                "classes": ("collapse",),
                "fields": (
                    "requires_login",
                    "submit_groups",
                    "view_groups",
                    "admin_groups",
                    "reviewer_groups",
                ),
            },
        ),
        (
            "Behavior",
            {
                "classes": ("collapse",),
                "fields": (
                    "allow_save_draft",
                    "allow_withdrawal",
                    "allow_resubmit",
                    "allow_batch_import",
                ),
            },
        ),
        (
            "API Access",
            {
                "classes": ("collapse",),
                "fields": ("api_enabled",),
                "description": (
                    "Enable this form for REST API submission. Requires the API URLs "
                    "to be included in your project's <code>urls.py</code> and a valid "
                    "<strong>APIToken</strong> in the <code>Authorization: Bearer</code> "
                    "header. All existing submit_groups / view_groups permissions still apply."
                ),
            },
        ),
        (
            "Multi-Step & Auto-Save",
            {
                "classes": ("collapse",),
                "fields": (
                    "enable_multi_step",
                    "form_steps",
                    "enable_auto_save",
                    "auto_save_interval",
                ),
            },
        ),
        (
            "PDF Generation",
            {
                "fields": ("pdf_generation",),
                "description": (
                    "Control when users can download a PDF of their submission. "
                    "Requires the <code>xhtml2pdf</code> package to be installed."
                ),
            },
        ),
        (
            "Metadata",
            {
                "fields": ("created_at", "updated_at", "created_by"),
                "classes": ("collapse",),
            },
        ),
    )

    def form_builder_link(self, obj):
        """Display a link to the visual form builder"""
        if obj.pk:
            url = reverse("admin:form_builder_edit", args=[obj.pk])
            return format_html(
                '<a href="{}" class="button" target="_blank">'
                '<i class="bi bi-pencil-square"></i> Form Builder'
                "</a>",
                url,
            )
        return "-"

    form_builder_link.short_description = "Form Builder"

    def workflow_builder_link(self, obj):
        """Display a link to the visual workflow builder"""
        if obj.pk:
            url = reverse("admin:workflow_builder", args=[obj.pk])
            return format_html(
                '<a href="{}" class="button" target="_blank">'
                '<i class="bi bi-diagram-3"></i> Workflow'
                "</a>",
                url,
            )
        return "-"

    workflow_builder_link.short_description = "Workflow Builder"

    def clone_link(self, obj):
        """Display a link to clone the form"""
        if obj.pk:
            return format_html(
                '<a href="#" class="button clone-form-btn" data-form-id="{}" data-form-name="{}">'
                '<i class="bi bi-files"></i> Clone'
                "</a>",
                obj.pk,
                obj.name,
            )
        return "-"

    clone_link.short_description = "Clone"

    def submission_count(self, obj):
        """Show total submission count for the form."""
        return obj.submissions.count()

    submission_count.short_description = "Submissions"

    def last_submission(self, obj):
        """Show the most recent submission info."""
        last = obj.submissions.order_by("-created_at").first()
        if last:
            return format_html(
                "{}<br><small>{}</small>",
                last.submitter.username,
                last.created_at.strftime("%Y-%m-%d %H:%M"),
            )
        return "-"

    last_submission.short_description = "Last Submission"

    def save_model(self, request, obj, form, change):
        """Auto-set created_by on new form definitions."""
        if not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    def clone_forms(self, request, queryset):
        """Admin action to clone selected forms"""

        cloned_count = 0
        for form in queryset:
            try:
                # Use the clone view logic
                with transaction.atomic():
                    # Generate unique slug
                    base_slug = f"{form.slug}-copy"
                    slug = base_slug
                    counter = 1
                    while FormDefinition.objects.filter(slug=slug).exists():
                        slug = f"{base_slug}-{counter}"
                        counter += 1

                    # Clone the form definition
                    cloned_form = FormDefinition.objects.create(
                        name=f"{form.name} (Copy)",
                        slug=slug,
                        description=form.description,
                        instructions=form.instructions,
                        is_active=False,
                        is_listed=form.is_listed,
                        version=1,
                        requires_login=form.requires_login,
                        allow_save_draft=form.allow_save_draft,
                        allow_withdrawal=form.allow_withdrawal,
                        allow_resubmit=form.allow_resubmit,
                        allow_batch_import=form.allow_batch_import,
                        created_by=request.user,
                    )

                    # Clone all fields
                    for field in form.fields.all().order_by("order"):
                        FormField.objects.create(
                            form_definition=cloned_form,
                            order=field.order,
                            field_name=field.field_name,
                            field_label=field.field_label,
                            field_type=field.field_type,
                            required=field.required,
                            help_text=field.help_text,
                            placeholder=field.placeholder,
                            width=field.width,
                            css_class=field.css_class,
                            choices=field.choices,
                            default_value=field.default_value,
                            prefill_source_config=field.prefill_source_config,
                            min_value=field.min_value,
                            max_value=field.max_value,
                            min_length=field.min_length,
                            max_length=field.max_length,
                            regex_validation=field.regex_validation,
                            regex_error_message=field.regex_error_message,
                            conditional_rules=field.conditional_rules,
                            allowed_extensions=field.allowed_extensions,
                            max_file_size_mb=field.max_file_size_mb,
                        )

                    # Copy group permissions
                    cloned_form.submit_groups.set(form.submit_groups.all())
                    cloned_form.view_groups.set(form.view_groups.all())
                    cloned_form.admin_groups.set(form.admin_groups.all())
                    cloned_form.reviewer_groups.set(form.reviewer_groups.all())

                    # Clone workflows, stages, and stage approval groups
                    for wf in form.workflows.all():
                        original_stages = list(
                            wf.stages.prefetch_related("approval_groups").order_by(
                                "order"
                            )
                        )
                        cloned_wf = WorkflowDefinition.objects.create(
                            form_definition=cloned_form,
                            name_label=wf.name_label,
                            requires_approval=wf.requires_approval,
                            approval_deadline_days=wf.approval_deadline_days,
                            send_reminder_after_days=wf.send_reminder_after_days,
                            auto_approve_after_days=wf.auto_approve_after_days,
                            notification_cadence=wf.notification_cadence,
                            notification_cadence_day=wf.notification_cadence_day,
                            notification_cadence_time=wf.notification_cadence_time,
                            notification_cadence_form_field=wf.notification_cadence_form_field,
                            visual_workflow_data=wf.visual_workflow_data,
                            trigger_conditions=wf.trigger_conditions,
                            hide_approval_history=wf.hide_approval_history,
                            collapse_parallel_stages=wf.collapse_parallel_stages,
                            allow_bulk_export=wf.allow_bulk_export,
                            allow_bulk_pdf_export=wf.allow_bulk_pdf_export,
                        )
                        for stage in original_stages:
                            cloned_stage = WorkflowStage.objects.create(
                                workflow=cloned_wf,
                                name=stage.name,
                                order=stage.order,
                                approval_logic=stage.approval_logic,
                                requires_manager_approval=stage.requires_manager_approval,
                                approve_label=stage.approve_label,
                                trigger_conditions=stage.trigger_conditions,
                                assignee_form_field=stage.assignee_form_field,
                                assignee_lookup_type=stage.assignee_lookup_type,
                                validate_assignee_group=stage.validate_assignee_group,
                                allow_reassign=stage.allow_reassign,
                                allow_send_back=stage.allow_send_back,
                            )
                            for sag in StageApprovalGroup.objects.filter(
                                stage=stage
                            ).order_by("position"):
                                StageApprovalGroup.objects.create(
                                    stage=cloned_stage,
                                    group=sag.group,
                                    position=sag.position,
                                )
                        # Clone SubWorkflowDefinition if present
                        try:
                            swc = wf.sub_workflow_config
                            SubWorkflowDefinition.objects.create(
                                parent_workflow=cloned_wf,
                                sub_workflow=swc.sub_workflow,
                                count_field=swc.count_field,
                                section_label=swc.section_label,
                                label_template=swc.label_template,
                                trigger=swc.trigger,
                                data_prefix=swc.data_prefix,
                            )
                        except SubWorkflowDefinition.DoesNotExist:
                            logger.debug(
                                "SubWorkflowDefinition not found during clone; skipping component"
                            )

                    cloned_count += 1
            except Exception as e:
                self.message_user(
                    request,
                    f'Error cloning form "{form.name}": {str(e)}',
                    level="ERROR",
                )

        if cloned_count > 0:
            self.message_user(
                request, f"Successfully cloned {cloned_count} form(s)", level="SUCCESS"
            )

    clone_forms.short_description = "Clone selected forms"

    @admin.action(description="Diff selected forms")
    def diff_forms(self, request, queryset):
        """Admin action: compare selected FormDefinitions side-by-side."""
        if queryset.count() < 2:
            self.message_user(
                request, "Select at least 2 forms to diff.", level="error"
            )
            return None
        pks = ",".join(str(pk) for pk in queryset.values_list("pk", flat=True))
        from django.urls import reverse

        url = reverse("admin:form_diff") + f"?pks={pks}"
        return HttpResponseRedirect(url)

    @admin.action(description="Export selected forms as JSON")
    def export_as_json(self, request, queryset):
        """Admin action: download selected FormDefinitions as a JSON file."""
        from .sync_api import build_export_payload

        payload = build_export_payload(queryset)
        filename = "forms_export.json"
        response = HttpResponse(
            json.dumps(payload, indent=2),
            content_type="application/json",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    def sync_import_admin_view(self, request):
        """Admin page for importing form definitions from a JSON file or raw JSON."""
        from .sync_api import import_payload

        context = dict(self.admin_site.each_context(request))
        context["title"] = "Import Form Definitions"
        context["opts"] = self.model._meta

        if request.method == "POST":
            conflict = request.POST.get("conflict", "update")
            json_text = request.POST.get("json_text", "").strip()
            uploaded = request.FILES.get("json_file")

            raw = None
            if uploaded:
                try:
                    raw = uploaded.read().decode("utf-8")
                except Exception as exc:
                    context["error"] = f"Could not read uploaded file: {exc}"
                    return render(
                        request,
                        "admin/django_forms_workflows/sync_import.html",
                        context,
                    )
            elif json_text:
                raw = json_text

            if not raw:
                context["error"] = "Please upload a JSON file or paste JSON text."
                return render(
                    request, "admin/django_forms_workflows/sync_import.html", context
                )

            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                context["error"] = f"Invalid JSON: {exc}"
                return render(
                    request, "admin/django_forms_workflows/sync_import.html", context
                )

            try:
                results = import_payload(payload, conflict=conflict)
            except Exception as exc:
                context["error"] = f"Import failed: {exc}"
                return render(
                    request, "admin/django_forms_workflows/sync_import.html", context
                )

            counts = {"created": 0, "updated": 0, "skipped": 0}
            for _, action in results:
                counts[action] = counts.get(action, 0) + 1

            context["results"] = results
            context["counts"] = counts

        return render(request, "admin/django_forms_workflows/sync_import.html", context)

    # ── Push/Pull admin actions & views ───────────────────────────────────────

    def sync_pull_admin_view(self, request):
        """Multi-step admin page for pulling form definitions from a remote instance.

        Step 0 (GET)  – show remote picker (configured remotes + manual URL/token)
        Step 1 (POST) – fetch available forms from the remote, show checkbox list
        Step 2 (POST) – import selected forms, show results
        """
        from .sync_api import (
            build_export_payload,
            fetch_remote_payload,
            get_sync_remotes,
            import_payload,
        )

        context = dict(self.admin_site.each_context(request))
        context["title"] = "Pull Forms from Remote"
        context["opts"] = self.model._meta
        context["remotes"] = get_sync_remotes()
        context["step"] = 0

        if request.method == "POST":
            step = request.POST.get("step", "1")

            # ── Step 1: fetch remote form list ──────────────────────────────
            if step == "1":
                remote_idx = request.POST.get("remote_idx", "")
                manual_url = request.POST.get("manual_url", "").strip()
                manual_token = request.POST.get("manual_token", "").strip()

                if remote_idx != "":
                    try:
                        remote = context["remotes"][int(remote_idx)]
                        remote_url = remote["url"]
                        remote_token = remote["token"]
                        remote_name = remote.get("name", remote_url)
                    except (IndexError, KeyError, ValueError):
                        context["error"] = "Invalid remote selection."
                        return render(
                            request,
                            "admin/django_forms_workflows/sync_pull.html",
                            context,
                        )
                elif manual_url and manual_token:
                    remote_url = manual_url
                    remote_token = manual_token
                    remote_name = manual_url
                else:
                    context["error"] = (
                        "Please select a configured remote or enter a URL and token."
                    )
                    return render(
                        request, "admin/django_forms_workflows/sync_pull.html", context
                    )

                try:
                    payload = fetch_remote_payload(remote_url, remote_token)
                except Exception as exc:
                    context["error"] = f"Could not connect to remote: {exc}"
                    return render(
                        request, "admin/django_forms_workflows/sync_pull.html", context
                    )

                remote_forms = payload.get("forms", [])

                # Build per-form diffs: remote vs local
                import json

                from .diff_views import _build_summary

                form_diffs = []
                for rf in remote_forms:
                    slug = rf.get("form", {}).get("slug", "")
                    local_fd = FormDefinition.objects.filter(slug=slug).first()
                    if local_fd:
                        local_payload = build_export_payload(
                            FormDefinition.objects.filter(pk=local_fd.pk)
                        )
                        local_data = (
                            local_payload["forms"][0]
                            if local_payload.get("forms")
                            else {}
                        )
                        local_json = json.dumps(local_data, indent=2, default=str)
                        remote_json = json.dumps(rf, indent=2, default=str)
                        summary = _build_summary([local_data, rf])
                        form_diffs.append(
                            {
                                "slug": slug,
                                "local_json": local_json,
                                "remote_json": remote_json,
                                "summary": summary[0] if summary else None,
                                "is_new": False,
                            }
                        )
                    else:
                        form_diffs.append({"slug": slug, "is_new": True})

                context["step"] = 1
                context["remote_url"] = remote_url
                context["remote_token"] = remote_token
                context["remote_name"] = remote_name
                context["remote_forms"] = remote_forms
                context["form_diffs"] = form_diffs
                return render(
                    request, "admin/django_forms_workflows/sync_pull.html", context
                )

            # ── Step 2: import selected forms ───────────────────────────────
            if step == "2":
                remote_url = request.POST.get("remote_url", "").strip()
                remote_token = request.POST.get("remote_token", "").strip()
                selected_slugs = request.POST.getlist("slugs")
                conflict = request.POST.get("conflict", "update")

                if not selected_slugs:
                    context["error"] = "No forms selected."
                    context["step"] = 0
                    return render(
                        request, "admin/django_forms_workflows/sync_pull.html", context
                    )

                try:
                    payload = fetch_remote_payload(
                        remote_url, remote_token, slugs=selected_slugs
                    )
                except Exception as exc:
                    context["error"] = f"Could not fetch selected forms: {exc}"
                    context["step"] = 0
                    return render(
                        request, "admin/django_forms_workflows/sync_pull.html", context
                    )

                try:
                    results = import_payload(payload, conflict=conflict)
                except Exception as exc:
                    context["error"] = f"Import failed: {exc}"
                    context["step"] = 0
                    return render(
                        request, "admin/django_forms_workflows/sync_pull.html", context
                    )

                counts = {"created": 0, "updated": 0, "skipped": 0}
                for _, action in results:
                    counts[action] = counts.get(action, 0) + 1

                context["step"] = 2
                context["results"] = results
                context["counts"] = counts
                return render(
                    request, "admin/django_forms_workflows/sync_pull.html", context
                )

        return render(request, "admin/django_forms_workflows/sync_pull.html", context)

    def sync_push_admin_view(self, request):
        """Multi-step admin page for pushing form definitions to a remote.

        Mirrors the pull flow:
        Step 0 (GET)  – show remote picker (configured remotes + manual URL/token)
        Step 1 (POST) – show all local forms with checkboxes + diff status
        Step 2 (POST) – execute push for selected forms, show results
        """
        from .sync_api import (
            build_export_payload,
            fetch_remote_payload,
            get_sync_remotes,
            push_to_remote,
        )

        context = dict(self.admin_site.each_context(request))
        context["title"] = "Push Forms to Remote"
        context["opts"] = self.model._meta
        context["remotes"] = get_sync_remotes()
        context["step"] = 0

        if request.method == "POST":
            step = request.POST.get("step", "1")

            # ── Step 1: show local forms with diff status ────────────────
            if step == "1":
                remote_idx = request.POST.get("remote_idx", "")
                manual_url = request.POST.get("manual_url", "").strip()
                manual_token = request.POST.get("manual_token", "").strip()
                conflict = request.POST.get("conflict", "update")

                if remote_idx != "":
                    try:
                        remote = context["remotes"][int(remote_idx)]
                        remote_url = remote["url"]
                        remote_token = remote["token"]
                        remote_name = remote.get("name", remote_url)
                    except (IndexError, KeyError, ValueError):
                        context["error"] = "Invalid remote selection."
                        return render(
                            request,
                            "admin/django_forms_workflows/sync_push.html",
                            context,
                        )
                elif manual_url and manual_token:
                    remote_url = manual_url
                    remote_token = manual_token
                    remote_name = manual_url
                else:
                    context["error"] = (
                        "Please select a configured remote or enter a URL and token."
                    )
                    return render(
                        request,
                        "admin/django_forms_workflows/sync_push.html",
                        context,
                    )

                # Build per-form diffs: local vs remote

                from .diff_views import _build_summary

                local_qs = self.model.objects.all()
                local_payload = build_export_payload(local_qs)
                local_forms = local_payload.get("forms", [])

                try:
                    remote_payload = fetch_remote_payload(remote_url, remote_token)
                    remote_forms_list = remote_payload.get("forms", [])
                except Exception:
                    remote_forms_list = []

                remote_by_slug = {
                    f.get("form", {}).get("slug"): f for f in remote_forms_list
                }
                form_diffs = []
                for lf in local_forms:
                    slug = lf.get("form", {}).get("slug", "")
                    name = lf.get("form", {}).get("name", slug)
                    rf = remote_by_slug.get(slug)
                    if rf:
                        summary = _build_summary([rf, lf])
                        form_diffs.append(
                            {
                                "slug": slug,
                                "name": name,
                                "summary": summary[0] if summary else None,
                                "is_new": False,
                            }
                        )
                    else:
                        form_diffs.append({"slug": slug, "name": name, "is_new": True})

                context["step"] = 1
                context["remote_url"] = remote_url
                context["remote_token"] = remote_token
                context["remote_name"] = remote_name
                context["conflict"] = conflict
                context["local_forms"] = local_forms
                context["form_diffs"] = form_diffs
                return render(
                    request,
                    "admin/django_forms_workflows/sync_push.html",
                    context,
                )

            # ── Step 2: push selected forms ──────────────────────────────
            if step == "2":
                remote_url = request.POST.get("remote_url", "").strip()
                remote_token = request.POST.get("remote_token", "").strip()
                remote_name = request.POST.get("remote_name", remote_url)
                conflict = request.POST.get("conflict", "update")
                selected_slugs = request.POST.getlist("slugs")

                if not selected_slugs:
                    context["error"] = "No forms selected."
                    return render(
                        request,
                        "admin/django_forms_workflows/sync_push.html",
                        context,
                    )

                queryset = self.model.objects.filter(slug__in=selected_slugs)
                try:
                    result = push_to_remote(
                        remote_url, remote_token, queryset, conflict=conflict
                    )
                except Exception as exc:
                    context["error"] = f"Push failed: {exc}"
                    return render(
                        request,
                        "admin/django_forms_workflows/sync_push.html",
                        context,
                    )

                # Normalize the remote API response into the flat shape the
                # template expects: {created, updated, skipped, results: [...]}
                name_map = {fd.slug: fd.name for fd in queryset}
                raw_counts = result.get("counts", {})
                context["push_result"] = {
                    "created": raw_counts.get("created", 0),
                    "updated": raw_counts.get("updated", 0),
                    "skipped": raw_counts.get("skipped", 0),
                    "results": [
                        {
                            "slug": f["slug"],
                            "name": name_map.get(f["slug"], f["slug"]),
                            "action": f["action"],
                        }
                        for f in result.get("forms", [])
                    ],
                }
                context["step"] = 2
                context["remote_name"] = remote_name
                return render(
                    request,
                    "admin/django_forms_workflows/sync_push.html",
                    context,
                )

        return render(request, "admin/django_forms_workflows/sync_push.html", context)

    def get_urls(self):
        """Add custom URLs for the form builder and workflow builder"""
        urls = super().get_urls()
        from . import diff_views, form_builder_views, workflow_builder_views

        custom_urls = [
            # Diff view
            path(
                "diff/",
                self.admin_site.admin_view(diff_views.diff_forms_view),
                name="form_diff",
            ),
            # Form Builder URLs
            path(
                "builder/new/",
                self.admin_site.admin_view(form_builder_views.form_builder_view),
                name="form_builder_new",
            ),
            path(
                "builder/<int:form_id>/",
                self.admin_site.admin_view(form_builder_views.form_builder_view),
                name="form_builder_edit",
            ),
            path(
                "builder/api/load/<int:form_id>/",
                self.admin_site.admin_view(form_builder_views.form_builder_load),
                name="form_builder_api_load",
            ),
            path(
                "builder/api/save/",
                self.admin_site.admin_view(form_builder_views.form_builder_save),
                name="form_builder_api_save",
            ),
            path(
                "builder/api/preview/",
                self.admin_site.admin_view(form_builder_views.form_builder_preview),
                name="form_builder_api_preview",
            ),
            path(
                "builder/api/templates/",
                self.admin_site.admin_view(form_builder_views.form_builder_templates),
                name="form_builder_api_templates",
            ),
            path(
                "builder/api/templates/<int:template_id>/",
                self.admin_site.admin_view(
                    form_builder_views.form_builder_load_template
                ),
                name="form_builder_api_load_template",
            ),
            path(
                "builder/api/clone/<int:form_id>/",
                self.admin_site.admin_view(form_builder_views.form_builder_clone),
                name="form_builder_api_clone",
            ),
            # Workflow Builder URLs
            path(
                "<int:form_id>/workflow/",
                self.admin_site.admin_view(
                    workflow_builder_views.workflow_builder_view
                ),
                name="workflow_builder",
            ),
            path(
                "workflow/api/load/<int:form_id>/",
                self.admin_site.admin_view(
                    workflow_builder_views.workflow_builder_load
                ),
                name="workflow_builder_load",
            ),
            path(
                "workflow/api/save/",
                self.admin_site.admin_view(
                    workflow_builder_views.workflow_builder_save
                ),
                name="workflow_builder_save",
            ),
            # Sync URLs
            path(
                "sync-import/",
                self.admin_site.admin_view(self.sync_import_admin_view),
                name="formdefinition_sync_import",
            ),
            path(
                "sync-pull/",
                self.admin_site.admin_view(self.sync_pull_admin_view),
                name="formdefinition_sync_pull",
            ),
            path(
                "sync-push/",
                self.admin_site.admin_view(self.sync_push_admin_view),
                name="formdefinition_sync_push",
            ),
        ]
        return custom_urls + urls


@admin.register(WorkflowStage)
class WorkflowStageAdmin(nested_admin.NestedModelAdmin):
    """Standalone admin for WorkflowStage.

    Stages at the same ``order`` value run in parallel — create one stage
    per group that needs its own approve_label or approval fields.
    """

    list_display = (
        "__str__",
        "workflow",
        "order",
        "approval_logic",
        "approve_label",
        "requires_manager_approval",
        "has_trigger_conditions",
    )
    list_filter = ("workflow", "approval_logic", "requires_manager_approval")
    list_select_related = ("workflow", "workflow__form_definition")
    search_fields = ("name", "workflow__form_definition__name")
    ordering = ("workflow", "order")
    inlines = [
        StageApprovalGroupInline,
        ChangeHistoryInline,
    ]
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "workflow",
                    ("order", "name"),
                    "approval_logic",
                    "approve_label",
                    "requires_manager_approval",
                )
            },
        ),
        (
            "Dynamic Assignment",
            {
                "classes": ("collapse",),
                "description": (
                    "When set, the workflow engine resolves the task assignee by looking up "
                    "the value stored in the specified form field. The lookup type controls "
                    "how the value is matched to a system user (email, username, full name, "
                    "or LDAP search). Falls back to the configured approval groups if the "
                    "field is empty or no matching user is found."
                ),
                "fields": (
                    "assignee_form_field",
                    "assignee_lookup_type",
                    "validate_assignee_group",
                    "allow_reassign",
                    "allow_send_back",
                ),
            },
        ),
        (
            "Editable Form Data",
            {
                "classes": ("collapse",),
                "description": (
                    "When enabled, approvers at this stage can edit the original "
                    "submission data instead of viewing it read-only."
                ),
                "fields": ("allow_edit_form_data",),
            },
        ),
        (
            "Conditional Trigger",
            {
                "classes": ("collapse",),
                "description": (
                    "When set, this stage only runs if the submission data matches these "
                    "conditions. Leave blank to always run this stage."
                ),
                "fields": ("trigger_conditions",),
            },
        ),
    )

    @admin.display(boolean=True, description="Has trigger conditions")
    def has_trigger_conditions(self, obj):
        return bool(obj.trigger_conditions)


@admin.register(WorkflowDefinition)
class WorkflowDefinitionAdmin(nested_admin.NestedModelAdmin):
    inlines = [
        WorkflowStageInline,
        NotificationRuleInline,
        ChangeHistoryInline,
    ]
    list_display = (
        "form_definition",
        "requires_approval",
        "hide_approval_history",
        "notification_rule_count",
        "allow_bulk_export",
        "allow_bulk_pdf_export",
    )
    list_filter = (
        "requires_approval",
        "hide_approval_history",
        "allow_bulk_export",
        "allow_bulk_pdf_export",
    )
    search_fields = ("form_definition__name",)
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "form_definition",
                    "name_label",
                    "requires_approval",
                    "hide_approval_history",
                    "collapse_parallel_stages",
                    "trigger_conditions",
                )
            },
        ),
        (
            "Timeouts",
            {
                "classes": ("collapse",),
                "fields": (
                    "approval_deadline_days",
                    "send_reminder_after_days",
                    "auto_approve_after_days",
                ),
            },
        ),
        (
            "Notification Batching",
            {
                "classes": ("collapse",),
                "description": (
                    "Control <em>when</em> approval-request and submission-received "
                    "notifications are sent. Non-immediate cadences queue notifications "
                    "and send a single digest email when the schedule fires. "
                    "Requires the <code>send_batched_notifications</code> Celery Beat task to be running."
                ),
                "fields": (
                    "notification_cadence",
                    "notification_cadence_day",
                    "notification_cadence_time",
                    "notification_cadence_form_field",
                ),
            },
        ),
        (
            "Bulk Export",
            {
                "fields": ("allow_bulk_export", "allow_bulk_pdf_export"),
                "description": (
                    "When enabled, users can select multiple submissions from the "
                    "approval and submissions list views and export them to Excel or PDF."
                ),
            },
        ),
    )

    @admin.display(description="Notification rules")
    def notification_rule_count(self, obj):
        count = obj.notifications.count()
        if count == 0:
            return "—"
        return format_html(
            '<span style="background:#0d6efd;color:#fff;padding:1px 8px;'
            'border-radius:10px;font-size:12px;font-weight:600">{}</span>',
            count,
        )


@admin.register(NotificationRule)
class NotificationRuleAdmin(admin.ModelAdmin):
    """Standalone admin for NotificationRule — searchable across all workflows."""

    list_display = (
        "workflow_form",
        "event",
        "stage_name",
        "notify_submitter",
        "notify_stage_assignees",
        "notify_stage_groups",
        "email_field",
        "static_emails_truncated",
        "has_conditions",
    )
    list_filter = (
        "event",
        "notify_submitter",
        "notify_stage_assignees",
        "notify_stage_groups",
        "workflow__form_definition",
    )
    list_select_related = ("workflow__form_definition", "stage")
    search_fields = (
        "workflow__form_definition__name",
        "stage__name",
        "email_field",
        "static_emails",
    )
    autocomplete_fields = ("workflow",)
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "workflow",
                    ("event", "stage"),
                    (
                        "notify_submitter",
                        "notify_stage_assignees",
                        "notify_stage_groups",
                    ),
                    ("email_field", "static_emails"),
                    "notify_groups",
                    "subject_template",
                )
            },
        ),
        (
            "Conditions (optional)",
            {
                "description": (
                    "Leave blank to always send. "
                    "Use the same JSON format as stage trigger_conditions — "
                    'e.g. <code>{"operator":"AND","conditions":[{"field":"department","operator":"equals","value":"Graduate"}]}</code>'
                ),
                "fields": ("conditions",),
            },
        ),
    )

    @admin.display(
        description="Form / Workflow", ordering="workflow__form_definition__name"
    )
    def workflow_form(self, obj):
        return obj.workflow.form_definition.name if obj.workflow_id else "—"

    @admin.display(description="Stage", ordering="stage__name")
    def stage_name(self, obj):
        return obj.stage.name if obj.stage_id else "— (all stages)"

    @admin.display(description="Static emails")
    def static_emails_truncated(self, obj):
        if not obj.static_emails:
            return "—"
        return obj.static_emails[:60] + ("…" if len(obj.static_emails) > 60 else "")

    @admin.display(description="Conditions?", boolean=True)
    def has_conditions(self, obj):
        return bool(obj.conditions)


@admin.register(PostSubmissionAction)
class PostSubmissionActionAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "form_definition",
        "action_type",
        "trigger",
        "is_active",
        "order",
    )
    list_filter = (
        "action_type",
        "trigger",
        "is_active",
        "form_definition",
    )
    search_fields = (
        "name",
        "description",
        "form_definition__name",
    )
    list_editable = ("is_active", "order")
    ordering = ("form_definition", "order", "name")

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "form_definition",
                    "name",
                    "description",
                    ("action_type", "trigger"),
                    ("is_active", "order"),
                )
            },
        ),
        (
            "Database Update Configuration",
            {
                "classes": ("collapse",),
                "fields": (
                    ("db_alias", "db_schema", "db_table"),
                    ("db_lookup_field", "db_user_field"),
                    "db_field_mappings",
                ),
                "description": (
                    "Configure database updates. Field mappings format: "
                    '[{"form_field": "email", "db_column": "EMAIL_ADDRESS"}, ...]'
                ),
            },
        ),
        (
            "LDAP Update Configuration",
            {
                "classes": ("collapse",),
                "fields": (
                    "ldap_dn_template",
                    "ldap_field_mappings",
                ),
                "description": (
                    "Configure LDAP updates. Field mappings format: "
                    '[{"form_field": "phone", "ldap_attribute": "telephoneNumber"}, ...]'
                ),
            },
        ),
        (
            "API Call Configuration",
            {
                "classes": ("collapse",),
                "fields": (
                    ("api_endpoint", "api_method"),
                    "api_headers",
                    "api_body_template",
                ),
                "description": (
                    "Configure API calls. Use {field_name} in body template for form field values."
                ),
            },
        ),
        (
            "Custom Handler Configuration",
            {
                "classes": ("collapse",),
                "fields": (
                    "custom_handler_path",
                    "custom_handler_config",
                ),
                "description": (
                    "Python path to custom handler function (e.g., 'myapp.handlers.custom_update')"
                ),
            },
        ),
        (
            "Email Notification Configuration",
            {
                "classes": ("collapse",),
                "fields": (
                    ("email_to", "email_to_field"),
                    ("email_cc", "email_cc_field"),
                    "email_subject_template",
                    "email_body_template",
                    "email_template_name",
                ),
                "description": (
                    "Configure email notifications. Use {field_name} for form field values. "
                    "email_to_field reads recipient from a form field (e.g., 'instructor_email')."
                ),
            },
        ),
        (
            "Conditional Execution",
            {
                "classes": ("collapse",),
                "fields": (
                    "condition_field",
                    ("condition_operator", "condition_value"),
                    "is_locked",
                ),
                "description": (
                    "Execute this action only when the condition is met. "
                    "Use is_locked to prevent duplicate executions."
                ),
            },
        ),
        (
            "Error Handling",
            {
                "classes": ("collapse",),
                "fields": (
                    "fail_silently",
                    ("retry_on_failure", "max_retries"),
                ),
            },
        ),
        (
            "Metadata",
            {
                "classes": ("collapse",),
                "fields": (
                    "created_at",
                    "updated_at",
                ),
            },
        ),
    )

    readonly_fields = ("created_at", "updated_at")


@admin.register(ActionExecutionLog)
class ActionExecutionLogAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "action",
        "submission",
        "trigger",
        "success",
        "executed_at",
    )
    list_filter = ("success", "trigger", "action__action_type")
    search_fields = (
        "action__name",
        "submission__id",
        "message",
    )
    readonly_fields = (
        "action",
        "submission",
        "trigger",
        "success",
        "message",
        "executed_at",
        "execution_data",
    )
    ordering = ("-executed_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(FormSubmission)
class FormSubmissionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "form_definition",
        "submitter",
        "status",
        "created_at",
        "submitted_at",
        "completed_at",
    )
    list_filter = ("status", "form_definition")
    date_hierarchy = "created_at"
    search_fields = (
        "id",
        "form_definition__name",
        "submitter__username",
        "submitter__email",
    )
    raw_id_fields = ("submitter",)
    readonly_fields = ("created_at", "submitted_at", "completed_at")
    inlines = [ChangeHistoryInline]


@admin.register(ApprovalTask)
class ApprovalTaskAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "submission",
        "step_name",
        "status",
        "assigned_to",
        "assigned_group",
        "due_date",
        "completed_at",
    )
    list_filter = ("status", "step_name", "assigned_group")
    search_fields = (
        "submission__id",
        "submission__form_definition__name",
        "assigned_to__username",
    )
    raw_id_fields = ("submission", "assigned_to", "completed_by")
    readonly_fields = ("created_at", "reminder_sent_at")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user", "action", "object_type", "object_id")
    list_filter = ("action", "object_type")
    date_hierarchy = "created_at"
    search_fields = (
        "user__username",
        "object_type",
        "object_id",
        "comments",
    )
    readonly_fields = (
        "created_at",
        "user",
        "action",
        "object_type",
        "object_id",
        "user_ip",
        "changes",
        "comments",
    )


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "department", "title", "employee_id")
    search_fields = ("user__username", "user__email", "department", "title")
    raw_id_fields = ("user", "manager")
    list_filter = ("department",)


@admin.register(FormTemplate)
class FormTemplateAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "category",
        "usage_count",
        "is_active",
        "is_system",
        "created_at",
    )
    list_filter = ("category", "is_active", "is_system")
    search_fields = ("name", "description", "slug")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("usage_count", "created_at", "updated_at", "created_by")

    fieldsets = (
        (
            "Basic Information",
            {"fields": ("name", "slug", "description", "category")},
        ),
        (
            "Template Data",
            {
                "fields": ("template_data",),
                "description": "JSON structure containing form definition and fields",
            },
        ),
        (
            "Preview",
            {
                "fields": ("preview_url",),
                "classes": ("collapse",),
            },
        ),
        (
            "Status",
            {
                "fields": ("is_active", "is_system"),
            },
        ),
        (
            "Metadata",
            {
                "fields": ("usage_count", "created_at", "updated_at", "created_by"),
                "classes": ("collapse",),
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        """Set created_by on new templates"""
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


# --- File Upload Configuration Admin ---


@admin.register(FileUploadConfig)
class FileUploadConfigAdmin(admin.ModelAdmin):
    """Admin for file upload configurations."""

    list_display = (
        "name",
        "naming_pattern",
        "upload_to",
        "enable_versioning",
        "is_active",
    )
    list_filter = ("is_active", "enable_versioning")
    search_fields = ("name", "description", "naming_pattern")
    list_editable = ("is_active",)
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        (
            None,
            {
                "fields": ("name", "description", "is_active"),
            },
        ),
        (
            "Naming Pattern",
            {
                "fields": (
                    "naming_pattern",
                    "pending_prefix",
                    "approved_prefix",
                    "rejected_prefix",
                ),
                "description": "Tokens: {user.id}, {user.username}, {user.employee_id}, "
                "{field_name}, {form_slug}, {submission_id}, {status}, {date}, "
                "{datetime}, {original_name}, {ext}",
            },
        ),
        (
            "Storage Settings",
            {
                "fields": (
                    "upload_to",
                    "approved_storage_path",
                    "rejected_storage_path",
                ),
            },
        ),
        (
            "File Restrictions",
            {
                "fields": (
                    "allowed_extensions",
                    "max_file_size_mb",
                    "allowed_mime_types",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Versioning",
            {
                "fields": ("enable_versioning", "max_versions"),
                "classes": ("collapse",),
            },
        ),
        (
            "Metadata",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )


class FileWorkflowHookInline(admin.TabularInline):
    """Inline for file workflow hooks on FileUploadConfig."""

    model = FileWorkflowHook
    extra = 0
    fields = ("name", "trigger", "action", "order", "is_active")
    ordering = ("order", "name")


@admin.register(FileWorkflowHook)
class FileWorkflowHookAdmin(admin.ModelAdmin):
    """Admin for file workflow hooks."""

    list_display = (
        "name",
        "trigger",
        "action",
        "form_definition",
        "upload_config",
        "order",
        "is_active",
    )
    list_filter = ("trigger", "action", "is_active", "form_definition")
    search_fields = ("name", "description", "webhook_url")
    list_editable = ("order", "is_active")
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ("form_definition", "upload_config")

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "name",
                    "description",
                    "is_active",
                    "order",
                ),
            },
        ),
        (
            "Scope",
            {
                "fields": (
                    "form_definition",
                    "upload_config",
                    "field_name",
                ),
                "description": "Leave empty to apply to all forms/configs/fields.",
            },
        ),
        (
            "Trigger & Action",
            {
                "fields": ("trigger", "action"),
            },
        ),
        (
            "File Operations",
            {
                "fields": ("target_pattern",),
                "classes": ("collapse",),
                "description": "For rename/move/copy actions. Supports naming pattern tokens.",
            },
        ),
        (
            "Webhook/API Configuration",
            {
                "fields": (
                    "webhook_url",
                    "webhook_method",
                    "webhook_headers",
                    "webhook_payload_template",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Custom Handler",
            {
                "fields": (
                    "custom_handler_path",
                    "custom_handler_config",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Conditional Execution",
            {
                "fields": (
                    "condition_field",
                    "condition_operator",
                    "condition_value",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Error Handling",
            {
                "fields": (
                    "fail_silently",
                    "retry_on_failure",
                    "max_retries",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Metadata",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )


@admin.register(ManagedFile)
class ManagedFileAdmin(admin.ModelAdmin):
    """Admin for managed files."""

    list_display = (
        "original_filename",
        "submission_link",
        "status",
        "version",
        "is_current",
        "file_size_display",
        "uploaded_by",
        "uploaded_at",
    )
    list_filter = ("status", "is_current", "uploaded_at")
    search_fields = (
        "original_filename",
        "stored_filename",
        "submission__id",
        "uploaded_by__username",
    )
    readonly_fields = (
        "submission",
        "form_field",
        "upload_config",
        "original_filename",
        "stored_filename",
        "file_path",
        "file_size",
        "mime_type",
        "file_hash",
        "version",
        "previous_version",
        "uploaded_by",
        "uploaded_at",
        "updated_at",
        "status_changed_at",
        "status_changed_by",
    )
    autocomplete_fields = ("submission",)

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "submission",
                    "form_field",
                    "upload_config",
                ),
            },
        ),
        (
            "File Information",
            {
                "fields": (
                    "original_filename",
                    "stored_filename",
                    "file_path",
                    "file_size",
                    "mime_type",
                    "file_hash",
                ),
            },
        ),
        (
            "Status",
            {
                "fields": (
                    "status",
                    "status_changed_at",
                    "status_changed_by",
                    "status_notes",
                ),
            },
        ),
        (
            "Versioning",
            {
                "fields": (
                    "version",
                    "previous_version",
                    "is_current",
                ),
            },
        ),
        (
            "Metadata",
            {
                "fields": (
                    "uploaded_by",
                    "uploaded_at",
                    "updated_at",
                    "metadata",
                ),
            },
        ),
    )

    def submission_link(self, obj):
        """Link to the submission."""
        url = reverse(
            "admin:django_forms_workflows_formsubmission_change",
            args=[obj.submission.id],
        )
        return format_html(
            '<a href="{}">{}</a>', url, f"Submission #{obj.submission.id}"
        )

    submission_link.short_description = "Submission"

    def file_size_display(self, obj):
        """Display file size in human-readable format."""
        if obj.file_size < 1024:
            return f"{obj.file_size} B"
        if obj.file_size < 1024 * 1024:
            return f"{obj.file_size / 1024:.1f} KB"
        return f"{obj.file_size / (1024 * 1024):.1f} MB"

    file_size_display.short_description = "Size"

    actions = ["mark_approved", "mark_rejected"]

    @admin.action(description="Mark selected files as approved")
    def mark_approved(self, request, queryset):
        for managed_file in queryset.filter(status="pending"):
            managed_file.mark_approved(user=request.user, notes="Approved via admin")
        self.message_user(request, f"Marked {queryset.count()} files as approved.")

    @admin.action(description="Mark selected files as rejected")
    def mark_rejected(self, request, queryset):
        for managed_file in queryset.filter(status="pending"):
            managed_file.mark_rejected(user=request.user, notes="Rejected via admin")
        self.message_user(request, f"Marked {queryset.count()} files as rejected.")


# ── Custom Group admin with LDAP indicator ────────────────────────────────────


class LDAPGroupProfileInline(admin.TabularInline):
    """Read-only inline showing LDAP metadata for a group."""

    model = LDAPGroupProfile
    extra = 0
    max_num = 1
    readonly_fields = ("ldap_dn", "last_synced")
    can_delete = False
    verbose_name = "LDAP Profile"
    verbose_name_name = "LDAP Profile"

    def has_add_permission(self, request, obj=None):
        return False


class LDAPManagedFilter(admin.SimpleListFilter):
    """Filter groups by whether they are LDAP-managed or Django-only."""

    title = "Origin"
    parameter_name = "ldap_managed"

    def lookups(self, request, model_admin):
        return (
            ("yes", "LDAP-managed"),
            ("no", "Django-only"),
        )

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.filter(ldap_profile__isnull=False)
        if self.value() == "no":
            return queryset.filter(ldap_profile__isnull=True)
        return queryset


admin.site.unregister(Group)


@admin.register(Group)
class CustomGroupAdmin(GroupAdmin):
    """Extended Group admin showing LDAP vs Django-only origin."""

    inlines = [LDAPGroupProfileInline]
    list_display = ("name", "ldap_badge", "user_count")
    list_filter = (LDAPManagedFilter,)

    def ldap_badge(self, obj):
        try:
            obj.ldap_profile  # noqa: B018  — intentional attribute access
            return mark_safe(
                '<span style="'
                "background:#2e7d32;color:#fff;padding:2px 8px;"
                'border-radius:10px;font-size:0.8em;">LDAP</span>'
            )
        except LDAPGroupProfile.DoesNotExist:
            return mark_safe(
                '<span style="'
                "background:#bdbdbd;color:#fff;padding:2px 8px;"
                'border-radius:10px;font-size:0.8em;">Django</span>'
            )

    ldap_badge.short_description = "Origin"
    ldap_badge.allow_tags = True

    def user_count(self, obj):
        return obj.user_set.count()

    user_count.short_description = "Users"


class SubWorkflowInstanceInline(admin.TabularInline):
    model = SubWorkflowInstance
    extra = 0
    readonly_fields = ("index", "status", "created_at", "completed_at")
    can_delete = False


@admin.register(SubWorkflowDefinition)
class SubWorkflowDefinitionAdmin(admin.ModelAdmin):
    list_display = (
        "parent_workflow",
        "sub_workflow",
        "count_field",
        "trigger",
        "label_template",
    )
    list_filter = ("trigger",)
    raw_id_fields = ("parent_workflow", "sub_workflow")


@admin.register(SubWorkflowInstance)
class SubWorkflowInstanceAdmin(admin.ModelAdmin):
    list_display = (
        "label",
        "parent_submission",
        "index",
        "status",
        "created_at",
        "completed_at",
    )
    list_filter = ("status",)
    search_fields = ("parent_submission__id",)
    readonly_fields = ("created_at", "updated_at", "completed_at")
    raw_id_fields = ("parent_submission", "definition")


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "notification_type",
        "status",
        "recipient_email",
        "subject",
        "submission",
    )
    list_filter = ("notification_type", "status")
    search_fields = ("recipient_email", "subject", "submission__id")
    readonly_fields = (
        "notification_type",
        "submission",
        "recipient_email",
        "subject",
        "status",
        "error_message",
        "created_at",
    )
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(APIToken)
class APITokenAdmin(admin.ModelAdmin):
    """
    Manage REST API personal access tokens.

    Tokens are created here by admins and handed to the consumer
    (CI pipelines, mobile apps, etc.).  The raw UUID is shown only once
    on the change page — copy it immediately after creation.
    """

    list_display = (
        "name",
        "user",
        "short_token",
        "is_active",
        "created_at",
        "last_used_at",
    )
    list_filter = ("is_active",)
    search_fields = ("name", "user__username", "user__email")
    readonly_fields = ("token", "created_at", "last_used_at")
    autocomplete_fields = ("user",)
    ordering = ("-created_at",)

    fieldsets = (
        (
            None,
            {
                "fields": ("user", "name", "is_active"),
            },
        ),
        (
            "Token",
            {
                "fields": ("token",),
                "description": (
                    "Copy this value now — it is shown in plain text here but "
                    "treat it like a password. Send it as:<br>"
                    "<code>Authorization: Bearer &lt;token&gt;</code>"
                ),
            },
        ),
        (
            "Audit",
            {
                "classes": ("collapse",),
                "fields": ("created_at", "last_used_at"),
            },
        ),
    )

    @admin.display(description="Token (prefix)")
    def short_token(self, obj):
        token_str = str(obj.token)
        return f"{token_str[:8]}…"


@admin.register(ChangeHistory)
class ChangeHistoryAdmin(admin.ModelAdmin):
    list_display = (
        "timestamp",
        "action",
        "content_type",
        "object_id",
        "user",
        "summary",
    )
    list_filter = ("action", "content_type", "timestamp")
    date_hierarchy = "timestamp"
    search_fields = ("summary", "user__username", "user__first_name", "user__last_name")
    readonly_fields = (
        "content_type",
        "object_id",
        "action",
        "timestamp",
        "user",
        "summary",
        "changes",
    )
    ordering = ("-timestamp",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
