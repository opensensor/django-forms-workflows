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
});
