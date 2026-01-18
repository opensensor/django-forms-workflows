"""
Django admin for Django Forms Workflows

Provides a friendly admin interface to build forms (with fields),
configure approval workflows, and review submissions and audit logs.
"""

from django.contrib import admin
from django.db import transaction
from django.urls import path, reverse
from django.utils.html import format_html

from .models import (
    ApprovalTask,
    AuditLog,
    FileUploadConfig,
    FileWorkflowHook,
    FormDefinition,
    FormField,
    FormSubmission,
    FormTemplate,
    ManagedFile,
    PostSubmissionAction,
    PrefillSource,
    UserProfile,
    WorkflowDefinition,
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


@admin.register(FormDefinition)
class FormDefinitionAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "slug",
        "is_active",
        "requires_login",
        "version",
        "created_at",
        "form_builder_link",
        "workflow_builder_link",
        "clone_link",
    )
    list_filter = ("is_active", "requires_login")
    search_fields = ("name", "slug", "description")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [FormFieldInline]
    filter_horizontal = ("submit_groups", "view_groups", "admin_groups")
    change_form_template = "admin/django_forms_workflows/formdef_change_form.html"
    actions = ["clone_forms"]

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
        ]
        return custom_urls + urls


@admin.register(WorkflowDefinition)
class WorkflowDefinitionAdmin(admin.ModelAdmin):
    list_display = (
        "form_definition",
        "requires_approval",
        "approval_logic",
        "requires_manager_approval",
    )
    list_filter = (
        "requires_approval",
        "approval_logic",
        "requires_manager_approval",
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
            "Post-approval DB updates",
            {
                "classes": ("collapse",),
                "fields": ("enable_db_updates", "db_update_mappings"),
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
            "Conditional Execution",
            {
                "classes": ("collapse",),
                "fields": (
                    "condition_field",
                    ("condition_operator", "condition_value"),
                ),
                "description": ("Execute this action only when the condition is met."),
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
