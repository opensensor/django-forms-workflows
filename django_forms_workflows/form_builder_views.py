"""
Visual Form Builder Views

Provides the visual drag-and-drop form builder interface for creating
and editing forms without code.
"""

import json
import logging

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET, require_POST

from .forms import DynamicForm
from .models import FormDefinition, FormField, PrefillSource

logger = logging.getLogger(__name__)


@staff_member_required
@require_GET
def form_builder_view(request, form_id=None):
    """
    Main form builder page.
    
    If form_id is provided, loads existing form for editing.
    Otherwise, shows empty builder for creating new form.
    """
    form_definition = None
    if form_id:
        form_definition = get_object_or_404(FormDefinition, id=form_id)
    
    # Get all active prefill sources for the property panel
    prefill_sources = PrefillSource.objects.filter(is_active=True).order_by('order', 'name')

    # Get field type choices - convert to JSON-serializable format
    field_types_json = json.dumps([
        {'value': ft[0], 'label': ft[1]}
        for ft in FormField.FIELD_TYPES
    ])

    context = {
        'form_definition': form_definition,
        'prefill_sources': prefill_sources,
        'field_types': field_types_json,
        'is_new': form_id is None,
    }

    return render(request, 'admin/django_forms_workflows/form_builder.html', context)


@staff_member_required
@require_GET
def form_builder_load(request, form_id):
    """
    API endpoint to load form data as JSON.
    
    Returns the form definition and all fields in a format suitable
    for the form builder JavaScript.
    """
    form_definition = get_object_or_404(FormDefinition, id=form_id)
    
    # Build field data
    fields_data = []
    for field in form_definition.fields.all().order_by('order'):
        field_data = {
            'id': field.id,
            'order': field.order,
            'field_label': field.field_label,
            'field_name': field.field_name,
            'field_type': field.field_type,
            'required': field.required,
            'help_text': field.help_text or '',
            'placeholder': field.placeholder or '',
            'width': field.width,
            'css_class': field.css_class or '',
            'choices': field.choices or '',
            'default_value': field.default_value or '',
            'prefill_source_id': field.prefill_source_config_id,
            'validation': {
                'min_value': field.min_value,
                'max_value': field.max_value,
                'min_length': field.min_length,
                'max_length': field.max_length,
                'regex_validation': field.regex_validation or '',
                'regex_error_message': field.regex_error_message or '',
            },
            'conditional': {
                'show_if_field': field.show_if_field,
                'show_if_value': field.show_if_value or '',
            }
        }
        fields_data.append(field_data)
    
    # Build form data
    form_data = {
        'id': form_definition.id,
        'name': form_definition.name,
        'slug': form_definition.slug,
        'description': form_definition.description,
        'instructions': form_definition.instructions or '',
        'is_active': form_definition.is_active,
        'requires_login': form_definition.requires_login,
        'allow_save_draft': form_definition.allow_save_draft,
        'allow_withdrawal': form_definition.allow_withdrawal,
        'fields': fields_data,
    }
    
    return JsonResponse(form_data)


