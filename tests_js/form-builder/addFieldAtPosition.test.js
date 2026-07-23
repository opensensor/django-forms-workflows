import { describe, expect, it, vi } from 'vitest';
import { FormBuilder } from '../../django_forms_workflows/static/django_forms_workflows/js/form-builder.js';

// Build an instance without running the constructor to avoid calling init() ->
// setupFieldPalette()/setupCanvas()/setupEventListeners()
function createInstance(FormBuilder) {
  const instance = Object.create(FormBuilder.prototype);
  instance.fields = [];
  instance.fieldIdCounter = 1;
  instance.undoStack = [];
  instance.redoStack = [];
  instance.maxUndoSteps = 50;
  // stub out methods that call bootstrap.Modal
  instance.editField = vi.fn();
  instance.renderCanvas = vi.fn();
  instance.updatePreview = vi.fn();
  return instance;
}

describe('FormBuilder#addFieldAtPosition', () => {
  it('inserts correctly on an empty canvas, when SortableJS reports an out-of-range drop position', () => {
    const instance = createInstance(FormBuilder);

    // Empty canvas: SortableJS's reported evt.newIndex can be 1 here (it
    // counts the empty-canvas placeholder), even though there's nowhere
    // valid to insert but index 0.
    instance.addFieldAtPosition('text', 1);

    expect(instance.fields).toHaveLength(1);
    expect(instance.editField).toHaveBeenCalledWith(0, true);
  });

  it('inserts at the requested position when it is already in range', () => {
    const instance = createInstance(FormBuilder);
    instance.fields = [{ field_name: 'existing' }];

    instance.addFieldAtPosition('text', 0);

    expect(instance.fields).toHaveLength(2);
    expect(instance.fields[1].field_name).toBe('existing');
    expect(instance.editField).toHaveBeenCalledWith(0, true);
  });
});
