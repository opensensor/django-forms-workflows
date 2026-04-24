"""
Django Forms Workflows - Core Models

Database-driven form definitions with approval workflows and external data integration.
"""

import logging
import secrets
import uuid

from django.conf import settings
from django.contrib.auth.models import Group
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models

logger = logging.getLogger(__name__)


class FormCategory(models.Model):
    """
    Grouping primitive for FormDefinitions.

    Categories control how forms are organised in the list view,
    which groups of users can see them, and how the UI renders the
    section (icon, collapse state, display order).
    """

    name = models.CharField(
        max_length=200,
        unique=True,
        help_text="Human-readable category name (e.g. 'HR', 'IT Requests')",
    )
    slug = models.SlugField(
        unique=True,
        help_text="URL-safe identifier; auto-populated from name",
    )
    description = models.TextField(
        blank=True,
        help_text="Optional description shown to administrators",
    )
    order = models.PositiveIntegerField(
        default=0,
        help_text="Controls display order in the form list (lower = first)",
    )
    is_collapsed_by_default = models.BooleanField(
        default=False,
        help_text="If True, the category section renders collapsed in the UI",
    )
    allowed_groups = models.ManyToManyField(
        Group,
        blank=True,
        related_name="form_categories",
        help_text=(
            "Groups that may see/access forms in this category. "
            "Leave empty to allow all authenticated users."
        ),
    )
    icon = models.CharField(
        max_length=100,
        blank=True,
        help_text="Bootstrap icon class (e.g. 'bi-people-fill') shown in the section header",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
        help_text=(
            "Optional parent category. Leave empty for a top-level category. "
            "Allows arbitrary nesting for more granular organisation and permissioning."
        ),
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "name"]
        verbose_name = "Form Category"
        verbose_name_plural = "Form Categories"

    def __str__(self):
        return self.name

    def get_ancestors(self):
        """Return a list of ancestor categories ordered from root to direct parent."""
        ancestors = []
        current = self.parent
        while current is not None:
            ancestors.insert(0, current)
            current = current.parent
        return ancestors

    def full_path(self):
        """Return a ' > ' separated path string from the root category to this one."""
        return " > ".join(cat.name for cat in self.get_ancestors() + [self])


