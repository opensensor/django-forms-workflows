import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { propertyEditorMethods } from '../../django_forms_workflows/static/django_forms_workflows/js/form-builder-property-editor.js';
import { createBuilderStore } from '../../django_forms_workflows/static/django_forms_workflows/js/form-builder-store.js';

function createContext({ fields = [], config = {} } = {}) {
  return {
    store: createBuilderStore({ fields }),
    config: { prefillSources: [], sharedOptionLists: [], ...config },
    currentFieldIndex: null,
    isNewField: false,
    deleteFieldSilently: vi.fn(),
    renderCanvas: vi.fn(),
    updatePreview: vi.fn(),
    // Real implementation (matches form-builder.js#escapeHtml) rather than a
    // stub - it's cheap under jsdom and several assertions below depend on
    // actual escaping behavior.
    escapeHtml(text) {
      const div = document.createElement('div');
      div.textContent = text;
      return div.innerHTML;
    },
    get fields() { return this.store.fields; },
    set fields(value) { this.store.setFields(value); },
    ...propertyEditorMethods,
  };
}

function stubBootstrapModal() {
  const instance = { show: vi.fn(), hide: vi.fn() };
  function Modal() { return instance; }
  Modal.getInstance = vi.fn(() => instance);
  vi.stubGlobal('bootstrap', { Modal });
  return instance;
}

afterEach(() => {
  document.body.innerHTML = '';
  vi.unstubAllGlobals();
});

describe('propertyEditorMethods.initializePropertyFormTabs', () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <input type="checkbox" id="propEnableConditional">
      <div id="conditionalRulesContainer" style="display: none;"></div>
    `;
  });

  it('wires the conditional-logic toggle to show/hide its section', () => {
    const ctx = createContext();
    ctx.initializeConditionsList = vi.fn();
    ctx.initializeValidationRulesList = vi.fn();
    ctx.initializeDependenciesList = vi.fn();
    const field = { conditional_rules: null, validation_rules: [], field_dependencies: [] };

    ctx.initializePropertyFormTabs(field);

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
    const ctx = createContext();
    ctx.initializeConditionsList = vi.fn();
    ctx.initializeValidationRulesList = vi.fn();
    ctx.initializeDependenciesList = vi.fn();
    const field = {
      conditional_rules: { conditions: [{ field: 'x', operator: 'equals', value: '1' }] },
      validation_rules: [{ type: 'required' }],
      field_dependencies: [{ source: 'a', target: 'b' }],
    };

    ctx.initializePropertyFormTabs(field);

    expect(ctx.initializeConditionsList).toHaveBeenCalledWith(field.conditional_rules.conditions);
    expect(ctx.initializeValidationRulesList).toHaveBeenCalledWith(field.validation_rules);
    expect(ctx.initializeDependenciesList).toHaveBeenCalledWith(field.field_dependencies);
  });

  it('defaults to empty lists when the field has no rules/dependencies yet', () => {
    const ctx = createContext();
    ctx.initializeConditionsList = vi.fn();
    ctx.initializeValidationRulesList = vi.fn();
    ctx.initializeDependenciesList = vi.fn();

    ctx.initializePropertyFormTabs({});

    expect(ctx.initializeConditionsList).toHaveBeenCalledWith([]);
    expect(ctx.initializeValidationRulesList).toHaveBeenCalledWith([]);
    expect(ctx.initializeDependenciesList).toHaveBeenCalledWith([]);
  });
});

describe('propertyEditorMethods.editField', () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <div id="fieldPropertyModal"><form id="fieldPropertyForm"></form></div>
    `;
  });

  it('sets the current/new field state, renders the property form, and shows the modal', () => {
    const modal = stubBootstrapModal();
    const ctx = createContext({ fields: [{ field_name: 'a' }, { field_name: 'b' }] });
    ctx.buildPropertyForm = vi.fn(() => '<p>form html</p>');
    ctx.initializePropertyFormTabs = vi.fn();

    ctx.editField(1, true);

    expect(ctx.currentFieldIndex).toBe(1);
    expect(ctx.isNewField).toBe(true);
    expect(ctx.buildPropertyForm).toHaveBeenCalledWith(ctx.fields[1]);
    expect(document.getElementById('fieldPropertyForm').innerHTML).toBe('<p>form html</p>');
    expect(ctx.initializePropertyFormTabs).toHaveBeenCalledWith(ctx.fields[1]);
    expect(modal.show).toHaveBeenCalledTimes(1);
  });

  it('deletes the field silently on modal close when it was new and never saved', () => {
    stubBootstrapModal();
    const ctx = createContext({ fields: [{ field_name: 'a' }] });
    ctx.buildPropertyForm = vi.fn(() => '');
    ctx.initializePropertyFormTabs = vi.fn();

    ctx.editField(0, true);
    document.getElementById('fieldPropertyModal').dispatchEvent(new Event('hidden.bs.modal'));

    expect(ctx.deleteFieldSilently).toHaveBeenCalledWith(0);
    expect(ctx.isNewField).toBe(false);
  });

  it('does not delete the field on modal close when it was not new', () => {
    stubBootstrapModal();
    const ctx = createContext({ fields: [{ field_name: 'a' }] });
    ctx.buildPropertyForm = vi.fn(() => '');
    ctx.initializePropertyFormTabs = vi.fn();

    ctx.editField(0, false);
    document.getElementById('fieldPropertyModal').dispatchEvent(new Event('hidden.bs.modal'));

    expect(ctx.deleteFieldSilently).not.toHaveBeenCalled();
  });
});

