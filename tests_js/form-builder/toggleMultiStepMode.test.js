import { describe, expect, it, vi } from 'vitest';
import { FormBuilder } from '../../django_forms_workflows/static/django_forms_workflows/js/form-builder.js';
import { createBuilderStore } from '../../django_forms_workflows/static/django_forms_workflows/js/form-builder-store.js';

function createInstance(fields, formSteps) {
  document.body.innerHTML = `
    <div id="singleStepCanvas"></div>
    <div id="multiStepCanvas"></div>
  `;

  const instance = Object.create(FormBuilder.prototype);
  instance.store = createBuilderStore({ fields, formSteps });
  instance.renderStepTabs = vi.fn();
  instance.renderCanvas = vi.fn();
  instance.updatePreview = vi.fn();
  return instance;
}

describe('FormBuilder#toggleMultiStepMode', () => {
  it('refreshes the live preview when enabling multi-step', () => {
    const instance = createInstance([{ field_name: 'a' }], []);

    instance.toggleMultiStepMode(true);

    expect(instance.updatePreview).toHaveBeenCalledTimes(1);
  });

  it('refreshes the live preview when disabling multi-step', () => {
    const instance = createInstance([{ field_name: 'a' }], [{ title: 'Step 1', fields: ['a'] }]);

    instance.toggleMultiStepMode(false);

    expect(instance.updatePreview).toHaveBeenCalledTimes(1);
  });
});
