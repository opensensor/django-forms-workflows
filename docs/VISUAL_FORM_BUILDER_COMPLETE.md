# Visual Form Builder - Complete Implementation

## Overview

The Visual Form Builder is a comprehensive drag-and-drop interface for creating and editing forms in the django-forms-workflows library. It provides an intuitive, user-friendly alternative to the traditional Django admin inline editing.

## Features Implemented

### ✅ Core Features

1. **Drag-and-Drop Interface**
   - Field palette with 16+ field types
   - Drag fields from palette to canvas
   - Reorder fields by dragging
   - Visual feedback during drag operations
   - Uses SortableJS for smooth interactions

2. **Field Property Panel**
   - Comprehensive field configuration
   - Validation rules (min/max values, length, regex)
   - Conditional visibility (show_if_field, show_if_value)
   - Prefill source selection
   - Field styling options (width, CSS classes)
   - Help text and placeholders

3. **Live Form Preview**
   - Real-time preview using actual DynamicForm rendering
   - Crispy forms Bootstrap 5 styling
   - Debounced updates (500ms delay)
   - Shows form exactly as end users will see it
   - Includes form header, instructions, and footer

4. **Form Template Library**
   - Pre-built templates for common use cases
   - Template categories (General, HR, IT, Finance, etc.)
   - Template selection modal on new form creation
   - Usage tracking for templates
   - System templates (cannot be deleted)
   - Default templates included:
     - Contact Form
     - Equipment Request
     - Feedback Survey

5. **Form Cloning**
   - Clone existing forms with all fields and settings
   - Clone button in admin list view
   - Clone button in form builder
   - Automatic slug generation for clones
   - Preserves all field properties and permissions

6. **Django Admin Integration**
   - Seamless integration with Django Admin
   - "Visual Builder" link in form list
   - Custom change form template
   - Preserves admin permissions and security
   - CSRF protection on all API endpoints

### 🎨 User Interface

**Three-Panel Layout:**
- **Left Panel (Field Palette)**: Draggable field types organized by category
- **Center Panel (Canvas)**: Form building area with field management
- **Right Panel (Live Preview)**: Real-time form preview

**Design Features:**
- Modern gradient header
- Bootstrap 5 styling
- Bootstrap Icons
- Responsive layout
- Smooth animations and transitions
- Loading states and spinners
- Error handling with user-friendly messages

## Architecture

### Backend (Django)

**Views** (`django_forms_workflows/form_builder_views.py`):
- `form_builder_view()` - Main form builder page
- `form_builder_load()` - Load existing form data
- `form_builder_save()` - Save form changes
- `form_builder_preview()` - Generate live preview
- `form_builder_templates()` - List available templates
- `form_builder_load_template()` - Load template data
- `form_builder_clone()` - Clone existing form

**Models** (`django_forms_workflows/models.py`):
- `FormTemplate` - Stores pre-built form templates
  - Fields: name, slug, description, category, template_data, preview_url
  - Status: is_active, is_system
  - Tracking: usage_count, created_at, updated_at, created_by

**Admin** (`django_forms_workflows/admin.py`):
- Custom URLs for form builder endpoints
- `FormDefinitionAdmin` with visual builder link
- `FormTemplateAdmin` for managing templates
- Clone action for bulk cloning
- Custom changelist template with clone buttons

### Frontend (JavaScript)

**Main Class** (`form-builder.js`):
```javascript
class FormBuilder {
    constructor(config)
    init()
    setupFieldPalette()
    setupCanvas()
    setupEventListeners()
    addField(fieldType)
    editField(index)
    saveField()
    deleteField(index)
    renderCanvas()
    updatePreview()
    generatePreview()
    loadForm()
    saveForm()
    showTemplateSelection()
    loadTemplate(templateId)
}
```

**Dependencies:**
- Bootstrap 5 (CSS framework)
- Bootstrap Icons (icon library)
- SortableJS (drag-and-drop)
- Alpine.js (prepared for future enhancements)

## API Endpoints

All endpoints require staff member authentication and CSRF tokens.

### GET /admin/django_forms_workflows/formdefinition/builder/new/
Create new form in visual builder

### GET /admin/django_forms_workflows/formdefinition/builder/<form_id>/
Edit existing form in visual builder

### GET /admin/django_forms_workflows/formdefinition/builder/api/load/<form_id>/
Load form data as JSON
**Response:**
```json
{
    "success": true,
    "id": 1,
    "name": "Form Name",
    "slug": "form-slug",
    "description": "...",
    "instructions": "...",
    "is_active": true,
    "requires_login": true,
    "allow_save_draft": true,
    "allow_withdrawal": true,
    "fields": [...]
}
```

### POST /admin/django_forms_workflows/formdefinition/builder/api/save/
Save form changes
**Request:**
```json
{
    "id": 1,  // null for new forms
    "name": "Form Name",
    "slug": "form-slug",
    "fields": [...]
}
```

### POST /admin/django_forms_workflows/formdefinition/builder/api/preview/
Generate live preview
**Request:**
```json
{
    "name": "Form Name",
    "fields": [...]
}
```
**Response:**
```json
{
    "success": true,
    "html": "<div>...</div>"
}
```