describe('propertyEditorMethods.buildPropertyForm', () => {
  it('delegates to each tab builder with the field and stitches their output into the tabbed form', () => {
    const ctx = createContext({ config: { prefillSources: [] } });
    ctx.buildBasicPropertiesTab = vi.fn(() => 'BASIC');
    ctx.buildConditionalLogicTab = vi.fn(() => 'CONDITIONAL');
    ctx.buildValidationTab = vi.fn(() => 'VALIDATION');
    ctx.buildDependenciesTab = vi.fn(() => 'DEPENDENCIES');
    const field = { field_type: 'text', width: 'full' };

    const html = ctx.buildPropertyForm(field);

    expect(ctx.buildBasicPropertiesTab).toHaveBeenCalledWith(field, expect.any(String), expect.any(String));
    expect(ctx.buildConditionalLogicTab).toHaveBeenCalledWith(field);
    expect(ctx.buildValidationTab).toHaveBeenCalledWith(field);
    expect(ctx.buildDependenciesTab).toHaveBeenCalledWith(field);
    expect(html).toContain('BASIC');
    expect(html).toContain('CONDITIONAL');
    expect(html).toContain('VALIDATION');
    expect(html).toContain('DEPENDENCIES');
  });

  it('marks the prefill source matching the field as selected', () => {
    const ctx = createContext({
      config: { prefillSources: [{ id: 1, name: 'Student ID' }, { id: 2, name: 'Email' }] },
    });
    const field = { field_type: 'text', width: 'full', prefill_source_id: 2 };

    const html = ctx.buildPropertyForm(field);

    expect(html).toMatch(/<option value="2" selected>/);
    expect(html).not.toMatch(/<option value="1" selected>/);
  });
});

describe('propertyEditorMethods.buildBasicPropertiesTab', () => {
  const baseField = {
    field_label: 'My Label',
    field_name: 'my_field',
    field_type: 'text',
    required: false,
    help_text: '',
    show_help_text_in_detail: false,
    placeholder: '',
    css_class: '',
  };

  it('renders core inputs for a plain text field with no type-specific extras', () => {
    const ctx = createContext();

    const html = ctx.buildBasicPropertiesTab(baseField, '<option value="1">A</option>', '<option value="full">Full</option>');

    expect(html).toContain('value="My Label"');
    expect(html).toContain('value="my_field"');
    expect(html).not.toContain('id="propChoices"');
    expect(html).not.toContain('id="propMaxValue"');
  });

  it('escapes the field type before rendering it into the disabled type input', () => {
    const ctx = createContext();
    const field = { ...baseField, field_type: '"><script>alert(1)</script>' };

    const html = ctx.buildBasicPropertiesTab(field, '', '');

    expect(html).not.toContain('"><script>alert(1)</script>');
    expect(html).toContain(ctx.escapeHtml(field.field_type));
  });

  it('renders a choices textarea for a select field', () => {
    const ctx = createContext();
    const field = { ...baseField, field_type: 'select', choices: 'a\nb' };

    const html = ctx.buildBasicPropertiesTab(field, '', '');

    expect(html).toContain('id="propChoices"');
    expect(html).toContain('>a\nb<');
  });

  it('renders the shared option list dropdown for a select field, marking the matching one selected', () => {
    const ctx = createContext({
      config: { sharedOptionLists: [{ id: 5, name: 'Counties', itemCount: 83 }] },
    });
    const field = { ...baseField, field_type: 'select', choices: '', shared_option_list_id: 5 };

    const html = ctx.buildBasicPropertiesTab(field, '', '');

    expect(html).toContain('id="propSharedOptionList"');
    expect(html).toContain('value="5" selected');
    expect(html).toContain('Counties (83 options)');
  });

  it('renders min/max/step inputs for a slider field', () => {
    const ctx = createContext();
    const field = { ...baseField, field_type: 'slider', validation: { min_value: 2, max_value: 8 } };

    const html = ctx.buildBasicPropertiesTab(field, '', '');

    expect(html).toContain('id="propMinValue" value="2"');
    expect(html).toContain('id="propMaxValue" value="8"');
  });

  it('renders a JSON textarea pre-filled from an object for a matrix field', () => {
    const ctx = createContext();
    const field = { ...baseField, field_type: 'matrix', choices: { rows: ['R1'], columns: ['C1'] } };

    const html = ctx.buildBasicPropertiesTab(field, '', '');

    expect(html).toContain('id="propChoices"');
    expect(html).toContain('"rows": [\n    "R1"\n  ]');
  });
});

