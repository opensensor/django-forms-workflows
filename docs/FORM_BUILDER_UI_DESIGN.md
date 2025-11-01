# Visual Form Builder UI - Design Document

## Overview

This document outlines the design and implementation plan for the Visual Form Builder UI, a Phase 2 priority feature for django-forms-workflows. The form builder will provide a drag-and-drop interface for creating and editing forms without requiring code changes.

## Goals

1. **Intuitive UX** - Business users can create forms without technical knowledge
2. **Live Preview** - See the form as it's being built in real-time
3. **Full Feature Support** - Support all existing form field types and configurations
4. **Django Admin Integration** - Seamless integration with existing admin interface
5. **Progressive Enhancement** - Works without JavaScript (falls back to current inline editing)
6. **No Heavy Dependencies** - Use lightweight, vanilla JS libraries where possible

## Architecture

### Technology Stack

**Frontend:**
- **SortableJS** (13KB gzipped) - Lightweight drag-and-drop library
  - No jQuery dependency
  - Touch-friendly
  - Accessible
  - Well-maintained
- **Alpine.js** (15KB gzipped) - Lightweight reactive framework
  - Similar to Vue.js but much smaller
  - Perfect for Django templates
  - No build step required
- **Bootstrap 5** (already in use) - UI components
- **Bootstrap Icons** (already in use) - Icons

**Backend:**
- Django views and templates
- JSON API endpoints for AJAX operations
- Existing models (FormDefinition, FormField, PrefillSource)

**Why not React/Vue?**
- Adds significant complexity and build tooling
- Requires separate frontend build pipeline
- Harder to integrate with Django Admin
- Overkill for this use case
- Alpine.js provides 80% of the benefits with 20% of the complexity

### Component Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Form Builder Page                         │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────────┐  ┌──────────────────┐  ┌────────────┐ │
│  │                  │  │                  │  │            │ │
│  │  Field Palette   │  │  Canvas Area     │  │  Preview   │ │
│  │                  │  │                  │  │  Panel     │ │
│  │  - Text Input    │  │  ┌────────────┐  │  │            │ │
│  │  - Email         │  │  │ Field 1    │  │  │  [Live     │ │
│  │  - Select        │  │  │ [Edit] [×] │  │  │   Form     │ │
│  │  - Textarea      │  │  └────────────┘  │  │   Preview] │ │
│  │  - Date          │  │  ┌────────────┐  │  │            │ │
│  │  - File Upload   │  │  │ Field 2    │  │  │            │ │
│  │  - Section       │  │  │ [Edit] [×] │  │  │            │ │
│  │  - ...           │  │  └────────────┘  │  │            │ │
│  │                  │  │                  │  │            │ │
│  │  [+ Custom]      │  │  [+ Add Field]   │  │            │ │
│  │                  │  │                  │  │            │ │
│  └──────────────────┘  └──────────────────┘  └────────────┘ │
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │              Property Panel (Modal/Sidebar)             │ │
│  ├─────────────────────────────────────────────────────────┤ │
│  │  Field Label: [________________]                        │ │
│  │  Field Name:  [________________]                        │ │
│  │  Field Type:  [Text Input ▼]                            │ │
│  │  Required:    [✓]                                       │ │
│  │  Help Text:   [________________]                        │ │
│  │  Placeholder: [________________]                        │ │
│  │  Width:       [Full ▼]                                  │ │
│  │  Prefill:     [Select Source ▼]                         │ │
│  │  Validation:  [Expand ▼]                                │ │
│  │  Conditional: [Expand ▼]                                │ │
│  │                                                          │ │
│  │  [Cancel]  [Save Field]                                 │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

## User Flows

### 1. Creating a New Form

```
1. Admin → Form Definitions → Add Form Definition
2. Fill in basic info (name, slug, description)
3. Click "Open Form Builder" button
4. Drag fields from palette to canvas
5. Click field to edit properties
6. See live preview on right
7. Save form
```

### 2. Editing an Existing Form

```
1. Admin → Form Definitions → Select form
2. Click "Edit in Form Builder" button
3. Existing fields shown in canvas
4. Drag to reorder, click to edit, × to delete
5. Add new fields from palette
6. Save changes
```