class FormDefinition(models.Model):
    """
    Master form configuration - created via Django Admin.

    Forms are stored in the database, not code, allowing non-developers
    to create and modify forms without deployments.
    """

    # Stable cross-instance identity
    uuid = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        db_index=True,
        help_text="Stable identity for cross-instance sync.",
    )

    # Category
    category = models.ForeignKey(
        FormCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="forms",
        help_text="Grouping category for this form. Leave blank for 'General/Other'.",
    )

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
    is_listed = models.BooleanField(
        default=True,
        help_text=(
            "When disabled, the form is hidden from the form list page but remains "
            "accessible to permitted users via its direct slug URL."
        ),
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
    reviewer_groups = models.ManyToManyField(
        Group,
        related_name="can_review_forms",
        blank=True,
        help_text=(
            "Groups that can view all submissions and full approval history for this form. "
            "Unlike admin groups, reviewers cannot manage the form itself."
        ),
    )

    # Behavior
    allow_save_draft = models.BooleanField(
        default=True, help_text="Users can save incomplete forms"
    )
    allow_withdrawal = models.BooleanField(
        default=True, help_text="Users can withdraw submitted forms before approval"
    )
    allow_resubmit = models.BooleanField(
        default=False,
        help_text=(
            "Allow submitters to start a new pre-filled submission from a rejected "
            "or withdrawn submission"
        ),
    )
    allow_batch_import = models.BooleanField(
        default=False,
        help_text=(
            "Allow users to download a pre-filled Excel template and upload it to "
            "submit multiple form entries at once. Each row is validated against the "
            "same rules as the individual form. File upload fields are excluded from "
            "batch import."
        ),
    )
    api_enabled = models.BooleanField(
        default=False,
        help_text=(
            "Expose this form via the REST API. Requires the API URLs to be included "
            "in your project's urls.py and the caller to supply a valid APIToken. "
            "All existing permission checks (submit_groups, view_groups) still apply."
        ),
    )
    embed_enabled = models.BooleanField(
        default=False,
        help_text=(
            "Allow this form to be embedded on external websites via an iframe. "
            "The form is served at /forms/<slug>/embed/ with a minimal layout. "
            "Works best with requires_login=False forms."
        ),
    )
    requires_login = models.BooleanField(
        default=True, help_text="Form requires authentication"
    )

    # Submission Controls
    close_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Automatically stop accepting submissions after this date/time",
    )
    max_submissions = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Maximum total submissions allowed (leave blank for unlimited)",
    )
    one_per_user = models.BooleanField(
        default=False,
        help_text="Restrict each authenticated user to a single submission",
    )

    # Bot Protection
    enable_captcha = models.BooleanField(
        default=False,
        help_text=(
            "Show a CAPTCHA challenge before submission. "
            "Requires FORMS_WORKFLOWS_CAPTCHA_SITE_KEY and "
            "FORMS_WORKFLOWS_CAPTCHA_SECRET_KEY in settings."
        ),
    )

    # Payment Configuration
    payment_enabled = models.BooleanField(
        default=False,
        help_text="Require payment for form submission.",
    )
    payment_provider = models.CharField(
        max_length=50,
        blank=True,
        help_text="Registered payment provider key (e.g., 'stripe').",
    )
    payment_amount_type = models.CharField(
        max_length=20,
        blank=True,
        default="fixed",
        choices=[
            ("fixed", "Fixed Amount"),
            ("field", "From Form Field"),
        ],
    )
    payment_fixed_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Fixed payment amount (when amount type is 'fixed').",
    )
    payment_amount_field = models.CharField(
        max_length=100,
        blank=True,
        help_text="field_name of a currency/decimal field for dynamic amounts.",
    )
    payment_currency = models.CharField(
        max_length=3,
        default="usd",
        blank=True,
        help_text="ISO 4217 currency code (e.g., 'usd', 'cad').",
    )
    payment_description_template = models.CharField(
        max_length=500,
        blank=True,
        help_text="Charge description. Supports {field_name} tokens.",
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

    # Success Page
    success_message = models.TextField(
        blank=True,
        help_text=(
            "Custom HTML shown after submission. Supports answer piping with "
            "{field_name} tokens that are replaced with the submitted values. "
            "Leave blank for the default confirmation message."
        ),
    )
    success_redirect_url = models.URLField(
        blank=True,
        help_text="Redirect to this URL after submission instead of showing a success page.",
    )
    success_redirect_rules = models.JSONField(
        blank=True,
        null=True,
        help_text=(
            "Conditional redirects based on form data. Format: "
            '[{"field": "field_name", "operator": "equals", "value": "...", "url": "https://..."}]. '
            "First matching rule wins; falls back to success_redirect_url or the default page."
        ),
    )

    # PDF Generation
    PDF_GENERATION_CHOICES = [
        ("none", "Disabled"),
        ("anytime", "Anytime"),
        ("post_approval", "Post Approval Only"),
    ]
    pdf_generation = models.CharField(
        max_length=20,
        choices=PDF_GENERATION_CHOICES,
        default="none",
        help_text=(
            "When a PDF of the submission can be downloaded. "
            "'Anytime' allows download as soon as the form is submitted; "
            "'Post Approval Only' restricts download to approved submissions."
        ),
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )

    # Change history (populated automatically by signals)
    change_history = GenericRelation(
        "django_forms_workflows.ChangeHistory",
        content_type_field="content_type",
        object_id_field="object_id",
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "Form Definition"
        verbose_name_plural = "Form Definitions"

    def __str__(self):
        return self.name

    @property
    def workflow(self):
        """Backward-compatible accessor — returns the first workflow or None.

        Before this was a OneToOneField with ``related_name="workflow"``.
        Now that WorkflowDefinition uses a ForeignKey (one-to-many), existing
        code that calls ``form_definition.workflow`` continues to work
        transparently.  For forms with multiple workflows, use
        ``form_definition.workflows.all()`` directly.
        """
        # Use the reverse manager installed by the ForeignKey (related_name="workflows")
        return self.workflows.first()


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

    # Code-defined database query (for complex queries like JOINs)
    database_query_key = models.CharField(
        max_length=100,
        blank=True,
        help_text="Key from FORMS_WORKFLOWS_DATABASE_QUERIES setting. "
        "Use this for complex queries (JOINs, additional WHERE conditions). "
        "Takes precedence over db_schema/db_table/db_column fields.",
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
        # Code-defined database query takes precedence
        if self.source_type == "database" and self.database_query_key:
            return f"dbquery.{self.database_query_key}"
        if self.source_type == "database" and self.db_schema and self.db_table:
            # Template-based multi-column lookup
            if self.db_template and self.db_columns:
                return f"{{{{ {self.db_schema}.{self.db_table}.* }}}}"
            # Single column lookup
            if self.db_column:
                return f"{{{{ {self.db_schema}.{self.db_table}.{self.db_column} }}}}"
        elif self.source_type == "ldap" and self.ldap_attribute:
            return f"ldap.{self.ldap_attribute}"
        elif self.source_type == "user":
            return self.source_key
        return self.source_key

    def has_custom_query(self):
        """Check if this source uses a code-defined database query."""
        return bool(self.database_query_key)

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
        ("phone", "Phone Number"),
        ("textarea", "Multi-line Text"),
        ("number", "Whole Number"),
        ("decimal", "Decimal Number"),
        ("currency", "Currency ($)"),
        ("date", "Date"),
        ("datetime", "Date and Time"),
        ("time", "Time"),
        ("email", "Email Address"),
        ("url", "Website URL"),
        ("select", "Dropdown Select"),
        ("multiselect", "Multiple Select (Checkboxes)"),
        ("multiselect_list", "Multiple Select (List)"),
        ("radio", "Radio Buttons"),
        ("checkbox", "Single Checkbox"),
        ("checkboxes", "Multiple Checkboxes"),
        ("file", "File Upload"),
        ("multifile", "Multi-File Upload"),
        ("hidden", "Hidden Field"),
        ("section", "Section Header (not a field)"),
        ("calculated", "Calculated / Formula"),
        ("spreadsheet", "Spreadsheet Upload (CSV / Excel)"),
        ("country", "Country Picker"),
        ("us_state", "US State Picker"),
        ("signature", "Signature"),
        ("rating", "Rating (Stars)"),
        ("matrix", "Matrix / Grid"),
        ("address", "Address"),
        ("slider", "Slider"),
        ("display_text", "Display Text (Read Only)"),
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
    show_help_text_in_detail = models.BooleanField(
        default=False,
        help_text=(
            "If checked, the field's help text is shown next to the value in the "
            "submission and approval detail view. Use for attestation or consent "
            "statements attached to initials/signature fields."
        ),
    )
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
            ("fourth", "One Quarter"),
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
    shared_option_list = models.ForeignKey(
        "SharedOptionList",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="form_fields",
        help_text=(
            "Use a centrally managed option list instead of inline choices. "
            "When set, this overrides the choices field above."
        ),
    )

    # Dynamic Behavior - Prefill from external sources
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
        """Return the prefill source identifier string for this field."""
        if self.prefill_source_config:
            return self.prefill_source_config.get_source_identifier()
        return ""

    # Formula / Calculated field
    formula = models.TextField(
        blank=True,
        default="",
        help_text=(
            'For "Calculated / Formula" fields: use {field_name} tokens to reference '
            "other fields. Supports literal text and concatenation. "
            "Example: {dept_code} - {job_type}"
        ),
    )

    # Conditional Logic (Client-Side Enhancements)
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

    # Approval Stage
    workflow_stage = models.ForeignKey(
        "WorkflowStage",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approval_fields",
        help_text="Stage this field appears in during approval.",
    )

    # File Upload Settings
    allowed_extensions = models.CharField(
        max_length=200, blank=True, help_text="Comma-separated: pdf,doc,docx,xls,xlsx"
    )
    max_file_size_mb = models.IntegerField(
        null=True, blank=True, help_text="Maximum file size in MB"
    )

    change_history = GenericRelation(
        "django_forms_workflows.ChangeHistory",
        content_type_field="content_type",
        object_id_field="object_id",
    )

    class Meta:
        ordering = ["order", "field_name"]
        unique_together = [["form_definition", "field_name"]]
        verbose_name = "Form Field"
        verbose_name_plural = "Form Fields"

    def __str__(self):
        return f"{self.field_label} ({self.field_name})"


class SharedOptionList(models.Model):
    """
    Centrally managed, reusable list of options.

    A single SharedOptionList (e.g. "Departments", "Building Locations",
    "Job Titles") can be referenced by any number of form fields across
    different forms.  When the list is updated, every field that
    references it automatically picks up the new options — no need to
    edit each form individually.
    """

    name = models.CharField(
        max_length=200,
        help_text="Display name (e.g. 'Departments', 'Building Locations')",
    )
    slug = models.SlugField(
        unique=True,
        help_text="Unique identifier used in the API and form builder",
    )
    items = models.JSONField(
        help_text=(
            "Ordered list of options. Each item is either a string (used as "
            'both value and label) or an object: {"value": "eng", "label": "Engineering"}.'
        ),
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive lists are hidden from the form builder but still resolve for existing fields.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Shared Option List"
        verbose_name_plural = "Shared Option Lists"

    def __str__(self):
        return f"{self.name} ({len(self.get_choices())} options)"

    def get_choices(self):
        """Return items as a list of (value, label) tuples."""
        result = []
        for item in self.items or []:
            if isinstance(item, dict):
                result.append((item.get("value", ""), item.get("label", "")))
            else:
                result.append((str(item), str(item)))
        return result


class DocumentTemplate(models.Model):
    """
    Custom PDF document template with merge fields.

    Allows form admins to design polished PDF documents (certificates,
    letters, contracts) that are populated with submission data.  Uses
    ``{field_name}`` merge-field syntax and supports conditional sections
    with ``{% if field_name %}...{% endif %}`` blocks.

    Generated documents are served via the existing permission-gated
    ``submission_pdf`` endpoint — they are **never** attached to emails
    to prevent PII from travelling through email.
    """

    form_definition = models.ForeignKey(
        FormDefinition,
        related_name="document_templates",
        on_delete=models.CASCADE,
        help_text="The form this template belongs to.",
    )
    name = models.CharField(
        max_length=200,
        help_text="Display name (e.g. 'Approval Certificate', 'Offer Letter').",
    )
    is_default = models.BooleanField(
        default=False,
        help_text=(
            "Use this template instead of the built-in PDF layout when "
            "downloading a submission PDF."
        ),
    )
    is_active = models.BooleanField(default=True)

    # Template content
    html_content = models.TextField(
        help_text=(
            "Full HTML document with CSS. Use {field_name} merge fields to "
            "insert submitted values. Use {% if field_name %}...{% endif %} "
            "for conditional sections. Available variables: {form_name}, "
            "{submission_id}, {submitted_at}, {status}, {submitter_name}, "
            "and all form field names."
        ),
    )
    page_size = models.CharField(
        max_length=20,
        default="letter",
        choices=[
            ("letter", "US Letter (8.5 x 11 in)"),
            ("a4", "A4 (210 x 297 mm)"),
            ("legal", "US Legal (8.5 x 14 in)"),
        ],
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["form_definition", "name"]
        verbose_name = "Document Template"
        verbose_name_plural = "Document Templates"

    def __str__(self):
        return f"{self.name} ({self.form_definition.name})"

    def render(self, submission):
        """Render this template with submission data, returning HTML string."""
        import re

        form_data = submission.form_data or {}

        # Build merge context with system variables + form data
        context = {
            "form_name": submission.form_definition.name,
            "submission_id": str(submission.id),
            "submitted_at": (
                submission.submitted_at.strftime("%B %d, %Y at %I:%M %p")
                if submission.submitted_at
                else ""
            ),
            "status": submission.status.replace("_", " ").title(),
            "submitter_name": (
                submission.submitter.get_full_name() or submission.submitter.username
                if submission.submitter
                else "Anonymous"
            ),
        }
        # Add all form field values
        for key, val in form_data.items():
            if isinstance(val, list):
                context[key] = ", ".join(str(v) for v in val)
            else:
                context[key] = str(val) if val is not None else ""

        html = self.html_content

        # Process conditional blocks: {% if field_name %}...{% endif %}
        def _eval_conditional(m):
            field = m.group(1)
            content = m.group(2)
            val = context.get(field, "")
            if val and val not in ("False", "false", "0", "None", ""):
                # Recursively process merge fields inside the block
                return re.sub(
                    r"\{(\w+)\}", lambda mm: context.get(mm.group(1), ""), content
                )
            return ""

        html = re.sub(
            r"\{%\s*if\s+(\w+)\s*%\}(.*?)\{%\s*endif\s*%\}",
            _eval_conditional,
            html,
            flags=re.DOTALL,
        )

        # Replace remaining {field_name} merge tokens
        html = re.sub(
            r"\{(\w+)\}",
            lambda m: context.get(m.group(1), ""),
            html,
        )

        return html


class WorkflowDefinition(models.Model):
    """
    Approval workflow configuration.

    Supports multi-step approvals with flexible routing logic via WorkflowStage:
    - All approvers must approve (AND)
    - Any approver can approve (OR)
    - Sequential approval chain
    - Manager approval from LDAP hierarchy
    """

    uuid = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        db_index=True,
        help_text="Stable identity for cross-instance sync.",
    )

    form_definition = models.ForeignKey(
        FormDefinition, related_name="workflows", on_delete=models.CASCADE
    )

    name_label = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text=(
            "User-facing label for this workflow shown in the submission "
            'detail header (e.g. "Contract Approval"). When blank, falls '
            "back to the form definition name."
        ),
    )

    START_TRIGGER_CHOICES = [
        ("on_submission", "On Submission (default)"),
        (
            "on_all_complete",
            "After All Other Workflows Complete",
        ),
    ]

    start_trigger = models.CharField(
        max_length=20,
        choices=START_TRIGGER_CHOICES,
        default="on_submission",
        help_text=(
            "When this workflow should start. "
            '"On Submission" starts immediately when the form is submitted. '
            '"After All Other Workflows Complete" waits until every other '
            "on_submission workflow on this form has finished before starting."
        ),
    )

    # Basic Approval
    requires_approval = models.BooleanField(default=True)

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

    # Notification Batching
    NOTIFICATION_CADENCE_CHOICES = [
        ("immediate", "Immediate (send right away)"),
        ("daily", "Daily digest"),
        ("weekly", "Weekly digest"),
        ("monthly", "Monthly digest"),
        ("form_field_date", "On date from a form field"),
    ]

    notification_cadence = models.CharField(
        max_length=20,
        choices=NOTIFICATION_CADENCE_CHOICES,
        default="immediate",
        help_text=(
            "When to send approval-request and submission notifications. "
            "Non-immediate options batch multiple notifications into a single digest email."
        ),
    )
    notification_cadence_day = models.IntegerField(
        null=True,
        blank=True,
        help_text=(
            "For weekly: day of week (0=Monday … 6=Sunday). "
            "For monthly: day of month (1–31)."
        ),
    )
    notification_cadence_time = models.TimeField(
        null=True,
        blank=True,
        help_text="Time of day to send batch digest (leave blank to use 08:00).",
    )
    notification_cadence_form_field = models.SlugField(
        blank=True,
        help_text=(
            "For 'On date from a form field': the field slug whose date value "
            "determines when to send the digest."
        ),
    )

    # Visual Workflow Builder Data
    visual_workflow_data = models.JSONField(
        blank=True,
        null=True,
        help_text="Visual workflow builder layout (nodes and connections)",
    )

    # Conditional trigger — when set, this workflow only runs if the
    # submission data matches the conditions.  None / empty = always run.
    trigger_conditions = models.JSONField(
        blank=True,
        null=True,
        help_text=(
            "Conditions that must be met for this workflow to run. "
            'Format: {"operator": "AND|OR", "conditions": '
            '[{"field": "field_name", "operator": "equals|not_equals|gt|lt|gte|lte|contains|in", '
            '"value": "..."}]}'
        ),
    )

    # Privacy
    hide_approval_history = models.BooleanField(
        default=False,
        help_text=(
            "When enabled, the submitter will not see approval history or "
            "individual approval steps — only the final decision (approved / rejected) "
            "is shown. Approvers and admins can still see the full history."
        ),
    )

    # Approval History Display
    collapse_parallel_stages = models.BooleanField(
        default=False,
        help_text=(
            "When enabled, parallel stages that share the same order number are "
            "collapsed into a single combined table in the approval history, "
            "instead of each appearing as its own card."
        ),
    )

    # Bulk Export
    allow_bulk_export = models.BooleanField(
        default=False,
        help_text=(
            "Allow users to select and bulk-export submissions for this form "
            "into an Excel spreadsheet from the approval and submissions list views."
        ),
    )
    allow_bulk_pdf_export = models.BooleanField(
        default=False,
        help_text=(
            "Allow users to select and bulk-export submissions for this form "
            "into a single merged PDF from the approval and submissions list views."
        ),
    )

    change_history = GenericRelation(
        "django_forms_workflows.ChangeHistory",
        content_type_field="content_type",
        object_id_field="object_id",
    )

    class Meta:
        verbose_name = "Workflow Definition"
        verbose_name_plural = "Workflow Definitions"

    def __str__(self):
        return f"Workflow for {self.form_definition.name}"


class WorkflowStage(models.Model):
    """
    A single stage in a staged approval workflow.

    Stages execute sequentially (stage 1 → stage 2 → … → finalize).
    Within each stage, tasks follow the stage's own approval_logic
    (all/any/sequence), allowing hybrid workflows like:
      Stage 1: Manager approval (sequence)
      Stage 2: Finance AND Legal approve in parallel (all)
      Stage 3: Any VP can sign off (any)

    """

    STAGE_LOGIC = [
        ("all", "All must approve (AND)"),
        ("any", "Any can approve (OR)"),
        ("sequence", "Sequential within stage"),
    ]

    uuid = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        db_index=True,
        help_text="Stable identity for cross-instance sync.",
    )

    workflow = models.ForeignKey(
        WorkflowDefinition,
        related_name="stages",
        on_delete=models.CASCADE,
    )
    name = models.CharField(max_length=100, help_text="Human-readable stage name")
    order = models.PositiveIntegerField(
        default=0, help_text="Execution order — lower numbers run first"
    )
    approval_logic = models.CharField(
        max_length=20,
        choices=STAGE_LOGIC,
        default="all",
        help_text="How approvals in this stage are resolved",
    )
    approval_groups = models.ManyToManyField(
        Group,
        through="StageApprovalGroup",
        related_name="workflow_stages",
        blank=True,
        help_text="Groups that participate in this stage",
    )
    requires_manager_approval = models.BooleanField(
        default=False,
        help_text="Also require submitter's manager approval in this stage (requires LDAP)",
    )
    approve_label = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text=(
            "Custom label for the approve/complete button shown to the approver "
            '(e.g. "Complete", "Confirm", "Sign Off"). Defaults to "Approve" when blank.'
        ),
    )
    # Conditional trigger — when set, this stage only runs if the
    # submission data matches the conditions.  None / empty = always run.
    trigger_conditions = models.JSONField(
        blank=True,
        null=True,
        help_text=(
            "Conditions that must be met for this stage to run. "
            "When advancing from a prior stage, only stages whose conditions "
            "match the submission data will be entered. "
            'Format: {"operator": "AND|OR", "conditions": '
            '[{"field": "field_name", "operator": "equals|not_equals|gt|lt|gte|lte|contains|in", '
            '"value": "..."}]}'
        ),
    )
    ASSIGNEE_LOOKUP_TYPES = [
        ("email", "Email address"),
        ("username", "Username (sAMAccountName)"),
        ("full_name", "Full name (First Last)"),
        ("ldap", "LDAP lookup by display name"),
    ]

    assignee_form_field = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text=(
            "Form field slug whose submitted value identifies the assignee. "
            "When set, the workflow engine resolves the assignee using the "
            "lookup type below and assigns this stage's task directly to them "
            "(bypassing the approval groups). Falls back to group assignment "
            "if the field is empty or no matching user is found."
        ),
    )
    assignee_lookup_type = models.CharField(
        max_length=20,
        choices=ASSIGNEE_LOOKUP_TYPES,
        default="email",
        help_text=(
            "How to resolve the form field value to a system user. "
            "'Email' looks up by email address. "
            "'Username' looks up by sAMAccountName/username. "
            "'Full name' matches against Django User first_name + last_name (iexact), "
            "then falls back to an LDAP search — NOTE: for Google SSO-only sites, "
            "first_name/last_name are only populated if Google SAML sends those "
            "attributes or users were pre-provisioned via sync_ldap_users. "
            "'LDAP lookup' searches Active Directory directly by display name and "
            "auto-provisions the Django user if not yet in the system — recommended "
            "for sites where SSO does not populate first/last name."
        ),
    )
    allow_send_back = models.BooleanField(
        default=False,
        help_text=(
            "Allow approvers at a later stage to return the submission to this stage "
            "for correction, without terminating the workflow. When enabled, this stage "
            "will appear as a 'Send Back' target option for all subsequent stages."
        ),
    )
    validate_assignee_group = models.BooleanField(
        default=True,
        help_text=(
            "When a dynamic assignee is resolved from a form field, require "
            "that the user belongs to at least one of this stage's approval "
            "groups. If unchecked, any resolved user can be assigned regardless "
            "of group membership."
        ),
    )
    allow_reassign = models.BooleanField(
        default=False,
        help_text=(
            "Allow the assigned approver (or any member of the stage's approval "
            "groups) to reassign this task to another member of the same "
            "approval groups."
        ),
    )
    allow_edit_form_data = models.BooleanField(
        default=False,
        help_text=(
            "Allow approvers at this stage to edit the original form submission "
            "data. When enabled, the submission fields are shown as editable "
            "inputs instead of a read-only table. Changes are saved when the "
            "approver approves the submission."
        ),
    )
    hide_comment_field = models.BooleanField(
        default=False,
        help_text=(
            "Hide the public decision comment field from approvers at this stage. "
            "Useful for stages where no notifications are sent to the submitter "
            "or where the comment would not be meaningful."
        ),
    )

    change_history = GenericRelation(
        "django_forms_workflows.ChangeHistory",
        content_type_field="content_type",
        object_id_field="object_id",
    )

    class Meta:
        ordering = ["order"]
        verbose_name = "Workflow Stage"
        verbose_name_plural = "Workflow Stages"

    def __str__(self) -> str:
        return f"Stage {self.order}: {self.name}"

    # ------------------------------------------------------------------
    # Helpers to retrieve groups by role (with fallback to approval)
    # ------------------------------------------------------------------

    def _groups_by_role(self, role: str):
        """Return groups for *role*, falling back to approval groups if none."""
        qs = Group.objects.filter(
            stageapprovalgroup__stage=self,
            stageapprovalgroup__role=role,
        ).order_by("stageapprovalgroup__position")
        if qs.exists():
            return qs
        # Fallback: approval groups
        return Group.objects.filter(
            stageapprovalgroup__stage=self,
            stageapprovalgroup__role="approval",
        ).order_by("stageapprovalgroup__position")

    def get_validation_groups(self):
        """Groups used to validate a dynamic assignee's membership."""
        return self._groups_by_role("validation")

    def get_reassignment_groups(self):
        """Groups that define the eligible reassignment pool."""
        return self._groups_by_role("reassignment")

    def get_approval_groups(self):
        """Groups used for fallback task assignment / approval logic."""
        return Group.objects.filter(
            stageapprovalgroup__stage=self,
            stageapprovalgroup__role="approval",
        ).order_by("stageapprovalgroup__position")


