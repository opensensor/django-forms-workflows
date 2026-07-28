import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { apiMethods } from '../../django_forms_workflows/static/django_forms_workflows/js/form-builder-api.js';
import { createBuilderStore } from '../../django_forms_workflows/static/django_forms_workflows/js/form-builder-store.js';

// Every input/checkbox/select loadForm/saveForm touch, plus the containers
// generatePreview/showTemplateSelection/loadTemplate write into.
function setupFormDOM() {
  document.body.innerHTML = `
    <input id="formName" value="">
    <input id="formSlug" value="">
    <textarea id="formDescription"></textarea>
    <textarea id="formInstructions"></textarea>
    <input type="checkbox" id="formIsActive">
    <input type="checkbox" id="formRequiresLogin">
    <input type="checkbox" id="formAllowDraft">
    <input type="checkbox" id="formAllowWithdrawal">
    <input id="formSuccessMessage" value="">
    <input id="formSuccessRedirectUrl" value="">
    <input id="formSuccessRedirectRules" value="">
    <input type="checkbox" id="formPaymentEnabled">
    <div id="paymentSettings" style="display:none"></div>
    <select id="formPaymentProvider"></select>
    <select id="formPaymentAmountType"><option value="fixed">fixed</option></select>
    <input id="formPaymentFixedAmount" value="">
    <input id="formPaymentAmountField" value="">
    <input id="formPaymentCurrency" value="usd">
    <input id="formPaymentDescription" value="">
    <input id="formCloseDate" value="">
    <input id="formMaxSubmissions" value="">
    <input type="checkbox" id="formOnePerUser">
    <input type="checkbox" id="formEnableCaptcha">
    <input type="checkbox" id="formEmbedEnabled">
    <input type="checkbox" id="formEnableAutoSave" checked>
    <input id="formAutoSaveInterval" value="30">
    <input type="checkbox" id="formEnableMultiStep">
    <button id="btnSave">Save</button>
    <span id="saveStatus"></span>
    <div id="formPreview"></div>
    <div id="templateList"></div>
    <div id="templateSelectionModal"></div>
    <button id="btnStartBlank">Start blank</button>
  `;
}

function createContext({ fields = [], formSteps = [], config = {} } = {}) {
  const store = createBuilderStore({ fields, formSteps });
  return {
    store,
    config: { apiUrls: {}, csrfToken: 'test-token', paymentProviders: [], ...config },
    previewTimeout: null,
    renderCanvas: vi.fn(),
    renderStepTabs: vi.fn(),
    toggleMultiStepMode: vi.fn(),
    updateFieldOrderFromSteps: vi.fn(),
    escapeHtml: (text) => text,
    get fields() { return this.store.fields; },
    set fields(value) { this.store.setFields(value); },
    get formSteps() { return this.store.formSteps; },
    set formSteps(value) { this.store.setFormSteps(value); },
    ...apiMethods,
  };
}

beforeEach(() => {
  setupFormDOM();
  vi.stubGlobal('alert', vi.fn());
  vi.stubGlobal('bootstrap', { Modal: function () { return { show: vi.fn(), hide: vi.fn() }; } });
});

afterEach(() => {
  document.body.innerHTML = '';
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('apiMethods.updatePreview', () => {
  it('debounces: only the last call within the window triggers generatePreview', () => {
    vi.useFakeTimers();
    const ctx = createContext();
    ctx.generatePreview = vi.fn();

    ctx.updatePreview();
    ctx.updatePreview();
    ctx.updatePreview();
    vi.advanceTimersByTime(500);

    expect(ctx.generatePreview).toHaveBeenCalledTimes(1);
    vi.useRealTimers();
  });
});

describe('apiMethods.generatePreview', () => {
  it('renders the returned HTML on success', async () => {
    const ctx = createContext({ fields: [{ field_name: 'a' }] });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, html: '<p>preview</p>' }),
    }));

    await ctx.generatePreview();

    expect(document.getElementById('formPreview').innerHTML).toBe('<p>preview</p>');
  });

  it('shows a "no fields yet" message when the request fails and there are no fields', async () => {
    const ctx = createContext({ fields: [] });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 500, text: async () => 'boom' }));

    await ctx.generatePreview();

    expect(document.getElementById('formPreview').innerHTML).toContain('No fields yet');
  });

  it('shows a field count when the request fails and fields exist', async () => {
    const ctx = createContext({ fields: [{ field_name: 'a' }, { field_name: 'b' }] });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 500, text: async () => 'boom' }));

    await ctx.generatePreview();

    expect(document.getElementById('formPreview').innerHTML).toContain('2 field(s) configured');
  });
});

