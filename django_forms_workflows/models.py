"""
Django Forms Workflows - Core Models

Database-driven form definitions with approval workflows and external data integration.
"""

from django.conf import settings
from django.contrib.auth.models import Group
from django.db import models


class FormDefinition(models.Model):
    """
    Master form configuration - created via Django Admin.

    Forms are stored in the database, not code, allowing non-developers
    to create and modify forms without deployments.
    """

    # Basic Info
    name = models.CharField(max_length=200, help_text="Display name for the form")
    slug = models.SlugField(
        unique=True, help_text="URL identifier (e.g., 'travel-request')"
    )
    description = models.TextField(help_text="Shown to users on form selection page")
    instructions = models.TextField(
        blank=True, help_text="Detailed instructions shown at top of form"
    )

    # Status
    is_active = models.BooleanField(
        default=True, help_text="Inactive forms are hidden from users"
    )
    version = models.IntegerField(
        default=1, help_text="Incremented when form structure changes"
    )

    # Permissions
    submit_groups = models.ManyToManyField(
        Group,
        related_name="can_submit_forms",
        blank=True,
        help_text="Groups that can submit this form",
    )
    view_groups = models.ManyToManyField(
        Group,
        related_name="can_view_forms",
        blank=True,
        help_text="Groups that can view this form",
    )
    admin_groups = models.ManyToManyField(
        Group,
        related_name="can_admin_forms",
        blank=True,
        help_text="Groups that can view all submissions",
    )

    # Behavior
    allow_save_draft = models.BooleanField(
        default=True, help_text="Users can save incomplete forms"
    )
    allow_withdrawal = models.BooleanField(
        default=True, help_text="Users can withdraw submitted forms before approval"
    )
    requires_login = models.BooleanField(
        default=True, help_text="Form requires authentication"
    )

    # Client-Side Enhancements
    enable_multi_step = models.BooleanField(
        default=False,
        help_text="Enable multi-step form with progress indicators",
    )
    form_steps = models.JSONField(
        blank=True,
        null=True,
        help_text='Multi-step configuration. Format: [{"title": "Step 1", "fields": ["field1", "field2"]}]',
    )
    enable_auto_save = models.BooleanField(
        default=True,
        help_text="Enable automatic draft saving",
    )
    auto_save_interval = models.IntegerField(
        default=30,
        help_text="Auto-save interval in seconds",
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "Form Definition"
        verbose_name_plural = "Form Definitions"

    def __str__(self):
        return self.name


class PrefillSource(models.Model):
    """
    Configurable pre-fill data sources for form fields.

    Allows administrators to define reusable pre-fill sources with custom
    field mappings for database lookups, making the library flexible for
    different deployment scenarios.
    """

    SOURCE_TYPES = [
        ("user", "User Model Field"),
        ("ldap", "LDAP Attribute"),
        ("database", "Database Query"),
        ("api", "API Call"),
        ("system", "System Value"),
        ("custom", "Custom Source"),
    ]

    # Basic Info
    name = models.CharField(
        max_length=200,
        unique=True,
        help_text="Display name (e.g., 'Current User - Email')",
    )
    source_type = models.CharField(
        max_length=20, choices=SOURCE_TYPES, help_text="Type of data source"
    )
    source_key = models.CharField(
        max_length=200,
        help_text="Source identifier (e.g., 'user.email', 'ldap.department', 'dbo.STBIOS.FIRST_NAME')",
    )

    # Display
    description = models.TextField(
        blank=True, help_text="Description shown to form builders"
    )
    is_active = models.BooleanField(
        default=True, help_text="Inactive sources are hidden from form builders"
    )

    # Database-specific configuration
    db_alias = models.CharField(
        max_length=100,
        blank=True,
        help_text="Django database alias (for database sources)",
    )
    db_schema = models.CharField(
        max_length=100, blank=True, help_text="Database schema name (e.g., 'dbo')"
    )
    db_table = models.CharField(
        max_length=100, blank=True, help_text="Database table name (e.g., 'STBIOS')"
    )
    db_column = models.CharField(
        max_length=100,
        blank=True,
        help_text="Database column name (e.g., 'FIRST_NAME') - for single column lookup",
    )
    db_columns = models.JSONField(
        blank=True,
        null=True,
        help_text="List of columns to fetch for template (e.g., ['FIRST_NAME', 'LAST_NAME'])",
    )
    db_template = models.CharField(
        max_length=500,
        blank=True,
        help_text="Template for combining columns (e.g., '{FIRST_NAME} {LAST_NAME}')",
    )
    db_lookup_field = models.CharField(
        max_length=100,
        blank=True,
        default="ID_NUMBER",
        help_text="Field to match against user (e.g., 'ID_NUMBER', 'EMAIL')",
    )
    db_user_field = models.CharField(
        max_length=100,
        blank=True,
        default="employee_id",
        help_text="UserProfile field to use for lookup (e.g., 'employee_id', 'email')",
    )

    # LDAP-specific configuration
    ldap_attribute = models.CharField(
        max_length=100,
        blank=True,
        help_text="LDAP attribute name (e.g., 'department', 'title')",
    )

    # API-specific configuration
    api_endpoint = models.CharField(
        max_length=500, blank=True, help_text="API endpoint URL"
    )
    api_field = models.CharField(
        max_length=100, blank=True, help_text="Field to extract from API response"
    )

    # Custom configuration (JSON)
    custom_config = models.JSONField(
        blank=True, null=True, help_text="Additional configuration as JSON"
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    order = models.IntegerField(default=0, help_text="Display order in dropdown")

    class Meta:
        ordering = ["order", "name"]
        verbose_name = "Prefill Source"
        verbose_name_plural = "Prefill Sources"

    def __str__(self):
        return self.name

    def get_source_identifier(self):
        """
        Get the source identifier string for backward compatibility.
        Returns the source_key or constructs it from components.
        """
        if self.source_type == "database" and self.db_schema and self.db_table:
            # Template-based multi-column lookup
            if self.db_template and self.db_columns:
                return f"{{{{ {self.db_schema}.{self.db_table}.* }}}}"
            # Single column lookup
            elif self.db_column:
                return f"{{{{ {self.db_schema}.{self.db_table}.{self.db_column} }}}}"
        elif self.source_type == "ldap" and self.ldap_attribute:
            return f"ldap.{self.ldap_attribute}"
        elif self.source_type == "user":
            return self.source_key
        return self.source_key

    def has_template(self):
        """Check if this source uses a multi-column template."""
        return bool(self.db_template and self.db_columns)


class FormField(models.Model):
    """
    Individual field configuration - inline edited in Django Admin.

    Supports 15+ field types, validation rules, conditional logic,
    and external data prefill from LDAP, databases, or APIs.
    """

    FIELD_TYPES = [
        ("text", "Single Line Text"),
        ("textarea", "Multi-line Text"),
        ("number", "Whole Number"),
        ("decimal", "Decimal/Currency"),
        ("date", "Date"),
        ("datetime", "Date and Time"),
        ("time", "Time"),
        ("email", "Email Address"),
        ("url", "Website URL"),
        ("select", "Dropdown Select"),
        ("multiselect", "Multiple Select"),
        ("radio", "Radio Buttons"),
        ("checkbox", "Single Checkbox"),
        ("checkboxes", "Multiple Checkboxes"),
        ("file", "File Upload"),
        ("hidden", "Hidden Field"),
        ("section", "Section Header (not a field)"),
    ]

    # Common prefill sources - can be extended via settings
    PREFILL_SOURCES = [
        ("", "No auto-fill"),
        ("user.email", "Current User - Email"),
        ("user.first_name", "Current User - First Name"),
        ("user.last_name", "Current User - Last Name"),
        ("user.full_name", "Current User - Full Name"),
        ("user.username", "Current User - Username"),
        ("ldap.department", "LDAP - Department"),
        ("ldap.title", "LDAP - Job Title"),
        ("ldap.manager", "LDAP - Manager Name"),
        ("ldap.manager_email", "LDAP - Manager Email"),
        ("ldap.phone", "LDAP - Phone Number"),
        ("ldap.employee_id", "LDAP - Employee ID"),
        ("last_submission", "Copy from Last Submission"),
        ("current_date", "Today's Date"),
        ("current_datetime", "Current Date & Time"),
    ]

    # Relationship
    form_definition = models.ForeignKey(
        FormDefinition, related_name="fields", on_delete=models.CASCADE
    )

    # Field Definition
    field_name = models.SlugField(
        help_text="Internal name (letters, numbers, underscores)"
    )
    field_label = models.CharField(max_length=200, help_text="Label shown to users")
    field_type = models.CharField(max_length=20, choices=FIELD_TYPES)

    # Display
    order = models.IntegerField(default=0, help_text="Fields are sorted by this number")
    help_text = models.TextField(blank=True, help_text="Instructions shown below field")
    placeholder = models.CharField(max_length=200, blank=True)
    css_class = models.CharField(
        max_length=100, blank=True, help_text="CSS classes for styling"
    )
    width = models.CharField(
        max_length=10,
        default="full",
        choices=[
            ("full", "Full Width"),
            ("half", "Half Width"),
            ("third", "One Third"),
        ],
    )

    # Validation
    required = models.BooleanField(default=False)
    readonly = models.BooleanField(
        default=False,
        help_text="If checked, the field will be displayed but not editable",
    )
    min_value = models.DecimalField(
        null=True,
        blank=True,
        max_digits=15,
        decimal_places=2,
        help_text="For number/decimal fields",
    )
    max_value = models.DecimalField(
        null=True,
        blank=True,
        max_digits=15,
        decimal_places=2,
        help_text="For number/decimal fields",
    )
    min_length = models.IntegerField(
        null=True, blank=True, help_text="Minimum characters for text fields"
    )
    max_length = models.IntegerField(
        null=True, blank=True, help_text="Maximum characters for text fields"
    )
    regex_validation = models.CharField(
        max_length=500, blank=True, help_text="Regular expression for validation"
    )
    regex_error_message = models.CharField(
        max_length=200, blank=True, help_text="Error shown if regex validation fails"
    )

    # Choices (for select, radio, checkboxes)
    choices = models.JSONField(
        blank=True,
        null=True,
        help_text='JSON: [{"value": "opt1", "label": "Option 1"}, ...] or comma-separated string',
    )

    # Dynamic Behavior - Prefill from external sources
    prefill_source = models.CharField(
        max_length=200,
        blank=True,
        help_text="DEPRECATED: Use prefill_source_config instead. Legacy format: user.email, ldap.department, {{ db.schema.table.column }}, etc.",
    )
    prefill_source_config = models.ForeignKey(
        PrefillSource,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="form_fields",
        help_text="Select a pre-configured prefill source",
    )
    default_value = models.TextField(blank=True)

    def get_prefill_source_key(self):
        """
        Get the prefill source key for this field.
        Prioritizes prefill_source_config over legacy prefill_source.
        """
        if self.prefill_source_config:
            return self.prefill_source_config.get_source_identifier()
        return self.prefill_source or ""

    # Conditional Display
    show_if_field = models.SlugField(
        blank=True, help_text="Only show if another field has specific value"
    )
    show_if_value = models.CharField(
        max_length=200, blank=True, help_text="Value that triggers showing this field"
    )

    # Advanced Conditional Logic (Client-Side Enhancements)
    conditional_rules = models.JSONField(
        blank=True,
        null=True,
        help_text='Advanced conditional rules with AND/OR logic. Format: {"operator": "AND|OR", "conditions": [{"field": "field_name", "operator": "equals", "value": "value"}], "action": "show|hide|require|enable"}',
    )

    # Dynamic Field Validation (Client-Side)
    validation_rules = models.JSONField(
        blank=True,
        null=True,
        help_text='Client-side validation rules. Format: [{"type": "required|email|min|max|pattern|custom", "value": "...", "message": "Error message"}]',
    )

    # Field Dependencies (Cascade Updates)
    field_dependencies = models.JSONField(
        blank=True,
        null=True,
        help_text='Field dependencies for cascade updates. Format: [{"sourceField": "field_name", "targetField": "dependent_field", "apiEndpoint": "/api/endpoint/"}]',
    )

    # Multi-Step Forms
    step_number = models.IntegerField(
        null=True,
        blank=True,
        help_text="Step number for multi-step forms (1, 2, 3, etc.)",
    )

    # File Upload Settings
    allowed_extensions = models.CharField(
        max_length=200, blank=True, help_text="Comma-separated: pdf,doc,docx,xls,xlsx"
    )
    max_file_size_mb = models.IntegerField(
        null=True, blank=True, help_text="Maximum file size in MB"
    )

    class Meta:
        ordering = ["order", "field_name"]
        unique_together = [["form_definition", "field_name"]]
        verbose_name = "Form Field"
        verbose_name_plural = "Form Fields"

    def __str__(self):
        return f"{self.field_label} ({self.field_name})"


class WorkflowDefinition(models.Model):
    """
    Approval workflow configuration.

    Supports multi-step approvals with flexible routing logic:
    - All approvers must approve (AND)
    - Any approver can approve (OR)
    - Sequential approval chain
    - Manager approval from LDAP hierarchy
    - Conditional escalation based on field values
    """

    APPROVAL_LOGIC = [
        ("all", "All must approve (AND)"),
        ("any", "Any can approve (OR)"),
        ("sequence", "Sequential approval chain"),
    ]

    form_definition = models.OneToOneField(
        FormDefinition, related_name="workflow", on_delete=models.CASCADE
    )

    # Basic Approval
    requires_approval = models.BooleanField(default=True)
    approval_groups = models.ManyToManyField(
        Group,
        related_name="can_approve_workflows",
        blank=True,
        help_text="Groups that can approve",
    )
    approval_logic = models.CharField(
        max_length=20, choices=APPROVAL_LOGIC, default="any"
    )

    # Manager Approval (requires LDAP integration)
    requires_manager_approval = models.BooleanField(
        default=False, help_text="Route to submitter's manager from LDAP"
    )
    manager_can_override_group = models.BooleanField(
        default=True, help_text="Manager can approve even if not in approval group"
    )

    # Conditional Escalation
    escalation_field = models.SlugField(
        blank=True, help_text="Field name to check for escalation (e.g., 'amount')"
    )
    escalation_threshold = models.DecimalField(
        null=True,
        blank=True,
        max_digits=15,
        decimal_places=2,
        help_text="If field value exceeds this, escalate",
    )
    escalation_groups = models.ManyToManyField(
        Group,
        related_name="escalation_workflows",
        blank=True,
        help_text="Additional approval needed if escalated",
    )

    # Timeouts
    approval_deadline_days = models.IntegerField(
        null=True, blank=True, help_text="Days before approval request expires"
    )
    send_reminder_after_days = models.IntegerField(
        null=True, blank=True, help_text="Send reminder email after this many days"
    )
    auto_approve_after_days = models.IntegerField(
        null=True, blank=True, help_text="Auto-approve if no response (use carefully)"
    )

    # Notifications
    notify_on_submission = models.BooleanField(default=True)
    notify_on_approval = models.BooleanField(default=True)
    notify_on_rejection = models.BooleanField(default=True)
    notify_on_withdrawal = models.BooleanField(default=True)

    additional_notify_emails = models.TextField(
        blank=True, help_text="Comma-separated emails for all notifications"
    )

    # Post-Approval Database Updates (optional feature)
    enable_db_updates = models.BooleanField(
        default=False, help_text="Enable database updates after approval"
    )
    db_update_mappings = models.JSONField(
        blank=True,
        null=True,
        help_text='JSON: [{"form_field": "field_name", "db_target": "{{ db.schema.table.column }}", "update_condition": "always"}]',
    )

    # Visual Workflow Builder Data
    visual_workflow_data = models.JSONField(
        blank=True,
        null=True,
        help_text="Visual workflow builder layout (nodes and connections)",
    )

    class Meta:
        verbose_name = "Workflow Definition"
        verbose_name_plural = "Workflow Definitions"

    def __str__(self):
        return f"Workflow for {self.form_definition.name}"


class PostSubmissionAction(models.Model):
    """
    Configurable post-submission actions to update external systems.

    Allows forms to write data back to external databases, LDAP, or APIs
    after submission or approval. Supports field mapping and conditional execution.
    """

    ACTION_TYPES = [
        ("database", "Database Update"),
        ("ldap", "LDAP Update"),
        ("api", "API Call"),
        ("email", "Email Notification"),
        ("custom", "Custom Handler"),
    ]

    TRIGGER_TYPES = [
        ("on_submit", "On Submission"),
        ("on_approve", "On Approval"),
        ("on_reject", "On Rejection"),
        ("on_complete", "On Workflow Complete"),
    ]

    # Core Configuration
    form_definition = models.ForeignKey(
        FormDefinition, on_delete=models.CASCADE, related_name="post_actions"
    )
    name = models.CharField(
        max_length=200, help_text="Descriptive name for this action"
    )
    action_type = models.CharField(max_length=20, choices=ACTION_TYPES)
    trigger = models.CharField(
        max_length=20,
        choices=TRIGGER_TYPES,
        default="on_approve",
        help_text="When to execute this action",
    )
    is_active = models.BooleanField(
        default=True, help_text="Whether this action is enabled"
    )
    order = models.IntegerField(
        default=0, help_text="Execution order (lower numbers run first)"
    )

    # Database Update Configuration
    db_alias = models.CharField(
        max_length=100,
        blank=True,
        help_text="Django database alias (e.g., 'external_db')",
    )
    db_schema = models.CharField(
        max_length=100, blank=True, help_text="Database schema name"
    )
    db_table = models.CharField(max_length=100, blank=True, help_text="Table to update")
    db_lookup_field = models.CharField(
        max_length=100,
        blank=True,
        default="ID_NUMBER",
        help_text="Database column to match against (WHERE clause)",
    )
    db_user_field = models.CharField(
        max_length=100,
        blank=True,
        default="employee_id",
        help_text="UserProfile field to use for lookup",
    )
    db_field_mappings = models.JSONField(
        blank=True,
        null=True,
        help_text='JSON: [{"form_field": "email", "db_column": "EMAIL_ADDRESS"}, ...]',
    )

    # LDAP Update Configuration
    ldap_dn_template = models.CharField(
        max_length=500,
        blank=True,
        help_text="LDAP DN template (e.g., 'CN={username},OU=Users,DC=example,DC=com')",
    )
    ldap_field_mappings = models.JSONField(
        blank=True,
        null=True,
        help_text='JSON: [{"form_field": "phone", "ldap_attribute": "telephoneNumber"}, ...]',
    )

    # API Call Configuration
    api_endpoint = models.URLField(
        blank=True, max_length=500, help_text="API endpoint URL"
    )
    api_method = models.CharField(
        max_length=10,
        blank=True,
        default="POST",
        help_text="HTTP method (GET, POST, PUT, PATCH)",
    )
    api_headers = models.JSONField(
        blank=True,
        null=True,
        help_text='JSON: {"Authorization": "Bearer {token}", "Content-Type": "application/json"}',
    )
    api_body_template = models.TextField(
        blank=True,
        help_text="JSON template for request body. Use {field_name} for form fields.",
    )

    # Custom Handler Configuration
    custom_handler_path = models.CharField(
        max_length=500,
        blank=True,
        help_text="Python path to custom handler function (e.g., 'myapp.handlers.custom_update')",
    )
    custom_handler_config = models.JSONField(
        blank=True, null=True, help_text="Configuration passed to custom handler"
    )

    # Conditional Execution
    condition_field = models.CharField(
        max_length=100,
        blank=True,
        help_text="Form field to check for conditional execution",
    )
    condition_operator = models.CharField(
        max_length=20,
        blank=True,
        choices=[
            ("equals", "Equals"),
            ("not_equals", "Not Equals"),
            ("contains", "Contains"),
            ("greater_than", "Greater Than"),
            ("less_than", "Less Than"),
            ("is_true", "Is True"),
            ("is_false", "Is False"),
        ],
        help_text="Comparison operator for condition",
    )
    condition_value = models.CharField(
        max_length=500, blank=True, help_text="Value to compare against"
    )

    # Error Handling
    fail_silently = models.BooleanField(
        default=False, help_text="If True, errors won't block submission/approval"
    )
    retry_on_failure = models.BooleanField(
        default=False, help_text="Retry failed actions"
    )
    max_retries = models.IntegerField(default=3, help_text="Maximum retry attempts")

    # Metadata
    description = models.TextField(
        blank=True, help_text="Description of what this action does"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["form_definition", "order", "name"]
        verbose_name = "Post-Submission Action"
        verbose_name_plural = "Post-Submission Actions"

    def __str__(self):
        return f"{self.name} ({self.get_action_type_display()}) - {self.form_definition.name}"

    def should_execute(self, submission):
        """
        Check if this action should execute based on conditions.
        """
        if not self.is_active:
            return False

        # Check conditional execution
        if self.condition_field and self.condition_operator:
            field_value = submission.form_data.get(self.condition_field)

            if self.condition_operator == "equals":
                return str(field_value) == self.condition_value
            elif self.condition_operator == "not_equals":
                return str(field_value) != self.condition_value
            elif self.condition_operator == "contains":
                return self.condition_value in str(field_value)
            elif self.condition_operator == "greater_than":
                try:
                    return float(field_value) > float(self.condition_value)
                except (ValueError, TypeError):
                    return False
            elif self.condition_operator == "less_than":
                try:
                    return float(field_value) < float(self.condition_value)
                except (ValueError, TypeError):
                    return False
            elif self.condition_operator == "is_true":
                return bool(field_value)
            elif self.condition_operator == "is_false":
                return not bool(field_value)

        return True


class FormSubmission(models.Model):
    """
    Actual form submission data.

    Stores the submitted form data as JSON along with status tracking,
    timestamps, and metadata for audit purposes.
    """

    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("submitted", "Submitted"),
        ("pending_approval", "Pending Approval"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("withdrawn", "Withdrawn"),
    ]

    # Core Fields
    form_definition = models.ForeignKey(
        FormDefinition, on_delete=models.PROTECT, related_name="submissions"
    )
    submitter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="form_submissions",
    )

    # Submission Data
    form_data = models.JSONField(help_text="The actual form responses")
    attachments = models.JSONField(
        default=list, blank=True, help_text="List of uploaded file paths"
    )

    # Status Tracking
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    current_step = models.CharField(
        max_length=100, blank=True, help_text="Current position in workflow"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Tracking
    submission_ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "submitter"]),
            models.Index(fields=["form_definition", "status"]),
        ]
        verbose_name = "Form Submission"
        verbose_name_plural = "Form Submissions"

    def __str__(self):
        return f"{self.form_definition.name} - {self.submitter.username} - {self.get_status_display()}"


