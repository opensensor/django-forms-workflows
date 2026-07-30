import { afterEach, describe, expect, it, vi } from 'vitest';
import { FormBuilder } from '../../django_forms_workflows/static/django_forms_workflows/js/form-builder.js';
import { createBuilderStore } from '../../django_forms_workflows/static/django_forms_workflows/js/form-builder-store.js';

function createInstance({ fields, formSteps }) {
  const instance = Object.create(FormBuilder.prototype);
  instance.store = createBuilderStore({ fields, formSteps });
  return instance;
}

// Renders the DOM order updateFieldOrderInStep reads back: one .field-item
// per fieldIndex, in the order the drag left them.
function setStepCanvasOrder(stepIndex, fieldIndexesInOrder) {
  document.body.innerHTML = `<div id="step-canvas-${stepIndex}"></div>`;
  const canvas = document.getElementById(`step-canvas-${stepIndex}`);
  fieldIndexesInOrder.forEach((fieldIndex) => {
    const el = document.createElement('div');
    el.className = 'field-item';
    el.dataset.fieldIndex = String(fieldIndex);
    canvas.appendChild(el);
  });
}

afterEach(() => {
  document.body.innerHTML = '';
});

describe('FormBuilder#updateFieldOrderInStep', () => {
  it('rewrites the step field order from the DOM order and refreshes the preview', () => {
    const instance = createInstance({
      fields: [{ field_name: 'a' }, { field_name: 'b' }],
      formSteps: [{ title: 'Step 1', fields: ['a', 'b'] }],
    });
    instance.updatePreview = vi.fn();
    setStepCanvasOrder(0, [1, 0]); // dragged 'b' above 'a'

    instance.updateFieldOrderInStep(0);

    expect(instance.formSteps[0].fields).toEqual(['b', 'a']);
    expect(instance.updatePreview).toHaveBeenCalledTimes(1);
  });
});
