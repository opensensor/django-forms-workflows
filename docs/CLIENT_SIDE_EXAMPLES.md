# Client-Side Enhancements - Examples

This document provides practical examples of using the client-side enhancements in Django Forms Workflows.

## Example 1: Conditional Field Visibility

**Scenario**: Show "Other Reason" text field only when "Reason" is set to "Other"

### Form Configuration

1. Create a form with two fields:
   - `reason` (select field with choices: "Maintenance", "Repair", "Upgrade", "Other")
   - `other_reason` (text field)

2. On the `other_reason` field, set the conditional logic:

**Simple approach (using show_if_field):**
```python
other_reason_field.show_if_field = "reason"
other_reason_field.show_if_value = "Other"
```

**Advanced approach (using conditional_rules):**
```python
other_reason_field.conditional_rules = {
    "operator": "AND",
    "action": "show",
    "conditions": [
        {
            "field": "reason",
            "operator": "equals",
            "value": "Other"
        }
    ]
}
```

### Result

- The "Other Reason" field is hidden by default
- When user selects "Other" from the Reason dropdown, the field appears
- When user selects any other option, the field disappears

## Example 2: Complex Conditional Logic with AND/OR

**Scenario**: Require manager approval field only if:
- Amount > $1000 OR
- Priority is "High"

### Form Configuration

```python
manager_approval_field.conditional_rules = {
    "operator": "OR",
    "action": "require",
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

### Result

- Manager approval field is optional by default
- Becomes required when amount exceeds $1000
- Also becomes required when priority is set to "high"
- Returns to optional when neither condition is met

## Example 3: Multi-Step Form

**Scenario**: Create a 3-step equipment request form

### Form Configuration

```python
from django_forms_workflows.models import FormDefinition

