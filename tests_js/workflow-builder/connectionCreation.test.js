import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { WorkflowBuilder } from '../../django_forms_workflows/static/django_forms_workflows/js/workflow-builder.js';
import { createWorkflowBuilderStore } from '../../django_forms_workflows/static/django_forms_workflows/js/workflow-builder-store.js';

// Same bare-instance pattern as nodeCreation.test.js: enough stubbed state
// for finishConnection() to run without the real DOM/canvas.
function createInstance() {
  const instance = Object.create(WorkflowBuilder.prototype);
  instance.store = createWorkflowBuilderStore();
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
});

afterEach(() => {
  vi.restoreAllMocks();
  document.body.innerHTML = '';
});

describe('WorkflowBuilder#finishConnection', () => {
  it('appends the new connection and selects it', () => {
    const instance = createInstance();

    instance.finishConnection(inputPointEvent('node_2'));

    expect(instance.connections).toEqual([{ from: 'node_1', to: 'node_2' }]);
    expect(instance.selectedConnection).toBe(0);
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
});
