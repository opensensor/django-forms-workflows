# Testing Multi-Step Forms

## Overview

This guide will help you test the multi-step form functionality that was just implemented.

---

## Changes Made

### 1. Form Layout Updates (`forms.py`)

All form fields are now wrapped in a `<div class="field-wrapper field-{fieldname}">` container. This allows the JavaScript to easily find and show/hide fields for multi-step forms.

### 2. Visual Form Builder UI Improvements

**Multi-Step Configuration Modal:**
- Upgraded to `modal-xl` for better visibility
- Added gradient header with primary color
- Improved step cards with:
  - Gradient headers (purple gradient)
  - Field checkboxes in a responsive grid (3 columns on large screens)
  - Field type labels under each field name
  - Live count of selected fields
  - Better spacing and visual hierarchy

**Form Settings Section:**
- Added "Client-Side Enhancements" section
- Auto-save toggle and interval input
- Multi-step toggle and configure button
- Configure button shows step count after configuration

### 3. JavaScript Enhancements

**Form Builder (`form-builder.js`):**
- Improved error handling with null checks
- Better validation when saving steps
- Success message shows step summary
- Field count badges update in real-time
- Warning if no fields exist when configuring steps

**Form Enhancements (`form-enhancements.js`):**
- Added console logging for debugging
- Updated field container selector to look for `.field-wrapper` first
- Better error messages when fields/containers not found

---

## Testing Steps

### Step 1: Configure Multi-Step Form in Visual Builder

1. **Open the visual form builder** (edit an existing form or create new)
2. **Add several fields** (at least 4-5 fields for testing)
   - Example: Date, Crop, Quantity (lbs), Notes, Priority
3. **Enable Multi-Step:**
   - Scroll to "Client-Side Enhancements" section
   - Check "Enable Multi-Step"
   - Click "Configure Steps" button
4. **Configure Steps:**
   - Click "Add Step" to create Step 1
   - Enter title: "Harvest Information"
   - Select fields: Date, Crop, Quantity (lbs)
   - Click "Add Step" to create Step 2
   - Enter title: "Additional Details"
   - Select fields: Notes, Priority
   - Click "Save Steps"
5. **Save the form**

### Step 2: Test Form Submission

1. **Navigate to the form submission page**
   - Go to Forms list
   - Click on the form you just configured
2. **Check browser console** (F12 → Console tab)
   - Look for messages like:
     ```
     Setting up multi-step form
     Using configured steps: [...]
     Creating multi-step form with 2 steps
     Showing step 1: {...}
     ```
3. **Verify multi-step UI:**
   - Progress bar should appear at top
   - Step indicators should show "1" and "2"
   - Only Step 1 fields should be visible
   - "Next" button should appear at bottom
4. **Test navigation:**
   - Fill out Step 1 fields
   - Click "Next"
   - Verify Step 2 fields appear
   - Verify Step 1 fields are hidden
   - Click "Previous"
   - Verify Step 1 fields reappear
5. **Test validation:**
   - Leave a required field empty in Step 1
   - Try to click "Next"
   - Verify validation error appears
   - Fill the field and proceed

### Step 3: Troubleshooting

If multi-step is not working:

1. **Check browser console for errors**
   - Look for JavaScript errors
   - Look for the debug messages we added

2. **Verify configuration is saved:**
   - Open browser DevTools → Console
   - Type: `window.formEnhancements.options`
   - Verify `multiStepEnabled: true`
   - Verify `steps` array has your configured steps

3. **Check field containers:**
   - In browser DevTools → Elements tab
   - Find a form field
   - Verify it's wrapped in `<div class="field-wrapper field-{name}">`
   - If not, you may need to hard refresh or restart the server

4. **Check field names match:**
   - In console, type: `window.formEnhancements.steps`
   - Verify field names in `fields` array match actual field names
   - Field names should match what you see in the form builder

5. **Common issues:**
   - **Hard refresh needed:** Press Ctrl+Shift+R (or Cmd+Shift+R on Mac)
   - **Server restart needed:** If you changed `forms.py`, restart Django server
   - **Field names mismatch:** Check that field names in step config match actual field names
   - **No field-wrapper class:** Make sure you're testing with a newly saved form

---

## Expected Console Output

When multi-step is working correctly, you should see:

```
Setting up multi-step form {multiStepEnabled: true, steps: Array(2), ...}
Using configured steps: [{title: "Harvest Information", fields: Array(3)}, ...]
Creating multi-step form with 2 steps
Showing step 1: {title: "Harvest Information", fields: Array(3)}
Showing field: date
Showing field: crop
Showing field: quantity_lbs
Hiding field: notes
Hiding field: priority
```

---

## Visual Improvements Summary

### Before
- Basic modal with simple list
- Plain checkboxes in a single column
- No visual feedback
- No field count
- Generic styling

### After
- Large modal (modal-xl) with gradient header
- Responsive 3-column grid for field selection
- Field type labels under each field
- Live count badge showing selected fields
- Beautiful gradient card headers (purple)
- Better spacing and typography
- Success message with step summary
- Configure button shows step count

---

## Next Steps

After confirming multi-step works:

1. **Test with more complex forms** (10+ fields, 3+ steps)
2. **Test with conditional logic** (fields that show/hide based on conditions)
3. **Test with validation rules** (required fields, patterns, etc.)
4. **Test auto-save** (verify drafts are saved between steps)
5. **Test on mobile devices** (responsive design)

---

## Known Limitations

1. **No drag-and-drop reordering** - Steps must be added in order
2. **No step preview in builder** - Must test on actual form
3. **Field reassignment** - If you move a field to a different step, you must reconfigure steps
4. **Section headers** - Section headers are not assigned to steps (they appear on all steps)

---

## Future Enhancements

1. **Visual step preview** in form builder
2. **Drag-and-drop step reordering**
3. **Step templates** (common step patterns)
4. **Conditional steps** (show/hide entire steps based on conditions)
5. **Step validation rules** (custom validation per step)
6. **Progress persistence** (remember which step user was on)
7. **Step animations** (smooth transitions between steps)

---

## Support

If you encounter issues:

1. Check browser console for errors
2. Verify configuration in DevTools
3. Hard refresh the page (Ctrl+Shift+R)
4. Restart Django server if needed
5. Check that field names match exactly
6. Verify field-wrapper classes exist

For debugging, you can access the FormEnhancements instance:
```javascript
// In browser console
window.formEnhancements.steps  // View configured steps
window.formEnhancements.currentStep  // Current step index
window.formEnhancements.showStep(0)  // Manually show step 1
```

