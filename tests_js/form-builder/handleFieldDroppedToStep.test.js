import { describe, expect, it, vi } from 'vitest';
import { FormBuilder } from '../../django_forms_workflows/static/django_forms_workflows/js/form-builder.js';
import { createBuilderStore } from '../../django_forms_workflows/static/django_forms_workflows/js/form-builder-store.js';

// Build an instance without running the constructor to avoid calling init() ->
// setupFieldPalette()/setupCanvas()/setupEventListeners()
function createInstance() {
  const instance = Object.create(FormBuilder.prototype);
  instance.store = createBuilderStore({ formSteps: [{ title: 'Step 1', fields: [] }] });
  instance.fields = [];
  instance.fieldIdCounter = 1;
  instance.undoStack = [];
  instance.redoStack = [];
  instance.maxUndoSteps = 50;
  instance.fieldTypes = [{ type: 'text' }];
  instance.editField = vi.fn();
  instance.renderSingleStep = vi.fn();
  instance.updatePreview = vi.fn();
  return instance;
}

describe('FormBuilder#handleFieldDroppedToStep', () => {
  it('pushes an undo snapshot before adding the field', () => {
    const instance = createInstance();

    instance.handleFieldDroppedToStep('text', 0);

    expect(instance.undoStack).toHaveLength(1);
    expect(JSON.parse(instance.undoStack[0]).fields).toEqual([]);
  });

  it('adds the field to both this.fields and the target step', () => {
    const instance = createInstance();

    instance.handleFieldDroppedToStep('text', 0);

    expect(instance.fields).toHaveLength(1);
    expect(instance.formSteps[0].fields).toEqual([instance.fields[0].field_name]);
  });

  it('does nothing when the field type is unknown', () => {
    const instance = createInstance();

    instance.handleFieldDroppedToStep('bogus', 0);

    expect(instance.undoStack).toHaveLength(0);
    expect(instance.fields).toHaveLength(0);
  });

  it('reorders this.fields to match the step position when dropped before an existing field, not just appended', () => {
    const instance = createInstance();
    instance.fields = [{ field_name: 'existing' }];
    instance.formSteps[0].fields = ['existing'];

    // Drop at position 0 -> new field belongs before 'existing' in the step.
    instance.handleFieldDroppedToStep('text', 0, 0);

    expect(instance.formSteps[0].fields[0]).not.toBe('existing');
    expect(instance.fields.map(f => f.field_name)).toEqual(instance.formSteps[0].fields);
  });

  it('opens the property editor for the newly-added field even after this.fields gets reordered', () => {
    const instance = createInstance();
    instance.fields = [{ field_name: 'existing' }];
    instance.formSteps[0].fields = ['existing'];

    instance.handleFieldDroppedToStep('text', 0, 0);

    const newFieldIndex = instance.fields.findIndex(f => f.field_name !== 'existing');
    expect(instance.editField).toHaveBeenCalledWith(newFieldIndex, true);
  });
});