form_def = FormDefinition.objects.get(slug='equipment-request')
form_def.enable_multi_step = True
form_def.form_steps = [
    {
        "title": "Requestor Information",
        "fields": ["name", "email", "department", "phone"]
    },
    {
        "title": "Equipment Details",
        "fields": ["equipment_type", "model", "quantity", "justification"]
    },
    {
        "title": "Budget & Approval",
        "fields": ["estimated_cost", "budget_code", "manager_approval"]
    }
]
form_def.save()
```

### Result

- Form displays as 3 separate steps
- Progress bar shows "Step 1 of 3", "Step 2 of 3", etc.
- Step indicators show numbered circles for each step
- Previous/Next buttons for navigation
- Required fields must be completed before advancing
- Submit button only appears on final step

## Example 4: Real-Time Validation

**Scenario**: Validate email format and minimum length for description

### Form Configuration

Email field validation is automatic based on field type:
```python
email_field.field_type = "email"
email_field.required = True
```

For custom validation on description:
```python
description_field.min_length = 20
description_field.max_length = 500
description_field.regex_validation = r'^[A-Za-z0-9\s\.,!?-]+$'
description_field.regex_error_message = "Only letters, numbers, and basic punctuation allowed"
```

### Result

- Email field shows error if format is invalid (e.g., "test@" or "test.com")
- Description field shows error if less than 20 characters
- Description field shows error if more than 500 characters
- Description field shows error if contains special characters
- Validation happens 500ms after user stops typing
- Valid fields show green border, invalid fields show red border

## Example 5: Auto-Save Drafts

**Scenario**: Auto-save form every 30 seconds

### Form Configuration

```python
form_def.enable_auto_save = True
form_def.auto_save_interval = 30  # seconds
form_def.save()
```

### Result

- Form data is automatically saved every 30 seconds
- Save indicator appears in bottom-right corner
- Shows "Saving..." when saving
- Shows "Saved" when successful (green background)
- Shows "Save failed" if error occurs (red background)
- User can close browser and return to find their draft

## Example 6: Field Dependencies (Cascade Updates)

**Scenario**: Update "State" dropdown based on selected "Country"

### Form Configuration

```python
state_field.field_dependencies = [
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

### API Endpoint

Create a view to return states for a country:

```python
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

@require_http_methods(["GET"])
def get_states(request):
    country_code = request.GET.get('country_code')
    
    # Your logic to get states for the country
    states = get_states_for_country(country_code)
    
    return JsonResponse({
        "success": True,
        "options": [
            {"value": state.code, "label": state.name}
            for state in states
        ]
    })
```

### Result

- When user selects a country, the state dropdown updates automatically
- State options are fetched from the API
- Old state options are replaced with new ones
- Works with select, radio, and checkbox fields

## Example 7: Combined Features

**Scenario**: Complex form with all features enabled

### Form Configuration

```python
# Enable all features
form_def.enable_multi_step = True
form_def.enable_auto_save = True
form_def.auto_save_interval = 30

# Define steps
form_def.form_steps = [
    {
        "title": "Basic Info",
        "fields": ["name", "email", "phone"]
    },
    {
        "title": "Request Details",
        "fields": ["request_type", "description", "amount"]
    },
    {
        "title": "Additional Info",
        "fields": ["justification", "attachments"]
    }
]
form_def.save()

# Add conditional logic
justification_field = form_def.fields.get(field_name='justification')
justification_field.conditional_rules = {
    "operator": "OR",
    "action": "require",
    "conditions": [
        {
            "field": "amount",
            "operator": "greater_than",
            "value": "500"
        },
        {
            "field": "request_type",
            "operator": "equals",
            "value": "special"
        }
    ]
}
justification_field.save()

# Add validation
description_field = form_def.fields.get(field_name='description')
description_field.min_length = 50
description_field.max_length = 1000
description_field.save()
```

### Result

- Multi-step form with 3 steps and progress indicator
- Auto-saves every 30 seconds
- Justification field appears and becomes required when:
  - Amount > $500, OR
  - Request type is "special"
- Description validates length in real-time
- All features work together seamlessly

## Example 8: Custom JavaScript Handler

**Scenario**: Custom logic for updating subcategory based on category

### JavaScript Configuration

```javascript
// Add custom handler after form initialization
formEnhancements.options.fieldDependencies.push({
    sourceField: 'category',
    targetField: 'subcategory',
    handler: function(sourceValue, targetField, formEnhancements) {
        // Define subcategories for each category
        const subcategories = {
            'equipment': [
                {value: 'tools', label: 'Tools'},
                {value: 'machinery', label: 'Machinery'},
                {value: 'vehicles', label: 'Vehicles'}
            ],
            'supplies': [
                {value: 'office', label: 'Office Supplies'},
                {value: 'cleaning', label: 'Cleaning Supplies'},
                {value: 'safety', label: 'Safety Equipment'}
            ],
            'services': [
                {value: 'maintenance', label: 'Maintenance'},
                {value: 'consulting', label: 'Consulting'},
                {value: 'training', label: 'Training'}
            ]
        };
        
        // Get options for selected category
        const options = subcategories[sourceValue] || [];
        
        // Update the subcategory field
        formEnhancements.updateFieldOptions(targetField, options);
    }
});
```

### Result

- When user selects a category, subcategory options update immediately
- No API call needed - logic runs entirely in browser
- Fast and responsive
- Easy to customize for specific needs

## Testing the Features

### Using Django Shell

```python
python manage.py shell

from django_forms_workflows.models import FormDefinition, FormField

# Get your form
form_def = FormDefinition.objects.get(slug='your-form-slug')

# Enable features
form_def.enable_multi_step = True
form_def.enable_auto_save = True
form_def.save()

# Add conditional logic to a field
field = form_def.fields.get(field_name='your_field')
field.conditional_rules = {
    "operator": "AND",
    "action": "show",
    "conditions": [
        {"field": "other_field", "operator": "equals", "value": "some_value"}
    ]
}
field.save()

# Test the configuration
from django_forms_workflows.forms import DynamicForm
form = DynamicForm(form_definition=form_def)
config = form.get_enhancements_config()
print(config)
```

### Browser Console Testing

```javascript
// Check if form enhancements are loaded
console.log(window.formEnhancements);

// Manually trigger validation
const field = document.querySelector('[name="email"]');
formEnhancements.validateField(field);

// Manually trigger auto-save
formEnhancements.performAutoSave();

// Check current step (for multi-step forms)
console.log(formEnhancements.currentStep);

// Go to next step
formEnhancements.nextStep();

// Evaluate all conditions
formEnhancements.evaluateAllConditions();
```

## Best Practices

1. **Keep it simple** - Start with basic conditional logic before adding complex rules
2. **Test thoroughly** - Test all condition combinations
3. **Provide feedback** - Use validation messages to guide users
4. **Mobile-friendly** - Test on mobile devices
5. **Performance** - Avoid too many dependencies that trigger API calls
6. **Graceful degradation** - Form should work even if JavaScript fails
7. **Clear steps** - Keep multi-step forms to 3-5 steps maximum
8. **Save frequently** - Use reasonable auto-save intervals (20-60 seconds)

## Troubleshooting

### Conditional logic not working

```javascript
// Debug in browser console
console.log(formEnhancements.options.conditionalRules);
console.log(formEnhancements.fieldValues);
formEnhancements.evaluateAllConditions();
```

### Auto-save failing

```javascript
// Check endpoint
console.log(formEnhancements.options.autoSaveEndpoint);

// Manually trigger save
formEnhancements.performAutoSave().then(console.log).catch(console.error);
```

### Multi-step not showing

```javascript
// Check configuration
console.log(formEnhancements.options.multiStepEnabled);
console.log(formEnhancements.steps);
```

