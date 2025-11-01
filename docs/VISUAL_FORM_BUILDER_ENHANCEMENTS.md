# Visual Form Builder Enhancements

## Overview

The visual form builder has been enhanced to support configuring all client-side features through an intuitive UI. Administrators can now configure conditional logic, validation rules, field dependencies, multi-step forms, and auto-save settings without writing any JSON or code.

---

## New Features

### 1. Tabbed Field Properties Modal

The field properties modal now uses tabs to organize settings:

- **Basic** - Standard field properties (label, name, type, width, etc.)
- **Conditional Logic** - Configure show/hide/require rules
- **Validation** - Add real-time validation rules
- **Dependencies** - Configure cascade updates

**Modal Size:** Upgraded to `modal-xl` for better visibility

---

### 2. Conditional Logic Builder

**Location:** Field Properties → Conditional Logic tab

**Features:**
- Toggle to enable/disable conditional logic
- Visual condition builder with:
  - Logical operator selector (AND/OR)
  - Action selector (show, hide, require, unrequire, enable, disable)
  - Multiple conditions with field, operator, and value
  - Add/remove condition rows
- JSON preview for advanced users
- Real-time UI updates

**Supported Operators:**
- equals
- not_equals
- contains
- not_contains
- greater_than
- less_than
- is_empty
- is_not_empty

**Example Use Case:**
```
Show "Manager Approval" field when:
  - Priority equals "high" OR
  - Estimated Cost greater than "1000"
```

---

### 3. Validation Rules Builder

**Location:** Field Properties → Validation tab

**Features:**
- Add multiple validation rules per field
- Visual rule builder with:
  - Validation type selector
  - Value input (for min/max/pattern rules)
  - Custom error message
  - Add/remove rule rows
- JSON preview for advanced users

**Supported Validation Types:**
- required
- email
- url
- min (minimum length)
- max (maximum length)
- pattern (regex)
- min_value (minimum numeric value)
- max_value (maximum numeric value)

**Example Use Case:**
```
Equipment ID field:
  - Type: pattern
  - Value: ^[A-Z]{2}\d{4}$
  - Message: "Format must be 2 letters + 4 digits (e.g., EQ1234)"
```

---

### 4. Field Dependencies Builder

**Location:** Field Properties → Dependencies tab

**Features:**
- Configure cascade updates
- Visual dependency builder with:
  - Source field selector
  - API endpoint input
  - Add/remove dependency rows
- JSON preview for advanced users

**Example Use Case:**
```
State field depends on Country field:
  - Source Field: country
  - API Endpoint: /api/get-states/
  
When user selects a country, the state dropdown updates with states for that country.
```

---

### 5. Multi-Step Form Configuration

**Location:** Form Settings → Client-Side Enhancements section

**Features:**
- Enable/disable multi-step forms
- "Configure Steps" button opens modal
- Visual step builder with:
  - Step title input
  - Field checkboxes for each step
  - Add/remove steps
  - Drag-and-drop reordering (future enhancement)
- Automatic step numbering

**Example Configuration:**
```
Step 1: Equipment Information
  - Equipment Type
  - Equipment ID
  - Issue Description

Step 2: Cost & Priority
  - Estimated Cost
  - Priority
  - Manager Approval Required
```

---

### 6. Auto-Save Configuration

**Location:** Form Settings → Client-Side Enhancements section

**Features:**
- Enable/disable auto-save checkbox
- Auto-save interval input (10-300 seconds)
- Default: Enabled, 30 seconds

---

## User Interface

### Form Settings Section

Added new "Client-Side Enhancements" section with:

```
┌─────────────────────────────────────────────────────────┐
│ ⚡ Client-Side Enhancements                             │
├─────────────────────────────────────────────────────────┤
│ ☑ Enable Auto-Save    [30] seconds                     │
│ ☐ Enable Multi-Step   [Configure Steps]                │
└─────────────────────────────────────────────────────────┘
```

### Field Properties Modal

```
┌─────────────────────────────────────────────────────────┐
│ Field Properties                                    [X] │
├─────────────────────────────────────────────────────────┤
│ [Basic] [Conditional Logic] [Validation] [Dependencies]│
├─────────────────────────────────────────────────────────┤
│                                                         │
│ (Tab content appears here)                             │
│                                                         │
├─────────────────────────────────────────────────────────┤
│                          [Cancel] [Save Field]          │
└─────────────────────────────────────────────────────────┘
```

---

## Data Flow

### Saving Field Properties

1. User configures settings in UI
2. JavaScript collects data from form inputs
3. Data is structured into JSON format
4. JSON is saved to field properties:
   - `conditional_rules`
   - `validation_rules`
   - `field_dependencies`
5. Form is saved to database
6. Configuration is loaded by form-enhancements.js on form submission page

### Saving Form Settings

