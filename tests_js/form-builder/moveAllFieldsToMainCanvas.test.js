import { describe, expect, it, vi } from 'vitest';
import { FormBuilder } from '../../django_forms_workflows/static/django_forms_workflows/js/form-builder.js';
import { createBuilderStore } from '../../django_forms_workflows/static/django_forms_workflows/js/form-builder-store.js';

function createInstance(formSteps) {
  const instance = Object.create(FormBuilder.prototype);
  instance.store = createBuilderStore({ formSteps });
  instance.renderCanvas = vi.fn();
  instance.updatePreview = vi.fn();
  return instance;
}

describe('FormBuilder#moveAllFieldsToMainCanvas', () => {
  it('refreshes both the canvas and the live preview', () => {
    const instance = createInstance([{ title: 'Step 1', fields: ['a'] }]);

    instance.moveAllFieldsToMainCanvas();

    expect(instance.renderCanvas).toHaveBeenCalledTimes(1);
    expect(instance.updatePreview).toHaveBeenCalledTimes(1);
  });
});
