import { describe, expect, it } from 'vitest';
import { createWorkflowBuilderStore } from '../../django_forms_workflows/static/django_forms_workflows/js/workflow-builder-store.js';

describe('createWorkflowBuilderStore', () => {
  it('is a factory, not a singleton — each call returns an independent store', () => {
    const a = createWorkflowBuilderStore();
    const b = createWorkflowBuilderStore();

    a.setNodes([{ id: 'node_1' }]);

    expect(a.nodes).toEqual([{ id: 'node_1' }]);
    expect(b.nodes).toEqual([]);
    expect(a).not.toBe(b);
  });

  it('defaults to empty nodes/connections and a nodeIdCounter of 1', () => {
    const store = createWorkflowBuilderStore();

    expect(store.nodes).toEqual([]);
    expect(store.connections).toEqual([]);
    expect(store.nodeIdCounter).toBe(1);
  });

  it('accepts initial state', () => {
    const store = createWorkflowBuilderStore({
      nodes: [{ id: 'node_1' }],
      connections: [{ from: 'node_1', to: 'node_2' }],
      nodeIdCounter: 5,
    });

    expect(store.nodes).toEqual([{ id: 'node_1' }]);
    expect(store.connections).toEqual([{ from: 'node_1', to: 'node_2' }]);
    expect(store.nodeIdCounter).toBe(5);
  });
});

describe('WorkflowBuilderStore.setNodes / setConnections', () => {
  it('setNodes updates state and emits nodes-changed', () => {
    const store = createWorkflowBuilderStore();
    let received = null;
    store.addEventListener('nodes-changed', (e) => { received = e.detail.nodes; });

    store.setNodes([{ id: 'node_1' }]);

    expect(store.nodes).toEqual([{ id: 'node_1' }]);
    expect(received).toEqual([{ id: 'node_1' }]);
  });

  it('setConnections updates state and emits connections-changed', () => {
    const store = createWorkflowBuilderStore();
    let received = null;
    store.addEventListener('connections-changed', (e) => { received = e.detail.connections; });

    store.setConnections([{ from: 'node_1', to: 'node_2' }]);

    expect(store.connections).toEqual([{ from: 'node_1', to: 'node_2' }]);
    expect(received).toEqual([{ from: 'node_1', to: 'node_2' }]);
  });
});

describe('WorkflowBuilderStore.nextNodeId', () => {
  it('returns node_counter and increments the counter', () => {
    const store = createWorkflowBuilderStore({ nodeIdCounter: 1 });

    expect(store.nextNodeId()).toBe('node_1');
    expect(store.nextNodeId()).toBe('node_2');
    expect(store.nodeIdCounter).toBe(3);
  });
});

describe('WorkflowBuilderStore.seedNodeIdCounterFromNodes', () => {
  it('seeds the counter one past the highest existing node_N id', () => {
    const store = createWorkflowBuilderStore();
    store.seedNodeIdCounterFromNodes([
      { id: 'node_1' },
      { id: 'node_5' },
      { id: 'node_3' },
    ]);

    expect(store.nodeIdCounter).toBe(6);
  });

  it('defaults to 1 when there are no nodes yet', () => {
    const store = createWorkflowBuilderStore({ nodeIdCounter: 99 });
    store.seedNodeIdCounterFromNodes([]);

    expect(store.nodeIdCounter).toBe(1);
  });

  it('ignores node ids that do not match the node_N shape', () => {
    const store = createWorkflowBuilderStore();
    store.seedNodeIdCounterFromNodes([
      { id: 'start' },
      { id: 'node_5' },
    ]);

    expect(store.nodeIdCounter).toBe(6);
  });

  it('does not crash on a node with no id', () => {
    const store = createWorkflowBuilderStore();
    store.seedNodeIdCounterFromNodes([{}, { id: 'node_2' }]);

    expect(store.nodeIdCounter).toBe(3);
  });
});

describe('WorkflowBuilderStore.snapshot / restore', () => {
  it('snapshot captures nodes and connections together', () => {
    const store = createWorkflowBuilderStore({
      nodes: [{ id: 'node_1' }],
      connections: [{ from: 'node_1', to: 'node_2' }],
    });

    expect(store.snapshot()).toEqual(
      JSON.stringify({ nodes: [{ id: 'node_1' }], connections: [{ from: 'node_1', to: 'node_2' }] })
    );
  });

  it('restore replaces nodes and connections and emits both change events', () => {
    const store = createWorkflowBuilderStore({ nodes: [{ id: 'old' }], connections: [] });
    const nodesChanged = [];
    const connectionsChanged = [];
    store.addEventListener('nodes-changed', (e) => nodesChanged.push(e.detail.nodes));
    store.addEventListener('connections-changed', (e) => connectionsChanged.push(e.detail.connections));

    const snapshot = JSON.stringify({
      nodes: [{ id: 'node_restored' }],
      connections: [{ from: 'node_restored', to: 'node_2' }],
    });
    store.restore(snapshot);

    expect(store.nodes).toEqual([{ id: 'node_restored' }]);
    expect(store.connections).toEqual([{ from: 'node_restored', to: 'node_2' }]);
    expect(nodesChanged).toEqual([[{ id: 'node_restored' }]]);
    expect(connectionsChanged).toEqual([[{ from: 'node_restored', to: 'node_2' }]]);
  });
});