describe('propertyEditorMethods.buildConditionalLogicTab', () => {
  it('defaults to disabled/hidden with no existing rules', () => {
    const ctx = createContext();
    const field = { field_name: 'target' };

    const html = ctx.buildConditionalLogicTab(field);

    expect(html).not.toContain('id="propEnableConditional" checked');
    expect(html).toContain('style="display: none;"');
    expect(field.conditional_rules).toBeNull();
  });

  it('reflects existing conditional rules as checked/visible with selected operator and action', () => {
    const ctx = createContext({
      fields: [{ field_name: 'target' }, { field_name: 'other', field_label: 'Other' }],
    });
    const field = {
      field_name: 'target',
      conditional_rules: { operator: 'OR', action: 'hide', conditions: [{ field: 'other', operator: 'equals', value: '1' }] },
    };

    const html = ctx.buildConditionalLogicTab(field);

    expect(html).toContain('id="propEnableConditional" checked');
    expect(html).toContain('style="display: block;"');
    expect(html).toMatch(/value="OR" selected/);
    expect(html).toMatch(/value="hide" selected/);
  });

  it('excludes the field itself from the "other fields" dropdown', () => {
    const ctx = createContext({
      fields: [{ field_name: 'target', field_label: 'Target' }, { field_name: 'other', field_label: 'Other' }],
    });

    const html = ctx.buildConditionalLogicTab({ field_name: 'target' });

    expect(html).not.toContain('Target</option>');
  });
});

describe('propertyEditorMethods.buildValidationTab', () => {
  it('defaults validation_rules to an empty array and leaves the JSON preview blank', () => {
    const ctx = createContext();
    const field = {};

    const html = ctx.buildValidationTab(field);

    expect(field.validation_rules).toEqual([]);
    expect(html).toContain('id="propValidationRulesJson"');
    expect(html).toMatch(/id="propValidationRulesJson"[^>]*>\s*</);
  });

  it('pre-fills the JSON preview from existing rules', () => {
    const ctx = createContext();
    const field = { validation_rules: [{ type: 'required' }] };

    const html = ctx.buildValidationTab(field);

    expect(html).toContain('"type": "required"');
  });
});

describe('propertyEditorMethods.buildDependenciesTab', () => {
  it('defaults field_dependencies to an empty array and leaves the JSON preview blank', () => {
    const ctx = createContext();
    const field = { field_name: 'target' };

    const html = ctx.buildDependenciesTab(field);

    expect(field.field_dependencies).toEqual([]);
    expect(html).toContain('id="propDependenciesJson"');
  });

  it('pre-fills the JSON preview from existing dependencies', () => {
    const ctx = createContext({ fields: [{ field_name: 'target' }, { field_name: 'source' }] });
    const field = { field_name: 'target', field_dependencies: [{ sourceField: 'source', targetField: 'target', apiEndpoint: '/api/x/' }] };

    const html = ctx.buildDependenciesTab(field);

    expect(html).toContain('"sourceField": "source"');
  });
});

