import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { WorkflowBuilder } from '../../django_forms_workflows/static/django_forms_workflows/js/workflow-builder.js';
import { createWorkflowBuilderStore } from '../../django_forms_workflows/static/django_forms_workflows/js/workflow-builder-store.js';

// Same bare-instance pattern as nodeCreation.test.js: enough stubbed state
// for finishConnection() to run without the real DOM/canvas.
function createInstance() {
  const instance = Object.create(WorkflowBuilder.prototype);
  instance.store = createWorkflowBuilderStore();
  instance.nodes = [{ id: 'node_1' }, { id: 'node_2' }];
  instance.connectionStart = { nodeId: 'node_1' };
  instance.selectedConnection = null;
  instance.render = vi.fn();
  return instance;
}

function inputPointEvent(nodeId) {
  const point = document.createElement('div');
  point.className = 'connection-point';
  point.dataset.point = 'input';
  point.dataset.nodeId = nodeId;
  document.body.appendChild(point);
  return { target: point };
}

beforeEach(() => {
  vi.restoreAllMocks();
  document.body.innerHTML = '<div id="propertiesContent">Node properties</div>';
});

afterEach(() => {
  vi.restoreAllMocks();
  document.body.innerHTML = '';
});

describe('WorkflowBuilder#finishConnection', () => {
  it('appends the new connection and selects it', () => {
    const instance = createInstance();
    instance.selectedNode = 'node_1';

    instance.finishConnection(inputPointEvent('node_2'));

    expect(instance.connections).toEqual([{ from: 'node_1', to: 'node_2' }]);
    expect(instance.selectedConnection).toBe(0);
    expect(instance.selectedNode).toBe(null);
    expect(document.getElementById('propertiesContent').textContent).toContain('Select a node');
    expect(instance.render).toHaveBeenCalledTimes(1);
  });

  it('adds the connection through the store setter, so connections-changed listeners see it', () => {
    const instance = createInstance();
    const listener = vi.fn();
    instance.store.addEventListener('connections-changed', listener);

    instance.finishConnection(inputPointEvent('node_2'));

    expect(listener).toHaveBeenCalledTimes(1);
    expect(listener.mock.calls[0][0].detail.connections).toEqual(instance.connections);
  });

  it('does not add a duplicate connection that already exists', () => {
    const instance = createInstance();
    instance.connections = [{ from: 'node_1', to: 'node_2' }];
    const listener = vi.fn();
    instance.store.addEventListener('connections-changed', listener);

    instance.finishConnection(inputPointEvent('node_2'));

    expect(instance.connections).toEqual([{ from: 'node_1', to: 'node_2' }]);
    expect(listener).not.toHaveBeenCalled();
  });

  it('does not add a connection back to the same node', () => {
    const instance = createInstance();

    instance.finishConnection(inputPointEvent('node_1'));

    expect(instance.connections).toEqual([]);
  });

  it('preserves numeric node IDs from the graph when connecting through DOM points', () => {
    const instance = createInstance();
    instance.nodes = [{ id: 1 }, { id: 2 }];
    instance.connectionStart = { nodeId: 1 };

    instance.finishConnection(inputPointEvent(2));

    expect(instance.connections).toEqual([{ from: 1, to: 2 }]);
  });
});

describe('keyboard connection handles', () => {
  it('connects two nodes and restores focus to the input after rendering', () => {
    const instance = createInstance();
    instance.nodes = [
      { id: 'node_1', type: 'stage', x: 0, y: 0, data: { name: 'First' } },
      { id: 'node_2', type: 'stage', x: 100, y: 0, data: { name: 'Second' } },
    ];
    instance.fields = [];
    instance.groups = [];
    instance.forms = [];
    instance.validationState = { nodeIssues: {} };
    const host = document.createElement('div');
    document.body.appendChild(host);
    instance.transformWrapper = host;
    instance.render = vi.fn(() => host.replaceChildren(...instance.nodes.map(node => instance.createNodeElement(node))));
    instance.render();

    host.querySelector('[data-node-id="node_1"] .connection-point.output')
      .dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    expect(instance.connectionStart).toEqual({ nodeId: 'node_1', point: 'output' });
    host.querySelector('[data-node-id="node_2"] .connection-point.input')
      .dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));

    expect(instance.connections).toEqual([{ from: 'node_1', to: 'node_2' }]);
    expect(instance.isConnecting).toBe(false);
    expect(instance.connectionStart).toBe(null);
    expect(document.activeElement).toBe(host.querySelector('[data-node-id="node_2"] .connection-point.input'));
  });

  it('cancels a keyboard connection with Escape', () => {
    const instance = createInstance();
    instance.isConnecting = true;
    instance.connectionStart = { nodeId: 'node_1', point: 'output' };

    instance.handleConnectionHandleKeydown(new KeyboardEvent('keydown', { key: 'Escape' }), 'node_1', 'output');

    expect(instance.isConnecting).toBe(false);
    expect(instance.connectionStart).toBe(null);
  });

  it('deletes the selected connection through the store setter', () => {
    const instance = createInstance();
    instance.connections = [{ from: 'node_1', to: 'node_2' }];
    instance.selectedConnection = 0;
    const listener = vi.fn();
    instance.store.addEventListener('connections-changed', listener);

    instance.deleteSelectedConnection();

    expect(instance.connections).toEqual([]);
    expect(listener).toHaveBeenCalledTimes(1);
    expect(instance.selectedConnection).toBe(null);
  });
});