class StageApprovalGroup(models.Model):
    """
    Through model for WorkflowStage ↔ Group M2M.

    Stores a ``position`` so admins can control the order groups are
    processed when approval_logic is ``"sequence"``.

    The ``role`` field distinguishes the purpose of a group within the stage:

    * **approval** – the default pool used for fallback task assignment and
      approval logic (AND/OR/sequence).
    * **validation** – used to check that a dynamically resolved assignee
      belongs to an allowed group.  When no validation groups are configured,
      approval groups are used instead.
    * **reassignment** – defines the eligible pool of users for task
      reassignment.  When no reassignment groups are configured, approval
      groups are used instead.

    The same Django ``Group`` may appear under multiple roles for a single
    stage (e.g. both approval and reassignment).
    """

    ROLE_CHOICES = [
        ("approval", "Approval (default)"),
        ("validation", "Assignee validation"),
        ("reassignment", "Reassignment pool"),
    ]

    stage = models.ForeignKey(
        WorkflowStage,
        on_delete=models.CASCADE,
    )
    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
    )
    position = models.PositiveIntegerField(
        default=0,
        help_text="Order in which this group is processed (lower = first)",
    )
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default="approval",
        help_text=(
            "Purpose of this group in the stage. "
            "'Approval' groups receive fallback tasks and define the default pool. "
            "'Validation' groups are checked when verifying a dynamic assignee's "
            "group membership (falls back to approval groups when none defined). "
            "'Reassignment' groups define who may be reassigned to "
            "(falls back to approval groups when none defined)."
        ),
    )

    class Meta:
        ordering = ["role", "position"]
        unique_together = [("stage", "group", "role")]
        verbose_name = "Stage Approval Group"
        verbose_name_plural = "Stage Approval Groups"

    def __str__(self) -> str:
        label = self.get_role_display() if self.role != "approval" else ""
        suffix = f" [{label}]" if label else ""
        return f"{self.group.name} (pos {self.position}){suffix}"