describe('apiMethods.loadForm', () => {
  function stubLoadResponse(overrides = {}) {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        name: 'My Form',
        slug: 'my-form',
        fields: [{ field_name: 'text_1' }],
        form_steps: [{ title: 'Step 1', fields: ['text_1'] }],
        enable_multi_step: false,
        ...overrides,
      }),
    }));
  }

  it('populates fields and formSteps from the response, preserving `title` (not `label`)', async () => {
    stubLoadResponse();
    const ctx = createContext();
    ctx.updatePreview = vi.fn();

    await ctx.loadForm();

    expect(ctx.fields).toEqual([{ field_name: 'text_1' }]);
    expect(ctx.formSteps).toEqual([{ title: 'Step 1', fields: ['text_1'] }]);
    expect(ctx.formSteps[0].label).toBeUndefined();
  });

  it('seeds the field id counter past the highest loaded field name', async () => {
    stubLoadResponse({ fields: [{ field_name: 'text_1' }, { field_name: 'text_7' }] });
    const ctx = createContext();
    ctx.updatePreview = vi.fn();

    await ctx.loadForm();

    expect(ctx.store.fieldIdCounter).toBe(8);
  });

  it('renders the single-step canvas when multi-step is off', async () => {
    stubLoadResponse({ enable_multi_step: false });
    const ctx = createContext();
    ctx.updatePreview = vi.fn();

    await ctx.loadForm();

    expect(ctx.renderCanvas).toHaveBeenCalledTimes(1);
    expect(ctx.toggleMultiStepMode).not.toHaveBeenCalled();
  });

  it('switches to multi-step mode when the loaded form has it enabled', async () => {
    stubLoadResponse({ enable_multi_step: true });
    const ctx = createContext();
    ctx.updatePreview = vi.fn();

    await ctx.loadForm();

    expect(ctx.toggleMultiStepMode).toHaveBeenCalledWith(true);
    expect(ctx.renderCanvas).not.toHaveBeenCalled();
  });

  it('alerts and does not throw when the request fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false }));
    const ctx = createContext();

    await expect(ctx.loadForm()).resolves.toBeUndefined();

    expect(window.alert).toHaveBeenCalled();
  });
});

describe('apiMethods.saveForm', () => {
  it('blocks the save and alerts when the form name is blank', async () => {
    const ctx = createContext();
    vi.stubGlobal('fetch', vi.fn());

    await ctx.saveForm();

    expect(window.alert).toHaveBeenCalledWith('Please enter a form name');
    expect(fetch).not.toHaveBeenCalled();
  });

  it('sends formSteps/fields through untouched, preserving `title`', async () => {
    document.getElementById('formName').value = 'My Form';
    document.getElementById('formSlug').value = 'my-form';
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ success: true }) });
    vi.stubGlobal('fetch', fetchMock);
    const ctx = createContext({
      fields: [{ field_name: 'text_1' }],
      formSteps: [{ title: 'Step 1', fields: ['text_1'] }],
    });

    await ctx.saveForm();

    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body.form_steps).toEqual([{ title: 'Step 1', fields: ['text_1'] }]);
    expect(body.fields).toEqual([{ field_name: 'text_1' }]);
    expect(document.getElementById('saveStatus').textContent).toBe('Saved successfully');
  });

  it('remaps field ids from field_id_mapping and re-renders the canvas', async () => {
    document.getElementById('formName').value = 'My Form';
    document.getElementById('formSlug').value = 'my-form';
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, field_id_mapping: { new_1: 42 } }),
    }));
    const ctx = createContext({ fields: [{ id: 'new_1', field_name: 'text_1' }] });

    await ctx.saveForm();

    expect(ctx.fields[0].id).toBe(42);
    expect(ctx.renderCanvas).toHaveBeenCalledTimes(1);
    expect(ctx.renderStepTabs).not.toHaveBeenCalled();
  });

  it('alerts and reports an error status when the save request fails', async () => {
    document.getElementById('formName').value = 'My Form';
    document.getElementById('formSlug').value = 'my-form';
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      json: async () => ({ success: false, error: 'Server exploded' }),
    }));
    const ctx = createContext();

    await ctx.saveForm();

    expect(window.alert).toHaveBeenCalledWith('Failed to save form: Server exploded');
    expect(document.getElementById('saveStatus').textContent).toBe('Error saving');
  });
});

describe('apiMethods.loadTemplate', () => {
  it('populates fields from the template and refreshes the canvas/preview', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        template_data: { name: 'Template A', fields: [{ field_name: 'text_1' }] },
      }),
    }));
    const ctx = createContext({ config: { apiUrls: { loadTemplate: '/templates/{id}/' } } });
    ctx.updatePreview = vi.fn();

    await ctx.loadTemplate('1');

    expect(ctx.fields).toEqual([{ field_name: 'text_1' }]);
    expect(ctx.renderCanvas).toHaveBeenCalledTimes(1);
    expect(window.alert).toHaveBeenCalledWith('Template loaded successfully! You can now customize the form.');
  });

  it('seeds the field id counter past the highest field name in the template', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        template_data: { name: 'Template A', fields: [{ field_name: 'text_3' }] },
      }),
    }));
    const ctx = createContext({ config: { apiUrls: { loadTemplate: '/templates/{id}/' } } });
    ctx.updatePreview = vi.fn();

    await ctx.loadTemplate('1');

    expect(ctx.store.fieldIdCounter).toBe(4);
  });

  it('alerts on invalid template data instead of throwing', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: false }),
    }));
    const ctx = createContext({ config: { apiUrls: { loadTemplate: '/templates/{id}/' } } });

    await expect(ctx.loadTemplate('1')).resolves.toBeUndefined();

    expect(window.alert).toHaveBeenCalledWith(expect.stringContaining('Failed to load template'));
  });
});

describe('apiMethods.showTemplateSelection', () => {
  it('renders template cards grouped by category', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        templates: [
          { id: 1, name: 'Contact', description: 'A contact form', category_display: 'General', usage_count: 3 },
        ],
      }),
    }));
    const ctx = createContext();

    await ctx.showTemplateSelection();

    expect(document.getElementById('templateList').innerHTML).toContain('Contact');
    expect(document.getElementById('templateList').innerHTML).toContain('General');
  });

  it('shows an empty-state message when there are no templates', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, templates: [] }),
    }));
    const ctx = createContext();

    await ctx.showTemplateSelection();

    expect(document.getElementById('templateList').innerHTML).toContain('No templates available');
  });
});
