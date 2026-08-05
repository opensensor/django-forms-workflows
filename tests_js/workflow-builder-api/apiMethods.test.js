import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { apiMethods } from '../../django_forms_workflows/static/django_forms_workflows/js/workflow-builder-api.js';
import { createWorkflowBuilderStore } from '../../django_forms_workflows/static/django_forms_workflows/js/workflow-builder-store.js';

// Every element loadWorkflow/saveWorkflow touch directly.
function setupBuilderDOM() {
  document.body.innerHTML = `
    <button id="btnSave">Save</button>
    <span id="saveStatus"></span>
    <span id="dirtyIndicator" hidden></span>
  `;
}

function createContext({ nodes = [], connections = [], config = {}, validation } = {}) {
  const store = createWorkflowBuilderStore({ nodes, connections });
  return {
    store,
    config: { apiUrls: {}, csrfToken: 'test-token', formId: 1, currentWorkflowId: null, ...config },
    fields: [],
    groups: [],
    forms: [],
    workflowTargets: [],
    isSaving: false,
    isDirty: false,
    lastSavedWorkflowSnapshot: null,
    setBuilderMessage: vi.fn(),
    selectNode: vi.fn(),
    initializeNodeStackOrder: vi.fn(),
    layoutNeedsNormalization: vi.fn().mockReturnValue(false),
    autoArrangeNodes: vi.fn(),
    refreshValidationState: vi.fn().mockReturnValue(
      validation || { errors: [], warnings: [], nodeIssues: {}, firstErrorNodeId: null }
    ),
    get nodes() { return this.store.nodes; },
    set nodes(value) { this.store.setNodes(value); },
    get connections() { return this.store.connections; },
    set connections(value) { this.store.setConnections(value); },
    get nodeIdCounter() { return this.store.nodeIdCounter; },
    set nodeIdCounter(value) { this.store.nodeIdCounter = value; },
    ...apiMethods,
  };
}

beforeEach(() => {
  setupBuilderDOM();
});

afterEach(() => {
  document.body.innerHTML = '';
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('apiMethods.setSaveStatus', () => {
  it('sets the status text and tone dataset attribute', () => {
    const ctx = createContext();

    ctx.setSaveStatus('Saving...', 'info');

    const status = document.getElementById('saveStatus');
    expect(status.textContent).toBe('Saving...');
    expect(status.dataset.tone).toBe('info');
  });

  it('is a no-op when the saveStatus element is missing', () => {
    document.body.innerHTML = '';
    const ctx = createContext();

    expect(() => ctx.setSaveStatus('Saving...')).not.toThrow();
  });
});

describe('apiMethods.getWorkflowSnapshot', () => {
  it('serializes nodes and connections together', () => {
    const ctx = createContext({
      nodes: [{ id: 'node_1' }],
      connections: [{ from: 'node_1', to: 'node_2' }],
    });

    expect(ctx.getWorkflowSnapshot()).toEqual(
      JSON.stringify({ nodes: [{ id: 'node_1' }], connections: [{ from: 'node_1', to: 'node_2' }] })
    );
  });
});

describe('apiMethods.syncSavedWorkflowSnapshot / updateDirtyState', () => {
  it('marks clean immediately after syncing', () => {
    const ctx = createContext({ nodes: [{ id: 'node_1' }] });

    ctx.syncSavedWorkflowSnapshot();

    expect(ctx.isDirty).toBe(false);
    expect(document.getElementById('dirtyIndicator').hidden).toBe(true);
    expect(document.getElementById('saveStatus').textContent).toBe('Ready');
  });

  it('marks dirty once nodes/connections change after syncing', () => {
    const ctx = createContext({ nodes: [{ id: 'node_1' }] });
    ctx.syncSavedWorkflowSnapshot();

    ctx.nodes = [{ id: 'node_1' }, { id: 'node_2' }];
    ctx.updateDirtyState();

    expect(ctx.isDirty).toBe(true);
    expect(document.getElementById('dirtyIndicator').hidden).toBe(false);
    expect(document.getElementById('saveStatus').textContent).toBe('Unsaved changes');
  });

  it('does not overwrite the save status while a save is in flight', () => {
    const ctx = createContext({ nodes: [{ id: 'node_1' }] });
    ctx.syncSavedWorkflowSnapshot();
    ctx.isSaving = true;
    ctx.setSaveStatus('Saving...', 'info');

    ctx.nodes = [{ id: 'node_1' }, { id: 'node_2' }];
    ctx.updateDirtyState();

    expect(document.getElementById('saveStatus').textContent).toBe('Saving...');
  });
});

describe('apiMethods.loadWorkflow', () => {
  function stubLoadResponse(overrides = {}) {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      json: async () => ({
        success: true,
        workflow: { nodes: [], connections: [] },
        fields: [],
        groups: [],
        forms: [],
        workflow_targets: [],
        ...overrides,
      }),
    }));
  }

  it('populates nodes/connections/fields/groups/forms from the response', async () => {
    stubLoadResponse({
      workflow: { nodes: [{ id: 'node_1' }], connections: [{ from: 'node_1', to: 'node_2' }] },
      fields: [{ field_name: 'a' }],
      groups: [{ id: 1 }],
      forms: [{ id: 2 }],
      workflow_targets: [{ id: 3 }],
    });
    const ctx = createContext();

    await ctx.loadWorkflow();

    expect(ctx.nodes).toEqual([{ id: 'node_1' }]);
    expect(ctx.connections).toEqual([{ from: 'node_1', to: 'node_2' }]);
    expect(ctx.fields).toEqual([{ field_name: 'a' }]);
    expect(ctx.groups).toEqual([{ id: 1 }]);
    expect(ctx.forms).toEqual([{ id: 2 }]);
    expect(ctx.workflowTargets).toEqual([{ id: 3 }]);
  });

  it('seeds nodeIdCounter past the highest loaded node_N id', async () => {
    stubLoadResponse({
      workflow: { nodes: [{ id: 'node_1' }, { id: 'node_7' }], connections: [] },
    });
    const ctx = createContext();

    await ctx.loadWorkflow();

    expect(ctx.nodeIdCounter).toBe(8);
  });

  it('leaves nodeIdCounter untouched when there are no nodes', async () => {
    stubLoadResponse({ workflow: { nodes: [], connections: [] } });
    const ctx = createContext({ config: {} });
    ctx.store.nodeIdCounter = 3;

    await ctx.loadWorkflow();

    expect(ctx.nodeIdCounter).toBe(3);
  });

  it('normalizes layout when needed after load', async () => {
    stubLoadResponse({ workflow: { nodes: [{ id: 'node_1' }], connections: [] } });
    const ctx = createContext();
    ctx.layoutNeedsNormalization = vi.fn().mockReturnValue(true);

    await ctx.loadWorkflow();

    expect(ctx.initializeNodeStackOrder).toHaveBeenCalledTimes(1);
    expect(ctx.autoArrangeNodes).toHaveBeenCalledWith({ suppressRender: true, silent: true });
  });

  it('surfaces a builder message when the response reports failure', async () => {
    stubLoadResponse({ success: false, error: 'nope' });
    const ctx = createContext();

    await ctx.loadWorkflow();

    expect(ctx.setBuilderMessage).toHaveBeenCalledWith(
      'danger', 'Failed to load workflow builder data.', ['nope']
    );
  });

  it('surfaces a builder message and does not throw when the request rejects', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network down')));
    const ctx = createContext();

    await expect(ctx.loadWorkflow()).resolves.toBeUndefined();

    expect(ctx.setBuilderMessage).toHaveBeenCalledWith(
      'danger', 'Failed to load workflow builder data.', ['network down']
    );
  });
});