class NotificationRule(models.Model):
    """
    Unified notification rule for all workflow events.

    Each rule specifies **when** to fire (event), **who** to send to
    (recipient sources), and optional **conditions** evaluated against
    form_data.  Multiple recipient sources are combined additively
    and deduplicated.

    Scope:
      - ``stage`` is null  → workflow-level rule.  For recipient sources
        like ``notify_stage_assignees`` / ``notify_stage_groups``, this
        means *all* stages' assignees/groups are included.
      - ``stage`` is set   → stage-scoped rule.  Recipient sources
        reference only that specific stage.

    Replaces the former ``WorkflowNotification``,
    ``StageFormFieldNotification``, and
    ``WorkflowStage.notify_assignee_on_final_decision``.
    """

    EVENT_TYPES = [
        ("submission_received", "Submission Received"),
        ("approval_request", "Approval Request (stage activated)"),
        ("stage_decision", "Stage Decision (individual stage completed)"),
        ("workflow_approved", "Workflow Approved (final decision)"),
        ("workflow_denied", "Workflow Denied (final decision)"),
        ("form_withdrawn", "Form Withdrawn"),
        ("approval_reminder", "Approval Reminder"),
        ("escalation", "Escalation"),
    ]

    workflow = models.ForeignKey(
        "WorkflowDefinition",
        on_delete=models.CASCADE,
        related_name="notification_rules",
    )
    stage = models.ForeignKey(
        "WorkflowStage",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notification_rules",
        help_text=(
            "Optional. When set, scopes this rule to a specific stage. "
            "Recipient sources like 'Notify stage assignees' and "
            "'Notify stage groups' will reference only this stage. "
            "When blank, they reference all stages in the workflow. "
            "Ignored when 'Use triggering stage' is checked."
        ),
    )
    use_triggering_stage = models.BooleanField(
        default=False,
        help_text=(
            "When checked, automatically scopes this rule to whichever "
            "stage triggered the event at runtime. This avoids needing "
            "to create a separate rule per stage. Overrides the Stage "
            "dropdown above."
        ),
    )
    event = models.CharField(
        max_length=30,
        choices=EVENT_TYPES,
        help_text="The workflow event that triggers this notification.",
    )
    conditions = models.JSONField(
        blank=True,
        null=True,
        help_text=(
            "Optional conditions evaluated against form_data. "
            "Uses the same format as stage trigger_conditions. "
            "When set, the notification only fires if conditions are met."
        ),
    )
    subject_template = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text=(
            "Custom email subject line. Supports {form_name} and "
            "{submission_id} placeholders. Leave blank for the default."
        ),
    )
    body_template = models.TextField(
        blank=True,
        default="",
        help_text=(
            "Custom email body (HTML). Rendered as a Django template with "
            "the full notification context (submission, form_data, approver, "
            "task, approval_url, submission_url, site_name, etc.). "
            "Leave blank to use the built-in template for this event type."
        ),
    )

    # ── Recipient sources (all optional, combined additively) ──

    notify_submitter = models.BooleanField(
        default=False,
        help_text="Include the person who submitted the form.",
    )
    email_field = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text=(
            "Form field slug whose submitted value is an email address. "
            "Resolved from form_data at send time (varies per submission)."
        ),
    )
    static_emails = models.CharField(
        max_length=1000,
        blank=True,
        default="",
        help_text="Comma-separated fixed email addresses.",
    )
    cc_email_field = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text=(
            "Form field slug whose submitted value is a CC email address. "
            "Resolved from form_data at send time (varies per submission)."
        ),
    )
    cc_static_emails = models.CharField(
        max_length=1000,
        blank=True,
        default="",
        help_text="Comma-separated fixed CC email addresses.",
    )
    notify_stage_assignees = models.BooleanField(
        default=False,
        help_text=(
            "Include dynamically-assigned approvers. When a stage is "
            "specified, only that stage's assignee is included. When no "
            "stage is specified, assignees from all stages are included."
        ),
    )
    notify_stage_groups = models.BooleanField(
        default=False,
        help_text=(
            "Include all users in the stage's approval groups. When a "
            "stage is specified, only that stage's groups are included. "
            "When no stage is specified, groups from all stages are included."
        ),
    )
    notify_groups = models.ManyToManyField(
        Group,
        blank=True,
        related_name="notification_rules",
        help_text=(
            "Additional groups to notify, independent of stage assignment. "
            "All users in these groups with a non-empty email will receive "
            "the notification."
        ),
    )

    class Meta:
        verbose_name = "Notification Rule"
        verbose_name_plural = "Notification Rules"
        ordering = ["workflow", "event", "stage"]

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.use_triggering_stage and self.stage_id:
            raise ValidationError(
                "'Use triggering stage' and a specific 'Stage' are mutually "
                "exclusive. Either pick a stage or check 'Use triggering stage'."
            )

        has_recipients = (
            self.notify_submitter
            or self.email_field
            or self.static_emails
            or self.notify_stage_assignees
            or self.notify_stage_groups
        )
        # notify_groups is M2M — can't check before save; validated in admin
        if not has_recipients:
            raise ValidationError(
                "At least one recipient source must be set: "
                "'Notify submitter', 'Email field', 'Static emails', "
                "'Notify stage assignees', or 'Notify stage groups'."
            )

    def __str__(self) -> str:
        parts = []
        if self.notify_submitter:
            parts.append("submitter")
        if self.email_field:
            parts.append(f"field:{self.email_field}")
        if self.static_emails:
            parts.append("static")
        if self.notify_stage_assignees:
            parts.append("assignees")
        if self.notify_stage_groups:
            parts.append("stage-groups")
        target = ", ".join(parts) if parts else "groups"
        if self.use_triggering_stage:
            stage_label = " [triggering stage]"
        elif self.stage_id:
            stage_label = f" [{self.stage.name}]"
        else:
            stage_label = ""
        return f"{self.get_event_display()}{stage_label} → {target}"


