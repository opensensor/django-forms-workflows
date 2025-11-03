"""
Visual Form Builder Views

Provides the visual drag-and-drop form builder interface for creating
and editing forms without code.
"""

import json
import logging
import uuid

from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET, require_POST

from .models import FormDefinition, FormField, FormTemplate, PrefillSource

logger = logging.getLogger(__name__)


@staff_member_required
@require_GET
def form_builder_templates(request):
    """
    API endpoint to list available form templates.

    Returns a list of templates organized by category.
    """
    templates = FormTemplate.objects.filter(is_active=True).order_by("category", "name")

    templates_data = []
    for template in templates:
        templates_data.append(
            {
                "id": template.id,
                "name": template.name,
                "slug": template.slug,
                "description": template.description,
                "category": template.category,
                "category_display": template.get_category_display(),
                "preview_url": template.preview_url,
                "usage_count": template.usage_count,
            }
        )

    return JsonResponse(
        {
            "success": True,
            "templates": templates_data,
        }
    )


@staff_member_required
@require_GET
def form_builder_load_template(request, template_id):
    """
    API endpoint to load a form template.

    Returns the template data that can be used to populate the form builder.
    """
    template = get_object_or_404(FormTemplate, id=template_id, is_active=True)

    # Increment usage counter
    template.increment_usage()

    return JsonResponse(
        {
            "success": True,
            "template_data": template.template_data,
        }
    )