describe('apiMethods.saveWorkflow', () => {
  it('blocks the save, reports status, and selects the first offending node on validation errors', async () => {
    const ctx = createContext({
      validation: { errors: ['Stage missing an approver'], warnings: [], firstErrorNodeId: 'node_2' },
    });
    vi.stubGlobal('fetch', vi.fn());

    await ctx.saveWorkflow();

    expect(fetch).not.toHaveBeenCalled();
    expect(document.getElementById('saveStatus').textContent).toBe('Fix validation errors');
    expect(ctx.selectNode).toHaveBeenCalledWith('node_2');
    expect(ctx.setBuilderMessage).toHaveBeenCalledWith(
      'danger', 'Fix validation errors before saving.', ['Stage missing an approver']
    );
  });

  it('sends nodes/connections and reports success', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ success: true }) });
    vi.stubGlobal('fetch', fetchMock);
    const ctx = createContext({
      nodes: [{ id: 'node_1' }],
      connections: [{ from: 'node_1', to: 'node_2' }],
      config: { formId: 5, currentWorkflowId: 9 },
    });

    await ctx.saveWorkflow();

    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body).toEqual({
      form_id: 5,
      workflow_id: 9,
      workflow: { nodes: [{ id: 'node_1' }], connections: [{ from: 'node_1', to: 'node_2' }] },
    });
    expect(document.getElementById('saveStatus').textContent).toBe('Saved successfully');
    expect(document.getElementById('btnSave').disabled).toBe(false);
  });

  it('adopts the returned workflow_id for a newly-created workflow', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true, json: async () => ({ success: true, workflow_id: 42 }),
    }));
    const ctx = createContext({ config: { currentWorkflowId: null } });

    await ctx.saveWorkflow();

    expect(ctx.config.currentWorkflowId).toBe(42);
  });

  it('reports an error status and does not throw when the save request fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false, json: async () => ({ success: false, error: 'Server exploded' }),
    }));
    const ctx = createContext();

    await expect(ctx.saveWorkflow()).resolves.toBeUndefined();

    expect(document.getElementById('saveStatus').textContent).toBe('Error saving');
    expect(ctx.setBuilderMessage).toHaveBeenCalledWith(
      'danger', 'Failed to save workflow: Server exploded', []
    );
    expect(document.getElementById('btnSave').disabled).toBe(false);
  });

  it('re-enables the save button even when the request rejects outright', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network down')));
    const ctx = createContext();

    await ctx.saveWorkflow();

    expect(document.getElementById('btnSave').disabled).toBe(false);
    expect(ctx.isSaving).toBe(false);
  });
});
