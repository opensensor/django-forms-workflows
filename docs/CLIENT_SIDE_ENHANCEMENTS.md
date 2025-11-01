# Client-Side Form Enhancements

This document describes the advanced client-side features available in Django Forms Workflows, including conditional logic, real-time validation, multi-step forms, auto-save, and field dependencies.

## Overview

The `FormEnhancements` JavaScript class provides a comprehensive set of client-side features that enhance the user experience without requiring page reloads. These features are automatically enabled based on your form configuration.

## Features

### 1. Advanced Conditional Logic

Control field visibility, requirements, and state based on complex conditions with AND/OR operators.

#### Configuration

Conditional rules can be configured in two ways:

**Simple Conditional Logic (Legacy)**
- Set `show_if_field` and `show_if_value` on a FormField
- The field will only show when the specified field has the specified value

**Advanced Conditional Logic**
- Set the `conditional_rules` JSON field on a FormField
- Supports complex AND/OR conditions with multiple dependencies

#### Rule Format

```json
{
  "operator": "AND",  // or "OR"
  "action": "show",   // show, hide, require, unrequire, enable, disable
  "conditions": [
    {
      "field": "field_name",
      "operator": "equals",  // equals, not_equals, contains, greater_than, less_than, in, not_in, is_empty, is_not_empty, is_true, is_false
      "value": "comparison_value"
    }
  ]
}
```

#### Supported Operators

- `equals` - Field value equals the comparison value
- `not_equals` - Field value does not equal the comparison value
- `contains` - Field value contains the comparison value (string)
- `not_contains` - Field value does not contain the comparison value
- `greater_than` - Field value is greater than comparison value (numeric)
- `less_than` - Field value is less than comparison value (numeric)
- `greater_or_equal` - Field value is greater than or equal to comparison value
- `less_or_equal` - Field value is less than or equal to comparison value
- `in` - Field value is in a list of values
- `not_in` - Field value is not in a list of values
- `is_empty` - Field value is empty
- `is_not_empty` - Field value is not empty
- `is_true` - Field value is truthy
- `is_false` - Field value is falsy

#### Supported Actions

- `show` - Show the field when conditions are met
- `hide` - Hide the field when conditions are met
- `require` - Make the field required when conditions are met
- `unrequire` - Make the field optional when conditions are met
- `enable` - Enable the field when conditions are met
- `disable` - Disable the field when conditions are met

#### Example: Show field if amount > 1000 OR priority is "high"

```json
{
  "operator": "OR",
  "action": "show",
  "conditions": [
    {
      "field": "amount",
      "operator": "greater_than",
      "value": "1000"
    },
    {
      "field": "priority",
      "operator": "equals",
      "value": "high"
    }
  ]
}
```

#### Example: Require field if type is "other" AND category is not empty

```json
{
  "operator": "AND",
  "action": "require",
  "conditions": [
    {
      "field": "type",
      "operator": "equals",
      "value": "other"
    },
    {
      "field": "category",
      "operator": "is_not_empty",
      "value": ""
    }
  ]
}
```

### 2. Dynamic Field Validation

Real-time validation with custom error messages that appear as users type.

#### Configuration

Validation rules are automatically generated from FormField configuration:
- `required` field
- `min_length` / `max_length`
- `min_value` / `max_value`
- `regex_validation` with custom error message
- Field type (email, url)

You can also add custom validation rules via the `validation_rules` JSON field:

```json
[
  {
    "type": "required",
    "message": "This field is required"
  },
  {
    "type": "email",
    "message": "Please enter a valid email address"
  },
  {
    "type": "min",
    "value": 5,
    "message": "Minimum 5 characters required"
  },
  {
    "type": "max",
    "value": 100,
    "message": "Maximum 100 characters allowed"
  },
  {
    "type": "pattern",
    "value": "^[A-Z]{2}\\d{4}$",
    "message": "Format must be: 2 letters followed by 4 digits"
  }
]
```

#### Supported Validation Types

- `required` - Field must have a value
- `email` - Must be a valid email address
- `url` - Must be a valid URL
- `min` - Minimum character length
- `max` - Maximum character length
- `min_value` - Minimum numeric value
- `max_value` - Maximum numeric value
- `pattern` - Must match a regular expression
- `custom` - Custom validator function (JavaScript only)

#### Features

- **Debounced validation** - Validation runs 500ms after user stops typing
- **Visual feedback** - Fields show green (valid) or red (invalid) borders
- **Inline error messages** - Error messages appear below the field
- **Non-blocking** - Validation happens in the background

### 3. Progressive Form Disclosure (Multi-Step Forms)

Break long forms into manageable steps with progress indicators.

#### Configuration

Enable multi-step forms on the FormDefinition:

```python
form_def.enable_multi_step = True
form_def.form_steps = [
    {
        "title": "Basic Information",
        "fields": ["name", "email", "phone"]
    },
    {
        "title": "Details",
        "fields": ["description", "category", "priority"]
    },
    {
        "title": "Review",
        "fields": ["terms_accepted"]
    }
]
```

Alternatively, add `step_number` to individual FormFields:

