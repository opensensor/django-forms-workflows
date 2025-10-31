"""
Dynamic Form Generation for Django Form Workflows

This module provides the DynamicForm class that generates forms
based on database-stored form definitions.
"""

from django import forms
from django.core.validators import RegexValidator
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Field, Submit, Div, HTML, Row, Column
from datetime import date, datetime
import json
import logging

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
        for field in form_definition.fields.exclude(field_type='section').order_by('order'):
            self.add_field(field, initial_data)
        
        # Setup form layout with Crispy Forms
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.form_class = 'needs-validation'
        
        # Build layout
        layout_fields = []
        for field in form_definition.fields.order_by('order'):
            if field.field_type == 'section':
                layout_fields.append(HTML(f'<h3 class="mt-4 mb-3">{field.field_label}</h3>'))
            else:
                if field.width == 'half':
                    layout_fields.append(
                        Row(
                            Column(Field(field.field_name), css_class='col-md-6'),
                        )
                    )
                elif field.width == 'third':
                    layout_fields.append(
                        Row(
                            Column(Field(field.field_name), css_class='col-md-4'),
                        )
                    )
                else:
                    layout_fields.append(Field(field.field_name))
        
        # Add submit buttons
        buttons = [Submit('submit', 'Submit', css_class='btn btn-primary')]
        if form_definition.allow_save_draft:
            buttons.append(Submit('save_draft', 'Save Draft', css_class='btn btn-secondary ms-2'))

        layout_fields.append(
            Div(*buttons, css_class='mt-4')
        )
        
        self.helper.layout = Layout(*layout_fields)

    def _parse_choices(self, choices):
        """
        Parse choices from either JSON format or comma-separated string.
        Returns list of tuples: [(value, label), ...]
        """
        if not choices:
            return []

        # If choices is a list of dicts (JSON format)
        if isinstance(choices, list):
            return [(c['value'], c['label']) for c in choices]

        # If choices is a comma-separated string
        if isinstance(choices, str):
            return [(c.strip(), c.strip()) for c in choices.split(',') if c.strip()]

        return []

    def add_field(self, field_def, initial_data):
        """Add a field to the form based on field definition"""
        
        # Get initial value
        initial = self.get_initial_value(field_def, initial_data)
        
        # Common field arguments
        field_args = {
            'label': field_def.field_label,
            'required': field_def.required,
            'help_text': field_def.help_text,
            'initial': initial
        }
        
        # Add placeholder if provided
        widget_attrs = {}
        if field_def.placeholder:
            widget_attrs['placeholder'] = field_def.placeholder
        if field_def.css_class:
            widget_attrs['class'] = field_def.css_class
        
        # Create appropriate field type
        if field_def.field_type == 'text':
            if widget_attrs:
                field_args['widget'] = forms.TextInput(attrs=widget_attrs)
            self.fields[field_def.field_name] = forms.CharField(
                max_length=field_def.max_length or 255,
                min_length=field_def.min_length or None,
                **field_args
            )
            
        elif field_def.field_type == 'textarea':
            widget_attrs['rows'] = 4
            self.fields[field_def.field_name] = forms.CharField(
                widget=forms.Textarea(attrs=widget_attrs),
                max_length=field_def.max_length or None,
                min_length=field_def.min_length or None,
                **field_args
            )
            
        elif field_def.field_type == 'number':
            if widget_attrs:
                field_args['widget'] = forms.NumberInput(attrs=widget_attrs)
            self.fields[field_def.field_name] = forms.IntegerField(
                min_value=int(field_def.min_value) if field_def.min_value else None,
                max_value=int(field_def.max_value) if field_def.max_value else None,
                **field_args
            )
            
        elif field_def.field_type == 'decimal':
            if widget_attrs:
                field_args['widget'] = forms.NumberInput(attrs=widget_attrs)
            self.fields[field_def.field_name] = forms.DecimalField(
                min_value=field_def.min_value,
                max_value=field_def.max_value,
                decimal_places=2,
                **field_args
            )
            
        elif field_def.field_type == 'date':
            widget_attrs['type'] = 'date'
            self.fields[field_def.field_name] = forms.DateField(
                widget=forms.DateInput(attrs=widget_attrs),
                **field_args
            )
            
        elif field_def.field_type == 'datetime':
            widget_attrs['type'] = 'datetime-local'
            self.fields[field_def.field_name] = forms.DateTimeField(
                widget=forms.DateTimeInput(attrs=widget_attrs),
                **field_args
            )
            
        elif field_def.field_type == 'time':
            widget_attrs['type'] = 'time'
            self.fields[field_def.field_name] = forms.TimeField(
                widget=forms.TimeInput(attrs=widget_attrs),
                **field_args
            )
            
        elif field_def.field_type == 'email':
            if widget_attrs:
                field_args['widget'] = forms.EmailInput(attrs=widget_attrs)
            self.fields[field_def.field_name] = forms.EmailField(**field_args)
            
        elif field_def.field_type == 'url':
            if widget_attrs:
                field_args['widget'] = forms.URLInput(attrs=widget_attrs)
            self.fields[field_def.field_name] = forms.URLField(**field_args)
            
        elif field_def.field_type == 'select':
            choices = [('', '-- Select --')] + self._parse_choices(field_def.choices)
            self.fields[field_def.field_name] = forms.ChoiceField(
                choices=choices,
                **field_args
            )

        elif field_def.field_type == 'multiselect':
            choices = self._parse_choices(field_def.choices)
            self.fields[field_def.field_name] = forms.MultipleChoiceField(
                choices=choices,
                widget=forms.CheckboxSelectMultiple,
                **field_args
            )

        elif field_def.field_type == 'radio':
            choices = self._parse_choices(field_def.choices)
            self.fields[field_def.field_name] = forms.ChoiceField(
                choices=choices,
                widget=forms.RadioSelect,
                **field_args
            )
            
        elif field_def.field_type == 'checkbox':
            self.fields[field_def.field_name] = forms.BooleanField(
                required=False,  # Checkboxes are never required
                label=field_def.field_label,
                help_text=field_def.help_text,
                initial=initial
            )
            
        elif field_def.field_type == 'checkboxes':
            choices = self._parse_choices(field_def.choices)
            self.fields[field_def.field_name] = forms.MultipleChoiceField(
                choices=choices,
                widget=forms.CheckboxSelectMultiple,
                required=field_def.required,
                label=field_def.field_label,
                help_text=field_def.help_text,
                initial=initial
            )
            
        elif field_def.field_type == 'file':
            self.fields[field_def.field_name] = forms.FileField(
                **field_args
            )
            
        elif field_def.field_type == 'hidden':
            self.fields[field_def.field_name] = forms.CharField(
                widget=forms.HiddenInput(),
                required=False,
                initial=initial
            )
        
        # Add custom validation if regex provided
        if field_def.regex_validation and field_def.field_type in ['text', 'textarea']:
            self.fields[field_def.field_name].validators.append(
                RegexValidator(
                    regex=field_def.regex_validation,
                    message=field_def.regex_error_message or 'Invalid format'
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
        return field_def.default_value or ''

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
            from .data_sources import UserDataSource, LDAPDataSource, DatabaseDataSource

            # Handle user.* sources
            if prefill_source.startswith('user.'):
                source = UserDataSource()
                field_name = prefill_source.replace('user.', '')
                return source.get_value(self.user, field_name) or ''

            # Handle ldap.* sources
            elif prefill_source.startswith('ldap.'):
                source = LDAPDataSource()
                field_name = prefill_source.replace('ldap.', '')
                return source.get_value(self.user, field_name) or ''

            # Handle db.* or {{ db.* }} sources
            elif prefill_source.startswith('db.') or prefill_source.startswith('{{'):
                source = DatabaseDataSource()
                # Parse the source string
                source_str = prefill_source.strip()
                if source_str.startswith('{{') and source_str.endswith('}}'):
                    source_str = source_str[2:-2].strip()
                if source_str.startswith('db.'):
                    source_str = source_str[3:]

                # Parse schema.table.column
                parts = source_str.split('.')
                if len(parts) >= 2:
                    # If we have a prefill_config with custom field mappings, use them
                    kwargs = {}
                    if prefill_config and prefill_config.source_type == 'database':
                        if prefill_config.db_alias:
                            kwargs['database_alias'] = prefill_config.db_alias
                        if prefill_config.db_lookup_field:
                            kwargs['lookup_field'] = prefill_config.db_lookup_field
                        if prefill_config.db_user_field:
                            kwargs['user_id_field'] = prefill_config.db_user_field

                    # Pass the full path to the data source
                    return source.get_value(self.user, source_str, **kwargs) or ''

            # Handle current_date
            elif prefill_source == 'current_date':
                return date.today()

            # Handle current_datetime
            elif prefill_source == 'current_datetime':
                return datetime.now()

            # Handle last_submission
            elif prefill_source == 'last_submission':
                from .models import FormSubmission
                last_sub = FormSubmission.objects.filter(
                    form_definition=self.form_definition,
                    submitter=self.user
                ).exclude(status='draft').order_by('-submitted_at').first()
                if last_sub and hasattr(last_sub, 'form_data'):
                    # This would need to be field-specific
                    # For now, return empty
                    pass

        except Exception as e:
            logger.error(f"Error getting prefill value for {prefill_source}: {e}")

        return ''