describe('propertyEditorMethods.initializeConditionsList / addConditionRow', () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <div id="conditionsList"></div>
      <button id="btnAddCondition">Add</button>
    `;
  });

  it('does nothing when the conditions-list container is missing', () => {
    document.body.innerHTML = '';
    const ctx = createContext();
    expect(() => ctx.initializeConditionsList([{ field: 'a', operator: 'equals', value: '1' }])).not.toThrow();
  });

  it('renders one row per existing condition', () => {
    const ctx = createContext({ fields: [{ field_name: 'a', field_label: 'A' }, { field_name: 'b', field_label: 'B' }] });
    ctx.currentFieldIndex = 1; // editing 'b', so 'a' remains selectable as a condition source

    ctx.initializeConditionsList([{ field: 'a', operator: 'equals', value: '1' }]);

    expect(document.getElementById('conditionsList').children.length).toBe(1);
    expect(document.getElementById('conditionsList').innerHTML).toContain('value="a" selected');
  });

  it('appends a new blank row when the add button is clicked', () => {
    const ctx = createContext({ fields: [{ field_name: 'a', field_label: 'A' }] });
    ctx.currentFieldIndex = 0;

    ctx.initializeConditionsList([]);
    document.getElementById('btnAddCondition').dispatchEvent(new Event('click'));

    expect(document.getElementById('conditionsList').children.length).toBe(1);
  });

  it('addConditionRow excludes the field currently being edited from the field dropdown', () => {
    const ctx = createContext({
      fields: [{ field_name: 'current', field_label: 'Current' }, { field_name: 'other', field_label: 'Other' }],
    });
    ctx.currentFieldIndex = 0;

    ctx.addConditionRow({}, 0);

    const html = document.getElementById('conditionsList').innerHTML;
    expect(html).not.toContain('>Current</option>');
    expect(html).toContain('>Other</option>');
  });

  it('addConditionRow does nothing when its container is missing', () => {
    document.body.innerHTML = '';
    const ctx = createContext({ fields: [{ field_name: 'a' }] });
    ctx.currentFieldIndex = 0;
    expect(() => ctx.addConditionRow({}, 0)).not.toThrow();
  });
});

describe('propertyEditorMethods.initializeValidationRulesList / addValidationRuleRow', () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <div id="validationRulesList"></div>
      <button id="btnAddValidation">Add</button>
    `;
  });

  it('does nothing when the validation-rules container is missing', () => {
    document.body.innerHTML = '';
    const ctx = createContext();
    expect(() => ctx.initializeValidationRulesList([{ type: 'required' }])).not.toThrow();
  });

  it('renders one row per existing rule, selecting its type', () => {
    const ctx = createContext();

    ctx.initializeValidationRulesList([{ type: 'email', message: 'Bad email' }]);

    const html = document.getElementById('validationRulesList').innerHTML;
    expect(document.getElementById('validationRulesList').children.length).toBe(1);
    expect(html).toContain('value="email" selected');
    expect(html).toContain('value="Bad email"');
  });

  it('appends a new blank row when the add button is clicked', () => {
    const ctx = createContext();

    ctx.initializeValidationRulesList([]);
    document.getElementById('btnAddValidation').dispatchEvent(new Event('click'));

    expect(document.getElementById('validationRulesList').children.length).toBe(1);
  });

  it('addValidationRuleRow does nothing when its container is missing', () => {
    document.body.innerHTML = '';
    const ctx = createContext();
    expect(() => ctx.addValidationRuleRow({}, 0)).not.toThrow();
  });
});