### 3. Using a Template

```
1. Admin → Form Definitions → Add Form Definition
2. Click "Start from Template"
3. Select template (Contact Form, Request Form, Survey, etc.)
4. Template fields loaded into canvas
5. Customize as needed
6. Save form
```

## Implementation Plan

### Phase 1: Core Builder (MVP)

**Models:**
- No new models needed initially
- Use existing FormDefinition and FormField models

**Views:**
- `form_builder_view(request, form_id=None)` - Main builder page
- `form_builder_api_save(request)` - AJAX endpoint to save form
- `form_builder_api_preview(request)` - AJAX endpoint for preview

**Templates:**
- `admin/django_forms_workflows/formbuilder.html` - Main builder page
- `admin/django_forms_workflows/formbuilder_field_palette.html` - Field palette partial
- `admin/django_forms_workflows/formbuilder_canvas.html` - Canvas partial
- `admin/django_forms_workflows/formbuilder_preview.html` - Preview partial
- `admin/django_forms_workflows/formbuilder_property_panel.html` - Property panel modal

**JavaScript:**
- `form-builder.js` - Main builder logic
  - Initialize SortableJS on canvas
  - Handle drag-and-drop from palette
  - Field property editing
  - AJAX save/load
  - Live preview updates

**CSS:**
- `form-builder.css` - Builder-specific styles

### Phase 2: Templates & Cloning

**Models:**
- `FormTemplate` model for pre-built form templates
  ```python
  class FormTemplate(models.Model):
      name = models.CharField(max_length=200)
      description = models.TextField()
      category = models.CharField(max_length=100)  # Contact, Request, Survey, etc.
      icon = models.CharField(max_length=50)  # Bootstrap icon name
      template_data = models.JSONField()  # Field definitions
      is_active = models.BooleanField(default=True)
      created_at = models.DateTimeField(auto_now_add=True)
  ```

**Features:**
- Template library UI
- Clone form functionality
- Export/import form definitions

### Phase 3: Advanced Features

- Conditional field visibility (client-side preview)
- Field validation preview
- Undo/redo functionality
- Keyboard shortcuts
- Accessibility improvements
- Mobile-responsive builder

## Data Structure

### Form Builder State (JavaScript)

```javascript
{
  formId: 123,
  formName: "Equipment Request",
  formSlug: "equipment-request",
  fields: [
    {
      id: "field_1",  // Temporary ID for new fields
      order: 1,
      field_label: "Equipment Type",
      field_name: "equipment_type",
      field_type: "select",
      required: true,
      help_text: "Select the type of equipment",
      placeholder: "",
      width: "full",
      choices: "Laptop\nDesktop\nMonitor\nKeyboard",
      prefill_source: null,
      validation: {
        min_value: null,
        max_value: null,
        min_length: null,
        max_length: null,
        regex_validation: "",
        regex_error_message: ""
      },
      conditional: {
        show_if_field: null,
        show_if_value: null
      }
    },
    // ... more fields
  ]
}
```

### API Endpoints

**GET `/admin/forms-workflows/builder/<form_id>/`**
- Returns form builder page

**GET `/admin/forms-workflows/builder/api/load/<form_id>/`**
- Returns form data as JSON

**POST `/admin/forms-workflows/builder/api/save/`**
- Saves form data
- Request body: form builder state JSON
- Response: success/error + saved form ID

**POST `/admin/forms-workflows/builder/api/preview/`**
- Returns HTML preview of form
- Request body: form builder state JSON
- Response: rendered form HTML

## Integration with Django Admin

### Option 1: Custom Admin View (Recommended)

Add a custom button to FormDefinitionAdmin that opens the builder in a new page:

```python
class FormDefinitionAdmin(admin.ModelAdmin):
    # ... existing config ...
    
    change_form_template = 'admin/django_forms_workflows/formdef_change_form.html'
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('<int:form_id>/builder/', 
                 self.admin_site.admin_view(form_builder_view),
                 name='formdef_builder'),
        ]
        return custom_urls + urls
```

### Option 2: Replace Inline (Advanced)

Replace the FormFieldInline with a custom widget that launches the builder.

**Recommendation:** Start with Option 1 for MVP, consider Option 2 later.

