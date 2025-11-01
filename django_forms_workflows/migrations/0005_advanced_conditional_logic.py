# Generated migration for advanced conditional logic

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('django_forms_workflows', '0004_formtemplate'),
    ]

    operations = [
        # Add advanced conditional logic fields to FormField
        migrations.AddField(
            model_name='formfield',
            name='conditional_rules',
            field=models.JSONField(
                blank=True,
                null=True,
                help_text='Advanced conditional rules with AND/OR logic. Format: {"operator": "AND|OR", "conditions": [{"field": "field_name", "operator": "equals", "value": "value"}], "action": "show|hide|require|enable"}',
            ),
        ),
        migrations.AddField(
            model_name='formfield',
            name='validation_rules',
            field=models.JSONField(
                blank=True,
                null=True,
                help_text='Client-side validation rules. Format: [{"type": "required|email|min|max|pattern|custom", "value": "...", "message": "Error message"}]',
            ),
        ),
        migrations.AddField(
            model_name='formfield',
            name='field_dependencies',
            field=models.JSONField(
                blank=True,
                null=True,
                help_text='Field dependencies for cascade updates. Format: [{"sourceField": "field_name", "targetField": "dependent_field", "apiEndpoint": "/api/endpoint/"}]',
            ),
        ),
        
        # Add multi-step form support to FormDefinition
        migrations.AddField(
            model_name='formdefinition',
            name='enable_multi_step',
            field=models.BooleanField(
                default=False,
                help_text='Enable multi-step form with progress indicators',
            ),
        ),
        migrations.AddField(
            model_name='formdefinition',
            name='form_steps',
            field=models.JSONField(
                blank=True,
                null=True,
                help_text='Multi-step configuration. Format: [{"title": "Step 1", "fields": ["field1", "field2"]}]',
            ),
        ),
        
        # Add auto-save configuration to FormDefinition
        migrations.AddField(
            model_name='formdefinition',
            name='enable_auto_save',
            field=models.BooleanField(
                default=True,
                help_text='Enable automatic draft saving',
            ),
        ),
        migrations.AddField(
            model_name='formdefinition',
            name='auto_save_interval',
            field=models.IntegerField(
                default=30,
                help_text='Auto-save interval in seconds',
            ),
        ),
        
        # Add step information to FormField for multi-step forms
        migrations.AddField(
            model_name='formfield',
            name='step_number',
            field=models.IntegerField(
                null=True,
                blank=True,
                help_text='Step number for multi-step forms (1, 2, 3, etc.)',
            ),
        ),
    ]