class ApprovalTask(models.Model):
    """
    Individual approval tasks in workflow.

    Each approval step creates one or more tasks assigned to users or groups.
    Tracks who approved, when, and any comments.
    """

    TASK_STATUS = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("expired", "Expired"),
        ("skipped", "Skipped"),
    ]

    submission = models.ForeignKey(
        FormSubmission, on_delete=models.CASCADE, related_name="approval_tasks"
    )

    # Assignment
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="assigned_approvals",
    )
    assigned_group = models.ForeignKey(
        Group,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="group_approvals",
    )

    # Status
    status = models.CharField(max_length=20, choices=TASK_STATUS, default="pending")
    step_name = models.CharField(max_length=100)

    # Response
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="completed_approvals",
    )
    decision = models.CharField(max_length=20, blank=True)
    comments = models.TextField(blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    due_date = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    reminder_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Approval Task"
        verbose_name_plural = "Approval Tasks"

    def __str__(self):
        return f"{self.step_name} for {self.submission}"


class AuditLog(models.Model):
    """
    Complete audit trail for compliance.

    Tracks all actions on forms, submissions, and approvals with
    user, IP address, timestamp, and detailed change information.
    """

    ACTION_TYPES = [
        ("create", "Created"),
        ("update", "Updated"),
        ("delete", "Deleted"),
        ("submit", "Submitted"),
        ("approve", "Approved"),
        ("reject", "Rejected"),
        ("withdraw", "Withdrawn"),
        ("assign", "Assigned"),
        ("comment", "Commented"),
    ]

    # What happened
    action = models.CharField(max_length=20, choices=ACTION_TYPES)
    object_type = models.CharField(max_length=50)
    object_id = models.IntegerField()

    # Who did it
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    user_ip = models.GenericIPAddressField(null=True, blank=True)

    # Details
    changes = models.JSONField(
        default=dict, blank=True, help_text="What changed in this action"
    )
    comments = models.TextField(blank=True)

    # When
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["object_type", "object_id"]),
            models.Index(fields=["user", "created_at"]),
        ]
        verbose_name = "Audit Log"
        verbose_name_plural = "Audit Logs"

    def __str__(self):
        return f"{self.user.username} - {self.get_action_display()} - {self.object_type} #{self.object_id}"