class PendingNotification(models.Model):
    """
    Queue of notifications waiting to be sent as part of a batch digest.

    When a WorkflowDefinition has a non-immediate notification_cadence,
    NotificationRule-level events are stored here instead of being emailed
    immediately.

    The ``send_batched_notifications`` periodic task finds due records, groups them
    by (recipient_email, notification_type, workflow_id), and sends one digest email
    per group.
    """

    NOTIFICATION_TYPES = [
        ("submission_received", "Submission Received"),
        ("approval_request", "Approval Request"),
        ("stage_decision", "Stage Decision"),
        ("workflow_approved", "Workflow Approved"),
        ("workflow_denied", "Workflow Denied"),
        ("form_withdrawn", "Form Withdrawn"),
        # Legacy names kept for unsent records created before migration
        ("approval_notification", "Approval Notification (legacy)"),
        ("rejection_notification", "Rejection Notification (legacy)"),
        ("withdrawal_notification", "Withdrawal Notification (legacy)"),
    ]

    workflow = models.ForeignKey(
        WorkflowDefinition,
        on_delete=models.CASCADE,
        related_name="pending_notifications",
    )
    notification_type = models.CharField(max_length=30, choices=NOTIFICATION_TYPES)
    submission = models.ForeignKey(
        "FormSubmission",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="pending_notifications",
    )
    approval_task = models.ForeignKey(
        "ApprovalTask",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pending_notifications",
    )
    recipient_email = models.EmailField()
    scheduled_for = models.DateTimeField(
        help_text="When this notification should be included in a batch send.",
        db_index=True,
    )
    sent = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Pending Notification"
        verbose_name_plural = "Pending Notifications"
        ordering = ["scheduled_for", "notification_type"]

    def __str__(self) -> str:
        return (
            f"{self.get_notification_type_display()} → {self.recipient_email} "
            f"(due {self.scheduled_for:%Y-%m-%d %H:%M})"
        )


