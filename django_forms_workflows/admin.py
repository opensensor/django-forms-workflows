"""
Django admin for Django Forms Workflows

Provides a friendly admin interface to build forms (with fields),
configure approval workflows, and review submissions and audit logs.
"""

import json

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
    ApprovalTask,
    AuditLog,
    FileUploadConfig,
    FileWorkflowHook,
    FormCategory,
    FormDefinition,
    FormField,
    FormSubmission,
    FormTemplate,
    LDAPGroupProfile,
    ManagedFile,
    PostSubmissionAction,
    PrefillSource,
    UserProfile,
    WorkflowDefinition,
    WorkflowStage,
    WorkflowStageGroupConfig,
)


# Inline for form fields when editing a form definition
class FormFieldInline(admin.StackedInline):
    model = FormField
    extra = 0
    ordering = ("order",)
    fk_name = "form_definition"
    fieldsets = (
        (
            None,
            {
                "fields": (
                    ("order", "field_label", "field_name", "field_type"),
                    ("required", "readonly"),
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
                    "prefill_source",
                    "default_value",
                ),
            },
        ),
        (
            "Conditional display",
            {
                "classes": ("collapse",),
                "fields": (("show_if_field", "show_if_value"),),
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


@admin.register(FormDefinition)
class FormDefinitionAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "slug",
        "category",
        "is_active",
        "requires_login",
        "version",
        "created_at",
        "form_builder_link",
        "workflow_builder_link",
        "clone_link",
    )
    list_filter = ("is_active", "requires_login", "category")
    list_select_related = ["category"]
    search_fields = ("name", "slug", "description")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [FormFieldInline]
    filter_horizontal = ("submit_groups", "view_groups", "admin_groups")
    change_form_template = "admin/django_forms_workflows/formdef_change_form.html"
    actions = ["clone_forms", "export_as_json", "push_forms_to_remote"]

    fieldsets = (
        (
            None,
            {
                "fields": (
                    ("name", "slug"),
                    "category",
                    "description",
                    "instructions",
                    ("is_active", "version"),
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
                        version=1,
                        requires_login=form.requires_login,
                        allow_save_draft=form.allow_save_draft,
                        allow_withdrawal=form.allow_withdrawal,
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
                            show_if_field=field.show_if_field,
                            show_if_value=field.show_if_value,
                            allowed_extensions=field.allowed_extensions,
                            max_file_size_mb=field.max_file_size_mb,
                        )

                    # Copy group permissions
                    cloned_form.submit_groups.set(form.submit_groups.all())
                    cloned_form.view_groups.set(form.view_groups.all())
                    cloned_form.admin_groups.set(form.admin_groups.all())

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

    @admin.action(description="Push selected forms to a remote instance")
    def push_forms_to_remote(self, request, queryset):
        """Admin action: redirect to the push view with selected form PKs."""
        pks = ",".join(str(pk) for pk in queryset.values_list("pk", flat=True))
        push_url = reverse("admin:formdefinition_sync_push")
        return HttpResponseRedirect(f"{push_url}?pks={pks}")

    def sync_pull_admin_view(self, request):
        """Multi-step admin page for pulling form definitions from a remote instance.

        Step 0 (GET)  – show remote picker (configured remotes + manual URL/token)
        Step 1 (POST) – fetch available forms from the remote, show checkbox list
        Step 2 (POST) – import selected forms, show results
        """
        from .sync_api import fetch_remote_payload, get_sync_remotes, import_payload

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
                context["step"] = 1
                context["remote_url"] = remote_url
                context["remote_token"] = remote_token
                context["remote_name"] = remote_name
                context["remote_forms"] = remote_forms
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
        """Admin page for pushing local form definitions to a remote instance.

        Arrives with ``?pks=1,2,3`` (selected from the changelist action) or
        without PKs (push all forms).

        Step 0 (GET)  – show forms to be pushed + remote picker
        Step 1 (POST) – execute push, show results
        """
        from .sync_api import get_sync_remotes, push_to_remote

        context = dict(self.admin_site.each_context(request))
        context["title"] = "Push Forms to Remote"
        context["opts"] = self.model._meta
        context["remotes"] = get_sync_remotes()
        context["step"] = 0

        # Resolve form queryset from ?pks= query param or POST field
        pks_raw = request.GET.get("pks") or request.POST.get("pks", "")
        if pks_raw:
            try:
                pk_list = [int(p) for p in pks_raw.split(",") if p.strip().isdigit()]
            except ValueError:
                pk_list = []
            queryset = self.model.objects.filter(pk__in=pk_list)
        else:
            queryset = self.model.objects.all()

        context["forms_to_push"] = queryset
        context["pks"] = pks_raw

        if request.method == "POST":
            step = request.POST.get("step", "push")
            if step == "push":
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
                        request, "admin/django_forms_workflows/sync_push.html", context
                    )

                try:
                    result = push_to_remote(
                        remote_url, remote_token, queryset, conflict=conflict
                    )
                except Exception as exc:
                    context["error"] = f"Push failed: {exc}"
                    return render(
                        request, "admin/django_forms_workflows/sync_push.html", context
                    )

                context["step"] = 1
                context["remote_name"] = remote_name
                context["push_result"] = result
                return render(
                    request, "admin/django_forms_workflows/sync_push.html", context
                )

        return render(request, "admin/django_forms_workflows/sync_push.html", context)

    def get_urls(self):
        """Add custom URLs for the form builder and workflow builder"""
        urls = super().get_urls()
        from . import form_builder_views, workflow_builder_views

        custom_urls = [
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


class WorkflowStageGroupConfigInline(admin.TabularInline):
    """Per-group overrides (button label + hidden fields) on a WorkflowStage."""

    model = WorkflowStageGroupConfig
    extra = 0
    fields = ("group", "approve_label", "hidden_fields")
    verbose_name = "Group Config Override"
    verbose_name_plural = "Group Config Overrides"


@admin.register(WorkflowStage)
class WorkflowStageAdmin(admin.ModelAdmin):
    """Standalone admin for WorkflowStage with per-group config inline.

    Stages are also editable via the WorkflowDefinition admin inline, but
    the group config overrides require this dedicated view because Django
    does not support nested inlines natively.
    """

    inlines = [WorkflowStageGroupConfigInline]
    list_display = ("__str__", "workflow", "order", "approval_logic", "approve_label")
    list_select_related = ("workflow", "workflow__form_definition")
    ordering = ("workflow", "order")
    filter_horizontal = ("approval_groups",)
    fields = (
        "workflow",
        ("order", "name"),
        "approval_logic",
        "approval_groups",
        "approve_label",
        "requires_manager_approval",
    )


class WorkflowStageInline(admin.StackedInline):
    """Inline for defining ordered stages on a WorkflowDefinition."""

    model = WorkflowStage
    extra = 0
    ordering = ("order",)
    filter_horizontal = ("approval_groups",)
    fields = (
        ("order", "name"),
        "approval_logic",
        "approval_groups",
        "approve_label",
        "requires_manager_approval",
    )


@admin.register(WorkflowDefinition)
class WorkflowDefinitionAdmin(admin.ModelAdmin):
    inlines = [WorkflowStageInline]
    list_display = (
        "form_definition",
        "requires_approval",
        "approval_logic",
        "requires_manager_approval",
        "allow_bulk_export",
        "allow_bulk_pdf_export",
    )
    list_filter = (
        "requires_approval",
        "approval_logic",
        "requires_manager_approval",
        "allow_bulk_export",
        "allow_bulk_pdf_export",
    )
    search_fields = ("form_definition__name",)
    filter_horizontal = ("approval_groups", "escalation_groups")
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "form_definition",
                    ("requires_approval", "approval_logic"),
                    "approval_groups",
                )
            },
        ),
        (
            "Manager approval",
            {
                "classes": ("collapse",),
                "fields": ("requires_manager_approval", "manager_can_override_group"),
            },
        ),
        (
            "Conditional escalation",
            {
                "classes": ("collapse",),
                "fields": (
                    ("escalation_field", "escalation_threshold"),
                    "escalation_groups",
                ),
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
            "Notifications",
            {
                "classes": ("collapse",),
                "fields": (
                    (
                        "notify_on_submission",
                        "notify_on_approval",
                        "notify_on_rejection",
                        "notify_on_withdrawal",
                    ),
                    "additional_notify_emails",
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
            "Post-approval DB updates",
            {
                "classes": ("collapse",),
                "fields": ("enable_db_updates", "db_update_mappings"),
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
        elif obj.file_size < 1024 * 1024:
            return f"{obj.file_size / 1024:.1f} KB"
        else:
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