# Optional: User Profile model for storing additional user data
# This can be extended or replaced based on your needs
class UserProfile(models.Model):
    """
    Extended user profile for storing additional user data.

    This is optional and can be customized based on your needs.
    Commonly used to store LDAP attributes or external system IDs.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="forms_profile"
    )

    # External System IDs
    employee_id = models.CharField(
        max_length=50,
        blank=True,
        db_index=True,
        help_text="Employee ID from LDAP or HR system (e.g., extensionAttribute1)",
    )
    external_id = models.CharField(
        max_length=100,
        blank=True,
        db_index=True,
        help_text="ID from external system (for database lookups)",
    )

    # Organizational Info (from LDAP or manual entry)
    department = models.CharField(max_length=200, blank=True)
    title = models.CharField(max_length=200, blank=True)
    phone = models.CharField(max_length=50, blank=True)
    office_location = models.CharField(max_length=200, blank=True)

    # Manager Hierarchy (from LDAP)
    manager_dn = models.CharField(
        max_length=500, blank=True, help_text="Manager's Distinguished Name from LDAP"
    )
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="direct_reports",
    )

    # Metadata
    ldap_last_sync = models.DateTimeField(
        null=True, blank=True, help_text="Last time LDAP attributes were synced"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"

    def __str__(self):
        return f"Profile for {self.user.username}"

    @property
    def full_name(self):
        """Get user's full name."""
        return self.user.get_full_name() or self.user.username

    @property
    def display_name(self):
        """Get display name with title if available."""
        if self.title:
            return f"{self.full_name} ({self.title})"
        return self.full_name

    @property
    def id_number(self):
        """Alias for employee_id for backward compatibility."""
        return self.employee_id

    @id_number.setter
    def id_number(self, value):
        """Set employee_id via id_number alias."""
        self.employee_id = value


