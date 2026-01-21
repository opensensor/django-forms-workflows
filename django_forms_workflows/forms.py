"""
Dynamic Form Generation for Django Form Workflows

This module provides the DynamicForm class that generates forms
based on database-stored form definitions, and the ApprovalStepForm
class for handling approval-step field editing.
"""

import logging
from datetime import date, datetime

from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Column, Div, Field, Layout, Row, Submit
from django import forms
from django.core.validators import RegexValidator

logger = logging.getLogger(__name__)


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

        # Build form fields from definition
        # Exclude fields with approval_step set - those are for approvers only
        for field in (
            form_definition.fields.exclude(field_type="section")
            .filter(approval_step__isnull=True)
            .order_by("order")
        ):
            self.add_field(field, initial_data)

        # Setup form layout with Crispy Forms
        self.helper = FormHelper()
        self.helper.form_method = "post"
        self.helper.form_class = "needs-validation"

        # Build layout - exclude approval step fields
        layout_fields = []
        for field in form_definition.fields.filter(approval_step__isnull=True).order_by(
            "order"
        ):
            if field.field_type == "section":
                layout_fields.append(
                    HTML(f'<h3 class="mt-4 mb-3">{field.field_label}</h3>')
                )
            else:
                # Wrap field in a div with field-wrapper class for multi-step support
                field_wrapper_class = f"field-wrapper field-{field.field_name}"

                if field.width == "half":
                    layout_fields.append(
                        Div(
                            Row(
                                Column(Field(field.field_name), css_class="col-md-6"),
                            ),
                            css_class=field_wrapper_class,
                        )
                    )
                elif field.width == "third":
                    layout_fields.append(
                        Div(
                            Row(
                                Column(Field(field.field_name), css_class="col-md-4"),
                            ),
                            css_class=field_wrapper_class,
                        )
                    )
                else:
                    layout_fields.append(
                        Div(Field(field.field_name), css_class=field_wrapper_class)
                    )

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
            if widget_attrs:
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
            choices = [("", "-- Select --")] + self._parse_choices(field_def.choices)
            self.fields[field_def.field_name] = forms.ChoiceField(
                choices=choices, **field_args
            )

        elif field_def.field_type == "multiselect":
            choices = self._parse_choices(field_def.choices)
            self.fields[field_def.field_name] = forms.MultipleChoiceField(
                choices=choices, widget=forms.CheckboxSelectMultiple, **field_args
            )

        elif field_def.field_type == "radio":
            choices = self._parse_choices(field_def.choices)
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
            choices = self._parse_choices(field_def.choices)
            self.fields[field_def.field_name] = forms.MultipleChoiceField(
                choices=choices,
                widget=forms.CheckboxSelectMultiple,
                required=field_def.required,
                label=field_def.field_label,
                help_text=field_def.help_text,
                initial=initial,
            )

        elif field_def.field_type == "file":
            self.fields[field_def.field_name] = forms.FileField(**field_args)

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
        - db.* or {{ db.* }} - Database queries
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
            elif prefill_source.startswith("ldap."):
                source = LDAPDataSource()
                field_name = prefill_source.replace("ldap.", "")
                return source.get_value(self.user, field_name) or ""

            # Handle db.* or {{ db.* }} sources
            elif prefill_source.startswith("db.") or prefill_source.startswith("{{"):
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

        config = {
            "autoSaveEnabled": getattr(self.form_definition, "enable_auto_save", True),
            "autoSaveInterval": getattr(self.form_definition, "auto_save_interval", 30)
            * 1000,  # Convert to ms
            "autoSaveEndpoint": f"/forms/{self.form_definition.slug}/auto-save/",
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
            # Legacy simple conditional logic
            if field.show_if_field and field.show_if_value:
                config["conditionalRules"].append(
                    {
                        "targetField": field.field_name,
                        "action": "show",
                        "operator": "AND",
                        "conditions": [
                            {
                                "field": field.show_if_field,
                                "operator": "equals",
                                "value": field.show_if_value,
                            }
                        ],
                    }
                )

            # Advanced conditional rules
            if hasattr(field, "conditional_rules") and field.conditional_rules:
                if isinstance(field.conditional_rules, str):
                    try:
                        rules = json.loads(field.conditional_rules)
                    except json.JSONDecodeError:
                        rules = None
                else:
                    rules = field.conditional_rules

                if rules:
                    config["conditionalRules"].append(
                        {"targetField": field.field_name, **rules}
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
    Form for approvers to fill in fields specific to their approval step.

    This form is used during the approval process to allow approvers to:
    - View all previously submitted/approved data as read-only
    - Edit fields designated for their approval step (approval_step = current step)
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
        self.current_step = approval_task.step_number or 1

        # Get existing form data
        self.form_data = submission.form_data or {}

        # Build form fields from definition
        self._build_fields()

        # Setup form layout with Crispy Forms
        self._setup_layout()

    def _build_fields(self):
        """Build all form fields, making approval step fields editable."""
        for field_def in self.form_definition.fields.exclude(
            field_type="section"
        ).order_by("order"):
            self._add_field(field_def)

    def _add_field(self, field_def):
        """Add a single field to the form."""
        # Determine if this field is editable for the current approval step
        is_editable = field_def.approval_step == self.current_step

        # Get current value from form data
        current_value = self.form_data.get(field_def.field_name, "")

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
            if widget_attrs:
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
            choices = [("", "-- Select --")] + self._parse_choices(field_def.choices)
            if widget_attrs:
                field_args["widget"] = forms.Select(attrs=widget_attrs)
            self.fields[field_def.field_name] = forms.ChoiceField(
                choices=choices, **field_args
            )

        elif field_def.field_type == "radio":
            choices = self._parse_choices(field_def.choices)
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

    def _setup_layout(self):
        """Setup Crispy Forms layout."""
        self.helper = FormHelper()
        self.helper.form_method = "post"
        self.helper.form_class = "needs-validation"

        layout_fields = []

        # Add fields organized by approval step
        current_step_fields = []
        other_fields = []

        for field_def in self.form_definition.fields.order_by("order"):
            if field_def.field_type == "section":
                section_html = HTML(
                    f'<h4 class="mt-4 mb-3">{field_def.field_label}</h4>'
                )
                if field_def.approval_step == self.current_step:
                    current_step_fields.append(section_html)
                else:
                    other_fields.append(section_html)
            else:
                field_wrapper = Div(
                    Field(field_def.field_name),
                    css_class=f"field-wrapper field-{field_def.field_name}",
                )
                if field_def.approval_step == self.current_step:
                    current_step_fields.append(field_wrapper)
                else:
                    other_fields.append(field_wrapper)

        # Add submitted data section first (read-only)
        if other_fields:
            layout_fields.append(
                HTML('<h3 class="mb-3">Submitted Information (Read-Only)</h3>')
            )
            layout_fields.extend(other_fields)

        # Add current step fields section
        if current_step_fields:
            layout_fields.append(HTML('<hr class="my-4">'))
            step_name = self.approval_task.step_name or f"Step {self.current_step}"
            layout_fields.append(
                HTML(f'<h3 class="mb-3">{step_name} - Your Input</h3>')
            )
            layout_fields.extend(current_step_fields)

        self.helper.layout = Layout(*layout_fields)
        self.helper.form_id = f"approval_form_{self.submission.pk}"

    def get_updated_form_data(self):
        """
        Get the updated form data after validation.
        Merges the approval step field values with existing form data.
        """
        if not self.is_valid():
            return self.form_data

        # Start with existing form data
        updated_data = dict(self.form_data)

        # Update only fields for the current approval step
        for field_def in self.form_definition.fields.filter(
            approval_step=self.current_step
        ):
            field_name = field_def.field_name
            if field_name in self.cleaned_data:
                value = self.cleaned_data[field_name]
                # Convert date/datetime to string for JSON serialization
                if isinstance(value, datetime):
                    value = value.isoformat()
                elif isinstance(value, date):
                    value = value.isoformat()
                updated_data[field_name] = value

        return updated_data

    def get_editable_field_names(self):
        """Get list of field names that are editable for the current approval step."""
        return list(
            self.form_definition.fields.filter(
                approval_step=self.current_step
            ).values_list("field_name", flat=True)
        )
