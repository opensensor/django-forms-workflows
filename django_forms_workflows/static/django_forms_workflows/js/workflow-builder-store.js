/**
 * Single owner of Workflow Builder state, shared across extracted modules.
 * Factory (not a singleton) since admin inlines can put two builders on one
 * page. Extends EventTarget so modules can react to changes instead of
 * closing over the whole WorkflowBuilder instance. Mirrors
 * form-builder-store.js's BuilderStore/createBuilderStore shape.
 */
export class WorkflowBuilderStore extends EventTarget {
    constructor({ nodes = [], connections = [], nodeIdCounter = 1 } = {}) {
        super();
        this.nodes = nodes;
        this.connections = connections;
        this.nodeIdCounter = nodeIdCounter;
    }

    setNodes(nodes) {
        this.nodes = nodes;
        this.dispatchEvent(new CustomEvent('nodes-changed', { detail: { nodes } }));
    }

    setConnections(connections) {
        this.connections = connections;
        this.dispatchEvent(new CustomEvent('connections-changed', { detail: { connections } }));
    }

    nextNodeId() {
        const id = `node_${this.nodeIdCounter}`;
        this.nodeIdCounter += 1;
        return id;
    }

    // Mirrors loadWorkflow()'s existing node-id-counter-seeding logic (and
    // form-builder-store.js's seedFieldIdCounterFromFields) — call after
    // loading nodes from a workflow so newly-generated ids can't collide.
    seedNodeIdCounterFromNodes(nodes) {
        const highest = nodes.reduce((max, node) => {
            const match = /node_(\d+)/.exec(node.id || '');
            return match ? Math.max(max, parseInt(match[1], 10)) : max;
        }, 0);
        this.nodeIdCounter = highest + 1;
    }

    snapshot() {
        return JSON.stringify({ nodes: this.nodes, connections: this.connections });
    }

    restore(snapshotJson) {
        const { nodes, connections } = JSON.parse(snapshotJson);
        this.setNodes(nodes);
        this.setConnections(connections);
    }
}

export function createWorkflowBuilderStore(initial) {
    return new WorkflowBuilderStore(initial);
}