class FileUploadConfig(models.Model):
    """
    Configurable file upload settings for form fields.

    Allows administrators to define naming patterns, storage settings,
    and workflow integration for file uploads.
    """

    # File naming pattern tokens:
    # {user.id} - User ID
    # {user.username} - Username
    # {user.employee_id} - Employee ID from profile
    # {field_name} - Form field name
    # {form_slug} - Form definition slug
    # {submission_id} - Submission ID
    # {status} - Current file status
    # {date} - Current date (YYYY-MM-DD)
    # {datetime} - Current datetime (YYYYMMDD_HHMMSS)
    # {original_name} - Original filename (without extension)
    # {ext} - File extension

    # Core Configuration
    name = models.CharField(
        max_length=200,
        unique=True,
        help_text="Display name for this configuration",
    )
    description = models.TextField(
        blank=True,
        help_text="Description of this file upload configuration",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this configuration is active",
    )

    # Naming Pattern
    naming_pattern = models.CharField(
        max_length=500,
        default="{user.username}_{field_name}_{datetime}.{ext}",
        help_text="File naming pattern. Tokens: {user.id}, {user.username}, {user.employee_id}, "
        "{field_name}, {form_slug}, {submission_id}, {status}, {date}, {datetime}, "
        "{original_name}, {ext}",
    )

    # Status-based naming (optional)
    pending_prefix = models.CharField(
        max_length=100,
        blank=True,
        default="pending_",
        help_text="Prefix to add to pending files",
    )
    approved_prefix = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Prefix to add to approved files (empty means no prefix)",
    )
    rejected_prefix = models.CharField(
        max_length=100,
        blank=True,
        default="rejected_",
        help_text="Prefix to add to rejected files",
    )

    # Storage settings
    upload_to = models.CharField(
        max_length=500,
        default="form_uploads/{form_slug}/{user.username}/",
        help_text="Upload directory pattern. Supports same tokens as naming_pattern.",
    )
    approved_storage_path = models.CharField(
        max_length=500,
        blank=True,
        help_text="Move approved files to this path. Leave empty to keep in place.",
    )
    rejected_storage_path = models.CharField(
        max_length=500,
        blank=True,
        help_text="Move rejected files to this path. Leave empty to keep in place.",
    )

    # File restrictions (override form field settings if set)
    allowed_extensions = models.CharField(
        max_length=200,
        blank=True,
        help_text="Comma-separated: pdf,doc,docx,xls,xlsx. Leave empty to use field settings.",
    )
    max_file_size_mb = models.IntegerField(
        null=True,
        blank=True,
        help_text="Maximum file size in MB. Leave empty to use field settings.",
    )
    allowed_mime_types = models.TextField(
        blank=True,
        help_text="Comma-separated MIME types. Leave empty to allow any.",
    )

    # Versioning
    enable_versioning = models.BooleanField(
        default=False,
        help_text="Keep previous versions of files",
    )
    max_versions = models.IntegerField(
        default=5,
        help_text="Maximum number of versions to keep",
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "File Upload Configuration"
        verbose_name_plural = "File Upload Configurations"

    def __str__(self):
        return self.name


class ManagedFile(models.Model):
    """
    Tracks file uploads with approval workflow integration.

    Provides status tracking, versioning, and workflow hooks for file uploads.
    """

    FILE_STATUS = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("superseded", "Superseded"),  # Replaced by a newer version
        ("deleted", "Deleted"),
    ]

    # Core relationships
    submission = models.ForeignKey(
        FormSubmission,
        on_delete=models.CASCADE,
        related_name="managed_files",
    )
    form_field = models.ForeignKey(
        FormField,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="managed_files",
    )
    upload_config = models.ForeignKey(
        FileUploadConfig,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="managed_files",
    )

    # File information
    original_filename = models.CharField(
        max_length=500,
        help_text="Original filename as uploaded",
    )
    stored_filename = models.CharField(
        max_length=500,
        help_text="Filename as stored (after naming pattern applied)",
    )
    file_path = models.CharField(
        max_length=1000,
        help_text="Full path to file storage",
    )
    file_size = models.BigIntegerField(
        default=0,
        help_text="File size in bytes",
    )
    mime_type = models.CharField(
        max_length=200,
        blank=True,
        help_text="MIME type of the file",
    )
    file_hash = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        help_text="SHA-256 hash of file content for integrity/dedup",
    )

    # Status tracking
    status = models.CharField(
        max_length=20,
        choices=FILE_STATUS,
        default="pending",
        db_index=True,
    )
    status_changed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When status last changed",
    )
    status_changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="file_status_changes",
        help_text="User who changed the status",
    )
    status_notes = models.TextField(
        blank=True,
        help_text="Notes about the status change (e.g., rejection reason)",
    )

    # Versioning
    version = models.IntegerField(
        default=1,
        help_text="Version number for this file",
    )
    previous_version = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="newer_versions",
        help_text="Link to previous version of this file",
    )
    is_current = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Is this the current version?",
    )

    # Metadata
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="uploaded_files",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Custom metadata (JSON)
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional metadata as JSON",
    )

    class Meta:
        ordering = ["-uploaded_at"]
        indexes = [
            models.Index(fields=["submission", "status"]),
            models.Index(fields=["status", "is_current"]),
        ]
        verbose_name = "Managed File"
        verbose_name_plural = "Managed Files"

    def __str__(self):
        return f"{self.original_filename} ({self.get_status_display()})"

    def mark_approved(self, user=None, notes=""):
        """Mark file as approved and trigger hooks."""
        from django.utils import timezone

        self.status = "approved"
        self.status_changed_at = timezone.now()
        self.status_changed_by = user
        self.status_notes = notes
        self.save(
            update_fields=[
                "status",
                "status_changed_at",
                "status_changed_by",
                "status_notes",
            ]
        )

    def mark_rejected(self, user=None, notes=""):
        """Mark file as rejected and trigger hooks."""
        from django.utils import timezone

        self.status = "rejected"
        self.status_changed_at = timezone.now()
        self.status_changed_by = user
        self.status_notes = notes
        self.save(
            update_fields=[
                "status",
                "status_changed_at",
                "status_changed_by",
                "status_notes",
            ]
        )

    def mark_superseded(self, notes=""):
        """Mark file as superseded by a newer version."""
        from django.utils import timezone

        self.status = "superseded"
        self.status_changed_at = timezone.now()
        self.status_notes = notes
        self.is_current = False
        self.save(
            update_fields=["status", "status_changed_at", "status_notes", "is_current"]
        )


