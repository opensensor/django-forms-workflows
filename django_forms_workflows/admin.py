"""
Django admin for Django Forms Workflows

Provides a friendly admin interface to build forms (with fields),
configure approval workflows, and review submissions and audit logs.
"""

from django.contrib import admin

from .models import (
    ApprovalTask,
    AuditLog,
    FormDefinition,
    FormField,
    FormSubmission,
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
                    ("order", "field_label", "field_name", "field_type", "required"),
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
    )
    list_filter = ("is_active", "requires_login")
    search_fields = ("name", "slug", "description")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [FormFieldInline]
    filter_horizontal = ("submit_groups", "view_groups", "admin_groups")


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