### GET /admin/django_forms_workflows/formdefinition/builder/api/templates/
List available templates
**Response:**
```json
{
    "success": true,
    "templates": [
        {
            "id": 1,
            "name": "Contact Form",
            "slug": "contact-form",
            "description": "...",
            "category": "general",
            "category_display": "General",
            "preview_url": "",
            "usage_count": 5
        }
    ]
}
```

### GET /admin/django_forms_workflows/formdefinition/builder/api/templates/<template_id>/
Load template data
**Response:**
```json
{
    "success": true,
    "template_data": {
        "name": "Contact Form",
        "fields": [...]
    }
}
```

### POST /admin/django_forms_workflows/formdefinition/builder/api/clone/<form_id>/
Clone existing form
**Response:**
```json
{
    "success": true,
    "form_id": 2,
    "message": "Form cloned successfully as \"Form Name (Copy)\""
}
```

## Usage

### Creating a New Form

1. Navigate to Django Admin → Form Definitions
2. Click "Add Form Definition" or use the "Visual Builder" button
3. Choose a template or start with a blank form
4. Drag fields from the palette to the canvas
5. Click the pencil icon to configure field properties
6. See live preview on the right panel
7. Click "Save Form" when done

### Editing an Existing Form

1. Navigate to Django Admin → Form Definitions
2. Click the "Visual Builder" link for the form you want to edit
3. Make changes to fields, settings, or order
4. Preview updates automatically
5. Click "Save Form" to persist changes

### Cloning a Form

**Option 1: From List View**
1. Navigate to Django Admin → Form Definitions
2. Click the "Clone" button next to the form
3. Confirm the clone operation
4. Edit the cloned form

**Option 2: From Form Builder**
1. Open a form in the visual builder
2. Click "Clone Form" button
3. Confirm the clone operation
4. Redirected to edit the cloned form

**Option 3: Bulk Clone**
1. Navigate to Django Admin → Form Definitions
2. Select multiple forms using checkboxes
3. Choose "Clone selected forms" from the action dropdown
4. Click "Go"

### Managing Templates

1. Navigate to Django Admin → Form Templates
2. View existing templates
3. Create new templates by saving form configurations
4. Edit template metadata (name, description, category)
5. Mark templates as active/inactive
6. System templates cannot be deleted

## Default Templates

### Contact Form
- Full Name (text, required)
- Email Address (email, required)
- Subject (text, required)
- Message (textarea, required)

### Equipment Request
- Equipment Type (select, required)
- Quantity (number, required)
- Business Justification (textarea, required)
- Urgency (radio, required)

### Feedback Survey
- Overall Satisfaction (radio, required)
- Additional Comments (textarea, optional)

## Management Commands

### create_default_templates
Creates the default form templates.

```bash
python manage.py create_default_templates
```

## Files Modified/Created

### Created Files
- `django_forms_workflows/form_builder_views.py` - Backend views
- `django_forms_workflows/static/django_forms_workflows/js/form-builder.js` - Frontend JavaScript
- `django_forms_workflows/templates/admin/django_forms_workflows/form_builder.html` - Main template
- `django_forms_workflows/templates/admin/django_forms_workflows/formdef_change_form.html` - Admin change form
- `django_forms_workflows/templates/admin/django_forms_workflows/formdefinition/change_list.html` - Admin list template
- `django_forms_workflows/management/commands/create_default_templates.py` - Management command
- `django_forms_workflows/migrations/0004_formtemplate.py` - Database migration

### Modified Files
- `django_forms_workflows/models.py` - Added FormTemplate model
- `django_forms_workflows/admin.py` - Added form builder URLs and FormTemplateAdmin

## Testing

1. **Create a new form**
   - Verify template selection modal appears
   - Test selecting a template
   - Test starting with blank form
   - Verify fields load correctly

2. **Edit existing form**
   - Verify form loads with all fields
   - Test adding new fields
   - Test editing field properties
   - Test deleting fields
   - Test reordering fields

3. **Live preview**
   - Verify preview updates when fields change
   - Verify preview shows correct styling
   - Verify preview handles empty forms

4. **Clone form**
   - Test cloning from list view
   - Test cloning from form builder
   - Test bulk clone action
   - Verify all fields and settings are copied

5. **Save form**
   - Test saving new form
   - Test saving changes to existing form
   - Verify redirect after save
   - Verify data persists correctly

## Future Enhancements

- Undo/redo functionality
- Form versioning UI
- Advanced validation builder
- Custom field templates
- Form import/export
- Collaborative editing
- Field groups/sections
- Conditional logic builder
- Integration with workflow designer

## Troubleshooting

### Preview not showing
- Check browser console for JavaScript errors
- Verify CSRF token is present
- Check server logs for API errors
- Ensure form has at least one field

### Fields not saving
- Verify CSRF token
- Check field validation
- Review server logs
- Ensure required fields are filled

### Template selection not appearing
- Verify templates exist in database
- Run `create_default_templates` command
- Check template `is_active` status

### Clone button not working
- Verify CSRF token
- Check user permissions
- Review server logs for errors