@staff_member_required
@require_POST
def form_builder_save(request):
    """
    API endpoint to save form data.
    
    Accepts JSON data from the form builder and creates/updates
    the FormDefinition and FormField records.
    """
    try:
        data = json.loads(request.body)
        
        # Extract form definition data
        form_id = data.get('id')
        form_name = data.get('name', '').strip()
        form_slug = data.get('slug', '').strip()
        form_description = data.get('description', '').strip()
        form_instructions = data.get('instructions', '').strip()
        is_active = data.get('is_active', True)
        requires_login = data.get('requires_login', True)
        allow_save_draft = data.get('allow_save_draft', True)
        allow_withdrawal = data.get('allow_withdrawal', True)
        fields_data = data.get('fields', [])
        
        # Validate required fields
        if not form_name:
            return JsonResponse({'success': False, 'error': 'Form name is required'}, status=400)
        if not form_slug:
            return JsonResponse({'success': False, 'error': 'Form slug is required'}, status=400)
        
        # Use transaction to ensure atomicity
        with transaction.atomic():
            # Create or update form definition
            if form_id:
                form_definition = get_object_or_404(FormDefinition, id=form_id)
                form_definition.name = form_name
                form_definition.slug = form_slug
                form_definition.description = form_description
                form_definition.instructions = form_instructions
                form_definition.is_active = is_active
                form_definition.requires_login = requires_login
                form_definition.allow_save_draft = allow_save_draft
                form_definition.allow_withdrawal = allow_withdrawal
                form_definition.version += 1  # Increment version on edit
                form_definition.save()
            else:
                form_definition = FormDefinition.objects.create(
                    name=form_name,
                    slug=form_slug,
                    description=form_description,
                    instructions=form_instructions,
                    is_active=is_active,
                    requires_login=requires_login,
                    allow_save_draft=allow_save_draft,
                    allow_withdrawal=allow_withdrawal,
                    created_by=request.user,
                )
            
            # Track existing field IDs to determine which to delete
            existing_field_ids = set(form_definition.fields.values_list('id', flat=True))
            updated_field_ids = set()
            
            # Create or update fields
            for field_data in fields_data:
                field_id = field_data.get('id')
                
                # Extract field properties
                field_props = {
                    'form_definition': form_definition,
                    'order': field_data.get('order', 0),
                    'field_label': field_data.get('field_label', ''),
                    'field_name': field_data.get('field_name', ''),
                    'field_type': field_data.get('field_type', 'text'),
                    'required': field_data.get('required', False),
                    'help_text': field_data.get('help_text', ''),
                    'placeholder': field_data.get('placeholder', ''),
                    'width': field_data.get('width', 'full'),
                    'css_class': field_data.get('css_class', ''),
                    'choices': field_data.get('choices', ''),
                    'default_value': field_data.get('default_value', ''),
                    'prefill_source_config_id': field_data.get('prefill_source_id'),
                }
                
                # Add validation properties
                validation = field_data.get('validation', {})
                field_props.update({
                    'min_value': validation.get('min_value'),
                    'max_value': validation.get('max_value'),
                    'min_length': validation.get('min_length'),
                    'max_length': validation.get('max_length'),
                    'regex_validation': validation.get('regex_validation', ''),
                    'regex_error_message': validation.get('regex_error_message', ''),
                })
                
                # Add conditional properties
                conditional = field_data.get('conditional', {})
                field_props.update({
                    'show_if_field': conditional.get('show_if_field', ''),
                    'show_if_value': conditional.get('show_if_value', ''),
                })
                
                # Create or update field
                if field_id and isinstance(field_id, int):
                    # Update existing field
                    FormField.objects.filter(id=field_id).update(**field_props)
                    updated_field_ids.add(field_id)
                else:
                    # Create new field
                    new_field = FormField.objects.create(**field_props)
                    updated_field_ids.add(new_field.id)
            
            # Delete fields that were removed
            fields_to_delete = existing_field_ids - updated_field_ids
            if fields_to_delete:
                FormField.objects.filter(id__in=fields_to_delete).delete()
        
        return JsonResponse({
            'success': True,
            'form_id': form_definition.id,
            'message': 'Form saved successfully',
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        logger.exception('Error saving form in builder')
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@staff_member_required
@require_POST
def form_builder_preview(request):
    """
    API endpoint to generate a preview of the form.
    
    Accepts JSON data and returns rendered HTML of how the form
    will look to end users.
    """
    try:
        data = json.loads(request.body)
        
        # Create a temporary form definition (not saved to DB)
        form_definition = FormDefinition(
            name=data.get('name', 'Preview'),
            slug=data.get('slug', 'preview'),
            description=data.get('description', ''),
            instructions=data.get('instructions', ''),
        )
        
        # We can't easily preview without saving to DB due to how DynamicForm works
        # For now, return a simple HTML representation
        # TODO: Enhance this to use actual DynamicForm rendering
        
        fields_html = []
        for field_data in data.get('fields', []):
            field_label = field_data.get('field_label', 'Untitled Field')
            field_type = field_data.get('field_type', 'text')
            required = field_data.get('required', False)
            help_text = field_data.get('help_text', '')
            
            required_badge = '<span class="text-danger">*</span>' if required else ''
            help_html = f'<small class="form-text text-muted">{help_text}</small>' if help_text else ''
            
            fields_html.append(f'''
                <div class="mb-3">
                    <label class="form-label">{field_label} {required_badge}</label>
                    <input type="text" class="form-control" placeholder="{field_type} field">
                    {help_html}
                </div>
            ''')
        
        preview_html = f'''
            <div class="card">
                <div class="card-body">
                    <h3>{data.get('name', 'Form Preview')}</h3>
                    {f'<p class="text-muted">{data.get("instructions", "")}</p>' if data.get('instructions') else ''}
                    <form>
                        {''.join(fields_html)}
                        <button type="submit" class="btn btn-primary">Submit</button>
                    </form>
                </div>
            </div>
        '''
        
        return JsonResponse({
            'success': True,
            'html': preview_html,
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        logger.exception('Error generating form preview')
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

