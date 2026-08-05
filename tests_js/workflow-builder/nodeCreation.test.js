import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { WorkflowBuilder } from '../../django_forms_workflows/static/django_forms_workflows/js/workflow-builder.js';
import { createWorkflowBuilderStore } from '../../django_forms_workflows/static/django_forms_workflows/js/workflow-builder-store.js';

// createStartNode/createNode still live directly on WorkflowBuilder.prototype
// (not yet extracted into their own module), same instantiation pattern as
// moduleAndEscaping.test.js — a bare instance with just enough stubbed state
// for these two methods to run without touching the real DOM/canvas.
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
});