1. User configures multi-step and auto-save settings
2. JavaScript collects data from form inputs
3. Data is saved to form definition:
   - `enable_auto_save`
   - `auto_save_interval`
   - `enable_multi_step`
   - `form_steps`
4. Form is saved to database
5. Configuration is loaded by DynamicForm.get_enhancements_config()

---

## Technical Implementation

### JavaScript Methods Added

**Conditional Logic:**
- `buildConditionalLogicTab(field)` - Renders conditional logic tab
- `initializeConditionsList(conditions)` - Populates condition rows
- `addConditionRow(condition, index)` - Adds a condition row

**Validation:**
- `buildValidationTab(field)` - Renders validation tab
- `initializeValidationRulesList(rules)` - Populates validation rows
- `addValidationRuleRow(rule, index)` - Adds a validation row

**Dependencies:**
- `buildDependenciesTab(field)` - Renders dependencies tab
- `initializeDependenciesList(dependencies)` - Populates dependency rows
- `addDependencyRow(dependency, index)` - Adds a dependency row

**Multi-Step:**
- `showMultiStepConfig()` - Opens multi-step configuration modal
- `addStepRow(step, index)` - Adds a step configuration row
- `saveMultiStepConfig()` - Saves step configuration

**Updated Methods:**
- `buildPropertyForm(field)` - Now returns tabbed interface
- `saveFieldProperties()` - Saves all new field properties
- `saveForm()` - Saves form-level enhancement settings
- `loadForm()` - Loads form-level enhancement settings

---

## Testing Guide

### Test Conditional Logic

1. Open visual form builder
2. Add a "Select" field for "Priority" with choices: low, medium, high
3. Add a "Checkbox" field for "Manager Approval Required"
4. Edit "Manager Approval Required" field
5. Go to "Conditional Logic" tab
6. Enable conditional logic
7. Set operator to "AND"
8. Set action to "require"
9. Add condition: Priority equals high
10. Save field
11. Save form
12. Test form submission - verify field is required when priority is high

### Test Validation Rules

1. Open visual form builder
2. Add a "Text" field for "Equipment ID"
3. Edit field
4. Go to "Validation" tab
5. Add validation rule:
   - Type: pattern
   - Value: ^[A-Z]{2}\d{4}$
   - Message: "Format: 2 letters + 4 digits"
6. Save field
7. Save form
8. Test form submission - verify validation works

### Test Multi-Step Forms

1. Open visual form builder
2. Add several fields
3. In form settings, enable "Multi-Step"
4. Click "Configure Steps"
5. Add Step 1: "Basic Info" with first 3 fields
6. Add Step 2: "Details" with remaining fields
7. Save steps
8. Save form
9. Test form submission - verify step navigation works

### Test Auto-Save

1. Open visual form builder
2. In form settings, verify "Enable Auto-Save" is checked
3. Set interval to 30 seconds
4. Save form
5. Test form submission - fill out form and wait 30 seconds
6. Verify "Saved" indicator appears

---

## Browser Compatibility

- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+

---

## Known Limitations

1. **No drag-and-drop for steps** - Steps must be added in order
2. **No visual preview of conditions** - Must test on actual form
3. **JSON editing required for complex rules** - Some advanced configurations require JSON editing
4. **No validation of API endpoints** - Dependency API endpoints are not validated

---

## Future Enhancements

1. **Visual condition preview** - Show/hide fields in builder based on conditions
2. **Drag-and-drop step reordering** - Reorder steps visually
3. **API endpoint validation** - Test API endpoints before saving
4. **Condition templates** - Pre-built condition patterns
5. **Validation rule templates** - Common validation patterns
6. **Import/Export** - Export field configurations as JSON
7. **Bulk operations** - Apply same rules to multiple fields
8. **Undo/Redo** - Undo changes in builder

---

## Troubleshooting

### Conditional logic not working

- Check that field names match exactly
- Verify operator is appropriate for field type
- Check browser console for JavaScript errors
- Verify form-enhancements.js is loaded

### Validation not triggering

- Check that validation type matches field type
- Verify error message is set
- Check browser console for errors
- Verify debounce delay (500ms)

### Multi-step not showing

- Verify "Enable Multi-Step" is checked
- Verify steps are configured with fields
- Check that form_steps is saved to database
- Verify form-enhancements.js is loaded

### Auto-save not working

- Verify "Enable Auto-Save" is checked
- Check auto-save interval is valid (10-300)
- Verify CSRF token is present
- Check browser console for AJAX errors
- Verify auto-save endpoint is accessible

---

## Summary

The visual form builder now provides a complete UI for configuring all client-side enhancements:

✅ Conditional logic with visual builder
✅ Validation rules with visual builder  
✅ Field dependencies with visual builder
✅ Multi-step form configuration
✅ Auto-save configuration
✅ JSON preview for advanced users
✅ Backward compatible with existing forms

**No code required!** Administrators can configure sophisticated form behavior entirely through the UI.

