import { afterEach, describe, expect, it, vi } from 'vitest';
import { FormBuilder } from '../../django_forms_workflows/static/django_forms_workflows/js/form-builder.js';
import { createBuilderStore } from '../../django_forms_workflows/static/django_forms_workflows/js/form-builder-store.js';

// Regression coverage for a bug found after the this.fields/formSteps sync
// fix: reordering this.fields *after* rendering (or only re-rendering the
// touched step) left other steps' data-field-index attributes pointing at
// the wrong entries once this.fields' array order changed underneath them.
// A subsequent drag-reorder that trusted those stale indices corrupted
// formSteps/this.fields (duplicate/missing field names), which the backend
// preview endpoint then 500'd on.
function createInstance({ fields = [], formSteps = [] } = {}) {
  const instance = Object.create(FormBuilder.prototype);
  instance.store = createBuilderStore({ fields, formSteps });
  instance.fieldIdCounter = 1;
  instance.undoStack = [];
  instance.redoStack = [];
  instance.maxUndoSteps = 50;
  instance.fieldTypes = [{ type: 'text' }];
  instance.editField = vi.fn(); // don't actually open the property modal
  instance.updatePreview = vi.fn();
  return instance;
}

function setupStepCanvases(stepIndexes) {
  document.body.innerHTML = stepIndexes.map(i => `<div id="step-canvas-${i}"></div>`).join('');
}

afterEach(() => {
  document.body.innerHTML = '';
});

describe('multi-step field-index sync across steps', () => {
  it('keeps every rendered field-item across every step pointing at the right field after a cross-step add', () => {
    const instance = createInstance({
      fields: [{ field_name: 'a', field_label: 'A', field_type: 'text' }, { field_name: 'b', field_label: 'B', field_type: 'text' }],
      formSteps: [
        { title: 'Step 1', fields: ['a'] },
        { title: 'Step 2', fields: ['b'] },
      ],
    });
    setupStepCanvases([0, 1]);

    // Drop a new field into step 0 before 'a' - this pushes 'a' and 'b' one
    // slot later in the flattened this.fields array, including 'b' which
    // lives in a step this handler never explicitly re-renders by name.
    instance.handleFieldDroppedToStep('text', 0, 0);

    document.querySelectorAll('.field-item').forEach(el => {
      const idx = parseInt(el.dataset.fieldIndex);
      const field = instance.fields[idx];
      expect(field).toBeDefined();
      expect(el.querySelector('.field-label').textContent).toBe(field.field_label);
    });
  });

  it('does not corrupt formSteps/this.fields when a step is reordered right after a cross-step field-index shift', () => {
    const instance = createInstance({
      fields: [{ field_name: 'a', field_label: 'A', field_type: 'text' }, { field_name: 'b', field_label: 'B', field_type: 'text' }],
      formSteps: [
        { title: 'Step 1', fields: ['a'] },
        { title: 'Step 2', fields: ['b'] },
      ],
    });
    setupStepCanvases([0, 1]);

    instance.handleFieldDroppedToStep('text', 0, 0); // shifts every later index

    // Simulate the very next user action from the bug report: reordering
    // within step 0, which reads data-field-index back out of the DOM.
    instance.updateFieldOrderInStep(0);

    const allNames = instance.fields.map(f => f.field_name);
    expect(new Set(allNames).size).toBe(allNames.length); // no duplicates
    expect(allNames).toHaveLength(3); // no fields silently dropped
    expect(instance.formSteps[1].fields).toEqual(['b']); // step 2 untouched
  });
});
