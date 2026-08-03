import { afterEach, describe, expect, it, vi } from 'vitest';
import { FormBuilder } from '../../django_forms_workflows/static/django_forms_workflows/js/form-builder.js';
import { createBuilderStore } from '../../django_forms_workflows/static/django_forms_workflows/js/form-builder-store.js';

function createInstance({ fields, formSteps }) {
  const instance = Object.create(FormBuilder.prototype);
  instance.store = createBuilderStore({ fields, formSteps });
  instance.renderSingleStep = vi.fn();
  instance.updatePreview = vi.fn();
  instance.undoStack = [];
  instance.redoStack = [];
  instance.maxUndoSteps = 50;
  return instance;
}

// The drag-drop library has already moved the dragged node into the target
// step's canvas by the time this handler runs; handleFieldMovedToStep reads
// its position back out of the DOM.
function buildFieldElement(fieldIndex) {
  const el = document.createElement('div');
  el.className = 'field-item';
  el.dataset.fieldIndex = String(fieldIndex);
  return el;
}

afterEach(() => {
  document.body.innerHTML = '';
});

describe('FormBuilder#handleFieldMovedToStep', () => {
  it('moves the field name out of its source step and into the target step at the dropped DOM position', () => {
    const instance = createInstance({
      fields: [{ field_name: 'a' }, { field_name: 'b' }, { field_name: 'c' }],
      formSteps: [{ title: 'Step 1', fields: ['a', 'b'] }, { title: 'Step 2', fields: ['c'] }],
    });
    document.body.innerHTML = '<div id="step-canvas-1"></div>';
    const canvas = document.getElementById('step-canvas-1');
    const cEl = buildFieldElement(2);
    const aEl = buildFieldElement(0);
    canvas.appendChild(cEl);
    canvas.appendChild(aEl); // 'a' dropped after 'c' in step 2

    instance.handleFieldMovedToStep(aEl, 1);

    expect(instance.formSteps[0].fields).toEqual(['b']);
    expect(instance.formSteps[1].fields).toEqual(['c', 'a']);
  });

  it('reorders this.fields to match the new cross-step order (regression: preview used to keep the stale array order)', () => {
    const instance = createInstance({
      fields: [{ field_name: 'a' }, { field_name: 'b' }, { field_name: 'c' }],
      formSteps: [{ title: 'Step 1', fields: ['a', 'b'] }, { title: 'Step 2', fields: ['c'] }],
    });
    document.body.innerHTML = '<div id="step-canvas-1"></div>';
    const canvas = document.getElementById('step-canvas-1');
    const cEl = buildFieldElement(2);
    const aEl = buildFieldElement(0);
    canvas.appendChild(cEl);
    canvas.appendChild(aEl);

    instance.handleFieldMovedToStep(aEl, 1);

    expect(instance.fields.map(f => f.field_name)).toEqual(['b', 'c', 'a']);
  });

  it('does nothing when the dragged element has no matching field', () => {
    const instance = createInstance({
      fields: [{ field_name: 'a' }],
      formSteps: [{ title: 'Step 1', fields: ['a'] }],
    });
    const orphanEl = buildFieldElement(99);

    instance.handleFieldMovedToStep(orphanEl, 0);

    expect(instance.formSteps[0].fields).toEqual(['a']);
    expect(instance.renderSingleStep).not.toHaveBeenCalled();
  });

  it('pushes an undo snapshot before moving the field, so Ctrl+Z can restore the pre-move step assignment', () => {
    const instance = createInstance({
      fields: [{ field_name: 'a' }, { field_name: 'b' }, { field_name: 'c' }],
      formSteps: [{ title: 'Step 1', fields: ['a', 'b'] }, { title: 'Step 2', fields: ['c'] }],
    });
    document.body.innerHTML = '<div id="step-canvas-1"></div>';
    const canvas = document.getElementById('step-canvas-1');
    const cEl = buildFieldElement(2);
    const aEl = buildFieldElement(0);
    canvas.appendChild(cEl);
    canvas.appendChild(aEl);

    instance.handleFieldMovedToStep(aEl, 1);

    expect(instance.undoStack).toHaveLength(1);
    expect(JSON.parse(instance.undoStack[0])).toEqual({
      fields: [{ field_name: 'a' }, { field_name: 'b' }, { field_name: 'c' }],
      formSteps: [{ title: 'Step 1', fields: ['a', 'b'] }, { title: 'Step 2', fields: ['c'] }],
    });
  });

  it('does not push an undo snapshot when the dragged element has no matching field', () => {
    const instance = createInstance({
      fields: [{ field_name: 'a' }],
      formSteps: [{ title: 'Step 1', fields: ['a'] }],
    });
    const orphanEl = buildFieldElement(99);

    instance.handleFieldMovedToStep(orphanEl, 0);

    expect(instance.undoStack).toHaveLength(0);
  });
});
