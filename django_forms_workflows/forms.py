"""
Dynamic Form Generation for Django Form Workflows

This module provides the DynamicForm class that generates forms
based on database-stored form definitions, and the ApprovalStepForm
class for handling approval-step field editing.
"""

import logging
import re
from datetime import date, datetime

from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Column, Div, Field, Layout, Row, Submit
from django import forms
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.validators import FileExtensionValidator, RegexValidator
from django.utils.deconstruct import deconstructible

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional picklist package imports
# ---------------------------------------------------------------------------

try:
    from django_countries import countries as _country_list

    _has_django_countries = True
except ImportError:
    _has_django_countries = False

try:
    from localflavor.us.us_states import US_STATES as _US_STATES

    _has_localflavor = True
except ImportError:
    _has_localflavor = False


# ---------------------------------------------------------------------------
# Formula / calculated-field helpers
# ---------------------------------------------------------------------------


def _evaluate_formula(formula: str, data: dict) -> str:
    """Substitute {field_name} tokens in *formula* with values from *data*.

    Unknown tokens are left as empty strings so the result is always a clean
    string rather than a raw template literal.
    """
    if not formula:
        return ""
    return re.sub(
        r"\{(\w+)\}",
        lambda m: str(data.get(m.group(1), "")),
        formula,
    )


# ---------------------------------------------------------------------------
# File upload validators
# ---------------------------------------------------------------------------


@deconstructible
class MaxFileSizeValidator:
    """Validate that a file does not exceed a given size in megabytes."""

    message = "File size must not exceed %(max_size)s MB."
    code = "file_too_large"

    def __init__(self, max_size_mb):
        self.max_size_mb = max_size_mb

    def __call__(self, value):
        if hasattr(value, "size") and value.size > self.max_size_mb * 1024 * 1024:
            raise ValidationError(
                self.message,
                code=self.code,
                params={"max_size": self.max_size_mb},
            )

    def __eq__(self, other):
        return (
            isinstance(other, MaxFileSizeValidator)
            and self.max_size_mb == other.max_size_mb
        )


def _build_file_validators(field_def):
    """Return a list of validators for file fields based on field definition."""
    validators = []
    if field_def.allowed_extensions:
        exts = [
            e.strip().lower()
            for e in field_def.allowed_extensions.split(",")
            if e.strip()
        ]
        if exts:
            validators.append(FileExtensionValidator(allowed_extensions=exts))
    if field_def.max_file_size_mb:
        validators.append(MaxFileSizeValidator(field_def.max_file_size_mb))
    return validators


# ---------------------------------------------------------------------------
# Multi-file upload support
# ---------------------------------------------------------------------------


class MultipleFileInput(forms.ClearableFileInput):
    """File input widget that accepts multiple files via a single input."""

    allow_multiple_selected = True

    def value_from_datadict(self, data, files, name):
        return files.getlist(name)