## Field Type Palette

### Basic Fields
- Text Input
- Email
- Number
- Textarea
- Select (Dropdown)
- Radio Buttons
- Checkboxes
- Checkbox (Single)

### Advanced Fields
- Date
- Time
- DateTime
- File Upload
- URL
- Phone Number
- Decimal/Currency

### Layout Elements
- Section Header
- HTML Block
- Divider

## Property Panel Configuration

### Basic Properties (Always Visible)
- Field Label
- Field Name (auto-generated from label, editable)
- Field Type
- Required checkbox
- Help Text
- Placeholder

### Advanced Properties (Collapsible Sections)

**Validation:**
- Min/Max Value (for numbers)
- Min/Max Length (for text)
- Regex Pattern
- Regex Error Message

**Choices & Defaults:**
- Choices (for select/radio/checkbox)
- Prefill Source (dropdown of available sources)
- Default Value

**Layout:**
- Width (Full, Half, Third)
- CSS Class

**Conditional Display:**
- Show if Field (dropdown of other fields)
- Show if Value

## Live Preview

The preview panel shows the form as it will appear to end users:
- Uses the same DynamicForm rendering logic
- Updates in real-time as fields are added/edited
- Shows validation states
- Responsive preview (desktop/tablet/mobile toggle)

## Accessibility

- Keyboard navigation support
- ARIA labels for drag-and-drop
- Screen reader announcements for field changes
- Focus management
- High contrast mode support

## Browser Support

- Chrome/Edge (latest 2 versions)
- Firefox (latest 2 versions)
- Safari (latest 2 versions)
- Mobile browsers (iOS Safari, Chrome Android)

## Performance Considerations

- Lazy load preview (debounced updates)
- Virtual scrolling for large field lists
- Efficient DOM updates (minimal re-renders)
- Optimistic UI updates
- Auto-save drafts to localStorage

## Security

- CSRF protection on all AJAX requests
- Permission checks (only staff/superusers)
- Input validation on backend
- XSS prevention (escape user input)
- Rate limiting on API endpoints

## Testing Strategy

### Unit Tests
- Field validation logic
- Form state management
- API endpoint responses

### Integration Tests
- Form creation flow
- Form editing flow
- Template usage flow
- Clone form flow

### E2E Tests (Playwright/Selenium)
- Drag-and-drop functionality
- Property panel editing
- Live preview updates
- Save and load forms

## Migration Path

### For Existing Users
1. Existing forms continue to work
2. Can edit via inline admin (current method)
3. Can switch to visual builder anytime
4. No data migration needed

### For New Users
1. Visual builder is default
2. Inline admin still available as fallback
3. Documentation shows both methods

## Future Enhancements

- Multi-language support
- Form analytics integration
- A/B testing support
- Custom field type plugins
- Collaborative editing (multiple users)
- Version history and rollback
- Form marketplace (share templates)

## Success Metrics

- Time to create a form (target: < 5 minutes for simple forms)
- User satisfaction (target: > 4/5 stars)
- Adoption rate (target: > 70% of new forms use builder)
- Error rate (target: < 5% of saves fail)
- Support tickets (target: < 10% increase)

## Timeline Estimate

- **Phase 1 (MVP):** 2-3 weeks
  - Week 1: Backend API + basic UI structure
  - Week 2: Drag-and-drop + property panel
  - Week 3: Live preview + testing
  
- **Phase 2 (Templates):** 1-2 weeks
  - Week 1: Template model + library UI
  - Week 2: Clone functionality + testing
  
- **Phase 3 (Advanced):** 2-3 weeks
  - Ongoing enhancements based on feedback

## Open Questions

1. Should we support importing forms from other tools (JotForm, Google Forms)?
2. Should we add a "test mode" to fill out the form before publishing?
3. Should we support form versioning in the builder UI?
4. Should we add collaboration features (comments, suggestions)?

## References

- [SortableJS Documentation](https://github.com/SortableJS/Sortable)
- [Alpine.js Documentation](https://alpinejs.dev/)
- [Django Admin Customization](https://docs.djangoproject.com/en/stable/ref/contrib/admin/)
- [Bootstrap 5 Documentation](https://getbootstrap.com/docs/5.3/)