```python
field.step_number = 1  # This field appears in step 1
```

#### Features

- **Progress bar** - Visual indicator showing current step and overall progress
- **Step indicators** - Numbered circles showing all steps
- **Navigation buttons** - Previous/Next buttons for easy navigation
- **Step validation** - Users must complete required fields before proceeding
- **Responsive design** - Works on mobile and desktop

#### Auto-Detection

If you don't configure steps explicitly, the system can auto-detect them from `data-step` attributes in your HTML:

```html
<div data-step="1" data-step-title="Contact Info">
    <!-- Fields for step 1 -->
</div>
<div data-step="2" data-step-title="Preferences">
    <!-- Fields for step 2 -->
</div>
```

### 4. Auto-Save Drafts

Automatically save form progress to prevent data loss.

#### Configuration

Enable auto-save on the FormDefinition:

```python
form_def.enable_auto_save = True
form_def.auto_save_interval = 30  # seconds
```

#### Features

- **Periodic saving** - Automatically saves every N seconds (default: 30)
- **Change detection** - Only saves when form data has changed
- **Visual indicator** - Shows save status in bottom-right corner
- **Error handling** - Gracefully handles save failures
- **CSRF protection** - Automatically includes CSRF token

#### Status Indicators

- **Auto-save enabled** - Ready to save
- **Saving...** - Currently saving (yellow background)
- **Saved** - Successfully saved (green background)
- **Save failed** - Error occurred (red background)

#### API Endpoint

Auto-save sends POST requests to:
```
/forms/{slug}/auto-save/
```

The endpoint expects JSON data with form field values and returns:

```json
{
  "success": true,
  "message": "Draft saved",
  "draft_id": 123,
  "saved_at": "2025-11-01T12:34:56Z"
}
```

### 5. Field Dependencies (Cascade Updates)

Automatically update field options based on other field values.

#### Configuration

Add field dependencies via the `field_dependencies` JSON field:

```json
[
  {
    "sourceField": "country",
    "targetField": "state",
    "apiEndpoint": "/api/get-states/",
    "valueMapping": {
      "country_code": "country"
    }
  }
]
```

#### Custom Handler

For complex logic, you can provide a custom JavaScript handler:

```javascript
{
  sourceField: "category",
  targetField: "subcategory",
  handler: function(sourceValue, targetField, formEnhancements) {
    // Custom logic to update targetField based on sourceValue
    const options = getSubcategoriesFor(sourceValue);
    formEnhancements.updateFieldOptions(targetField, options);
  }
}
```

#### API Response Format

The API endpoint should return:

```json
{
  "success": true,
  "options": [
    {"value": "opt1", "label": "Option 1"},
    {"value": "opt2", "label": "Option 2"}
  ]
}
```

## Usage

### Automatic Initialization

The form enhancements are automatically initialized when you include the JavaScript file and configuration:

```html
{% load static %}
<script src="{% static 'django_forms_workflows/js/form-enhancements.js' %}"></script>
<script>
    const config = {{ form_enhancements_config|safe }};
    const formEnhancements = new FormEnhancements(formElement, config);
</script>
```

### Manual Initialization

You can also manually initialize the enhancements:

```javascript
const formElement = document.getElementById('my-form');
const formEnhancements = new FormEnhancements(formElement, {
    autoSaveEnabled: true,
    autoSaveInterval: 30000,
    autoSaveEndpoint: '/forms/my-form/auto-save/',
    multiStepEnabled: true,
    steps: [...],
    conditionalRules: [...],
    fieldDependencies: [...],
    validationRules: [...]
});
```

### Cleanup

To destroy the form enhancements and clean up resources:

```javascript
formEnhancements.destroy();
```

## Browser Compatibility

- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+

## Dependencies

- Bootstrap 5 (for styling)
- Bootstrap Icons (for icons)

## Performance Considerations

- **Debouncing** - Validation and auto-save are debounced to avoid excessive processing
- **Efficient DOM updates** - Only affected fields are updated when conditions change
- **Minimal re-renders** - Smart caching prevents unnecessary re-evaluation

## Troubleshooting

### Conditional logic not working

1. Check that field names match exactly (case-sensitive)
2. Verify the JSON format is valid
3. Check browser console for errors
4. Ensure the form has `data-form-enhancements="true"` attribute

### Auto-save not working

1. Verify `enable_auto_save` is True on FormDefinition
2. Check that the auto-save endpoint is accessible
3. Verify CSRF token is present
4. Check browser console for network errors

### Multi-step form not showing

1. Verify `enable_multi_step` is True on FormDefinition
2. Check that `form_steps` is properly configured
3. Ensure field names in steps match actual field names

### Validation not appearing

1. Check that validation rules are properly configured
2. Verify field names match
3. Check browser console for JavaScript errors
4. Ensure Bootstrap CSS is loaded for styling

## Examples

See the example project for working demonstrations of all features:

- `example_project/` - Complete working example
- Equipment Repair Request - Conditional logic based on amount
- Barn Maintenance Request - Multi-step form
- Harvest Report - Auto-save and validation