class UserNotificationPreference(models.Model):
    """Per-user opt-out for a specific NotificationRule.

    A record exists only when the user has explicitly muted a rule.
    Absence of a record means "send as normal". When ``muted`` is True,
    ``send_notification_rules`` drops the user's email from the resolved
    recipient list before sending (or queuing for digest).
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_preferences",
    )
    rule = models.ForeignKey(
        "NotificationRule",
        on_delete=models.CASCADE,
        related_name="user_preferences",
    )
    muted = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "User Notification Preference"
        verbose_name_plural = "User Notification Preferences"
        unique_together = [("user", "rule")]
        indexes = [models.Index(fields=["rule", "muted"])]

    def __str__(self) -> str:
        state = "muted" if self.muted else "subscribed"
        return f"{self.user} [{state}] → rule #{self.rule_id}"


class WebhookEndpoint(models.Model):
    """First-class outbound webhook subscriptions for workflow lifecycle events."""

    EVENT_TYPES = [
        ("submission.created", "Submission Created"),
        ("submission.approved", "Submission Approved"),
        ("submission.rejected", "Submission Rejected"),
        ("submission.returned", "Submission Returned"),
        ("task.created", "Approval Task Created"),
    ]

    workflow = models.ForeignKey(
        WorkflowDefinition,
        on_delete=models.CASCADE,
        related_name="webhook_endpoints",
    )
    name = models.CharField(max_length=200)
    url = models.URLField(max_length=500)
    secret = models.CharField(
        max_length=255,
        blank=True,
        help_text=(
            "HMAC signing secret. Leave blank to auto-generate a secure secret on save."
        ),
    )
    events = models.JSONField(
        default=list,
        blank=True,
        help_text="List of subscribed event names, e.g. ['submission.created']",
    )
    custom_headers = models.JSONField(
        blank=True,
        null=True,
        help_text='Optional static headers as JSON, e.g. {"Authorization": "Bearer ..."}',
    )
    is_active = models.BooleanField(default=True)
    timeout_seconds = models.PositiveIntegerField(default=15)
    retry_on_failure = models.BooleanField(default=True)
    max_retries = models.PositiveIntegerField(default=3)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["workflow", "name"]
        verbose_name = "Webhook Endpoint"
        verbose_name_plural = "Webhook Endpoints"

    def clean(self):
        from django.core.exceptions import ValidationError

        if not isinstance(self.events, list | tuple):
            raise ValidationError({"events": "Events must be stored as a list."})

        valid_events = {value for value, _label in self.EVENT_TYPES}
        invalid_events = sorted(set(self.events) - valid_events)
        if invalid_events:
            raise ValidationError(
                {"events": f"Unsupported webhook events: {', '.join(invalid_events)}"}
            )
        if self.is_active and not self.events:
            raise ValidationError(
                {"events": "Select at least one event for an active webhook endpoint."}
            )
        if self.custom_headers is not None and not isinstance(
            self.custom_headers, dict
        ):
            raise ValidationError(
                {"custom_headers": "Custom headers must be a JSON object/dict."}
            )

    def save(self, *args, **kwargs):
        if not self.secret:
            self.secret = secrets.token_hex(32)
        super().save(*args, **kwargs)

    def subscribes_to(self, event: str) -> bool:
        return self.is_active and event in (self.events or [])

    def __str__(self):
        workflow_label = self.workflow.name_label or self.workflow.form_definition.name
        return f"{self.name} → {workflow_label}"


class WebhookDeliveryLog(models.Model):
    """Audit trail for outbound webhook delivery attempts."""

    endpoint = models.ForeignKey(
        "WebhookEndpoint",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="delivery_logs",
    )
    workflow = models.ForeignKey(
        WorkflowDefinition,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="webhook_delivery_logs",
    )
    submission = models.ForeignKey(
        "FormSubmission",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="webhook_delivery_logs",
    )
    approval_task = models.ForeignKey(
        "ApprovalTask",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="webhook_delivery_logs",
    )
    event = models.CharField(
        max_length=50, choices=WebhookEndpoint.EVENT_TYPES, db_index=True
    )
    endpoint_name = models.CharField(max_length=200, blank=True, default="")
    delivery_url = models.URLField(max_length=500)
    attempt_number = models.PositiveIntegerField(default=1)
    success = models.BooleanField(default=False, db_index=True)
    status_code = models.PositiveIntegerField(null=True, blank=True)
    error_message = models.TextField(blank=True, default="")
    request_headers = models.JSONField(blank=True, null=True)
    payload = models.JSONField(blank=True, null=True)
    response_body = models.TextField(blank=True, default="")
    delivered_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-delivered_at"]
        verbose_name = "Webhook Delivery Log"
        verbose_name_plural = "Webhook Delivery Logs"
        indexes = [
            models.Index(fields=["event", "success"]),
            models.Index(fields=["submission", "event"]),
        ]

    def __str__(self):
        status = "✓" if self.success else "✗"
        return f"{status} {self.event} → {self.delivery_url}"


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

    # Email Notification Configuration
    email_to = models.TextField(
        blank=True,
        help_text="Static email addresses (comma-separated) for recipients",
    )
    email_to_field = models.CharField(
        max_length=100,
        blank=True,
        help_text="Form field containing recipient email address (e.g., 'instructor_email')",
    )
    email_cc = models.TextField(
        blank=True,
        help_text="Static CC email addresses (comma-separated)",
    )
    email_cc_field = models.CharField(
        max_length=100,
        blank=True,
        help_text="Form field containing CC email address",
    )
    email_subject_template = models.CharField(
        max_length=500,
        blank=True,
        help_text="Email subject template. Use {field_name} for form field values.",
    )
    email_body_template = models.TextField(
        blank=True,
        help_text="Email body template. Use {field_name} for form field values.",
    )
    email_template_name = models.CharField(
        max_length=200,
        blank=True,
        help_text="Django template path for HTML email (e.g., 'emails/approval.html')",
    )

    # Lock mechanism to prevent duplicate actions
    is_locked = models.BooleanField(
        default=False,
        help_text="If True, this action will only execute once per submission (prevents duplicates)",
    )

    # Conditional Execution
    condition_field = models.CharField(
        max_length=100,
        blank=True,
        help_text="Form field to check for conditional execution",
    )
    condition_operator = models.CharField(
        max_length=30,
        blank=True,
        choices=[
            ("equals", "Equals"),
            ("not_equals", "Not Equals"),
            ("contains", "Contains"),
            ("not_contains", "Does Not Contain"),
            ("greater_than", "Greater Than"),
            ("less_than", "Less Than"),
            ("greater_than_today", "Date Is After Today"),
            ("less_than_today", "Date Is Before Today"),
            ("is_today", "Date Is Today"),
            ("is_true", "Is True"),
            ("is_false", "Is False"),
            ("is_empty", "Is Empty"),
            ("is_not_empty", "Is Not Empty"),
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
        from datetime import date, datetime

        if not self.is_active:
            return False

        # Check if action is locked and has already executed
        if self.is_locked:
            # Check if this action has already executed successfully for this submission
            # ActionExecutionLog is defined later in this module; safe to reference at runtime
            if ActionExecutionLog.objects.filter(
                action=self, submission=submission, success=True
            ).exists():
                return False

        # Check conditional execution
        if self.condition_field and self.condition_operator:
            field_value = submission.form_data.get(self.condition_field)

            if self.condition_operator == "equals":
                return str(field_value) == self.condition_value
            if self.condition_operator == "not_equals":
                return str(field_value) != self.condition_value
            if self.condition_operator == "contains":
                return self.condition_value in str(field_value)
            if self.condition_operator == "not_contains":
                return self.condition_value not in str(field_value)
            if self.condition_operator == "greater_than":
                try:
                    return float(field_value) > float(self.condition_value)
                except (ValueError, TypeError):
                    return False
            elif self.condition_operator == "less_than":
                try:
                    return float(field_value) < float(self.condition_value)
                except (ValueError, TypeError):
                    return False
            elif self.condition_operator == "greater_than_today":
                # Compare date field against today
                try:
                    if isinstance(field_value, str):
                        field_date = datetime.strptime(
                            field_value[:10], "%Y-%m-%d"
                        ).date()
                    elif isinstance(field_value, datetime):
                        field_date = field_value.date()
                    elif isinstance(field_value, date):
                        field_date = field_value
                    else:
                        return False
                    return field_date > date.today()
                except (ValueError, TypeError):
                    return False
            elif self.condition_operator == "less_than_today":
                # Compare date field against today
                try:
                    if isinstance(field_value, str):
                        field_date = datetime.strptime(
                            field_value[:10], "%Y-%m-%d"
                        ).date()
                    elif isinstance(field_value, datetime):
                        field_date = field_value.date()
                    elif isinstance(field_value, date):
                        field_date = field_value
                    else:
                        return False
                    return field_date < date.today()
                except (ValueError, TypeError):
                    return False
            elif self.condition_operator == "is_today":
                # Check if date field equals today
                try:
                    if isinstance(field_value, str):
                        field_date = datetime.strptime(
                            field_value[:10], "%Y-%m-%d"
                        ).date()
                    elif isinstance(field_value, datetime):
                        field_date = field_value.date()
                    elif isinstance(field_value, date):
                        field_date = field_value
                    else:
                        return False
                    return field_date == date.today()
                except (ValueError, TypeError):
                    return False
            elif self.condition_operator == "is_true":
                return bool(field_value)
            elif self.condition_operator == "is_false":
                return not bool(field_value)
            elif self.condition_operator == "is_empty":
                return field_value is None or str(field_value).strip() == ""
            elif self.condition_operator == "is_not_empty":
                return field_value is not None and str(field_value).strip() != ""

        return True


class ActionExecutionLog(models.Model):
    """
    Log of post-submission action executions.

    Used to track which actions have been executed for each submission,
    enabling the is_locked functionality to prevent duplicate actions.
    """

    action = models.ForeignKey(
        PostSubmissionAction,
        on_delete=models.CASCADE,
        related_name="execution_logs",
    )
    submission = models.ForeignKey(
        "FormSubmission",
        on_delete=models.CASCADE,
        related_name="action_logs",
    )
    trigger = models.CharField(
        max_length=20,
        help_text="The trigger type that initiated this execution",
    )
    success = models.BooleanField(default=False)
    message = models.TextField(blank=True)
    executed_at = models.DateTimeField(auto_now_add=True)
    execution_data = models.JSONField(
        blank=True, null=True, help_text="Additional execution details"
    )

    class Meta:
        ordering = ["-executed_at"]
        verbose_name = "Action Execution Log"
        verbose_name_plural = "Action Execution Logs"
        indexes = [
            models.Index(fields=["action", "submission", "success"]),
        ]

    def __str__(self):
        status = "✓" if self.success else "✗"
        return f"{status} {self.action.name} on submission {self.submission_id}"


class FormSubmission(models.Model):
    """
    Actual form submission data.

    Stores the submitted form data as JSON along with status tracking,
    timestamps, and metadata for audit purposes.
    """

    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("pending_payment", "Pending Payment"),
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
        null=True,
        blank=True,
        help_text="Null for anonymous (public-form) submissions.",
    )

    # Submission Data
    form_data = models.JSONField(
        help_text="The actual form responses",
        encoder=DjangoJSONEncoder,
    )
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

    change_history = GenericRelation(
        "django_forms_workflows.ChangeHistory",
        content_type_field="content_type",
        object_id_field="object_id",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "submitter"]),
            models.Index(fields=["form_definition", "status"]),
        ]
        verbose_name = "Form Submission"
        verbose_name_plural = "Form Submissions"

    def __str__(self):
        who = self.submitter.username if self.submitter_id else "Anonymous"
        return f"{self.form_definition.name} - {who} - {self.get_status_display()}"


class PaymentRecord(models.Model):
    """
    Tracks payment lifecycle for a form submission.

    One submission may have multiple payment attempts (failed then
    succeeded) but only one completed payment.  The ``provider_data``
    field stores sanitized provider responses for audit — no card
    numbers or PII.  Generated documents and receipts are served via
    the existing permission-gated download endpoint, never emailed.
    """

    PAYMENT_STATUS_CHOICES = [
        ("pending", "Pending"),
        ("requires_action", "Requires Action"),
        ("processing", "Processing"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("cancelled", "Cancelled"),
        ("refunded", "Refunded"),
    ]

    submission = models.ForeignKey(
        "FormSubmission",
        on_delete=models.CASCADE,
        related_name="payment_records",
    )
    form_definition = models.ForeignKey(
        FormDefinition,
        on_delete=models.PROTECT,
        related_name="payment_records",
    )

    provider_name = models.CharField(max_length=50)
    transaction_id = models.CharField(max_length=255, blank=True, db_index=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="usd")
    description = models.CharField(max_length=500, blank=True)

    status = models.CharField(
        max_length=20, choices=PAYMENT_STATUS_CHOICES, default="pending"
    )
    error_message = models.TextField(blank=True)
    provider_data = models.JSONField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    idempotency_key = models.CharField(max_length=255, unique=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["submission", "status"]),
            models.Index(fields=["transaction_id"]),
        ]
        verbose_name = "Payment Record"
        verbose_name_plural = "Payment Records"

    def __str__(self):
        return (
            f"Payment {self.transaction_id or '(pending)'} "
            f"— ${self.amount} {self.currency.upper()} "
            f"— {self.get_status_display()}"
        )


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
        ("returned", "Returned for Correction"),
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

    # Stage association (staged workflows only)
    workflow_stage = models.ForeignKey(
        WorkflowStage,
        related_name="tasks",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        help_text="Stage this task belongs to (staged workflows only)",
    )

    # Sub-workflow association (sub-workflow tasks only)
    sub_workflow_instance = models.ForeignKey(
        "SubWorkflowInstance",
        related_name="approval_tasks",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="Sub-workflow instance this task belongs to (sub-workflow tasks only)",
    )
    stage_number = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Stage number (1-indexed) for display purposes",
    )

    # Status
    status = models.CharField(max_length=20, choices=TASK_STATUS, default="pending")
    step_name = models.CharField(max_length=100)
    step_number = models.IntegerField(
        null=True,
        blank=True,
        help_text="Step number in sequential approval workflow (1, 2, 3, etc.)",
    )

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

    @property
    def display_label(self) -> str:
        """Standardised human-readable label for this approval task.

        Single source of truth shared by the approval inbox, approval page,
        submission detail, and PDF exports so the same task reads identically
        across every surface.

        Format:
          * Sub-workflow task →  ``"{swi.label}: Step {stage.order}: {stage.name}"``
          * Otherwise        →  ``"Step {stage.order}: {stage.name}"``

        Falls back gracefully when the stage or sub-workflow instance is missing.
        """
        stage = self.workflow_stage
        swi = self.sub_workflow_instance
        return format_stage_label(stage, swi=swi, fallback_name=self.step_name)


def format_stage_label(stage, swi=None, fallback_name: str = "") -> str:
    """Return the standardised display label for a workflow stage.

    Shared helper used by views and templates that need to render a stage's
    label the same way the approval inbox does, without needing an
    ApprovalTask in hand (e.g. historical stages on submission detail or
    PDF exports).
    """
    name = (getattr(stage, "name", None) or fallback_name or "").strip()
    order = getattr(stage, "order", None)
    step_part = f"Step {order}: {name}" if order and name else name
    if swi is not None:
        try:
            swi_label = swi.label
        except Exception:
            swi_label = ""
        if swi_label:
            return f"{swi_label}: {step_part}" if step_part else swi_label
    return step_part


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
        ("send_back", "Returned for Correction"),
        ("withdraw", "Withdrawn"),
        ("assign", "Assigned"),
        ("comment", "Commented"),
    ]

    # What happened
    action = models.CharField(max_length=20, choices=ACTION_TYPES)
    object_type = models.CharField(max_length=50)
    object_id = models.IntegerField()

    # Who did it (null for anonymous / public-form submissions)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
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


class LDAPGroupProfile(models.Model):
    """
    Marks a Django Group as LDAP-managed.

    The presence of this record on a Group means the group was created and
    is maintained by LDAP synchronisation. Groups without this profile are
    treated as Django-only and are never touched by the LDAP sync logic.
    """

    group = models.OneToOneField(
        Group,
        on_delete=models.CASCADE,
        related_name="ldap_profile",
    )
    ldap_dn = models.CharField(
        max_length=500,
        blank=True,
        help_text="Full Distinguished Name of this group in LDAP",
    )
    last_synced = models.DateTimeField(
        auto_now=True,
        help_text="Last time this group was seen during an LDAP sync",
    )

    class Meta:
        verbose_name = "LDAP Group Profile"
        verbose_name_plural = "LDAP Group Profiles"

    def __str__(self):
        return f"LDAP: {self.group.name}"


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
        if self.condition_operator == "not_equals":
            return str(field_value) != self.condition_value
        if self.condition_operator == "contains":
            return self.condition_value in str(field_value)
        if self.condition_operator == "greater_than":
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


class SubWorkflowDefinition(models.Model):
    """
    Configuration for spawning sub-workflows from a parent workflow.

    When a form has payment installments or other repeated sub-processes,
    this config tells the engine how many sub-workflows to spawn (by reading
    a numeric field from the form submission) and which WorkflowDefinition
    to use for each instance.
    """

    TRIGGER_CHOICES = [
        ("on_submission", "On Submission"),
        ("on_approval", "After Parent Approval"),
    ]

    uuid = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        db_index=True,
        help_text="Stable identity for cross-instance sync.",
    )

    parent_workflow = models.OneToOneField(
        WorkflowDefinition,
        related_name="sub_workflow_config",
        on_delete=models.CASCADE,
        help_text="The parent workflow that spawns sub-workflows",
    )
    sub_workflow = models.ForeignKey(
        WorkflowDefinition,
        related_name="used_as_sub_workflow",
        on_delete=models.PROTECT,
        help_text="Workflow definition used for each sub-workflow instance",
    )
    count_field = models.CharField(
        max_length=100,
        help_text="Form field name whose integer value determines how many sub-workflows to spawn (e.g. 'number_of_payments')",
    )
    section_label = models.CharField(
        max_length=100,
        blank=True,
        help_text="Heading shown to end users in the approval history (e.g. 'Payment Approvals'). "
        "If blank, defaults to the sub-workflow form name.",
    )
    label_template = models.CharField(
        max_length=100,
        default="Sub-workflow {index}",
        help_text="Label for each instance — use {index} as placeholder (e.g. 'Payment {index}')",
    )
    trigger = models.CharField(
        max_length=20,
        choices=TRIGGER_CHOICES,
        default="on_approval",
        help_text="When to spawn sub-workflow instances",
    )
    data_prefix = models.CharField(
        max_length=100,
        blank=True,
        help_text="Form field prefix to scope data per instance (e.g. 'payment' matches payment_type_1, payment_amount_1 …)",
    )
    detached = models.BooleanField(
        default=False,
        help_text=(
            "When True, sub-workflows are spawned independently and do not affect the "
            "parent submission status. When False (default), the parent moves to "
            "'Approved – Pending Completion' until all sub-workflow instances finish."
        ),
    )
    reject_parent = models.BooleanField(
        default=False,
        help_text=(
            "When True, rejecting any sub-workflow instance immediately rejects the "
            "parent submission and cancels all other pending sub-workflows. "
            "When False (default), a rejected sub-workflow is treated as complete and "
            "the parent moves to 'Approved' once all instances are finished."
        ),
    )

    class Meta:
        verbose_name = "Sub-workflow Definition"
        verbose_name_plural = "Sub-workflow Definitions"

    def __str__(self):
        return f"Sub-WF config for: {self.parent_workflow.form_definition}"


class SubWorkflowInstance(models.Model):
    """
    A running instance of a sub-workflow tied to a parent form submission.

    Created by the engine when the parent workflow is submitted or approved
    (depending on SubWorkflowDefinition.trigger). Each instance tracks its
    own approval stages independently using ApprovalTask rows that carry
    a sub_workflow_instance FK.
    """

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("in_progress", "In Progress"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ]

    parent_submission = models.ForeignKey(
        FormSubmission,
        related_name="sub_workflows",
        on_delete=models.CASCADE,
    )
    definition = models.ForeignKey(
        SubWorkflowDefinition,
        related_name="instances",
        on_delete=models.PROTECT,
    )
    index = models.PositiveIntegerField(help_text="Which instance (1, 2, 3 …)")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["index"]
        unique_together = [["parent_submission", "definition", "index"]]
        verbose_name = "Sub-workflow Instance"
        verbose_name_plural = "Sub-workflow Instances"

    @property
    def label(self) -> str:
        """Compute the instance label live from the definition template."""
        return self.definition.label_template.format(index=self.index)

    def __str__(self):
        return f"{self.label} (Submission #{self.parent_submission_id})"

    @property
    def form_data_slice(self) -> dict:
        """Return only the form fields relevant to this sub-workflow instance."""
        prefix = self.definition.data_prefix
        fd = self.parent_submission.form_data
        if not prefix:
            return fd
        suffix = f"_{self.index}"
        return {
            k: v for k, v in fd.items() if k.startswith(prefix) and k.endswith(suffix)
        }


class NotificationLog(models.Model):
    """Audit trail of every notification email attempted by the package's Celery tasks."""

    NOTIFICATION_TYPES = [
        ("submission_received", "Submission Received"),
        ("approval_request", "Approval Request"),
        ("stage_decision", "Stage Decision"),
        ("workflow_approved", "Workflow Approved"),
        ("workflow_denied", "Workflow Denied"),
        ("form_withdrawn", "Form Withdrawn"),
        ("approval_reminder", "Approval Reminder"),
        ("escalation", "Escalation"),
        ("batched", "Batched Digest"),
        # Legacy names kept for historical records
        ("submission_created", "Submission Received (legacy)"),
        ("approval_notification", "Approved (legacy)"),
        ("rejection_notification", "Rejected (legacy)"),
        ("other", "Other"),
    ]
    STATUS_CHOICES = [
        ("sent", "Sent"),
        ("failed", "Failed"),
        ("skipped", "Skipped"),
    ]

    notification_type = models.CharField(
        max_length=50,
        choices=NOTIFICATION_TYPES,
        default="other",
        db_index=True,
    )
    submission = models.ForeignKey(
        "FormSubmission",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notification_logs",
    )
    recipient_email = models.EmailField(db_index=True)
    subject = models.CharField(max_length=500)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="sent",
        db_index=True,
    )
    error_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Notification Log"
        verbose_name_plural = "Notification Logs"

    def __str__(self):
        return (
            f"[{self.get_status_display()}] {self.get_notification_type_display()} "
            f"→ {self.recipient_email} ({self.created_at:%Y-%m-%d %H:%M})"
        )