class MultipleFileField(forms.FileField):
    """Form field that accepts and validates a list of uploaded files."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, list | tuple):
            return [single_file_clean(d, initial) for d in data if d]
        if data:
            return [single_file_clean(data, initial)]
        if not self.required:
            return []
        raise forms.ValidationError(self.error_messages["required"])


class DynamicForm(forms.Form):
    """
    Dynamically generated form based on FormDefinition.

    This form is built entirely from database configuration, with no
    hardcoded fields. It supports:
    - 15+ field types
    - Data prefilling from multiple sources (LDAP, databases, APIs)
    - Custom validation rules
    - Responsive layouts
    - Draft saving
    """

    def __init__(self, form_definition, user=None, initial_data=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.form_definition = form_definition
        self.user = user
        self.initial_data = initial_data or {}

        # Build form fields from definition
        # Exclude fields scoped to a workflow stage - those are for approvers only
        for field in (
            form_definition.fields.exclude(field_type="section")
            .filter(workflow_stage__isnull=True)
            .order_by("order")
        ):
            self.add_field(field, initial_data)

        # Setup form layout with Crispy Forms
        self.helper = FormHelper()
        self.helper.form_method = "post"
        self.helper.form_class = "needs-validation"

        # Build layout - exclude approval step fields and workflow stage fields
        layout_fields = []
        fields = list(
            form_definition.fields.filter(workflow_stage__isnull=True).order_by("order")
        )
        i = 0
        while i < len(fields):
            field = fields[i]
            if field.field_type == "section":
                layout_fields.append(
                    HTML(f'<h3 class="mt-4 mb-3">{field.field_label}</h3>')
                )
                i += 1
            elif field.width == "half":
                # Pair consecutive half-width fields into one row (FROM / TO columns)
                next_field = fields[i + 1] if i + 1 < len(fields) else None
                if (
                    next_field
                    and next_field.width == "half"
                    and next_field.field_type != "section"
                ):
                    layout_fields.append(
                        Row(
                            Div(
                                Field(field.field_name),
                                css_class=f"col-md-6 field-wrapper field-{field.field_name}",
                            ),
                            Div(
                                Field(next_field.field_name),
                                css_class=f"col-md-6 field-wrapper field-{next_field.field_name}",
                            ),
                        )
                    )
                    i += 2
                else:
                    layout_fields.append(
                        Div(
                            Row(Column(Field(field.field_name), css_class="col-md-6")),
                            css_class=f"field-wrapper field-{field.field_name}",
                        )
                    )
                    i += 1
            elif field.width == "third":
                layout_fields.append(
                    Div(
                        Row(
                            Column(Field(field.field_name), css_class="col-md-4"),
                        ),
                        css_class=f"field-wrapper field-{field.field_name}",
                    )
                )
                i += 1
            elif field.width == "fourth":
                layout_fields.append(
                    Div(
                        Row(
                            Column(Field(field.field_name), css_class="col-md-3"),
                        ),
                        css_class=f"field-wrapper field-{field.field_name}",
                    )
                )
                i += 1
            else:
                layout_fields.append(
                    Div(
                        Field(field.field_name),
                        css_class=f"field-wrapper field-{field.field_name}",
                    )
                )
                i += 1

        # Add submit buttons
        buttons = [Submit("submit", "Submit", css_class="btn btn-primary")]
        if form_definition.allow_save_draft:
            buttons.append(
                Submit("save_draft", "Save Draft", css_class="btn btn-secondary ms-2")
            )

        layout_fields.append(Div(*buttons, css_class="mt-4"))

        self.helper.layout = Layout(*layout_fields)

        # Add form ID for JavaScript targeting
        self.helper.form_id = f"form_{form_definition.slug}"
        self.helper.attrs = {
            "data-form-enhancements": "true",
            "data-form-slug": form_definition.slug,
        }

    def _parse_choices(self, choices):
        """
        Parse choices from either JSON format or comma-separated string.
        Returns list of tuples: [(value, label), ...]
        """
        if not choices:
            return []

        # If choices is a list of dicts (JSON format)
        if isinstance(choices, list):
            return [(c["value"], c["label"]) for c in choices]

        # If choices is a comma-separated string
        if isinstance(choices, str):
            return [(c.strip(), c.strip()) for c in choices.split(",") if c.strip()]

        return []

    def _get_choices_from_prefill_source(self, field_def):
        """
        Return a list of (value, label) tuples from a database choices query when the
        field's PrefillSource points to a query with ``return_choices=True``.

        Returns None if the field has no such source (so the caller can fall back to
        the stored ``field_def.choices``). Returns [] if the query ran but was empty.
        """
        prefill_key = field_def.get_prefill_source_key()
        if not prefill_key or not prefill_key.startswith("dbquery."):
            return None

        query_key = prefill_key[len("dbquery.") :]

        from django.conf import settings

        queries = getattr(settings, "FORMS_WORKFLOWS_DATABASE_QUERIES", {})
        if not queries.get(query_key, {}).get("return_choices"):
            return None

        from .data_sources import DatabaseDataSource

        source = DatabaseDataSource()
        return source.execute_choices_query(query_key)

    def add_field(self, field_def, initial_data):
        """Add a field to the form based on field definition"""

        # Get initial value
        initial = self.get_initial_value(field_def, initial_data)

        # Common field arguments
        field_args = {
            "label": field_def.field_label,
            "required": field_def.required,
            "help_text": field_def.help_text,
            "initial": initial,
        }

        # Add placeholder if provided
        widget_attrs = {}
        if field_def.placeholder:
            widget_attrs["placeholder"] = field_def.placeholder
        if field_def.css_class:
            widget_attrs["class"] = field_def.css_class
        if field_def.readonly:
            widget_attrs["readonly"] = "readonly"
            # Readonly fields should not be required since they can't be edited
            field_args["required"] = False

        # Create appropriate field type
        if field_def.field_type == "text":
            if widget_attrs:
                field_args["widget"] = forms.TextInput(attrs=widget_attrs)
            self.fields[field_def.field_name] = forms.CharField(
                max_length=field_def.max_length or 255,
                min_length=field_def.min_length or None,
                **field_args,
            )

        elif field_def.field_type == "phone":
            widget_attrs.update(
                {
                    "type": "tel",
                    "inputmode": "tel",
                    "pattern": r"[+]?[(]?[0-9]{3}[)]?[-\s.]?[0-9]{3}[-\s.]?[0-9]{4,6}",
                }
            )
            field = forms.CharField(
                max_length=20,
                widget=forms.TextInput(attrs=widget_attrs),
                **field_args,
            )
            field.validators.append(
                RegexValidator(
                    regex=r"^\+?[(]?[0-9]{3}[)]?[-\s.]?[0-9]{3}[-\s.]?[0-9]{4,6}$",
                    message="Enter a valid phone number (e.g. 555-555-5555 or +1 555 555 5555).",
                )
            )
            self.fields[field_def.field_name] = field

        elif field_def.field_type == "textarea":
            widget_attrs["rows"] = 4
            self.fields[field_def.field_name] = forms.CharField(
                widget=forms.Textarea(attrs=widget_attrs),
                max_length=field_def.max_length or None,
                min_length=field_def.min_length or None,
                **field_args,
            )

        elif field_def.field_type == "number":
            if widget_attrs:
                field_args["widget"] = forms.NumberInput(attrs=widget_attrs)
            self.fields[field_def.field_name] = forms.IntegerField(
                min_value=int(field_def.min_value) if field_def.min_value else None,
                max_value=int(field_def.max_value) if field_def.max_value else None,
                **field_args,
            )

        elif field_def.field_type == "decimal":
            widget_attrs.setdefault("inputmode", "decimal")
            widget_attrs.setdefault("step", "any")
            field_args["widget"] = forms.NumberInput(attrs=widget_attrs)
            self.fields[field_def.field_name] = forms.DecimalField(
                min_value=field_def.min_value,
                max_value=field_def.max_value,
                decimal_places=2,
                **field_args,
            )

        elif field_def.field_type == "currency":
            widget_attrs.setdefault("inputmode", "decimal")
            widget_attrs.setdefault("step", "0.01")
            widget_attrs["data-input-type"] = "currency"
            field_args["widget"] = forms.NumberInput(attrs=widget_attrs)
            self.fields[field_def.field_name] = forms.DecimalField(
                min_value=field_def.min_value,
                max_value=field_def.max_value,
                decimal_places=2,
                **field_args,
            )

        elif field_def.field_type == "date":
            widget_attrs["type"] = "date"
            self.fields[field_def.field_name] = forms.DateField(
                widget=forms.DateInput(attrs=widget_attrs), **field_args
            )

        elif field_def.field_type == "datetime":
            widget_attrs["type"] = "datetime-local"
            self.fields[field_def.field_name] = forms.DateTimeField(
                widget=forms.DateTimeInput(attrs=widget_attrs), **field_args
            )

        elif field_def.field_type == "time":
            widget_attrs["type"] = "time"
            self.fields[field_def.field_name] = forms.TimeField(
                widget=forms.TimeInput(attrs=widget_attrs), **field_args
            )

        elif field_def.field_type == "email":
            if widget_attrs:
                field_args["widget"] = forms.EmailInput(attrs=widget_attrs)
            self.fields[field_def.field_name] = forms.EmailField(**field_args)

        elif field_def.field_type == "url":
            if widget_attrs:
                field_args["widget"] = forms.URLInput(attrs=widget_attrs)
            self.fields[field_def.field_name] = forms.URLField(**field_args)

        elif field_def.field_type == "select":
            _db_choices = self._get_choices_from_prefill_source(field_def)
            choices = [("", "-- Select --")] + (
                _db_choices
                if _db_choices is not None
                else self._parse_choices(field_def.choices)
            )
            self.fields[field_def.field_name] = forms.ChoiceField(
                choices=choices, **field_args
            )

        elif field_def.field_type == "multiselect":
            _db_choices = self._get_choices_from_prefill_source(field_def)
            choices = (
                _db_choices
                if _db_choices is not None
                else self._parse_choices(field_def.choices)
            )
            self.fields[field_def.field_name] = forms.MultipleChoiceField(
                choices=choices, widget=forms.CheckboxSelectMultiple, **field_args
            )

        elif field_def.field_type == "multiselect_list":
            _db_choices = self._get_choices_from_prefill_source(field_def)
            choices = (
                _db_choices
                if _db_choices is not None
                else self._parse_choices(field_def.choices)
            )
            self.fields[field_def.field_name] = forms.MultipleChoiceField(
                choices=choices,
                widget=forms.SelectMultiple(attrs={"class": "form-select"}),
                **field_args,
            )

        elif field_def.field_type == "radio":
            _db_choices = self._get_choices_from_prefill_source(field_def)
            choices = (
                _db_choices
                if _db_choices is not None
                else self._parse_choices(field_def.choices)
            )
            self.fields[field_def.field_name] = forms.ChoiceField(
                choices=choices, widget=forms.RadioSelect, **field_args
            )

        elif field_def.field_type == "checkbox":
            self.fields[field_def.field_name] = forms.BooleanField(
                required=field_def.required,
                label=field_def.field_label,
                help_text=field_def.help_text,
                initial=initial,
            )

        elif field_def.field_type == "checkboxes":
            _db_choices = self._get_choices_from_prefill_source(field_def)
            choices = (
                _db_choices
                if _db_choices is not None
                else self._parse_choices(field_def.choices)
            )
            self.fields[field_def.field_name] = forms.MultipleChoiceField(
                choices=choices,
                widget=forms.CheckboxSelectMultiple,
                required=field_def.required,
                label=field_def.field_label,
                help_text=field_def.help_text,
                initial=initial,
            )

        elif field_def.field_type == "file":
            file_validators = _build_file_validators(field_def)
            accept_attrs = {}
            if field_def.allowed_extensions:
                exts = ",".join(
                    f".{e.strip()}"
                    for e in field_def.allowed_extensions.split(",")
                    if e.strip()
                )
                accept_attrs["accept"] = exts
            self.fields[field_def.field_name] = forms.FileField(
                validators=file_validators,
                widget=forms.ClearableFileInput(attrs=accept_attrs)
                if accept_attrs
                else forms.ClearableFileInput(),
                **field_args,
            )

        elif field_def.field_type == "multifile":
            self.fields[field_def.field_name] = MultipleFileField(
                required=field_def.required,
                label=field_def.field_label,
                help_text=field_def.help_text,
            )

        elif field_def.field_type == "calculated":
            # Evaluate the formula against any already-known data so the field
            # is pre-filled on edit / re-visit.  Always stored as text.
            evaluated = _evaluate_formula(field_def.formula, self.initial_data or {})
            self.fields[field_def.field_name] = forms.CharField(
                required=False,
                label=field_def.field_label,
                help_text=field_def.help_text or field_def.formula,
                initial=evaluated or initial,
                widget=forms.TextInput(
                    attrs={
                        "readonly": "readonly",
                        "data-calculated": "true",
                        "data-formula": field_def.formula,
                        "class": "form-control form-control-calculated",
                    }
                ),
            )

        elif field_def.field_type == "spreadsheet":
            self.fields[field_def.field_name] = forms.FileField(
                required=field_def.required,
                label=field_def.field_label,
                help_text=field_def.help_text or "Accepted formats: .csv, .xls, .xlsx",
                widget=forms.ClearableFileInput(attrs={"accept": ".csv,.xls,.xlsx"}),
            )

        elif field_def.field_type == "country":
            if not _has_django_countries:
                raise ImproperlyConfigured(
                    "The 'country' field type requires django-countries. "
                    "Install it with: pip install django-forms-workflows[picklists]"
                )
            country_choices = [("", "-- Select Country --")] + list(_country_list)
            self.fields[field_def.field_name] = forms.ChoiceField(
                choices=country_choices,
                widget=forms.Select(attrs={"class": "form-select"}),
                **field_args,
            )

        elif field_def.field_type == "us_state":
            if not _has_localflavor:
                raise ImproperlyConfigured(
                    "The 'us_state' field type requires django-localflavor. "
                    "Install it with: pip install django-forms-workflows[picklists]"
                )
            state_choices = [("", "-- Select State --")] + list(_US_STATES)
            self.fields[field_def.field_name] = forms.ChoiceField(
                choices=state_choices,
                widget=forms.Select(attrs={"class": "form-select"}),
                **field_args,
            )

        elif field_def.field_type == "hidden":
            self.fields[field_def.field_name] = forms.CharField(
                widget=forms.HiddenInput(), required=False, initial=initial
            )

        # Add custom validation if regex provided
        if field_def.regex_validation and field_def.field_type in ["text", "textarea"]:
            self.fields[field_def.field_name].validators.append(
                RegexValidator(
                    regex=field_def.regex_validation,
                    message=field_def.regex_error_message or "Invalid format",
                )
            )

    def get_initial_value(self, field_def, initial_data):
        """
        Determine initial value for field based on prefill settings.

        Uses the data source abstraction layer to fetch values from:
        - User model (user.email, user.first_name, etc.)
        - LDAP/AD (ldap.department, ldap.title, etc.)
        - External databases (db.schema.table.column)
        - APIs (api.endpoint.field)
        - Previous submissions (last_submission)
        - Current date/time
        """

        # Check if we have saved data
        if initial_data and field_def.field_name in initial_data:
            return initial_data[field_def.field_name]

        # Handle prefill sources using data source abstraction
        # Use the new get_prefill_source_key method which handles both
        # the new prefill_source_config and legacy prefill_source
        prefill_key = field_def.get_prefill_source_key()
        if prefill_key and self.user:
            return self._get_prefill_value(prefill_key, field_def.prefill_source_config)

        # Default value
        return field_def.default_value or ""

    def _get_prefill_value(self, prefill_source, prefill_config=None):
        """
        Get prefill value from configured data sources.

        Supports:
        - user.* - User model fields
        - ldap.* - LDAP attributes
        - dbquery.* - Code-defined database queries (for complex SQL)
        - db.* or {{ db.* }} - Simple database queries
        - api.* - API calls
        - current_date, current_datetime - Current date/time
        - last_submission - Previous submission data

        Args:
            prefill_source: Source key string (e.g., 'user.email', 'ldap.department')
            prefill_config: Optional PrefillSource model instance with custom configuration
        """
        try:
            # Import data sources
            from .data_sources import DatabaseDataSource, LDAPDataSource, UserDataSource

            # Handle user.* sources
            if prefill_source.startswith("user."):
                source = UserDataSource()
                field_name = prefill_source.replace("user.", "")
                return source.get_value(self.user, field_name) or ""

            # Handle ldap.* sources
            if prefill_source.startswith("ldap."):
                source = LDAPDataSource()
                field_name = prefill_source.replace("ldap.", "")
                return source.get_value(self.user, field_name) or ""

            # Handle dbquery.* sources (code-defined complex queries)
            if prefill_source.startswith("dbquery."):
                source = DatabaseDataSource()
                query_key = prefill_source.replace("dbquery.", "")
                return source.execute_custom_query(self.user, query_key) or ""

            # Handle db.* or {{ db.* }} sources
            if prefill_source.startswith("db.") or prefill_source.startswith("{{"):
                source = DatabaseDataSource()

                # Build kwargs from prefill_config
                kwargs = {}
                if prefill_config and prefill_config.source_type == "database":
                    if prefill_config.db_alias:
                        kwargs["database_alias"] = prefill_config.db_alias
                    if prefill_config.db_lookup_field:
                        kwargs["lookup_field"] = prefill_config.db_lookup_field
                    if prefill_config.db_user_field:
                        kwargs["user_id_field"] = prefill_config.db_user_field

                    # Check if this is a template-based multi-column lookup
                    if prefill_config.has_template():
                        return (
                            source.get_template_value(
                                self.user,
                                schema=prefill_config.db_schema,
                                table=prefill_config.db_table,
                                columns=prefill_config.db_columns,
                                template=prefill_config.db_template,
                                **kwargs,
                            )
                            or ""
                        )

                # Standard single-column lookup
                source_str = prefill_source.strip()
                if source_str.startswith("{{") and source_str.endswith("}}"):
                    source_str = source_str[2:-2].strip()
                if source_str.startswith("db."):
                    source_str = source_str[3:]

                # Parse schema.table.column
                parts = source_str.split(".")
                if len(parts) >= 2:
                    # Pass the full path to the data source
                    return source.get_value(self.user, source_str, **kwargs) or ""

            # Handle current_date
            elif prefill_source == "current_date":
                return date.today()

            # Handle current_datetime
            elif prefill_source == "current_datetime":
                return datetime.now()

            # Handle last_submission
            elif prefill_source == "last_submission":
                from .models import FormSubmission

                last_sub = (
                    FormSubmission.objects.filter(
                        form_definition=self.form_definition, submitter=self.user
                    )
                    .exclude(status="draft")
                    .order_by("-submitted_at")
                    .first()
                )
                if last_sub and hasattr(last_sub, "form_data"):
                    # This would need to be field-specific
                    # For now, return empty
                    pass

        except Exception as e:
            logger.error(f"Error getting prefill value for {prefill_source}: {e}")

        return ""

    def get_enhancements_config(self):
        """
        Generate JavaScript configuration for form enhancements.
        Returns a dictionary that can be serialized to JSON.
        """
        import json

        from django.urls import reverse

        config = {
            "autoSaveEnabled": getattr(self.form_definition, "enable_auto_save", True),
            "autoSaveInterval": getattr(self.form_definition, "auto_save_interval", 30)
            * 1000,  # Convert to ms
            "autoSaveEndpoint": reverse(
                "forms_workflows:form_auto_save",
                kwargs={"slug": self.form_definition.slug},
            ),
            "multiStepEnabled": getattr(
                self.form_definition, "enable_multi_step", False
            ),
            "steps": getattr(self.form_definition, "form_steps", None) or [],
            "conditionalRules": [],
            "fieldDependencies": [],
            "validationRules": [],
        }

        # Collect conditional rules from all fields
        for field in self.form_definition.fields.all():
            # Conditional rules
            if field.conditional_rules:
                if isinstance(field.conditional_rules, str):
                    try:
                        rules = json.loads(field.conditional_rules)
                    except json.JSONDecodeError:
                        rules = None
                else:
                    rules = field.conditional_rules

                if rules:
                    # conditional_rules may be stored as a list of rule dicts
                    # (one per show/hide rule) or as a single rule dict.
                    rule_list = rules if isinstance(rules, list) else [rules]
                    for rule in rule_list:
                        if isinstance(rule, dict):
                            config["conditionalRules"].append(
                                {"targetField": field.field_name, **rule}
                            )

            # Field dependencies
            if hasattr(field, "field_dependencies") and field.field_dependencies:
                if isinstance(field.field_dependencies, str):
                    try:
                        deps = json.loads(field.field_dependencies)
                    except json.JSONDecodeError:
                        deps = []
                else:
                    deps = field.field_dependencies

                if deps:
                    config["fieldDependencies"].extend(deps)

            # Validation rules
            validation_rules = []

            if field.required:
                validation_rules.append(
                    {"type": "required", "message": f"{field.field_label} is required"}
                )

            if field.field_type == "email":
                validation_rules.append(
                    {"type": "email", "message": "Please enter a valid email address"}
                )

            if field.field_type == "url":
                validation_rules.append(
                    {"type": "url", "message": "Please enter a valid URL"}
                )

            if field.min_length:
                validation_rules.append(
                    {
                        "type": "min",
                        "value": field.min_length,
                        "message": f"Minimum {field.min_length} characters required",
                    }
                )

            if field.max_length:
                validation_rules.append(
                    {
                        "type": "max",
                        "value": field.max_length,
                        "message": f"Maximum {field.max_length} characters allowed",
                    }
                )

            if field.min_value is not None:
                validation_rules.append(
                    {
                        "type": "min_value",
                        "value": float(field.min_value),
                        "message": f"Minimum value is {field.min_value}",
                    }
                )

            if field.max_value is not None:
                validation_rules.append(
                    {
                        "type": "max_value",
                        "value": float(field.max_value),
                        "message": f"Maximum value is {field.max_value}",
                    }
                )

            if field.regex_validation:
                validation_rules.append(
                    {
                        "type": "pattern",
                        "value": field.regex_validation,
                        "message": field.regex_error_message or "Invalid format",
                    }
                )

            # File type / size validation rules
            if field.field_type in ("file", "multifile") and field.allowed_extensions:
                exts = [
                    e.strip().lower()
                    for e in field.allowed_extensions.split(",")
                    if e.strip()
                ]
                if exts:
                    readable = ", ".join(f".{e}" for e in exts)
                    validation_rules.append(
                        {
                            "type": "file_type",
                            "value": ",".join(exts),
                            "message": f"Allowed file types: {readable}",
                        }
                    )

            if field.field_type in ("file", "multifile") and field.max_file_size_mb:
                validation_rules.append(
                    {
                        "type": "file_size",
                        "value": field.max_file_size_mb,
                        "message": f"File size must not exceed {field.max_file_size_mb} MB",
                    }
                )

            # Custom validation rules from field config
            if hasattr(field, "validation_rules") and field.validation_rules:
                if isinstance(field.validation_rules, str):
                    try:
                        custom_rules = json.loads(field.validation_rules)
                    except json.JSONDecodeError:
                        custom_rules = []
                else:
                    custom_rules = field.validation_rules

                if custom_rules:
                    validation_rules.extend(custom_rules)

            if validation_rules:
                config["validationRules"].append(
                    {"field": field.field_name, "rules": validation_rules}
                )

        return config


class ApprovalStepForm(forms.Form):
    """
    Form for approvers to fill in fields specific to their workflow stage.

    This form is used during the approval process to allow approvers to:
    - View all previously submitted/approved data as read-only
    - Edit fields designated for their workflow stage
    - Have approver name auto-filled from their user account
    - Have date fields auto-filled with the current date
    """

    def __init__(
        self,
        form_definition,
        submission,
        approval_task,
        user=None,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.form_definition = form_definition
        self.submission = submission
        self.approval_task = approval_task
        self.user = user

        # Get existing form data
        self.form_data = submission.form_data or {}

        # Cache sub-workflow instance index so _add_field can resolve indexed keys
        # (e.g. payment_dept_code_1) without a per-field DB query.
        self._swi_index = (
            approval_task.sub_workflow_instance.index
            if approval_task.sub_workflow_instance_id
            and approval_task.sub_workflow_instance
            else None
        )

        # Build form fields from definition
        self._build_fields()

        # Setup form layout with Crispy Forms
        self._setup_layout()

    def _build_fields(self):
        """Build fields for this approval task.

        The task carries a ``workflow_stage`` FK that identifies which
        FormFields belong to it.
        """
        if self.approval_task.workflow_stage_id:
            qs = (
                self.form_definition.fields.exclude(field_type="section")
                .filter(workflow_stage_id=self.approval_task.workflow_stage_id)
                .order_by("order")
            )
        else:
            # Workflow with no stages — no stage-specific fields to show.
            qs = self.form_definition.fields.none()
        for field_def in qs:
            self._add_field(field_def)

    def _add_field(self, field_def):
        """Add a single field to the form."""
        is_editable = True

        # Get current value from form data.
        # Sub-workflow fields are stored with an index suffix (e.g. payment_dept_code_1);
        # try the indexed key first, then fall back to the bare field name.
        if self._swi_index is not None:
            indexed_key = f"{field_def.field_name}_{self._swi_index}"
            current_value = self.form_data.get(indexed_key) or self.form_data.get(
                field_def.field_name, ""
            )
        else:
            current_value = self.form_data.get(field_def.field_name, "")

        # Fall back to the field's configured default value when the slot is still empty.
        if not current_value and field_def.default_value:
            current_value = field_def.default_value

        # Auto-fill approver name from current user
        if is_editable and self._is_approver_name_field(field_def):
            current_value = self._get_approver_name()
        # Auto-fill date with current date
        elif is_editable and self._is_date_field(field_def):
            current_value = date.today()

        # Common field arguments
        field_args = {
            "label": field_def.field_label,
            "required": field_def.required if is_editable else False,
            "help_text": field_def.help_text,
            "initial": current_value,
        }

        # Widget attributes
        widget_attrs = {}
        if field_def.placeholder:
            widget_attrs["placeholder"] = field_def.placeholder
        if field_def.css_class:
            widget_attrs["class"] = field_def.css_class

        # Make non-editable fields read-only
        if not is_editable:
            widget_attrs["readonly"] = "readonly"
            widget_attrs["disabled"] = "disabled"
            field_args["required"] = False

        # Create appropriate field type
        self._create_field(field_def, field_args, widget_attrs, is_editable)

    def _is_approver_name_field(self, field_def):
        """Check if this is an approver name field (to auto-fill)."""
        name_lower = field_def.field_name.lower()
        return "name" in name_lower and (
            "advisor" in name_lower
            or "registrar" in name_lower
            or "manager" in name_lower
            or "fa_" in name_lower
            or "approver" in name_lower
        )

    def _is_date_field(self, field_def):
        """Check if this is a date field for the approval step."""
        return field_def.field_type in ["date", "datetime"]

    def _get_approver_name(self):
        """Get the approver's name for auto-fill."""
        if self.user:
            full_name = self.user.get_full_name()
            if full_name:
                return full_name
            return self.user.username
        return ""

    def _create_field(self, field_def, field_args, widget_attrs, is_editable):
        """Create the appropriate Django form field."""
        if field_def.field_type == "text":
            if widget_attrs:
                field_args["widget"] = forms.TextInput(attrs=widget_attrs)
            self.fields[field_def.field_name] = forms.CharField(
                max_length=field_def.max_length or 255,
                **field_args,
            )

        elif field_def.field_type == "phone":
            widget_attrs.update(
                {
                    "type": "tel",
                    "inputmode": "tel",
                    "pattern": r"[+]?[(]?[0-9]{3}[)]?[-\s.]?[0-9]{3}[-\s.]?[0-9]{4,6}",
                }
            )
            field = forms.CharField(
                max_length=20,
                widget=forms.TextInput(attrs=widget_attrs),
                **field_args,
            )
            field.validators.append(
                RegexValidator(
                    regex=r"^\+?[(]?[0-9]{3}[)]?[-\s.]?[0-9]{3}[-\s.]?[0-9]{4,6}$",
                    message="Enter a valid phone number (e.g. 555-555-5555 or +1 555 555 5555).",
                )
            )
            self.fields[field_def.field_name] = field

        elif field_def.field_type == "textarea":
            widget_attrs["rows"] = 4
            self.fields[field_def.field_name] = forms.CharField(
                widget=forms.Textarea(attrs=widget_attrs),
                **field_args,
            )

        elif field_def.field_type == "number":
            if widget_attrs:
                field_args["widget"] = forms.NumberInput(attrs=widget_attrs)
            self.fields[field_def.field_name] = forms.IntegerField(**field_args)

        elif field_def.field_type == "decimal":
            widget_attrs.setdefault("inputmode", "decimal")
            widget_attrs.setdefault("step", "any")
            field_args["widget"] = forms.NumberInput(attrs=widget_attrs)
            self.fields[field_def.field_name] = forms.DecimalField(
                decimal_places=2,
                **field_args,
            )

        elif field_def.field_type == "currency":
            widget_attrs.setdefault("inputmode", "decimal")
            widget_attrs.setdefault("step", "0.01")
            widget_attrs["data-input-type"] = "currency"
            field_args["widget"] = forms.NumberInput(attrs=widget_attrs)
            self.fields[field_def.field_name] = forms.DecimalField(
                decimal_places=2,
                **field_args,
            )

        elif field_def.field_type == "date":
            widget_attrs["type"] = "date"
            self.fields[field_def.field_name] = forms.DateField(
                widget=forms.DateInput(attrs=widget_attrs), **field_args
            )

        elif field_def.field_type == "datetime":
            widget_attrs["type"] = "datetime-local"
            self.fields[field_def.field_name] = forms.DateTimeField(
                widget=forms.DateTimeInput(attrs=widget_attrs), **field_args
            )

        elif field_def.field_type == "email":
            if widget_attrs:
                field_args["widget"] = forms.EmailInput(attrs=widget_attrs)
            self.fields[field_def.field_name] = forms.EmailField(**field_args)

        elif field_def.field_type == "select":
            _db_choices = self._get_choices_from_prefill_source(field_def)
            choices = [("", "-- Select --")] + (
                _db_choices
                if _db_choices is not None
                else self._parse_choices(field_def.choices)
            )
            if widget_attrs:
                field_args["widget"] = forms.Select(attrs=widget_attrs)
            self.fields[field_def.field_name] = forms.ChoiceField(
                choices=choices, **field_args
            )

        elif field_def.field_type == "multiselect":
            _db_choices = self._get_choices_from_prefill_source(field_def)
            choices = (
                _db_choices
                if _db_choices is not None
                else self._parse_choices(field_def.choices)
            )
            self.fields[field_def.field_name] = forms.MultipleChoiceField(
                choices=choices,
                widget=forms.CheckboxSelectMultiple,
                **field_args,
            )

        elif field_def.field_type == "multiselect_list":
            _db_choices = self._get_choices_from_prefill_source(field_def)
            choices = (
                _db_choices
                if _db_choices is not None
                else self._parse_choices(field_def.choices)
            )
            self.fields[field_def.field_name] = forms.MultipleChoiceField(
                choices=choices,
                widget=forms.SelectMultiple(attrs={"class": "form-select"}),
                **field_args,
            )

        elif field_def.field_type == "radio":
            _db_choices = self._get_choices_from_prefill_source(field_def)
            choices = (
                _db_choices
                if _db_choices is not None
                else self._parse_choices(field_def.choices)
            )
            self.fields[field_def.field_name] = forms.ChoiceField(
                choices=choices,
                widget=forms.RadioSelect(attrs=widget_attrs),
                **field_args,
            )

        elif field_def.field_type == "checkbox":
            self.fields[field_def.field_name] = forms.BooleanField(
                required=field_args.get("required", False),
                label=field_def.field_label,
                help_text=field_def.help_text,
                initial=field_args["initial"],
            )

        elif field_def.field_type == "file":
            file_validators = _build_file_validators(field_def)
            accept_attrs = {}
            if field_def.allowed_extensions:
                exts = ",".join(
                    f".{e.strip()}"
                    for e in field_def.allowed_extensions.split(",")
                    if e.strip()
                )
                accept_attrs["accept"] = exts
            self.fields[field_def.field_name] = forms.FileField(
                required=field_args.get("required", False),
                label=field_def.field_label,
                help_text=field_def.help_text,
                validators=file_validators,
                widget=forms.ClearableFileInput(attrs=accept_attrs),
            )

        elif field_def.field_type == "multifile":
            self.fields[field_def.field_name] = MultipleFileField(
                required=field_args.get("required", False),
                label=field_def.field_label,
                help_text=field_def.help_text,
            )

        elif field_def.field_type == "calculated":
            existing = (self.existing_data or {}).get(field_def.field_name, "")
            evaluated = (
                _evaluate_formula(field_def.formula, self.existing_data or {})
                or existing
            )
            self.fields[field_def.field_name] = forms.CharField(
                required=False,
                label=field_def.field_label,
                help_text=field_def.help_text or field_def.formula,
                initial=evaluated,
                widget=forms.TextInput(
                    attrs={
                        "readonly": "readonly",
                        "data-calculated": "true",
                        "data-formula": field_def.formula,
                        "class": "form-control form-control-calculated",
                    }
                ),
            )

        elif field_def.field_type == "spreadsheet":
            self.fields[field_def.field_name] = forms.FileField(
                required=field_args.get("required", False),
                label=field_def.field_label,
                help_text=field_def.help_text or "Accepted formats: .csv, .xls, .xlsx",
                widget=forms.ClearableFileInput(attrs={"accept": ".csv,.xls,.xlsx"}),
            )

        elif field_def.field_type == "country":
            if not _has_django_countries:
                raise ImproperlyConfigured(
                    "The 'country' field type requires django-countries. "
                    "Install it with: pip install django-forms-workflows[picklists]"
                )
            country_choices = [("", "-- Select Country --")] + list(_country_list)
            self.fields[field_def.field_name] = forms.ChoiceField(
                choices=country_choices,
                widget=forms.Select(attrs={"class": "form-select"}),
                **field_args,
            )

        elif field_def.field_type == "us_state":
            if not _has_localflavor:
                raise ImproperlyConfigured(
                    "The 'us_state' field type requires django-localflavor. "
                    "Install it with: pip install django-forms-workflows[picklists]"
                )
            state_choices = [("", "-- Select State --")] + list(_US_STATES)
            self.fields[field_def.field_name] = forms.ChoiceField(
                choices=state_choices,
                widget=forms.Select(attrs={"class": "form-select"}),
                **field_args,
            )

        else:
            # Default to text field for unknown types
            if widget_attrs:
                field_args["widget"] = forms.TextInput(attrs=widget_attrs)
            self.fields[field_def.field_name] = forms.CharField(
                max_length=255,
                **field_args,
            )

    def _parse_choices(self, choices):
        """Parse choices from either JSON format or comma-separated string."""
        if not choices:
            return []
        if isinstance(choices, list):
            return [(c["value"], c["label"]) for c in choices]
        if isinstance(choices, str):
            return [(c.strip(), c.strip()) for c in choices.split(",") if c.strip()]
        return []

    def _get_choices_from_prefill_source(self, field_def):
        """
        Return (value, label) tuples from a database choices query when the field's
        PrefillSource points to a query with ``return_choices=True``, or None if the
        field has no such source (so the caller falls back to stored choices).
        """
        prefill_key = field_def.get_prefill_source_key()
        if not prefill_key or not prefill_key.startswith("dbquery."):
            return None

        query_key = prefill_key[len("dbquery.") :]

        from django.conf import settings

        queries = getattr(settings, "FORMS_WORKFLOWS_DATABASE_QUERIES", {})
        if not queries.get(query_key, {}).get("return_choices"):
            return None

        from .data_sources import DatabaseDataSource

        source = DatabaseDataSource()
        return source.execute_choices_query(query_key)

    def _build_layout_fields(self, field_defs):
        """Convert a list of field definitions into crispy layout elements,
        respecting half / third / fourth width settings."""
        layout_fields = []
        fields = list(field_defs)
        i = 0
        while i < len(fields):
            field = fields[i]
            if field.field_type == "section":
                layout_fields.append(
                    HTML(f'<h4 class="mt-4 mb-3">{field.field_label}</h4>')
                )
                i += 1
            elif field.width == "half":
                next_field = fields[i + 1] if i + 1 < len(fields) else None
                if (
                    next_field
                    and next_field.width == "half"
                    and next_field.field_type != "section"
                ):
                    layout_fields.append(
                        Row(
                            Div(
                                Field(field.field_name),
                                css_class=f"col-md-6 field-wrapper field-{field.field_name}",
                            ),
                            Div(
                                Field(next_field.field_name),
                                css_class=f"col-md-6 field-wrapper field-{next_field.field_name}",
                            ),
                        )
                    )
                    i += 2
                else:
                    layout_fields.append(
                        Div(
                            Row(Column(Field(field.field_name), css_class="col-md-6")),
                            css_class=f"field-wrapper field-{field.field_name}",
                        )
                    )
                    i += 1
            elif field.width == "third":
                layout_fields.append(
                    Div(
                        Row(Column(Field(field.field_name), css_class="col-md-4")),
                        css_class=f"field-wrapper field-{field.field_name}",
                    )
                )
                i += 1
            elif field.width == "fourth":
                layout_fields.append(
                    Div(
                        Row(Column(Field(field.field_name), css_class="col-md-3")),
                        css_class=f"field-wrapper field-{field.field_name}",
                    )
                )
                i += 1
            else:
                layout_fields.append(
                    Div(
                        Field(field.field_name),
                        css_class=f"field-wrapper field-{field.field_name}",
                    )
                )
                i += 1
        return layout_fields

    def _setup_layout(self):
        """Setup Crispy Forms layout."""
        self.helper = FormHelper()
        self.helper.form_method = "post"
        self.helper.form_class = "needs-validation"

        layout_fields = []
        stage_id = self.approval_task.workflow_stage_id

        # Separate fields into current stage vs other (read-only) groups
        current_stage_defs = []
        other_defs = []
        for field_def in self.form_definition.fields.order_by("order"):
            if field_def.workflow_stage_id == stage_id:
                current_stage_defs.append(field_def)
            else:
                other_defs.append(field_def)

        # Add submitted data section first (read-only)
        if other_defs:
            layout_fields.append(
                HTML('<h3 class="mb-3">Submitted Information (Read-Only)</h3>')
            )
            layout_fields.extend(self._build_layout_fields(other_defs))

        # Add current stage fields section with width support
        current_stage_fields = self._build_layout_fields(current_stage_defs)
        if current_stage_fields:
            layout_fields.append(HTML('<hr class="my-4">'))
            step_name = self.approval_task.step_name or "Review"
            layout_fields.append(
                HTML(f'<h3 class="mb-3">{step_name} - Your Input</h3>')
            )
            layout_fields.extend(current_stage_fields)

        self.helper.layout = Layout(*layout_fields)
        self.helper.form_id = f"approval_form_{self.submission.pk}"

    def get_updated_form_data(self):
        """
        Get the updated form data after validation.
        Merges the stage field values with existing form data.
        """
        if not self.is_valid():
            return self.form_data

        # Start with existing form data
        updated_data = dict(self.form_data)

        # Update only fields for the current workflow stage
        stage_id = self.approval_task.workflow_stage_id
        qs = self.form_definition.fields.filter(workflow_stage_id=stage_id)
        for field_def in qs:
            field_name = field_def.field_name
            if field_name in self.cleaned_data:
                value = self.cleaned_data[field_name]
                # Convert date/datetime to string for JSON serialization
                if isinstance(value, datetime):
                    value = value.isoformat()
                elif isinstance(value, date):
                    value = value.isoformat()
                elif isinstance(value, list) and value and hasattr(value[0], "read"):
                    # Multi-file upload: serialize each file to storage
                    from .views import _serialize_single_file

                    value = [
                        _serialize_single_file(
                            f, f"{field_name}_{i}", self.submission.id
                        )
                        for i, f in enumerate(value)
                    ]
                elif hasattr(value, "read"):
                    # Single file upload: serialize to storage
                    from .views import _serialize_single_file

                    value = _serialize_single_file(
                        value, field_name, self.submission.id
                    )
                updated_data[field_name] = value

        return updated_data

    def get_editable_field_names(self):
        """Get list of field names that are editable for the current workflow stage."""
        stage_id = self.approval_task.workflow_stage_id
        return list(
            self.form_definition.fields.filter(workflow_stage_id=stage_id).values_list(
                "field_name", flat=True
            )
        )