class FileWorkflowHook(models.Model):
    """
    Configurable workflow hooks for file operations.

    Allows defining actions to execute when file status changes,
    such as renaming, moving, webhook calls, or external integrations.
    """

    TRIGGER_CHOICES = [
        ("on_upload", "On Upload"),
        ("on_submit", "On Submission"),
        ("on_approve", "On Approval"),
        ("on_reject", "On Rejection"),
        ("on_supersede", "On Supersede"),
    ]

    ACTION_CHOICES = [
        ("rename", "Rename File"),
        ("move", "Move File"),
        ("copy", "Copy File"),
        ("delete", "Delete File"),
        ("webhook", "Call Webhook"),
        ("api", "API Call"),
        ("custom", "Custom Handler"),
    ]

    # Core configuration
    name = models.CharField(
        max_length=200,
        help_text="Descriptive name for this hook",
    )
    description = models.TextField(
        blank=True,
        help_text="Description of what this hook does",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this hook is active",
    )
    order = models.IntegerField(
        default=0,
        help_text="Execution order (lower numbers run first)",
    )

    # Scope (which files this hook applies to)
    form_definition = models.ForeignKey(
        FormDefinition,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="file_hooks",
        help_text="Specific form (leave empty for all forms)",
    )
    upload_config = models.ForeignKey(
        FileUploadConfig,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="hooks",
        help_text="Specific upload config (leave empty for all)",
    )
    field_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Specific field name (leave empty for all file fields)",
    )

    # Trigger and action
    trigger = models.CharField(
        max_length=20,
        choices=TRIGGER_CHOICES,
        help_text="When to execute this hook",
    )
    action = models.CharField(
        max_length=20,
        choices=ACTION_CHOICES,
        help_text="Action to perform",
    )

    # Action-specific configuration
    # For rename/move/copy
    target_pattern = models.CharField(
        max_length=500,
        blank=True,
        help_text="Target path/name pattern. Supports same tokens as FileUploadConfig.",
    )

    # For webhook/API
    webhook_url = models.URLField(
        blank=True,
        max_length=500,
        help_text="Webhook URL to call",
    )
    webhook_method = models.CharField(
        max_length=10,
        blank=True,
        default="POST",
        help_text="HTTP method for webhook",
    )
    webhook_headers = models.JSONField(
        default=dict,
        blank=True,
        help_text="Headers to send with webhook request",
    )
    webhook_payload_template = models.TextField(
        blank=True,
        help_text="JSON template for webhook payload. Use {field} for tokens.",
    )

    # For custom handler
    custom_handler_path = models.CharField(
        max_length=500,
        blank=True,
        help_text="Python path to custom handler (e.g., 'myapp.handlers.process_file')",
    )
    custom_handler_config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Configuration passed to custom handler",
    )

    # Conditional execution
    condition_field = models.CharField(
        max_length=100,
        blank=True,
        help_text="Form field to check for conditional execution",
    )
    condition_operator = models.CharField(
        max_length=20,
        blank=True,
        choices=[
            ("equals", "Equals"),
            ("not_equals", "Not Equals"),
            ("contains", "Contains"),
            ("greater_than", "Greater Than"),
            ("less_than", "Less Than"),
            ("is_true", "Is True"),
            ("is_false", "Is False"),
            ("file_ext_equals", "File Extension Equals"),
            ("file_size_greater", "File Size Greater Than (MB)"),
            ("file_size_less", "File Size Less Than (MB)"),
        ],
        help_text="Comparison operator for condition",
    )
    condition_value = models.CharField(
        max_length=500,
        blank=True,
        help_text="Value to compare against",
    )

    # Error handling
    fail_silently = models.BooleanField(
        default=False,
        help_text="If True, errors won't block the workflow",
    )
    retry_on_failure = models.BooleanField(
        default=False,
        help_text="Retry failed actions",
    )
    max_retries = models.IntegerField(
        default=3,
        help_text="Maximum retry attempts",
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "name"]
        verbose_name = "File Workflow Hook"
        verbose_name_plural = "File Workflow Hooks"

    def __str__(self):
        scope = ""
        if self.form_definition:
            scope = f" for {self.form_definition.name}"
        return f"{self.name} ({self.get_trigger_display()}{scope})"

    def should_execute(self, managed_file, submission=None):
        """
        Check if this hook should execute for the given file.
        """
        if not self.is_active:
            return False

        # Check form scope
        if self.form_definition_id:
            if managed_file.submission.form_definition_id != self.form_definition_id:
                return False

        # Check upload config scope
        if self.upload_config_id:
            if managed_file.upload_config_id != self.upload_config_id:
                return False

        # Check field name scope
        if self.field_name:
            if (
                managed_file.form_field
                and managed_file.form_field.field_name != self.field_name
            ):
                return False

        # Check conditional execution
        if self.condition_field and self.condition_operator:
            return self._check_condition(managed_file, submission)

        return True

    def _check_condition(self, managed_file, submission=None):
        """Evaluate condition for this hook."""
        # Get submission from file if not provided
        if submission is None:
            submission = managed_file.submission

        # File-specific conditions
        if self.condition_operator == "file_ext_equals":
            ext = managed_file.original_filename.rsplit(".", 1)[-1].lower()
            return ext == self.condition_value.lower()

        if self.condition_operator == "file_size_greater":
            try:
                size_mb = managed_file.file_size / (1024 * 1024)
                return size_mb > float(self.condition_value)
            except (ValueError, TypeError):
                return False

        if self.condition_operator == "file_size_less":
            try:
                size_mb = managed_file.file_size / (1024 * 1024)
                return size_mb < float(self.condition_value)
            except (ValueError, TypeError):
                return False

        # Form field conditions
        field_value = submission.form_data.get(self.condition_field)

        if self.condition_operator == "equals":
            return str(field_value) == self.condition_value
        elif self.condition_operator == "not_equals":
            return str(field_value) != self.condition_value
        elif self.condition_operator == "contains":
            return self.condition_value in str(field_value)
        elif self.condition_operator == "greater_than":
            try:
                return float(field_value) > float(self.condition_value)
            except (ValueError, TypeError):
                return False
        elif self.condition_operator == "less_than":
            try:
                return float(field_value) < float(self.condition_value)
            except (ValueError, TypeError):
                return False
        elif self.condition_operator == "is_true":
            return bool(field_value)
        elif self.condition_operator == "is_false":
            return not bool(field_value)

        return True


