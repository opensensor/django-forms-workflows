import { beforeEach, describe, expect, it, vi } from 'vitest';
import { FormBuilder } from '../../django_forms_workflows/static/django_forms_workflows/js/form-builder.js';

function createInstance(FormBuilder) {
  const instance = Object.create(FormBuilder.prototype);
  instance.initializeConditionsList = vi.fn();
  instance.initializeValidationRulesList = vi.fn();
  instance.initializeDependenciesList = vi.fn();
  return instance;
}

describe('FormBuilder#initializePropertyFormTabs', () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <input type="checkbox" id="propEnableConditional">
      <div id="conditionalRulesContainer" style="display: none;"></div>
    `;
  });

  it('wires the conditional-logic toggle to show/hide its section', () => {
    const instance = createInstance(FormBuilder);
    const field = { conditional_rules: null, validation_rules: [], field_dependencies: [] };

    instance.initializePropertyFormTabs(field);

    const checkbox = document.getElementById('propEnableConditional');
    const container = document.getElementById('conditionalRulesContainer');

    checkbox.checked = true;
    checkbox.dispatchEvent(new Event('change'));
    expect(container.style.display).toBe('block');

    checkbox.checked = false;
    checkbox.dispatchEvent(new Event('change'));
    expect(container.style.display).toBe('none');
  });

  it("initializes all three tabs' lists with the field's current data", () => {
    const instance = createInstance(FormBuilder);
    const field = {
      conditional_rules: { conditions: [{ field: 'x', operator: 'equals', value: '1' }] },
      validation_rules: [{ type: 'required' }],
      field_dependencies: [{ source: 'a', target: 'b' }],
    };

    instance.initializePropertyFormTabs(field);

    expect(instance.initializeConditionsList).toHaveBeenCalledWith(field.conditional_rules.conditions);
    expect(instance.initializeValidationRulesList).toHaveBeenCalledWith(field.validation_rules);
    expect(instance.initializeDependenciesList).toHaveBeenCalledWith(field.field_dependencies);
  });

  it('defaults to empty lists when the field has no rules/dependencies yet', () => {
    const instance = createInstance(FormBuilder);
    const field = {};

    instance.initializePropertyFormTabs(field);

    expect(instance.initializeConditionsList).toHaveBeenCalledWith([]);
    expect(instance.initializeValidationRulesList).toHaveBeenCalledWith([]);
    expect(instance.initializeDependenciesList).toHaveBeenCalledWith([]);
  });
});