describe('propertyEditorMethods.initializeDependenciesList / addDependencyRow', () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <div id="dependenciesList"></div>
      <button id="btnAddDependency">Add</button>
    `;
  });

  it('does nothing when the dependencies container is missing', () => {
    document.body.innerHTML = '';
    const ctx = createContext();
    expect(() => ctx.initializeDependenciesList([{ sourceField: 'a' }])).not.toThrow();
  });

  it('renders one row per existing dependency', () => {
    const ctx = createContext({
      fields: [{ field_name: 'current', field_label: 'Current' }, { field_name: 'source', field_label: 'Source' }],
    });
    ctx.currentFieldIndex = 0;

    ctx.initializeDependenciesList([{ sourceField: 'source', apiEndpoint: '/api/x/' }]);

    const html = document.getElementById('dependenciesList').innerHTML;
    expect(document.getElementById('dependenciesList').children.length).toBe(1);
    expect(html).toContain('value="source" selected');
    expect(html).toContain('value="/api/x/"');
  });

  it('appends a new blank row when the add button is clicked', () => {
    const ctx = createContext({ fields: [{ field_name: 'current' }] });
    ctx.currentFieldIndex = 0;

    ctx.initializeDependenciesList([]);
    document.getElementById('btnAddDependency').dispatchEvent(new Event('click'));

    expect(document.getElementById('dependenciesList').children.length).toBe(1);
  });

  it('addDependencyRow excludes the field currently being edited from the source dropdown', () => {
    const ctx = createContext({
      fields: [{ field_name: 'current', field_label: 'Current' }, { field_name: 'other', field_label: 'Other' }],
    });
    ctx.currentFieldIndex = 0;

    ctx.addDependencyRow({}, 0);

    const html = document.getElementById('dependenciesList').innerHTML;
    expect(html).not.toContain('>Current</option>');
    expect(html).toContain('>Other</option>');
  });
});

describe('propertyEditorMethods.saveFieldProperties', () => {
  function setupDOM({ fieldType = 'text' } = {}) {
    document.body.innerHTML = `
      <div id="fieldPropertyModal"></div>
      <input id="propFieldLabel" value="New Label">
      <input id="propFieldName" value="new_name">
      <input type="checkbox" id="propRequired" checked>
      <input id="propHelpText" value="Help">
      <input type="checkbox" id="propShowHelpTextInDetail">
      <input id="propPlaceholder" value="Placeholder">
      <select id="propWidth"><option value="half" selected>Half</option></select>
      <input id="propCssClass" value="my-class">
      <select id="propPrefillSource"><option value="" selected>None</option></select>
      <select id="propApprovalStep"><option value="2" selected>Step 2</option></select>
      ${fieldType === 'matrix' ? '<textarea id="propChoices">{"rows":["R1"],"columns":["C1"]}</textarea>' : ''}
      <input type="checkbox" id="propEnableConditional">
      <textarea id="propConditionalRulesJson"></textarea>
      <select id="propConditionalOperator"><option value="AND" selected>AND</option></select>
      <select id="propConditionalAction"><option value="show" selected>Show</option></select>
      <textarea id="propValidationRulesJson"></textarea>
      <textarea id="propDependenciesJson"></textarea>
    `;
  }

  it('does nothing when there is no field currently being edited', () => {
    const ctx = createContext();
    ctx.currentFieldIndex = null;

    expect(() => ctx.saveFieldProperties()).not.toThrow();
    expect(ctx.renderCanvas).not.toHaveBeenCalled();
  });

  it('writes basic properties back onto the field, re-renders, and closes the modal', () => {
    setupDOM();
    const modal = stubBootstrapModal();
    const field = { field_type: 'text' };
    const ctx = createContext({ fields: [field] });
    ctx.currentFieldIndex = 0;
    ctx.isNewField = true;

    ctx.saveFieldProperties();

    expect(field.field_label).toBe('New Label');
    expect(field.field_name).toBe('new_name');
    expect(field.required).toBe(true);
    expect(field.help_text).toBe('Help');
    expect(field.placeholder).toBe('Placeholder');
    expect(field.width).toBe('half');
    expect(field.css_class).toBe('my-class');
    expect(field.approval_step).toBe(2);
    expect(ctx.isNewField).toBe(false);
    expect(modal.hide).toHaveBeenCalledTimes(1);
    expect(ctx.renderCanvas).toHaveBeenCalledTimes(1);
    expect(ctx.updatePreview).toHaveBeenCalledTimes(1);
  });

  it('parses matrix choices as JSON when the field type is matrix', () => {
    setupDOM({ fieldType: 'matrix' });
    stubBootstrapModal();
    const field = { field_type: 'matrix' };
    const ctx = createContext({ fields: [field] });
    ctx.currentFieldIndex = 0;

    ctx.saveFieldProperties();

    expect(field.choices).toEqual({ rows: ['R1'], columns: ['C1'] });
  });

  it('builds conditional_rules from the condition rows in the DOM when enabled', () => {
    setupDOM();
    document.getElementById('propEnableConditional').checked = true;
    document.body.insertAdjacentHTML('beforeend', `
      <select class="condition-field" data-index="0"><option value="other_field" selected>Other</option></select>
      <select class="condition-operator" data-index="0"><option value="equals" selected>Equals</option></select>
      <input class="condition-value" data-index="0" value="42">
    `);
    stubBootstrapModal();
    const field = { field_type: 'text' };
    const ctx = createContext({ fields: [field] });
    ctx.currentFieldIndex = 0;

    ctx.saveFieldProperties();

    expect(field.conditional_rules).toEqual({
      operator: 'AND',
      action: 'show',
      conditions: [{ field: 'other_field', operator: 'equals', value: '42' }],
    });
  });

  it('prefers a manually-edited conditional-rules JSON blob over the UI rows', () => {
    setupDOM();
    document.getElementById('propEnableConditional').checked = true;
    document.getElementById('propConditionalRulesJson').value = JSON.stringify({ operator: 'OR', action: 'hide', conditions: [] });
    stubBootstrapModal();
    const field = { field_type: 'text' };
    const ctx = createContext({ fields: [field] });
    ctx.currentFieldIndex = 0;

    ctx.saveFieldProperties();

    expect(field.conditional_rules).toEqual({ operator: 'OR', action: 'hide', conditions: [] });
  });

  it('clears conditional_rules when the enable checkbox is off', () => {
    setupDOM();
    stubBootstrapModal();
    const field = { field_type: 'text', conditional_rules: { operator: 'AND', action: 'show', conditions: [] } };
    const ctx = createContext({ fields: [field] });
    ctx.currentFieldIndex = 0;

    ctx.saveFieldProperties();

    expect(field.conditional_rules).toBeNull();
  });

  it('builds validation_rules from the validation rows in the DOM', () => {
    setupDOM();
    document.body.insertAdjacentHTML('beforeend', `
      <select class="validation-type" data-index="0"><option value="min" selected>Min</option></select>
      <input class="validation-value" data-index="0" value="3">
      <input class="validation-message" data-index="0" value="Too short">
    `);
    stubBootstrapModal();
    const field = { field_type: 'text' };
    const ctx = createContext({ fields: [field] });
    ctx.currentFieldIndex = 0;

    ctx.saveFieldProperties();

    expect(field.validation_rules).toEqual([{ type: 'min', value: '3', message: 'Too short' }]);
  });

  it('prefers a manually-edited validation-rules JSON blob over the UI rows', () => {
    setupDOM();
    document.getElementById('propValidationRulesJson').value = JSON.stringify([{ type: 'required' }]);
    stubBootstrapModal();
    const field = { field_type: 'text' };
    const ctx = createContext({ fields: [field] });
    ctx.currentFieldIndex = 0;

    ctx.saveFieldProperties();

    expect(field.validation_rules).toEqual([{ type: 'required' }]);
  });

  it('builds field_dependencies from the dependency rows in the DOM', () => {
    setupDOM();
    document.body.insertAdjacentHTML('beforeend', `
      <select class="dependency-source" data-index="0"><option value="source_field" selected>Source</option></select>
      <input class="dependency-endpoint" data-index="0" value="/api/options/">
    `);
    stubBootstrapModal();
    // saveFieldProperties overwrites field_name from #propFieldName (set to
    // "new_name" by setupDOM) before it reaches the dependencies section, so
    // that's the targetField dependencies end up carrying, not the field's
    // original name.
    const field = { field_type: 'text', field_name: 'target_field' };
    const ctx = createContext({ fields: [field] });
    ctx.currentFieldIndex = 0;

    ctx.saveFieldProperties();

    expect(field.field_dependencies).toEqual([
      { sourceField: 'source_field', targetField: 'new_name', apiEndpoint: '/api/options/' },
    ]);
  });

  it('prefers a manually-edited dependencies JSON blob over the UI rows', () => {
    setupDOM();
    document.getElementById('propDependenciesJson').value = JSON.stringify([{ sourceField: 'x', targetField: 'y', apiEndpoint: '/z/' }]);
    stubBootstrapModal();
    const field = { field_type: 'text' };
    const ctx = createContext({ fields: [field] });
    ctx.currentFieldIndex = 0;

    ctx.saveFieldProperties();

    expect(field.field_dependencies).toEqual([{ sourceField: 'x', targetField: 'y', apiEndpoint: '/z/' }]);
  });

  it('saves min/max validation bounds when rating/slider inputs are present', () => {
    setupDOM();
    document.body.insertAdjacentHTML('beforeend', `
      <input id="propMinValue" value="1">
      <input id="propMaxValue" value="10">
    `);
    stubBootstrapModal();
    const field = { field_type: 'slider' };
    const ctx = createContext({ fields: [field] });
    ctx.currentFieldIndex = 0;

    ctx.saveFieldProperties();

    expect(field.validation).toEqual({ min_value: 1, max_value: 10 });
  });
});