class FormTemplate(models.Model):
    """
    Pre-built form templates for common use cases.

    Templates allow users to quickly create forms from common patterns
    like contact forms, request forms, surveys, etc.
    """

    CATEGORY_CHOICES = [
        ("general", "General"),
        ("hr", "Human Resources"),
        ("it", "IT & Technology"),
        ("finance", "Finance"),
        ("facilities", "Facilities"),
        ("survey", "Survey"),
        ("request", "Request"),
        ("feedback", "Feedback"),
        ("other", "Other"),
    ]

    # Basic Info
    name = models.CharField(
        max_length=200,
        help_text="Template name (e.g., 'Contact Form', 'Travel Request')",
    )
    slug = models.SlugField(unique=True, help_text="URL-friendly identifier")
    description = models.TextField(help_text="Description of what this template is for")
    category = models.CharField(
        max_length=50,
        choices=CATEGORY_CHOICES,
        default="general",
        help_text="Template category for organization",
    )

    # Template Data
    template_data = models.JSONField(
        help_text="JSON structure containing form definition and fields"
    )

    # Preview
    preview_url = models.URLField(
        blank=True,
        max_length=500,
        help_text="Optional URL to preview image or screenshot",
    )

    # Status
    is_active = models.BooleanField(
        default=True, help_text="Inactive templates are hidden from users"
    )
    is_system = models.BooleanField(
        default=False, help_text="System templates cannot be deleted"
    )

    # Usage Stats
    usage_count = models.IntegerField(
        default=0, help_text="Number of times this template has been used"
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="User who created this template",
    )

    class Meta:
        ordering = ["category", "name"]
        verbose_name = "Form Template"
        verbose_name_plural = "Form Templates"

    def __str__(self):
        return f"{self.name} ({self.get_category_display()})"

    def increment_usage(self):
        """Increment the usage counter when template is used"""
        self.usage_count += 1
        self.save(update_fields=["usage_count"])