class APIToken(models.Model):
    """
    Personal access token for the REST API.

    Each token is owned by a Django user and inherits all of that user's
    permissions (submit_groups, view_groups, etc.).  Tokens are created and
    revoked via Django Admin.  Only forms with ``api_enabled=True`` are
    accessible via the API regardless of token ownership.

    Usage::

        Authorization: Bearer <token-uuid>
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="api_tokens",
        help_text="The user this token authenticates as.",
    )
    token = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        db_index=True,
        help_text="Send as: Authorization: Bearer <token>",
    )
    name = models.CharField(
        max_length=100,
        help_text="Human-readable label, e.g. 'CI Pipeline' or 'Mobile App v2'.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive tokens are rejected immediately.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Updated on every successful API request.",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "API Token"
        verbose_name_plural = "API Tokens"

    def __str__(self):
        status = "active" if self.is_active else "revoked"
        return f"{self.name} ({self.user.username}) [{status}]"


# ═══════════════════════════════════════════════════════════════════════════
# Change History — lightweight model-level change tracking
# ═══════════════════════════════════════════════════════════════════════════


class ChangeHistory(models.Model):
    """
    Records field-level changes to tracked models.

    Each row represents a single save/update event and stores a JSON dict of
    changed fields: ``{"field_name": {"old": ..., "new": ...}}``.

    Usage
    -----
    **Automatic**: Add ``change_history = GenericRelation(ChangeHistory)``
    to any model and register it with ``track_model_changes()`` in
    ``apps.py``/``signals.py``.  Changes are captured via ``pre_save`` /
    ``post_save`` signals.

    **Manual** (for JSONField diffs like ``FormSubmission.form_data``):
        ``ChangeHistory.log_json_diff(instance, field, old, new, user=…)``
    """

    ACTION_CHOICES = [
        ("create", "Created"),
        ("update", "Updated"),
        ("delete", "Deleted"),
    ]

    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        related_name="change_history",
    )
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")

    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="change_history_entries",
    )

    # JSON dict of changed fields: {field: {old, new}}
    changes = models.JSONField(
        default=dict,
        blank=True,
        encoder=DjangoJSONEncoder,
        help_text="Field-level diffs: {field_name: {old: …, new: …}}",
    )
    # Optional human-readable summary
    summary = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["-timestamp"]
        verbose_name = "change history"
        verbose_name_plural = "change history"
        indexes = [
            models.Index(
                fields=["content_type", "object_id", "-timestamp"],
                name="chghist_ct_obj_ts",
            ),
        ]

    def __str__(self):
        model_name = self.content_type.model if self.content_type_id else "?"
        who = self.user.get_full_name() or self.user.username if self.user else "system"
        n = len(self.changes) if self.changes else 0
        return (
            f"{self.get_action_display()} {model_name} #{self.object_id} "
            f"({n} field{'s' if n != 1 else ''}) by {who}"
        )

    # ── Convenience constructors ────────────────────────────────────────

    @classmethod
    def log_json_diff(cls, instance, field_name, old_value, new_value, user=None):
        """
        Compare two JSON-serialisable values and log the per-key diff.

        Useful for ``FormSubmission.form_data`` edits where the column is a
        single JSONField but we want per-key granularity.
        """
        if not isinstance(old_value, dict) or not isinstance(new_value, dict):
            changes = {field_name: {"old": old_value, "new": new_value}}
        else:
            changes = {}
            all_keys = set(old_value.keys()) | set(new_value.keys())
            for key in sorted(all_keys):
                old_v = old_value.get(key)
                new_v = new_value.get(key)
                if old_v != new_v:
                    changes[key] = {"old": old_v, "new": new_v}

        if not changes:
            return None  # nothing changed

        ct = ContentType.objects.get_for_model(instance)
        return cls.objects.create(
            content_type=ct,
            object_id=instance.pk,
            action="update",
            user=user,
            changes=changes,
            summary=f"Edited {field_name} ({len(changes)} field{'s' if len(changes) != 1 else ''} changed)",
        )

    @classmethod
    def log_create(cls, instance, user=None):
        """Record a model creation event."""
        ct = ContentType.objects.get_for_model(instance)
        return cls.objects.create(
            content_type=ct,
            object_id=instance.pk,
            action="create",
            user=user,
            summary=f"Created {ct.model} #{instance.pk}",
        )

    @classmethod
    def log_update(cls, instance, changes, user=None):
        """Record a model update with field-level diffs."""
        if not changes:
            return None
        ct = ContentType.objects.get_for_model(instance)
        n = len(changes)
        return cls.objects.create(
            content_type=ct,
            object_id=instance.pk,
            action="update",
            user=user,
            changes=changes,
            summary=f"Updated {n} field{'s' if n != 1 else ''} on {ct.model} #{instance.pk}",
        )

    @classmethod
    def log_delete(cls, instance, user=None):
        """Record a model deletion event."""
        ct = ContentType.objects.get_for_model(instance)
        return cls.objects.create(
            content_type=ct,
            object_id=instance.pk,
            action="delete",
            user=user,
            summary=f"Deleted {ct.model} #{instance.pk}",
        )