@staff_member_required
@require_POST
def form_builder_clone(request, form_id):
    """
    API endpoint to clone an existing form.

    Creates a copy of the form with all fields and settings,
    appending "(Copy)" to the name and generating a new slug.
    """
    try:
        # Get the original form
        original_form = get_object_or_404(FormDefinition, id=form_id)

        # Create a new form with copied data
        with transaction.atomic():
            # Generate unique slug
            base_slug = f"{original_form.slug}-copy"
            slug = base_slug
            counter = 1
            while FormDefinition.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1

            # Clone the form definition
            cloned_form = FormDefinition.objects.create(
                name=f"{original_form.name} (Copy)",
                slug=slug,
                description=original_form.description,
                instructions=original_form.instructions,
                is_active=False,  # Start as inactive
                version=1,
                requires_login=original_form.requires_login,
                allow_save_draft=original_form.allow_save_draft,
                allow_withdrawal=original_form.allow_withdrawal,
                created_by=request.user,
            )

            # Clone all fields
            for field in original_form.fields.all().order_by("order"):
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
            cloned_form.submit_groups.set(original_form.submit_groups.all())
            cloned_form.view_groups.set(original_form.view_groups.all())
            cloned_form.admin_groups.set(original_form.admin_groups.all())

            return JsonResponse(
                {
                    "success": True,
                    "form_id": cloned_form.id,
                    "message": f'Form cloned successfully as "{cloned_form.name}"',
                }
            )

    except Exception as e:
        logger.exception("Error cloning form")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


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
    prefill_sources = PrefillSource.objects.filter(is_active=True).order_by(
        "order", "name"
    )

    # Get field type choices - convert to JSON-serializable format
    field_types_json = json.dumps(
        [{"value": ft[0], "label": ft[1]} for ft in FormField.FIELD_TYPES]
    )

    context = {
        "form_definition": form_definition,
        "prefill_sources": prefill_sources,
        "field_types": field_types_json,
        "is_new": form_id is None,
    }

    return render(request, "admin/django_forms_workflows/form_builder.html", context)


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
    for field in form_definition.fields.all().order_by("order"):
        field_data = {
            "id": field.id,
            "order": field.order,
            "field_label": field.field_label,
            "field_name": field.field_name,
            "field_type": field.field_type,
            "required": field.required,
            "help_text": field.help_text or "",
            "placeholder": field.placeholder or "",
            "width": field.width,
            "css_class": field.css_class or "",
            "choices": field.choices or "",
            "default_value": field.default_value or "",
            "prefill_source_id": field.prefill_source_config_id,
            "validation": {
                "min_value": field.min_value,
                "max_value": field.max_value,
                "min_length": field.min_length,
                "max_length": field.max_length,
                "regex_validation": field.regex_validation or "",
                "regex_error_message": field.regex_error_message or "",
            },
            "conditional": {
                "show_if_field": field.show_if_field,
                "show_if_value": field.show_if_value or "",
            },
        }
        fields_data.append(field_data)

    # Build form data
    form_data = {
        "id": form_definition.id,
        "name": form_definition.name,
        "slug": form_definition.slug,
        "description": form_definition.description,
        "instructions": form_definition.instructions or "",
        "is_active": form_definition.is_active,
        "requires_login": form_definition.requires_login,
        "allow_save_draft": form_definition.allow_save_draft,
        "allow_withdrawal": form_definition.allow_withdrawal,
        "enable_multi_step": form_definition.enable_multi_step,
        "form_steps": form_definition.form_steps or [],
        "enable_auto_save": form_definition.enable_auto_save,
        "auto_save_interval": form_definition.auto_save_interval,
        "fields": fields_data,
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
        form_id = data.get("id")
        form_name = data.get("name", "").strip()
        form_slug = data.get("slug", "").strip()
        form_description = data.get("description", "").strip()
        form_instructions = data.get("instructions", "").strip()
        is_active = data.get("is_active", True)
        requires_login = data.get("requires_login", True)
        allow_save_draft = data.get("allow_save_draft", True)
        allow_withdrawal = data.get("allow_withdrawal", True)
        enable_multi_step = data.get("enable_multi_step", False)
        form_steps = data.get("form_steps", [])
        enable_auto_save = data.get("enable_auto_save", True)
        auto_save_interval = data.get("auto_save_interval", 30)
        fields_data = data.get("fields", [])

        # Validate required fields
        if not form_name:
            return JsonResponse(
                {"success": False, "error": "Form name is required"}, status=400
            )
        if not form_slug:
            return JsonResponse(
                {"success": False, "error": "Form slug is required"}, status=400
            )

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
                form_definition.enable_multi_step = enable_multi_step
                form_definition.form_steps = form_steps
                form_definition.enable_auto_save = enable_auto_save
                form_definition.auto_save_interval = auto_save_interval
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
                    enable_multi_step=enable_multi_step,
                    form_steps=form_steps,
                    enable_auto_save=enable_auto_save,
                    auto_save_interval=auto_save_interval,
                    created_by=request.user,
                )

            # Track existing field IDs to determine which to delete
            existing_field_ids = set(
                form_definition.fields.values_list("id", flat=True)
            )
            updated_field_ids = set()
            field_id_mapping = {}  # Map old IDs to new IDs for frontend update

            # Create or update fields
            for field_data in fields_data:
                field_id = field_data.get("id")
                old_id = field_id  # Store original ID for mapping

                # Extract field properties
                field_props = {
                    "form_definition": form_definition,
                    "order": field_data.get("order", 0),
                    "field_label": field_data.get("field_label", ""),
                    "field_name": field_data.get("field_name", ""),
                    "field_type": field_data.get("field_type", "text"),
                    "required": field_data.get("required", False),
                    "help_text": field_data.get("help_text", ""),
                    "placeholder": field_data.get("placeholder", ""),
                    "width": field_data.get("width", "full"),
                    "css_class": field_data.get("css_class", ""),
                    "choices": field_data.get("choices", ""),
                    "default_value": field_data.get("default_value", ""),
                    "prefill_source_config_id": field_data.get("prefill_source_id"),
                }

                # Add validation properties
                validation = field_data.get("validation", {})
                field_props.update(
                    {
                        "min_value": validation.get("min_value"),
                        "max_value": validation.get("max_value"),
                        "min_length": validation.get("min_length"),
                        "max_length": validation.get("max_length"),
                        "regex_validation": validation.get("regex_validation", ""),
                        "regex_error_message": validation.get(
                            "regex_error_message", ""
                        ),
                    }
                )

                # Add conditional properties
                conditional = field_data.get("conditional", {})
                field_props.update(
                    {
                        "show_if_field": conditional.get("show_if_field", ""),
                        "show_if_value": conditional.get("show_if_value", ""),
                    }
                )

                # Add client-side enhancement properties
                field_props.update(
                    {
                        "conditional_rules": field_data.get("conditional_rules"),
                        "validation_rules": field_data.get("validation_rules"),
                        "field_dependencies": field_data.get("field_dependencies"),
                        "step_number": field_data.get("step_number"),
                    }
                )

                # Create or update field
                if field_id and isinstance(field_id, int):
                    # Update existing field
                    FormField.objects.filter(id=field_id).update(**field_props)
                    updated_field_ids.add(field_id)
                    field_id_mapping[str(old_id)] = field_id
                else:
                    # Create new field
                    new_field = FormField.objects.create(**field_props)
                    updated_field_ids.add(new_field.id)
                    field_id_mapping[str(old_id)] = new_field.id

            # Delete fields that were removed
            fields_to_delete = existing_field_ids - updated_field_ids
            if fields_to_delete:
                FormField.objects.filter(id__in=fields_to_delete).delete()

        return JsonResponse(
            {
                "success": True,
                "form_id": form_definition.id,
                "message": "Form saved successfully",
                "field_id_mapping": field_id_mapping,
            }
        )

    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "error": "Invalid JSON data"}, status=400
        )
    except Exception as e:
        logger.exception("Error saving form in builder")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


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

        # If no fields, return a simple message
        if not data.get("fields"):
            return JsonResponse(
                {
                    "success": True,
                    "html": """
                    <div class="alert alert-info small">
                        <i class="bi bi-info-circle"></i>
                        <strong>No fields yet</strong><br>
                        Add fields from the palette to see the preview
                    </div>
                """,
                }
            )

        # Generate a unique temporary slug for preview
        temp_slug = f"preview-{uuid.uuid4().hex[:8]}"

        # Create a temporary form definition (not saved to DB)
        form_definition = FormDefinition(
            name=data.get("name", "Preview"),
            slug=temp_slug,
            description=data.get("description", ""),
            instructions=data.get("instructions", ""),
        )

        # Use actual DynamicForm rendering with crispy forms
        # We'll create temporary objects in a rolled-back transaction
        from django.db import transaction

        from .forms import DynamicForm

        with transaction.atomic():
            # Save the form definition temporarily
            form_definition.is_active = data.get("is_active", True)
            form_definition.requires_login = data.get("requires_login", True)
            form_definition.allow_save_draft = data.get("allow_save_draft", True)
            form_definition.allow_withdrawal = data.get("allow_withdrawal", True)
            form_definition.save()

            # Create temporary fields
            for field_data in data.get("fields", []):
                validation = field_data.get("validation", {})
                conditional = field_data.get("conditional", {})

                # Build field kwargs
                field_kwargs = {
                    "form_definition": form_definition,
                    "order": field_data.get("order", 0),
                    "field_name": field_data.get("field_name", "field"),
                    "field_label": field_data.get("field_label", "Field"),
                    "field_type": field_data.get("field_type", "text"),
                    "required": field_data.get("required", False),
                    "help_text": field_data.get("help_text", ""),
                    "placeholder": field_data.get("placeholder", ""),
                    "width": field_data.get("width", "full"),
                    "css_class": field_data.get("css_class", ""),
                    "choices": field_data.get("choices", ""),
                    "default_value": field_data.get("default_value", ""),
                    "regex_validation": validation.get("regex_validation", ""),
                    "regex_error_message": validation.get("regex_error_message", ""),
                }

                # Add optional fields only if they have values
                if field_data.get("prefill_source_id"):
                    field_kwargs["prefill_source_config_id"] = field_data.get(
                        "prefill_source_id"
                    )

                if validation.get("min_value") is not None:
                    field_kwargs["min_value"] = validation.get("min_value")
                if validation.get("max_value") is not None:
                    field_kwargs["max_value"] = validation.get("max_value")
                if validation.get("min_length") is not None:
                    field_kwargs["min_length"] = validation.get("min_length")
                if validation.get("max_length") is not None:
                    field_kwargs["max_length"] = validation.get("max_length")

                # Only set show_if_field if it has a value (SlugField doesn't accept empty string)
                if conditional.get("show_if_field"):
                    field_kwargs["show_if_field"] = conditional.get("show_if_field")
                    field_kwargs["show_if_value"] = conditional.get("show_if_value", "")

                FormField.objects.create(**field_kwargs)

            # Generate the form using DynamicForm
            dynamic_form = DynamicForm(form_definition)

            # Render the form using crispy forms template rendering
            from django.template import Context, Template

            # Use crispy forms to render the form properly
            template_string = """
                {% load crispy_forms_tags %}
                {% crispy form %}
            """
            template = Template(template_string)
            context = Context({"form": dynamic_form})
            form_html = template.render(context)

            # Wrap in a nice preview container matching the actual form_submit.html layout
            preview_html = f"""
                <div class="preview-container">
                    <div class="d-flex justify-content-between align-items-center mb-4">
                        <h5 class="mb-1">{form_definition.name}</h5>
                    </div>
                    {f'<div class="alert alert-info"><i class="bi bi-info-circle"></i> {form_definition.instructions}</div>' if form_definition.instructions else ""}
                    <div class="card">
                        <div class="card-body">
                            {form_html}
                        </div>
                    </div>
                    <div class="mt-3 pt-2 border-top">
                        <small class="text-muted">
                            <i class="bi bi-eye"></i> Live preview - changes are not saved until you click "Save Form"
                        </small>
                    </div>
                </div>
            """

            # Rollback the transaction to avoid saving to DB
            transaction.set_rollback(True)

        return JsonResponse(
            {
                "success": True,
                "html": preview_html,
            }
        )

    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "error": "Invalid JSON data"}, status=400
        )
    except Exception as e:
        logger.exception("Error generating form preview")
        return JsonResponse({"success": False, "error": str(e)}, status=500)
