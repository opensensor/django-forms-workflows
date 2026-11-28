import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { WorkflowBuilder } from '../../django_forms_workflows/static/django_forms_workflows/js/workflow-builder.js';
import { createWorkflowBuilderStore } from '../../django_forms_workflows/static/django_forms_workflows/js/workflow-builder-store.js';

// createStartNode/createNode/deleteNode still live directly on WorkflowBuilder.prototype
// (not yet extracted into their own module), same instantiation pattern as
// moduleAndEscaping.test.js — a bare instance with just enough stubbed state
// for these methods to run without touching the real DOM/canvas.
function createInstance() {
  const instance = Object.create(WorkflowBuilder.prototype);
  instance.store = createWorkflowBuilderStore();
  instance.nodeStackOrder = new Map();
  instance.nextNodeStackOrder = 1;
  instance.render = vi.fn();
  return instance;
}

beforeEach(() => {
  vi.restoreAllMocks();
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('WorkflowBuilder#createStartNode', () => {
  it('generates the id via store.nextNodeId(), advancing the shared counter', () => {
    const instance = createInstance();

    instance.createStartNode();

    expect(instance.nodes).toEqual([
      expect.objectContaining({ id: 'node_1', type: 'start', x: 100, y: 100, data: {} }),
    ]);
    expect(instance.store.nodeIdCounter).toBe(2);
  });

  it('brings the new node to front and renders', () => {
    const instance = createInstance();
    instance.bringNodeToFront = vi.fn();

    instance.createStartNode();

    expect(instance.bringNodeToFront).toHaveBeenCalledWith('node_1');
    expect(instance.render).toHaveBeenCalledTimes(1);
  });

  it('adds the node through the store setter, so nodes-changed listeners see it', () => {
    const instance = createInstance();
    const listener = vi.fn();
    instance.store.addEventListener('nodes-changed', listener);

    instance.createStartNode();

    expect(listener).toHaveBeenCalledTimes(1);
    expect(listener.mock.calls[0][0].detail.nodes).toEqual(instance.nodes);
  });
});

describe('WorkflowBuilder#setupPalette', () => {
  it('creates a node at the visible canvas center using canvas coordinates', () => {
    document.body.innerHTML = '<button class="palette-node" data-node-type="stage"></button>';
    const instance = createInstance();
    instance.canvas = document.createElement('div');
    instance.canvas.getBoundingClientRect = () => ({ left: 100, top: 50, width: 200, height: 100 });
    instance.clientToCanvas = vi.fn().mockReturnValue([40, 60]);
    instance.createNode = vi.fn();
    instance.setupPalette();

    document.querySelector('.palette-node').click();

    expect(instance.clientToCanvas).toHaveBeenCalledWith(200, 100);
    expect(instance.createNode).toHaveBeenCalledWith('stage', 40, 60);
  });
});

describe('WorkflowBuilder#deleteNode', () => {
  it('records the persisted action ID from node data when deleting an action', () => {
    const instance = createInstance();
    instance.deletedActionIds = [];
    instance.nodes = [{ id: 'action-1', type: 'action', data: { action_id: 17 } }];
    instance.deselectAll = vi.fn();
    vi.stubGlobal('confirm', vi.fn().mockReturnValue(true));

    instance.deleteNode('action-1');

    expect(instance.nodes).toEqual([]);
    expect(instance.deletedActionIds).toEqual([17]);
  });

  it('does not delete the node or record action id when confirmation is canceled', () => {
    const instance = createInstance();
    instance.deletedActionIds = [99];
    instance.nodes = [{ id: 'action-1', type: 'action', data: { action_id: 17 } }];
    instance.deselectAll = vi.fn();
    vi.stubGlobal('confirm', vi.fn().mockReturnValue(false));

    instance.deleteNode('action-1');

    expect(instance.nodes).toEqual([{ id: 'action-1', type: 'action', data: { action_id: 17 } }]);
    expect(instance.deletedActionIds).toEqual([99]);
  });
});

describe('WorkflowBuilder#createNode', () => {
  it('generates sequential ids across calls, sharing the counter with createStartNode', () => {
    const instance = createInstance();
    instance.bringNodeToFront = vi.fn();
    instance.getDefaultNodeData = vi.fn().mockReturnValue({});

    instance.createStartNode();
    instance.createNode('stage', 200, 150);
    instance.createNode('action', 300, 250);

    expect(instance.nodes.map(n => n.id)).toEqual(['node_1', 'node_2', 'node_3']);
    expect(instance.store.nodeIdCounter).toBe(4);
  });

  it('uses getDefaultNodeData(type) for the new node\'s data', () => {
    const instance = createInstance();
    instance.bringNodeToFront = vi.fn();
    instance.getDefaultNodeData = vi.fn().mockReturnValue({ label: 'Stage default' });

    instance.createNode('stage', 10, 20);

    expect(instance.nodes[0]).toEqual(
      expect.objectContaining({ type: 'stage', x: 10, y: 20, data: { label: 'Stage default' } })
    );
    expect(instance.getDefaultNodeData).toHaveBeenCalledWith('stage');
  });

  it('does not collide with an id already seeded from a loaded workflow', () => {
    const instance = createInstance();
    instance.bringNodeToFront = vi.fn();
    instance.getDefaultNodeData = vi.fn().mockReturnValue({});
    instance.store.seedNodeIdCounterFromNodes([{ id: 'node_1' }, { id: 'node_5' }]);

    instance.createNode('action', 0, 0);

    expect(instance.nodes[0].id).toBe('node_6');
  });

  it('adds the node through the store setter, so nodes-changed listeners see it', () => {
    const instance = createInstance();
    instance.bringNodeToFront = vi.fn();
    instance.getDefaultNodeData = vi.fn().mockReturnValue({});
    const listener = vi.fn();
    instance.store.addEventListener('nodes-changed', listener);

    instance.createNode('stage', 10, 20);

    expect(listener).toHaveBeenCalledTimes(1);
    expect(listener.mock.calls[0][0].detail.nodes).toEqual(instance.nodes);
  });
});
