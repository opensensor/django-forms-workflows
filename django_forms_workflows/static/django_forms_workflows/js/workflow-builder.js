/**
 * Visual Workflow Builder
 *
 * Drag-and-drop workflow builder for post-submission actions and approvals.
 */

class WorkflowBuilder {
    constructor(config) {
        this.config = config;
        this.nodes = [];
        this.connections = [];
        this.selectedNode = null;
        this.selectedConnection = null;
        this.nodeIdCounter = 1;
        this.isDraggingNode = false;
        this.isConnecting = false;
        this.connectionStart = null;
        this.tempLine = null;
        this.fields = [];
        this.groups = [];
        this.forms = [];
        this.workflowTargets = [];
        this.validationState = { errors: [], warnings: [], nodeIssues: {}, firstErrorNodeId: null };
        this.isDirty = false;
        this.isSaving = false;
        this.lastSavedWorkflowSnapshot = null;
        this.nodeStackOrder = new Map();
        this.nextNodeStackOrder = 1;
        this.draggingNodeId = null;

        // Pan & zoom state
        this.panX = 0;
        this.panY = 0;
        this.zoom = 1;
        this.isPanning = false;
        this.minZoom = 0.25;
        this.maxZoom = 2;
        this.workspaceWidth = 0;
        this.workspaceHeight = 0;
        this.minWorkspaceWidth = 2400;
        this.minWorkspaceHeight = 1600;
        this.workspacePaddingX = 360;
        this.workspacePaddingY = 280;

        this.init();
    }

    async init() {
        console.log('Initializing workflow builder...');
        this.setupCanvas();
        this.setupPalette();
        this.setupEventListeners();
        await this.loadWorkflow();

        console.log('After load, nodes count:', this.nodes.length);

        // Create start node if no nodes exist
        if (this.nodes.length === 0) {
            console.log('No nodes found, creating start node');
            this.createStartNode();
        }

        this.syncSavedWorkflowSnapshot();

        console.log('Rendering workflow...');
        this.render();
        console.log('Workflow builder initialized');
    }

    setupCanvas() {
        this.canvas = document.getElementById('workflowCanvas');
        this.svg = document.getElementById('connectionsSvg');

        // Create a single transform wrapper that holds both SVG and nodes.
        // Applying pan/zoom to one wrapper keeps arrows and nodes aligned.
        this.transformWrapper = document.createElement('div');
        this.transformWrapper.className = 'workflow-transform-wrapper';

        // Move SVG into the wrapper, then add wrapper to canvas
        this.canvas.appendChild(this.transformWrapper);
        this.transformWrapper.appendChild(this.svg);
        this.updateWorkspaceBounds();
        window.addEventListener('resize', () => this.updateWorkspaceBounds());

        // Make canvas droppable
        this.canvas.addEventListener('dragover', (e) => {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'copy';
        });

        this.canvas.addEventListener('drop', (e) => {
            e.preventDefault();
            const nodeType = e.dataTransfer.getData('nodeType');
            if (nodeType) {
                const [x, y] = this.clientToCanvas(e.clientX, e.clientY);
                this.createNode(nodeType, x, y);
            }
        });

        // Click on canvas background to deselect
        this.canvas.addEventListener('click', (e) => {
            if (e.target === this.canvas || e.target === this.svg
                || e.target === this.transformWrapper) {
                this.deselectAll();
            }
        });

        // ── Pan (middle-click or Ctrl+left-click on background) ─────────
        this.canvas.addEventListener('mousedown', (e) => {
            const isBackground = e.target === this.canvas || e.target === this.svg
                || e.target === this.transformWrapper
                || e.target.tagName === 'svg' || e.target.closest('.connections-svg');
            const shouldPan = isBackground && (e.button === 1 || (e.button === 0 && (e.ctrlKey || e.metaKey || e.shiftKey)));
            if (!shouldPan) return;

            e.preventDefault();
            this.isPanning = true;
            this.canvas.classList.add('is-panning');
            const startX = e.clientX, startY = e.clientY;
            const startPanX = this.panX, startPanY = this.panY;

            const onMove = (ev) => {
                this.panX = startPanX + (ev.clientX - startX);
                this.panY = startPanY + (ev.clientY - startY);
                this.applyTransform();
            };
            const onUp = () => {
                this.isPanning = false;
                this.canvas.classList.remove('is-panning');
                document.removeEventListener('mousemove', onMove);
                document.removeEventListener('mouseup', onUp);
            };
            document.addEventListener('mousemove', onMove);
            document.addEventListener('mouseup', onUp);
        });

        // Prevent default middle-click scroll
        this.canvas.addEventListener('auxclick', (e) => { if (e.button === 1) e.preventDefault(); });

        // ── Zoom (mouse wheel) ──────────────────────────────────────────
        this.canvas.addEventListener('wheel', (e) => {
            e.preventDefault();
            const rect = this.canvas.getBoundingClientRect();
            // Cursor position relative to canvas element
            const cx = e.clientX - rect.left;
            const cy = e.clientY - rect.top;

            const oldZoom = this.zoom;
            const delta = e.deltaY > 0 ? -0.1 : 0.1;
            this.zoom = Math.min(this.maxZoom, Math.max(this.minZoom, this.zoom + delta));

            // Adjust pan so zoom centres on cursor
            const scale = this.zoom / oldZoom;
            this.panX = cx - scale * (cx - this.panX);
            this.panY = cy - scale * (cy - this.panY);

            this.applyTransform();
            this.updateZoomIndicator();
        }, { passive: false });
    }

    /** Convert client (screen) coordinates to canvas (node) coordinates. */
    clientToCanvas(clientX, clientY) {
        const rect = this.canvas.getBoundingClientRect();
        const x = (clientX - rect.left + this.canvas.scrollLeft - this.panX) / this.zoom;
        const y = (clientY - rect.top + this.canvas.scrollTop - this.panY) / this.zoom;
        return [x, y];
    }

    getWorkspaceBounds(extraPoints = []) {
        const viewportWidth = this.canvas?.clientWidth || 0;
        const viewportHeight = this.canvas?.clientHeight || 0;
        let maxX = Math.max(this.minWorkspaceWidth, viewportWidth + this.workspacePaddingX);
        let maxY = Math.max(this.minWorkspaceHeight, viewportHeight + this.workspacePaddingY);

        this.nodes.forEach((node) => {
            maxX = Math.max(maxX, node.x + 340 + this.workspacePaddingX);
            maxY = Math.max(maxY, node.y + 220 + this.workspacePaddingY);
        });

        extraPoints.forEach((point) => {
            if (!point) return;
            maxX = Math.max(maxX, point.x + this.workspacePaddingX);
            maxY = Math.max(maxY, point.y + this.workspacePaddingY);
        });

        return {
            width: Math.ceil(maxX),
            height: Math.ceil(maxY),
        };
    }

    setWorkspaceSize(width, height) {
        if (!this.transformWrapper || !this.svg) return;
        if (width === this.workspaceWidth && height === this.workspaceHeight) return;

        this.workspaceWidth = width;
        this.workspaceHeight = height;
        this.transformWrapper.style.width = `${width}px`;
        this.transformWrapper.style.height = `${height}px`;
        this.svg.setAttribute('width', width);
        this.svg.setAttribute('height', height);
        this.svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
    }

    updateWorkspaceBounds(extraPoints = []) {
        if (!this.canvas || !this.transformWrapper || !this.svg) return;
        const bounds = this.getWorkspaceBounds(extraPoints);
        this.setWorkspaceSize(bounds.width, bounds.height);
    }

    /** Apply the current pan/zoom transform to the single wrapper (nodes + SVG). */
    applyTransform() {
        const t = `translate(${this.panX}px, ${this.panY}px) scale(${this.zoom})`;
        this.transformWrapper.style.transform = t;
    }

    /** Update the zoom percentage indicator. */
    updateZoomIndicator() {
        const el = document.getElementById('zoomLevel');
        if (el) el.textContent = `${Math.round(this.zoom * 100)}%`;
    }

    /** Zoom to a specific level, centred on the canvas midpoint. */
    setZoom(newZoom) {
        const rect = this.canvas.getBoundingClientRect();
        const cx = rect.width / 2, cy = rect.height / 2;
        const oldZoom = this.zoom;
        this.zoom = Math.min(this.maxZoom, Math.max(this.minZoom, newZoom));
        const scale = this.zoom / oldZoom;
        this.panX = cx - scale * (cx - this.panX);
        this.panY = cy - scale * (cy - this.panY);
        this.applyTransform();
        this.updateZoomIndicator();
    }

    /** Reset pan/zoom to default. */
    resetView() {
        this.panX = 0;
        this.panY = 0;
        this.zoom = 1;
        this.applyTransform();
        this.updateZoomIndicator();
    }

    setupPalette() {
        const paletteNodes = document.querySelectorAll('.palette-node');
        paletteNodes.forEach(node => {
            node.addEventListener('dragstart', (e) => {
                const nodeType = node.dataset.nodeType;
                e.dataTransfer.setData('nodeType', nodeType);
                e.dataTransfer.effectAllowed = 'copy';
            });
        });
    }

    setupEventListeners() {
        document.getElementById('btnSave').addEventListener('click', () => this.saveWorkflow());
        const autoArrangeBtn = document.getElementById('btnAutoArrange');
        if (autoArrangeBtn) {
            autoArrangeBtn.addEventListener('click', () => this.autoArrangeNodes());
        }
        const deleteConnectionBtn = document.getElementById('btnDeleteConnection');
        if (deleteConnectionBtn) {
            deleteConnectionBtn.addEventListener('click', () => this.deleteSelectedConnection());
        }
        const workflowTrackSelect = document.getElementById('workflowTrackSelect');
        if (workflowTrackSelect) {
            workflowTrackSelect.addEventListener('change', (event) => {
                const workflowId = event.target.value;
                window.location.href = `${this.config.workflowBuilderUrl}?workflow_id=${workflowId}`;
            });
        }

        window.addEventListener('beforeunload', (event) => {
            if (!this.isDirty || this.isSaving) return;
            event.preventDefault();
            event.returnValue = '';
        });

        document.addEventListener('keydown', (event) => {
            if (this.selectedConnection === null) return;
            if (this.isEditableElement(document.activeElement)) return;
            if (event.key === 'Delete' || event.key === 'Backspace') {
                event.preventDefault();
                this.deleteSelectedConnection();
            }
        });
    }

    isEditableElement(element) {
        if (!element) return false;
        const tagName = element.tagName?.toLowerCase();
        return element.isContentEditable || ['input', 'textarea', 'select'].includes(tagName);
    }

    setSaveStatus(text, tone = 'neutral') {
        const status = document.getElementById('saveStatus');
        if (!status) return;
        status.textContent = text;
        status.dataset.tone = tone;
    }

    getWorkflowSnapshot() {
        return JSON.stringify({
            nodes: this.nodes,
            connections: this.connections,
        });
    }

    syncSavedWorkflowSnapshot() {
        this.lastSavedWorkflowSnapshot = this.getWorkflowSnapshot();
        this.updateDirtyState();
    }

    updateDirtyState() {
        this.isDirty = this.lastSavedWorkflowSnapshot !== null
            && this.getWorkflowSnapshot() !== this.lastSavedWorkflowSnapshot;
        this.updateDirtyIndicator();
    }

    updateDirtyIndicator() {
        const badge = document.getElementById('dirtyIndicator');
        if (badge) {
            badge.hidden = !this.isDirty;
        }

        if (!this.isSaving) {
            if (this.isDirty) {
                this.setSaveStatus('Unsaved changes', 'warning');
            } else {
                this.setSaveStatus('Ready', 'neutral');
            }
        }
    }

    formatNodeReference(node) {
        if (!node) return 'Unknown node';
        const specificName = node.data?.name || node.data?.sub_workflow_name || node.data?.name_label || node.data?.form_name;
        return specificName
            ? `${this.getNodeTypeLabel(node.type)}: ${specificName}`
            : this.getNodeTypeLabel(node.type);
    }

    updateConnectionSelectionUI() {
        const button = document.getElementById('btnDeleteConnection');
        const status = document.getElementById('selectionStatus');
        const hasSelection = this.selectedConnection !== null && this.connections[this.selectedConnection];

        if (button) {
            button.disabled = !hasSelection;
        }

        if (!status) return;

        if (!hasSelection) {
            status.innerHTML = '';
            return;
        }

        const connection = this.connections[this.selectedConnection];
        const fromNode = this.nodes.find(node => node.id === connection.from);
        const toNode = this.nodes.find(node => node.id === connection.to);
        status.innerHTML = `
            <div class="alert alert-primary py-2 px-3 mb-0 d-flex align-items-center justify-content-between gap-2">
                <div>
                    <div class="fw-semibold"><i class="bi bi-bezier2"></i> Connection selected</div>
                    <div class="small">${this.escapeHtml(this.formatNodeReference(fromNode))} → ${this.escapeHtml(this.formatNodeReference(toNode))}</div>
                </div>
                <button type="button" class="btn btn-sm btn-outline-danger" onclick="workflowBuilder.deleteSelectedConnection()">
                    <i class="bi bi-trash"></i> Remove
                </button>
            </div>
        `;
    }

    setBuilderMessage(level, title, details = [], autoHide = false) {
        const container = document.getElementById('builderMessage');
        if (!container) return;

        const safeDetails = (details || []).slice(0, 6);
        container.innerHTML = `
            <div class="alert alert-${level} mb-2 py-2 px-3">
                <div class="fw-semibold">${this.escapeHtml(title)}</div>
                ${safeDetails.length ? `
                    <ul class="mb-0 small mt-2">
                        ${safeDetails.map(detail => `<li>${this.escapeHtml(detail)}</li>`).join('')}
                    </ul>
                ` : ''}
            </div>
        `;

        if (autoHide) {
            window.clearTimeout(this.builderMessageTimeout);
            this.builderMessageTimeout = window.setTimeout(() => {
                if (container) {
                    container.innerHTML = '';
                }
            }, 4000);
        }
    }

    updateValidationDisplay() {
        const container = document.getElementById('validationSummary');
        if (!container) return;

        const { errors, warnings } = this.validationState;
        if (errors.length) {
            container.innerHTML = `
                <div class="alert alert-danger validation-summary mb-0 py-2 px-3">
                    <div class="fw-semibold"><i class="bi bi-exclamation-triangle"></i> ${errors.length} validation error${errors.length === 1 ? '' : 's'} blocking save</div>
                    <ul class="small mb-0 mt-2">
                        ${errors.slice(0, 4).map(error => `<li>${this.escapeHtml(error)}</li>`).join('')}
                    </ul>
                </div>
            `;
            return;
        }

        if (warnings.length) {
            container.innerHTML = `
                <div class="alert alert-warning validation-summary mb-0 py-2 px-3">
                    <div class="fw-semibold"><i class="bi bi-exclamation-circle"></i> ${warnings.length} warning${warnings.length === 1 ? '' : 's'}</div>
                    <ul class="small mb-0 mt-2">
                        ${warnings.slice(0, 4).map(warning => `<li>${this.escapeHtml(warning)}</li>`).join('')}
                    </ul>
                </div>
            `;
            return;
        }

        container.innerHTML = `
            <div class="alert alert-success validation-summary mb-0 py-2 px-3">
                <div class="fw-semibold"><i class="bi bi-check-circle"></i> Builder validation looks good</div>
            </div>
        `;
    }

    async loadWorkflow() {
        try {
            console.log('Loading workflow from:', this.config.apiUrls.load);
            const response = await fetch(this.config.apiUrls.load);
            const data = await response.json();

            console.log('Workflow data received:', data);

            if (data.success) {
                this.nodes = data.workflow.nodes || [];
                this.connections = data.workflow.connections || [];
                this.fields = data.fields || [];
                this.groups = data.groups || [];
                this.forms = data.forms || [];
                this.workflowTargets = data.workflow_targets || [];

                console.log('Loaded nodes:', this.nodes);
                console.log('Loaded connections:', this.connections);
                console.log('Available forms:', this.forms);

                // Update node ID counter
                if (this.nodes.length > 0) {
                    const maxId = Math.max(...this.nodes.map(n => {
                        const match = n.id.match(/node_(\d+)/);
                        return match ? parseInt(match[1]) : 0;
                    }));
                    this.nodeIdCounter = maxId + 1;
                }

                this.initializeNodeStackOrder();
                if (this.layoutNeedsNormalization()) {
                    this.autoArrangeNodes({ suppressRender: true, silent: true });
                }
            } else {
                console.error('Failed to load workflow:', data.error);
                this.setBuilderMessage('danger', 'Failed to load workflow builder data.', [data.error || 'Unknown error']);
            }
        } catch (error) {
            console.error('Error loading workflow:', error);
            this.setBuilderMessage('danger', 'Failed to load workflow builder data.', [error.message || 'Unknown error']);
        }
    }

    async saveWorkflow() {
        const validation = this.refreshValidationState();
        if (validation.errors.length) {
            this.setSaveStatus('Fix validation errors', 'danger');
            this.setBuilderMessage(
                'danger',
                'Fix validation errors before saving.',
                validation.errors
            );
            if (validation.firstErrorNodeId) {
                this.selectNode(validation.firstErrorNodeId);
            }
            return;
        }

        const saveBtn = document.getElementById('btnSave');
        const originalText = saveBtn.innerHTML;
        this.isSaving = true;
        saveBtn.disabled = true;
        saveBtn.innerHTML = '<i class="bi bi-hourglass-split"></i> Saving...';
        this.setSaveStatus('Saving...', 'info');
        this.setBuilderMessage(
            validation.warnings.length ? 'warning' : 'info',
            validation.warnings.length
                ? 'Saving workflow with warnings.'
                : 'Saving workflow…',
            validation.warnings
        );

        const workflowData = {
            form_id: this.config.formId,
            workflow_id: this.config.currentWorkflowId,
            workflow: {
                nodes: this.nodes,
                connections: this.connections
            }
        };

        console.log('Saving workflow data:', workflowData);
        console.log('Nodes:', this.nodes);
        console.log('Connections:', this.connections);

        try {
            const response = await fetch(this.config.apiUrls.save, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.config.csrfToken
                },
                body: JSON.stringify(workflowData)
            });

            console.log('Response status:', response.status);
            console.log('Response ok:', response.ok);

            const result = await response.json();
            console.log('Response data:', result);

            if (!response.ok || !result.success) {
                const error = new Error(result.error || 'Failed to save workflow');
                error.details = result.errors || [];
                throw error;
            }

            if (result.workflow_id) {
                this.config.currentWorkflowId = result.workflow_id;
            }

            this.syncSavedWorkflowSnapshot();
            this.setSaveStatus('Saved successfully', 'success');
            this.setBuilderMessage(
                'success',
                'Workflow saved successfully.',
                validation.warnings.length ? ['Saved with non-blocking warnings shown below.'] : [],
                true
            );
            setTimeout(() => {
                this.setSaveStatus('Ready', 'neutral');
            }, 2000);
        } catch (error) {
            console.error('Error saving workflow:', error);
            this.setBuilderMessage(
                'danger',
                `Failed to save workflow: ${error.message}`,
                error.details || []
            );
            this.setSaveStatus('Error saving', 'danger');
        } finally {
            this.isSaving = false;
            saveBtn.disabled = false;
            saveBtn.innerHTML = originalText;
        }
    }

    createStartNode() {
        const node = {
            id: `node_${this.nodeIdCounter++}`,
            type: 'start',
            x: 100,
            y: 100,
            data: {}
        };
        this.nodes.push(node);
        this.bringNodeToFront(node.id);
        this.render();
    }

    createNode(type, x, y) {
        const node = {
            id: `node_${this.nodeIdCounter++}`,
            type: type,
            x: x,
            y: y,
            data: this.getDefaultNodeData(type)
        };
        this.nodes.push(node);
        this.bringNodeToFront(node.id);
        this.render();
    }

    initializeNodeStackOrder() {
        this.nodeStackOrder = new Map();
        this.nextNodeStackOrder = 1;
        this.nodes.forEach((node) => {
            this.nodeStackOrder.set(node.id, this.nextNodeStackOrder++);
        });
    }

    bringNodeToFront(nodeId) {
        if (!nodeId) return;
        this.nodeStackOrder.set(nodeId, this.nextNodeStackOrder++);
    }

    getEstimatedNodeWidth(type) {
        switch (type) {
            case 'workflow_settings':
                return 320;
            case 'form':
            case 'sub_workflow':
                return 300;
            case 'stage':
            case 'approval':
            case 'approval_config':
                return 280;
            case 'action':
            case 'email':
            case 'condition':
                return 260;
            case 'join':
                return 140;
            case 'start':
            case 'end':
                return 180;
            default:
                return 240;
        }
    }

    getEstimatedNodeHeight(type) {
        switch (type) {
            case 'workflow_settings':
                return 180;
            case 'form':
            case 'sub_workflow':
                return 170;
            case 'stage':
            case 'approval':
            case 'approval_config':
                return 160;
            case 'action':
            case 'email':
            case 'condition':
                return 150;
            case 'join':
                return 96;
            default:
                return 140;
        }
    }

    nodesOverlap(a, b, padding = 16) {
        const aWidth = this.getEstimatedNodeWidth(a.type);
        const aHeight = this.getEstimatedNodeHeight(a.type);
        const bWidth = this.getEstimatedNodeWidth(b.type);
        const bHeight = this.getEstimatedNodeHeight(b.type);

        return !(
            a.x + aWidth + padding <= b.x
            || b.x + bWidth + padding <= a.x
            || a.y + aHeight + padding <= b.y
            || b.y + bHeight + padding <= a.y
        );
    }

    layoutNeedsNormalization() {
        const nodes = [...this.nodes];
        const sameLaneThreshold = 110;
        const minimumGap = 56;

        for (let i = 0; i < nodes.length; i++) {
            for (let j = i + 1; j < nodes.length; j++) {
                if (this.nodesOverlap(nodes[i], nodes[j], 20)) {
                    return true;
                }
            }
        }

        const byLane = [...nodes].sort((a, b) => (a.y - b.y) || (a.x - b.x));
        for (let i = 1; i < byLane.length; i++) {
            const prev = byLane[i - 1];
            const current = byLane[i];
            if (Math.abs(current.y - prev.y) > sameLaneThreshold || current.x < prev.x) {
                continue;
            }
            const requiredX = prev.x + this.getEstimatedNodeWidth(prev.type) + minimumGap;
            if (current.x < requiredX) {
                return true;
            }
        }

        return false;
    }

    resolveNodeCollisions() {
        const sortedNodes = [...this.nodes].sort((a, b) => (a.x - b.x) || (a.y - b.y));

        sortedNodes.forEach((node, index) => {
            let attempts = 0;
            while (attempts < 24) {
                const blockingNode = sortedNodes
                    .slice(0, index)
                    .find((candidate) => this.nodesOverlap(candidate, node, 12));
                if (!blockingNode) {
                    break;
                }

                const sameLane = Math.abs(blockingNode.y - node.y) <= 110;
                if (sameLane) {
                    node.x = Math.max(
                        node.x,
                        blockingNode.x + this.getEstimatedNodeWidth(blockingNode.type) + 72,
                    );
                } else {
                    node.y = Math.max(
                        node.y,
                        blockingNode.y + this.getEstimatedNodeHeight(blockingNode.type) + 52,
                    );
                }
                attempts += 1;
            }
        });
    }

    autoArrangeNodes(options = {}) {
        const { suppressRender = false, silent = false } = options;
        if (!this.nodes.length) return;

        const laneThreshold = 120;
        const horizontalGap = 84;
        const sortedByY = [...this.nodes].sort((a, b) => (a.y - b.y) || (a.x - b.x));
        const lanes = [];

        sortedByY.forEach((node) => {
            let lane = lanes.find((candidate) => Math.abs(candidate.centerY - node.y) <= laneThreshold);
            if (!lane) {
                lane = { centerY: node.y, nodes: [] };
                lanes.push(lane);
            }
            lane.nodes.push(node);
            lane.centerY = Math.round(lane.nodes.reduce((total, entry) => total + entry.y, 0) / lane.nodes.length);
        });

        lanes
            .sort((a, b) => a.centerY - b.centerY)
            .forEach((lane) => {
                lane.nodes.sort((a, b) => a.x - b.x);
                let cursorX = Math.max(80, lane.nodes[0]?.x || 80);
                lane.nodes.forEach((node, index) => {
                    if (index === 0) {
                        node.x = Math.max(80, node.x);
                    } else {
                        node.x = Math.max(node.x, cursorX);
                    }
                    cursorX = node.x + this.getEstimatedNodeWidth(node.type) + horizontalGap;
                });
            });

        this.resolveNodeCollisions();
        this.updateWorkspaceBounds();

        if (!silent) {
            this.setBuilderMessage(
                'info',
                'Workflow layout auto-arranged.',
                ['Nodes were spaced out to reduce overlap and make dragging easier.'],
                true,
            );
        }

        if (!suppressRender) {
            this.render();
        }
    }

    getDefaultNodeData(type) {
        switch (type) {
            case 'form':
                return {
                    form_id: null,
                    form_name: 'Select Form',
                    form_builder_url: '#',
                    field_count: 0,
                    fields: [],
                    has_more_fields: false,
                    is_initial: false,
                };
            case 'stage':
                return {
                    stage_id: null,
                    name: 'New Stage',
                    order: 1,
                    approval_logic: 'all',
                    requires_manager_approval: false,
                    allow_send_back: false,
                    allow_reassign: false,
                    allow_edit_form_data: false,
                    approve_label: '',
                    assignee_form_field: '',
                    assignee_lookup_type: 'email',
                    validate_assignee_group: true,
                    trigger_conditions: null,
                    approval_fields: [],
                    approval_groups: [],
                };
            case 'workflow_settings':
                return {
                    name_label: '',
                    requires_approval: true,
                    approval_deadline_days: null,
                    send_reminder_after_days: null,
                    auto_approve_after_days: null,
                    notification_cadence: 'immediate',
                    notification_cadence_day: null,
                    notification_cadence_time: '',
                    notification_cadence_form_field: '',
                    trigger_conditions: null,
                    notification_rules: [],
                };
            case 'condition':
                return {
                    field: '',
                    operator: 'equals',
                    value: '',
                    true_path: '',
                    false_path: ''
                };
            case 'action':
                return {
                    name: 'New Action',
                    action_type: 'database',
                    trigger: 'on_approve',
                    config: {}
                };
            case 'email':
                return {
                    name: 'Send Email',
                    email_to: '',
                    email_to_field: '',
                    email_cc: '',
                    email_cc_field: '',
                    email_subject_template: '',
                    email_body_template: '',
                    email_template_name: '',
                    trigger: 'on_approve'
                };
            case 'sub_workflow':
                return {
                    sub_workflow_def_id: null,
                    sub_workflow_id: null,
                    sub_workflow_form_id: null,
                    sub_workflow_name: '',
                    section_label: '',
                    count_field: '',
                    label_template: 'Sub-workflow {index}',
                    trigger: 'on_approval',
                    data_prefix: '',
                    detached: false,
                    reject_parent: false,
                };
            case 'join':
                return {};
            case 'end':
                return {
                    status: 'approved'
                };
            default:
                return {};
        }
    }

    deleteNode(nodeId) {
        if (confirm('Delete this node?')) {
            this.nodes = this.nodes.filter(n => n.id !== nodeId);
            this.connections = this.connections.filter(c => c.from !== nodeId && c.to !== nodeId);
            this.deselectAll();
            this.render();
        }
    }

    selectNode(nodeId) {
        this.deselectAll();
        this.selectedNode = nodeId;
        this.selectedConnection = null;
        const node = this.nodes.find(n => n.id === nodeId);
        if (node) {
            this.refreshValidationState();
            this.showNodeProperties(node);
        }
        this.updateConnectionSelectionUI();
        this.render();
    }

    deselectAll() {
        this.selectedNode = null;
        this.selectedConnection = null;
        this.showEmptyProperties();
        this.updateConnectionSelectionUI();
        this.render();
    }

    selectConnection(index) {
        if (!this.connections[index]) return;
        this.selectedNode = null;
        this.selectedConnection = index;
        this.showEmptyProperties();
        this.updateConnectionSelectionUI();
        this.render();
    }

    deleteSelectedConnection() {
        if (this.selectedConnection === null || !this.connections[this.selectedConnection]) return;
        this.connections.splice(this.selectedConnection, 1);
        this.selectedConnection = null;
        this.updateConnectionSelectionUI();
        this.render();
    }

    showNodeProperties(node) {
        const content = document.getElementById('propertiesContent');
        content.innerHTML = this.buildPropertiesForm(node);

        // Add event listeners for property changes
        content.querySelectorAll('input, select, textarea').forEach(input => {
            input.addEventListener('change', (e) => {
                this.updateNodeProperty(node.id, e.target.name, e.target.value);
            });
        });
    }

    showEmptyProperties() {
        const content = document.getElementById('propertiesContent');
        content.innerHTML = `
            <div class="properties-empty">
                <i class="bi bi-info-circle properties-empty-icon"></i>
                <p>Select a node to edit its properties</p>
            </div>
        `;
    }

    buildPropertiesForm(node) {
        let html = `<h6 class="mb-3">${this.getNodeTypeLabel(node.type)}</h6>`;
        html += this.buildNodeIssuesAlert(node);

        switch (node.type) {
            case 'start':
                html += '<p class="text-muted">This is the workflow start point.</p>';
                break;

            case 'form':
                html += this.buildFormProperties(node);
                break;

            case 'workflow_settings':
                html += this.buildWorkflowSettingsProperties(node);
                break;

            case 'stage':
                html += this.buildStageProperties(node);
                break;


            case 'approval':
                html += this.buildApprovalProperties(node);
                break;

            case 'condition':
                html += this.buildConditionProperties(node);
                break;

            case 'action':
                html += this.buildActionProperties(node);
                break;

            case 'email':
                html += this.buildEmailProperties(node);
                break;

            case 'sub_workflow':
                html += this.buildSubWorkflowProperties(node);
                break;

            case 'join':
                html += '<div class="alert alert-secondary"><i class="bi bi-info-circle"></i> This join node automatically merges parallel approval stages. It cannot be edited or removed independently.</div>';
                break;

            case 'end':
                html += this.buildEndProperties(node);
                break;
        }

        return html;
    }

    buildStageProperties(node) {
        const data = node.data || {};
        const orderedApprovalGroups = this.getNormalizedStageApprovalGroups(data.approval_groups || []);
        const selectedGroupIds = orderedApprovalGroups.map(g => g.id);
        const selectedApprovalFieldIds = new Set((data.approval_fields || []).map(field => field.id));

        const basicsSection = `
            <div class="mb-3">
                <label class="form-label"><strong>Stage Name</strong></label>
                <input type="text" class="form-control" name="name"
                       value="${this.escapeHtml(data.name || '')}"
                       onchange="workflowBuilder.updateStageConfig('${node.id}')" />
            </div>

            <div class="mb-3">
                <label class="form-label"><strong>Order</strong></label>
                <input type="number" class="form-control" name="order" min="1"
                       value="${data.order || 1}"
                       onchange="workflowBuilder.updateStageConfig('${node.id}')" />
                <small class="text-muted">Stages with the same order number run in parallel (fork/join).</small>
            </div>

            <div class="mb-3">
                <label class="form-label"><strong>Approve Button Label</strong></label>
                <input type="text" class="form-control" name="approve_label"
                       value="${this.escapeHtml(data.approve_label || '')}"
                       placeholder="Approve"
                       onchange="workflowBuilder.updateStageConfig('${node.id}')" />
                <small class="text-muted">Custom label for the approve button (e.g. "Sign Off")</small>
            </div>

            <div class="mb-3">
                <div class="form-check form-switch">
                    <input class="form-check-input" type="checkbox" id="stage_requires_manager_${node.id}"
                           name="requires_manager_approval" ${data.requires_manager_approval ? 'checked' : ''}
                           onchange="workflowBuilder.updateStageConfig('${node.id}')">
                    <label class="form-check-label" for="stage_requires_manager_${node.id}">
                        <i class="bi bi-person-badge"></i> <strong>Require Manager Approval</strong>
                    </label>
                </div>
            </div>

            <div class="mb-3">
                <div class="form-check form-switch">
                    <input class="form-check-input" type="checkbox" id="stage_allow_send_back_${node.id}"
                           name="allow_send_back" ${data.allow_send_back ? 'checked' : ''}
                           onchange="workflowBuilder.updateStageConfig('${node.id}')">
                    <label class="form-check-label" for="stage_allow_send_back_${node.id}">
                        <i class="bi bi-arrow-return-left"></i> <strong>Allow Send Back to This Stage</strong>
                    </label>
                </div>
                <small class="text-muted">Later stages can return submissions here for correction without rejecting the workflow.</small>
            </div>

            <div class="mb-3">
                <div class="form-check form-switch">
                    <input class="form-check-input" type="checkbox" id="stage_allow_reassign_${node.id}"
                           name="allow_reassign" ${data.allow_reassign ? 'checked' : ''}
                           onchange="workflowBuilder.updateStageConfig('${node.id}')">
                    <label class="form-check-label" for="stage_allow_reassign_${node.id}">
                        <i class="bi bi-arrow-left-right"></i> <strong>Allow Reassignment</strong>
                    </label>
                </div>
                <small class="text-muted">Allow current reviewers to reassign tasks to another eligible member of the stage groups.</small>
            </div>

            <div class="mb-3">
                <div class="form-check form-switch">
                    <input class="form-check-input" type="checkbox" id="stage_allow_edit_form_data_${node.id}"
                           name="allow_edit_form_data" ${data.allow_edit_form_data ? 'checked' : ''}
                           onchange="workflowBuilder.updateStageConfig('${node.id}')">
                    <label class="form-check-label" for="stage_allow_edit_form_data_${node.id}">
                        <i class="bi bi-pencil-square"></i> <strong>Allow Reviewer Edits</strong>
                    </label>
                </div>
                <small class="text-muted">Approvers at this stage may edit the original submission while reviewing it.</small>
            </div>
        `;

        const routingSection = `
            <div class="mb-3">
                <label class="form-label"><i class="bi bi-people"></i> <strong>Approval Groups</strong></label>
                <select class="form-select builder-multiselect-lg" id="stage_groups_${node.id}" name="approval_groups" multiple size="6"
                        onchange="workflowBuilder.updateStageConfig('${node.id}')">
        `;

        this.groups.forEach(group => {
            const selected = selectedGroupIds.includes(group.id) ? 'selected' : '';
            html += `<option value="${group.id}" ${selected}>${this.escapeHtml(group.name)}</option>`;
        });

        html += `
                </select>
                <small class="text-muted d-block mt-1">Hold Ctrl/Cmd to select multiple groups.</small>
            </div>

            ${this.buildStageApprovalOrderEditor(node, orderedApprovalGroups)}

            <div class="mb-3">
                <label class="form-label">Approval Logic</label>
                <select class="form-select" name="approval_logic"
                        onchange="workflowBuilder.updateStageConfig('${node.id}')">
                    <option value="any" ${data.approval_logic === 'any' ? 'selected' : ''}>Any (OR)</option>
                    <option value="all" ${data.approval_logic === 'all' ? 'selected' : ''}>All (AND)</option>
                    <option value="sequence" ${data.approval_logic === 'sequence' ? 'selected' : ''}>Sequential</option>
                </select>
            </div>
        `;

        const approvalFieldsSection = `
            <div class="mb-3">
                <label class="form-label"><strong>Fields shown during this stage</strong></label>
                <select class="form-select builder-multiselect-lg" id="stage_fields_${node.id}" name="approval_fields" multiple size="6"
                        onchange="workflowBuilder.updateStageConfig('${node.id}')">
                    ${this.fields.map(field => `
                        <option value="${field.id}" ${selectedApprovalFieldIds.has(field.id) ? 'selected' : ''}>${this.escapeHtml(field.field_label)} (${field.field_name})</option>
                    `).join('')}
                </select>
                <small class="text-muted d-block mt-1">Selected fields become editable approval-step fields for this stage only.</small>
            </div>
        `;

        const assigneeSection = `
            <div class="mb-3">
                <label class="form-label"><strong>Assignee Field</strong></label>
                <select class="form-select" name="assignee_form_field"
                        onchange="workflowBuilder.updateStageConfig('${node.id}')">
                    <option value="">-- Use approval groups --</option>
                    ${this.fields.map(f => `
                        <option value="${f.field_name}" ${data.assignee_form_field === f.field_name ? 'selected' : ''}>${this.escapeHtml(f.field_label)} (${f.field_name})</option>
                    `).join('')}
                </select>
                <small class="text-muted">When selected, the stage resolves the approver from a submitted form field before falling back to approval groups.</small>
            </div>

            <div class="mb-3">
                <label class="form-label"><strong>Lookup Type</strong></label>
                <select class="form-select" name="assignee_lookup_type"
                        onchange="workflowBuilder.updateStageConfig('${node.id}')">
                    <option value="email" ${data.assignee_lookup_type === 'email' ? 'selected' : ''}>Email address</option>
                    <option value="username" ${data.assignee_lookup_type === 'username' ? 'selected' : ''}>Username</option>
                    <option value="full_name" ${data.assignee_lookup_type === 'full_name' ? 'selected' : ''}>Full name</option>
                    <option value="ldap" ${data.assignee_lookup_type === 'ldap' ? 'selected' : ''}>LDAP display name</option>
                </select>
            </div>

            <div class="mb-3">
                <div class="form-check form-switch">
                    <input class="form-check-input" type="checkbox" id="stage_validate_assignee_group_${node.id}"
                           name="validate_assignee_group" ${data.validate_assignee_group !== false ? 'checked' : ''}
                           onchange="workflowBuilder.updateStageConfig('${node.id}')">
                    <label class="form-check-label" for="stage_validate_assignee_group_${node.id}">
                        <strong>Require Assignee to Belong to Stage Groups</strong>
                    </label>
                </div>
            </div>
        `;

        return `
            <div class="alert alert-info">
                <i class="bi bi-info-circle"></i> Configure an approval stage with its own groups and logic.
            </div>
            ${this.buildPropertySection('Stage Basics', basicsSection, {
                icon: 'diagram-3',
                description: 'Set the stage name, order, button label, and reviewer capabilities.',
            })}
            ${this.buildPropertySection('Approver Routing', routingSection, {
                icon: 'people',
                description: 'Choose which groups approve and whether they act together, separately, or in sequence.',
            })}
            ${this.buildPropertySection('Approval-Only Fields', approvalFieldsSection, {
                icon: 'ui-checks-grid',
                description: 'Limit extra editable fields to this approval step.',
            })}
            ${this.buildPropertySection('Dynamic Assignee', assigneeSection, {
                icon: 'person-badge',
                description: 'Resolve approvers from submitted form data when needed.',
            })}
            ${this.buildTriggerConditionsEditor(node, 'Stage trigger conditions')}
        `;
    }

    getNormalizedStageApprovalGroups(groups) {
        return [...(groups || [])]
            .filter(group => group && group.id)
            .sort((a, b) => {
                const posA = a.position ?? 0;
                const posB = b.position ?? 0;
                if (posA !== posB) return posA - posB;
                return (a.name || '').localeCompare(b.name || '');
            })
            .map((group, index) => ({ ...group, position: index }));
    }

    buildStageApprovalOrderEditor(node, orderedGroups) {
        if (!orderedGroups.length) {
            return `
                <div class="alert alert-secondary small">
                    Select one or more approval groups above. For sequential stages, the order shown here controls which group is asked first.
                </div>
            `;
        }

        return `
            <div class="mb-3">
                <label class="form-label"><strong>Approval Group Order</strong></label>
                <div class="list-group">
                    ${orderedGroups.map((group, index) => `
                        <div class="list-group-item d-flex justify-content-between align-items-center py-2">
                            <div>
                                <span class="badge bg-secondary me-2">${index + 1}</span>
                                ${this.escapeHtml(group.name)}
                            </div>
                            <div class="btn-group btn-group-sm" role="group">
                                <button type="button" class="btn btn-outline-secondary" ${index === 0 ? 'disabled' : ''}
                                        onclick="workflowBuilder.moveStageApprovalGroup('${node.id}', ${group.id}, -1)">
                                    <i class="bi bi-arrow-up"></i>
                                </button>
                                <button type="button" class="btn btn-outline-secondary" ${index === orderedGroups.length - 1 ? 'disabled' : ''}
                                        onclick="workflowBuilder.moveStageApprovalGroup('${node.id}', ${group.id}, 1)">
                                    <i class="bi bi-arrow-down"></i>
                                </button>
                            </div>
                        </div>
                    `).join('')}
                </div>
                <small class="text-muted d-block mt-1">This order is used when the stage logic is <strong>Sequential</strong>.</small>
            </div>
        `;
    }

    buildWorkflowSettingsProperties(node) {
        const data = node.data || {};

        const basicsSection = `
            <div class="mb-3">
                <label class="form-label">Workflow Track Label</label>
                <input type="text" class="form-control" name="name_label"
                       value="${this.escapeHtml(data.name_label || '')}"
                       placeholder="e.g. Finance Approval"
                       onchange="workflowBuilder.updateWorkflowSettings('${node.id}')" />
                <small class="text-muted">Helpful when a form has multiple workflow tracks.</small>
            </div>
        `;

        const timingSection = `
            <div class="mb-3">
                <label class="form-label">Approval Deadline (days)</label>
                <input type="number" class="form-control" name="approval_deadline_days" min="1"
                       value="${data.approval_deadline_days || ''}" placeholder="No deadline"
                       onchange="workflowBuilder.updateWorkflowSettings('${node.id}')" />
            </div>
            <div class="mb-3">
                <label class="form-label">Send Reminder After (days)</label>
                <input type="number" class="form-control" name="send_reminder_after_days" min="1"
                       value="${data.send_reminder_after_days || ''}" placeholder="No reminder"
                       onchange="workflowBuilder.updateWorkflowSettings('${node.id}')" />
            </div>
            <div class="mb-3">
                <label class="form-label">Auto-Approve After (days)</label>
                <input type="number" class="form-control" name="auto_approve_after_days" min="1"
                       value="${data.auto_approve_after_days || ''}" placeholder="Never"
                       onchange="workflowBuilder.updateWorkflowSettings('${node.id}')" />
            </div>
            <div class="mb-3">
                <label class="form-label">Notification Cadence</label>
                <select class="form-select" name="notification_cadence"
                        onchange="workflowBuilder.updateWorkflowSettings('${node.id}')">
                    <option value="immediate" ${data.notification_cadence === 'immediate' ? 'selected' : ''}>Immediate</option>
                    <option value="daily" ${data.notification_cadence === 'daily' ? 'selected' : ''}>Daily Digest</option>
                    <option value="weekly" ${data.notification_cadence === 'weekly' ? 'selected' : ''}>Weekly Digest</option>
                    <option value="monthly" ${data.notification_cadence === 'monthly' ? 'selected' : ''}>Monthly Digest</option>
                    <option value="form_field_date" ${data.notification_cadence === 'form_field_date' ? 'selected' : ''}>On Date From Form Field</option>
                </select>
            </div>

            <div class="mb-3">
                <label class="form-label">Digest Day</label>
                <input type="number" class="form-control" name="notification_cadence_day" min="0" max="31"
                       value="${data.notification_cadence_day || ''}" placeholder="Weekly: 0-6, Monthly: 1-31"
                       onchange="workflowBuilder.updateWorkflowSettings('${node.id}')" />
                <small class="text-muted">Used for weekly and monthly cadences only.</small>
            </div>

            <div class="mb-3">
                <label class="form-label">Digest Time</label>
                <input type="time" class="form-control" name="notification_cadence_time"
                       value="${this.escapeHtml(data.notification_cadence_time || '')}"
                       onchange="workflowBuilder.updateWorkflowSettings('${node.id}')" />
            </div>

            <div class="mb-3">
                <label class="form-label">Date Field</label>
                <select class="form-select" name="notification_cadence_form_field"
                        onchange="workflowBuilder.updateWorkflowSettings('${node.id}')">
                    <option value="">-- Select a date field --</option>
                    ${this.fields.map(f => `
                        <option value="${f.field_name}" ${data.notification_cadence_form_field === f.field_name ? 'selected' : ''}>${this.escapeHtml(f.field_label)} (${f.field_name})</option>
                    `).join('')}
                </select>
                <small class="text-muted">Used only when cadence is “On Date From Form Field”.</small>
            </div>
        `;

        return `
            <div class="alert alert-info">
                <i class="bi bi-info-circle"></i> Workflow-level notification and deadline settings.
            </div>
            ${this.buildPropertySection('Workflow Identity', basicsSection, {
                icon: 'signpost-split',
                description: 'Label this track so admins can tell multiple workflow paths apart.',
            })}
            ${this.buildPropertySection('Timing, Deadlines & Notifications', timingSection, {
                icon: 'clock-history',
                description: 'Control deadlines, reminders, digests, and date-driven notifications.',
            })}
            ${this.buildNotificationRulesEditor(node)}
            ${this.buildTriggerConditionsEditor(node, 'Workflow trigger conditions')}
        `;
    }

    getNotificationRuleStageOptions() {
        return this.nodes
            .filter(node => node.type === 'stage')
            .map(node => ({
                nodeId: node.id,
                stageId: node.data?.stage_id || null,
                name: node.data?.name || 'Unnamed Stage',
                order: node.data?.order || 0,
            }))
            .sort((a, b) => (a.order - b.order) || a.name.localeCompare(b.name));
    }

    getNotificationRuleState(rule) {
        return {
            rule_id: rule?.rule_id || null,
            stage_id: rule?.stage_id || null,
            stage_node_id: rule?.stage_node_id || '',
            event: rule?.event || 'approval_request',
            subject_template: rule?.subject_template || '',
            notify_submitter: !!rule?.notify_submitter,
            email_field: rule?.email_field || '',
            static_emails: rule?.static_emails || '',
            notify_stage_assignees: !!rule?.notify_stage_assignees,
            notify_stage_groups: !!rule?.notify_stage_groups,
            notify_groups: (rule?.notify_groups || []).map(group => ({
                id: typeof group === 'object' ? group.id : group,
                name: typeof group === 'object' ? group.name : String(group),
            })).filter(group => group.id),
            conditions: rule?.conditions || null,
        };
    }

    buildNotificationRulesEditor(node) {
        const rules = (node.data.notification_rules || []).map(rule => this.getNotificationRuleState(rule));
        const stageOptions = this.getNotificationRuleStageOptions();
        const eventOptions = [
            ['submission_received', 'Submission Received'],
            ['approval_request', 'Approval Request'],
            ['stage_decision', 'Stage Decision'],
            ['workflow_approved', 'Workflow Approved'],
            ['workflow_denied', 'Workflow Denied'],
            ['form_withdrawn', 'Form Withdrawn'],
        ];

        const content = `
            ${(rules.length ? rules : [null]).map((rule, index) => {
                const state = this.getNotificationRuleState(rule || {});
                const selectedGroupIds = new Set((state.notify_groups || []).map(group => group.id));
                return `
                    <div class="card mb-3 notification-rule-card" data-rule-index="${index}" data-rule-id="${state.rule_id || ''}">
                        <div class="card-body py-3">
                            <div class="d-flex justify-content-between align-items-center mb-2">
                                <h6 class="mb-0">Rule ${index + 1}</h6>
                                ${rules.length ? `
                                    <button type="button" class="btn btn-sm btn-outline-danger"
                                            onclick="workflowBuilder.removeNotificationRule('${node.id}', ${index})">
                                        Remove
                                    </button>
                                ` : ''}
                            </div>
                            <div class="mb-3">
                                <label class="form-label form-label-sm">Scope</label>
                                <select class="form-select form-select-sm" name="notification_rule_stage"
                                        onchange="workflowBuilder.updateNotificationRules('${node.id}')">
                                    <option value="">Workflow-level</option>
                                    ${stageOptions.map(option => `
                                        <option value="${option.nodeId}" ${state.stage_node_id === option.nodeId ? 'selected' : ''}>Stage ${option.order}: ${this.escapeHtml(option.name)}</option>
                                    `).join('')}
                                </select>
                            </div>
                            <div class="mb-3">
                                <label class="form-label form-label-sm">Event</label>
                                <select class="form-select form-select-sm" name="notification_rule_event"
                                        onchange="workflowBuilder.updateNotificationRules('${node.id}')">
                                    ${eventOptions.map(([value, label]) => `
                                        <option value="${value}" ${state.event === value ? 'selected' : ''}>${label}</option>
                                    `).join('')}
                                </select>
                            </div>
                            <div class="mb-3">
                                <label class="form-label form-label-sm">Subject Template</label>
                                <input type="text" class="form-control form-control-sm" name="notification_rule_subject_template"
                                       value="${this.escapeHtml(state.subject_template)}"
                                       placeholder="Submission Approved: {form_name} (ID {submission_id})"
                                       onchange="workflowBuilder.updateNotificationRules('${node.id}')" />
                            </div>
                            <div class="mb-3">
                                <label class="form-label form-label-sm">Email Field</label>
                                <select class="form-select form-select-sm" name="notification_rule_email_field"
                                        onchange="workflowBuilder.updateNotificationRules('${node.id}')">
                                    <option value="">-- None --</option>
                                    ${this.fields.map(field => `
                                        <option value="${field.field_name}" ${state.email_field === field.field_name ? 'selected' : ''}>${this.escapeHtml(field.field_label)} (${field.field_name})</option>
                                    `).join('')}
                                </select>
                            </div>
                            <div class="mb-3">
                                <label class="form-label form-label-sm">Static Emails</label>
                                <input type="text" class="form-control form-control-sm" name="notification_rule_static_emails"
                                       value="${this.escapeHtml(state.static_emails)}"
                                       placeholder="ops@example.com, owner@example.com"
                                       onchange="workflowBuilder.updateNotificationRules('${node.id}')" />
                            </div>
                            <div class="mb-3">
                                <label class="form-label form-label-sm">Additional Groups</label>
                                <select class="form-select form-select-sm" name="notification_rule_notify_groups" multiple size="4"
                                        onchange="workflowBuilder.updateNotificationRules('${node.id}')">
                                    ${this.groups.map(group => `
                                        <option value="${group.id}" ${selectedGroupIds.has(group.id) ? 'selected' : ''}>${this.escapeHtml(group.name)}</option>
                                    `).join('')}
                                </select>
                            </div>
                            <div class="row g-2 mb-3">
                                <div class="col-12 col-md-6">
                                    <div class="form-check form-switch">
                                        <input class="form-check-input" type="checkbox" name="notification_rule_notify_submitter"
                                               ${state.notify_submitter ? 'checked' : ''}
                                               onchange="workflowBuilder.updateNotificationRules('${node.id}')">
                                        <label class="form-check-label">Notify submitter</label>
                                    </div>
                                </div>
                                <div class="col-12 col-md-6">
                                    <div class="form-check form-switch">
                                        <input class="form-check-input" type="checkbox" name="notification_rule_notify_stage_assignees"
                                               ${state.notify_stage_assignees ? 'checked' : ''}
                                               onchange="workflowBuilder.updateNotificationRules('${node.id}')">
                                        <label class="form-check-label">Notify stage assignees</label>
                                    </div>
                                </div>
                                <div class="col-12 col-md-6">
                                    <div class="form-check form-switch">
                                        <input class="form-check-input" type="checkbox" name="notification_rule_notify_stage_groups"
                                               ${state.notify_stage_groups ? 'checked' : ''}
                                               onchange="workflowBuilder.updateNotificationRules('${node.id}')">
                                        <label class="form-check-label">Notify stage groups</label>
                                    </div>
                                </div>
                            </div>
                            ${this.buildConditionsEditor({
                                title: 'Rule conditions',
                                conditions: state.conditions,
                                onChangeHandler: `workflowBuilder.updateNotificationRules('${node.id}')`,
                                editorKind: 'notification-rule',
                                extraAttributes: `data-rule-index="${index}"`,
                                removeConditionHandler: `workflowBuilder.removeNotificationRuleCondition('${node.id}', ${index}, __INDEX__)`,
                            })}
                            <button type="button" class="btn btn-sm btn-outline-primary"
                                    onclick="workflowBuilder.addNotificationRuleCondition('${node.id}', ${index})">
                                <i class="bi bi-plus-lg"></i> Add Rule Condition
                            </button>
                        </div>
                    </div>
                `;
            }).join('')}
            <button type="button" class="btn btn-sm btn-outline-primary" onclick="workflowBuilder.addNotificationRule('${node.id}')">
                <i class="bi bi-plus-lg"></i> Add Notification Rule
            </button>
        `;

        return this.buildPropertySection('Notification Rules', content, {
            icon: 'bell',
            description: 'Configure event-driven recipients here instead of dropping to Django Admin.',
        });
    }

    getNormalizedTriggerConditions(rawConditions) {
        if (!rawConditions) {
            return { operator: 'AND', conditions: [] };
        }

        if (Array.isArray(rawConditions.conditions)) {
            return {
                operator: (rawConditions.operator || 'AND').toUpperCase() === 'OR' ? 'OR' : 'AND',
                conditions: rawConditions.conditions.map(condition => ({
                    field: condition.field || '',
                    operator: condition.operator || 'equals',
                    value: condition.value ?? ''
                }))
            };
        }

        if (rawConditions.field) {
            return {
                operator: 'AND',
                conditions: [{
                    field: rawConditions.field || '',
                    operator: rawConditions.operator || 'equals',
                    value: rawConditions.value ?? ''
                }]
            };
        }

        return { operator: 'AND', conditions: [] };
    }

    buildConditionsEditor({ title, conditions, onChangeHandler, editorKind, extraAttributes = '', removeConditionHandler = null, showHeader = true }) {
        const state = this.getNormalizedTriggerConditions(conditions);
        const operatorOptions = [
            ['equals', 'Equals'],
            ['not_equals', 'Not equals'],
            ['contains', 'Contains'],
            ['in', 'In list'],
            ['gt', 'Greater than'],
            ['gte', 'Greater than or equal'],
            ['lt', 'Less than'],
            ['lte', 'Less than or equal'],
            ['is_empty', 'Is empty'],
            ['not_empty', 'Is not empty'],
        ];

        let rowsHtml = '';
        state.conditions.forEach((condition, index) => {
            const operator = condition.operator || 'equals';
            const needsValue = !['is_empty', 'not_empty'].includes(operator);
            rowsHtml += `
                <div class="border rounded p-2 mb-2 trigger-condition-row" data-index="${index}">
                    <div class="mb-2">
                        <label class="form-label form-label-sm mb-1">Field</label>
                        <select class="form-select form-select-sm" name="condition_field"
                                onchange="${onChangeHandler}">
                            <option value="">-- Select field --</option>
                            ${this.fields.map(field => `
                                <option value="${field.field_name}" ${condition.field === field.field_name ? 'selected' : ''}>${this.escapeHtml(field.field_label)} (${field.field_name})</option>
                            `).join('')}
                        </select>
                    </div>
                    <div class="mb-2">
                        <label class="form-label form-label-sm mb-1">Operator</label>
                        <select class="form-select form-select-sm" name="condition_operator"
                                onchange="${onChangeHandler}">
                            ${operatorOptions.map(([value, label]) => `
                                <option value="${value}" ${operator === value ? 'selected' : ''}>${label}</option>
                            `).join('')}
                        </select>
                    </div>
                    <div class="mb-2">
                        <label class="form-label form-label-sm mb-1">Value</label>
                        <input type="text" class="form-control form-control-sm" name="condition_value"
                               value="${this.escapeHtml(condition.value ?? '')}"
                               placeholder="${operator === 'in' ? 'Comma-separated values' : 'Comparison value'}"
                               ${needsValue ? '' : 'disabled'}
                               onchange="${onChangeHandler}" />
                    </div>
                    ${removeConditionHandler ? `
                    <div class="text-end">
                        <button type="button" class="btn btn-sm btn-outline-danger"
                                onclick="${removeConditionHandler.replace('__INDEX__', String(index))}">
                            Remove
                        </button>
                    </div>
                    ` : ''}
                </div>
            `;
        });

        if (!rowsHtml) {
            rowsHtml = '<p class="text-muted small mb-2">Always run unless you add at least one condition.</p>';
        }

        return `
            ${showHeader ? `<hr /><h6>${this.escapeHtml(title)}</h6>` : ''}
            <div class="conditions-editor" data-editor-kind="${editorKind}" ${extraAttributes}>
            <div class="mb-2">
                <label class="form-label form-label-sm">Match mode</label>
                <select class="form-select form-select-sm" name="condition_group_operator"
                        onchange="${onChangeHandler}">
                    <option value="AND" ${state.operator === 'AND' ? 'selected' : ''}>All conditions must match (AND)</option>
                    <option value="OR" ${state.operator === 'OR' ? 'selected' : ''}>Any condition may match (OR)</option>
                </select>
            </div>
            ${rowsHtml}
            </div>
        `;
    }

    buildTriggerConditionsEditor(node, title) {
        const content = `
            ${this.buildConditionsEditor({
                title,
                conditions: node.data.trigger_conditions,
                onChangeHandler: `workflowBuilder.updateNodeTriggerConditions('${node.id}')`,
                editorKind: 'node-trigger',
                removeConditionHandler: `workflowBuilder.removeTriggerCondition('${node.id}', __INDEX__)`,
                showHeader: false,
            })}
            <button type="button" class="btn btn-sm btn-outline-primary"
                    onclick="workflowBuilder.addTriggerCondition('${node.id}')">
                <i class="bi bi-plus-lg"></i> Add Condition
            </button>
        `;

        return this.buildPropertySection(title, content, {
            icon: 'funnel',
            description: 'Only apply this node when the submitted data matches these conditions.',
        });
    }


    buildFormProperties(node) {
        const data = node.data || {};
        const fields = data.fields || [];
        const hasMoreFields = data.has_more_fields || false;
        const isInitial = data.is_initial !== false;  // Initial form node (default true for backward compatibility)

        let html = `
            <div class="alert alert-info">
                <i class="bi bi-info-circle"></i> This node represents ${isInitial ? 'the initial form' : 'an additional form'} that users fill out and submit.
            </div>
        `;

        // For additional form nodes, show form selector
        if (!isInitial) {
            html += `
                <div class="mb-3">
                    <label class="form-label"><i class="bi bi-file-earmark-text"></i> <strong>Select Form</strong></label>
                    <select class="form-select" name="form_id" onchange="workflowBuilder.updateFormSelection('${node.id}', this.value)">
                        <option value="">-- Select a form --</option>
            `;

            this.forms.forEach(form => {
                const selected = data.form_id == form.id ? 'selected' : '';
                html += `<option value="${form.id}" ${selected}>${this.escapeHtml(form.name)} (${form.field_count} fields)</option>`;
            });

            html += `
                    </select>
                    <small class="form-text text-muted">Choose which form to display at this step</small>
                </div>
            `;
        } else {
            // For initial form node, just show the name (read-only)
            html += `
                <div class="mb-3">
                    <label class="form-label">Form Name</label>
                    <input type="text" class="form-control" value="${this.escapeHtml(data.form_name || '')}" disabled />
                </div>
            `;
        }

        html += `
            <div class="mb-3">
                <label class="form-label">Total Fields</label>
                <input type="text" class="form-control" value="${data.field_count || 0}" disabled />
            </div>
        `;

        // Show multi-step information if enabled
        if (data.enable_multi_step && data.step_count > 0) {
            html += `
                <div class="alert alert-success">
                    <i class="bi bi-list-ol"></i> <strong>Multi-Step Form</strong>
                    <br><small class="text-muted">${data.step_count} step${data.step_count > 1 ? 's' : ''} configured</small>
                </div>
            `;

            // Show step details
            if (data.form_steps && data.form_steps.length > 0) {
                html += `
                    <div class="mb-3">
                        <label class="form-label">Form Steps</label>
                        <div class="list-group">
                `;

                data.form_steps.forEach((step, index) => {
                    const stepFields = step.fields || [];
                    html += `
                        <div class="list-group-item">
                            <div class="d-flex justify-content-between align-items-start">
                                <div>
                                    <strong><i class="bi bi-${index + 1}-circle"></i> ${this.escapeHtml(step.title || `Step ${index + 1}`)}</strong>
                                    <small class="text-muted d-block">${stepFields.length} field${stepFields.length !== 1 ? 's' : ''}</small>
                                </div>
                                <span class="badge bg-primary">${index + 1}</span>
                            </div>
                        </div>
                    `;
                });

                html += `
                        </div>
                    </div>
                `;
            }
        }

        if (fields.length > 0) {
            html += `
                <div class="mb-3">
                    <label class="form-label">Form Fields</label>
                    <div class="list-group">
            `;

            fields.forEach(field => {
                const prefillBadge = field.prefill_source ?
                    `<span class="badge bg-info ms-2" title="Auto-filled from ${field.prefill_source}"><i class="bi bi-magic"></i> ${field.prefill_source}</span>` : '';
                const requiredBadge = field.required ?
                    `<span class="badge bg-warning ms-1">Required</span>` : '';

                html += `
                    <div class="list-group-item">
                        <div class="d-flex justify-content-between align-items-start">
                            <div>
                                <strong>${this.escapeHtml(field.label)}</strong>
                                <small class="text-muted d-block">${field.name} (${field.type})</small>
                            </div>
                            <div>
                                ${requiredBadge}
                                ${prefillBadge}
                            </div>
                        </div>
                    </div>
                `;
            });

            if (hasMoreFields) {
                html += `
                    <div class="list-group-item text-muted text-center">
                        <i class="bi bi-three-dots"></i> More fields available
                    </div>
                `;
            }

            html += `
                    </div>
                </div>
            `;
        }

        html += `
            <div class="mt-3">
                <a href="${data.form_builder_url || '#'}" target="_blank" class="btn btn-outline-primary btn-sm w-100">
                    <i class="bi bi-pencil-square"></i> Edit Form in Form Builder
                </a>
            </div>
        `;

        return html;
    }

    buildApprovalProperties(node) {
        const data = node.data || {};
        let html = `
            <div class="mb-3">
                <label class="form-label">Step Name</label>
                <input type="text" class="form-control" name="step_name" value="${this.escapeHtml(data.step_name || '')}" />
            </div>
            <div class="mb-3">
                <label class="form-label">Approval Type</label>
                <select class="form-select" name="approval_type">
                    <option value="group" ${data.approval_type === 'group' ? 'selected' : ''}>Group Approval</option>
                    <option value="manager" ${data.approval_type === 'manager' ? 'selected' : ''}>Manager Approval</option>
                    <option value="parallel" ${data.approval_type === 'parallel' ? 'selected' : ''}>Parallel Approval</option>
                </select>
            </div>
        `;

        if (data.approval_type === 'group' || !data.approval_type) {
            html += `
                <div class="mb-3">
                    <label class="form-label">Approval Group</label>
                    <select class="form-select" name="group_id">
                        <option value="">Select group...</option>
                        ${this.groups.map(g => `
                            <option value="${g.id}" ${data.group_id == g.id ? 'selected' : ''}>${this.escapeHtml(g.name)}</option>
                        `).join('')}
                    </select>
                </div>
            `;
        }

        return html;
    }

    buildConditionProperties(node) {
        return `
            <div class="alert alert-warning mb-0">
                <i class="bi bi-exclamation-triangle"></i>
                Legacy condition nodes are not currently persisted by the workflow builder. Use workflow or stage <strong>trigger_conditions</strong> in Django Admin for conditional routing.
            </div>
        `;
    }

    buildActionProperties(node) {
        const data = node.data || {};
        return `
            <div class="mb-3">
                <label class="form-label">Action Name</label>
                <input type="text" class="form-control" name="name" value="${this.escapeHtml(data.name || '')}" placeholder="e.g., Update User Record" onchange="workflowBuilder.updateActionConfig('${node.id}')" />
            </div>
            <div class="mb-3">
                <label class="form-label">Action Type</label>
                <select class="form-select" name="action_type" onchange="workflowBuilder.updateActionConfig('${node.id}')">
                    <option value="database" ${data.action_type === 'database' ? 'selected' : ''}>Database Update</option>
                    <option value="ldap" ${data.action_type === 'ldap' ? 'selected' : ''}>LDAP Update</option>
                    <option value="api" ${data.action_type === 'api' ? 'selected' : ''}>API Call</option>
                    <option value="custom" ${data.action_type === 'custom' ? 'selected' : ''}>Custom Handler</option>
                </select>
            </div>
            <div class="mb-3">
                <label class="form-label">When to Execute</label>
                <select class="form-select" name="trigger" onchange="workflowBuilder.updateActionConfig('${node.id}')">
                    <option value="on_submit" ${data.trigger === 'on_submit' ? 'selected' : ''}>On Submission</option>
                    <option value="on_approve" ${data.trigger === 'on_approve' ? 'selected' : ''}>On Approval</option>
                    <option value="on_reject" ${data.trigger === 'on_reject' ? 'selected' : ''}>On Rejection</option>
                    <option value="on_complete" ${data.trigger === 'on_complete' ? 'selected' : ''}>On Complete</option>
                </select>
            </div>
            <hr class="my-3" />
            <div class="mb-3">
                <label class="form-label">Configuration (JSON)</label>
                <textarea class="form-control font-monospace" name="config" rows="4" placeholder='{"table": "users", "field": "status", "value": "approved"}' onchange="workflowBuilder.updateActionConfig('${node.id}')">${this.escapeHtml(typeof data.config === 'string' ? data.config : JSON.stringify(data.config || {}, null, 2))}</textarea>
                <small class="text-muted">Action-specific configuration in JSON format</small>
            </div>
        `;
    }

    buildEmailProperties(node) {
        const data = node.data || {};
        const fieldOptions = this.fields.map(f => `
            <option value="${f.field_name}" ${data.email_to_field === f.field_name ? 'selected' : ''}>${this.escapeHtml(f.field_label)} (${f.field_name})</option>
        `).join('');
        const ccFieldOptions = this.fields.map(f => `
            <option value="${f.field_name}" ${data.email_cc_field === f.field_name ? 'selected' : ''}>${this.escapeHtml(f.field_label)} (${f.field_name})</option>
        `).join('');
        return `
            <div class="mb-3">
                <label class="form-label">Email Name</label>
                <input type="text" class="form-control" name="name" value="${this.escapeHtml(data.name || '')}" placeholder="e.g., Approval Notification" onchange="workflowBuilder.updateEmailConfig('${node.id}')" />
            </div>
            <div class="mb-3">
                <label class="form-label">Static Recipients</label>
                <input type="text" class="form-control" name="email_to" value="${this.escapeHtml(data.email_to || '')}" placeholder="email@example.com, approver@example.com" onchange="workflowBuilder.updateEmailConfig('${node.id}')" />
                <small class="text-muted">Comma-separated email addresses.</small>
            </div>
            <div class="mb-3">
                <label class="form-label">Recipient Field</label>
                <select class="form-select" name="email_to_field" onchange="workflowBuilder.updateEmailConfig('${node.id}')">
                    <option value="">-- None --</option>
                    ${fieldOptions}
                </select>
                <small class="text-muted">Optional form field that contains the recipient email address.</small>
            </div>
            <div class="mb-3">
                <label class="form-label">CC Addresses</label>
                <input type="text" class="form-control" name="email_cc" value="${this.escapeHtml(data.email_cc || '')}" placeholder="manager@example.com" onchange="workflowBuilder.updateEmailConfig('${node.id}')" />
            </div>
            <div class="mb-3">
                <label class="form-label">CC Field</label>
                <select class="form-select" name="email_cc_field" onchange="workflowBuilder.updateEmailConfig('${node.id}')">
                    <option value="">-- None --</option>
                    ${ccFieldOptions}
                </select>
            </div>
            <div class="mb-3">
                <label class="form-label">When to Send</label>
                <select class="form-select" name="trigger" onchange="workflowBuilder.updateEmailConfig('${node.id}')">
                    <option value="on_submit" ${data.trigger === 'on_submit' ? 'selected' : ''}>On Submission</option>
                    <option value="on_approve" ${data.trigger === 'on_approve' ? 'selected' : ''}>On Approval</option>
                    <option value="on_reject" ${data.trigger === 'on_reject' ? 'selected' : ''}>On Rejection</option>
                    <option value="on_complete" ${data.trigger === 'on_complete' ? 'selected' : ''}>On Complete</option>
                </select>
            </div>
            <div class="mb-3">
                <label class="form-label">Subject Template</label>
                <input type="text" class="form-control" name="email_subject_template" value="${this.escapeHtml(data.email_subject_template || '')}" placeholder="Form {form_name} approved" onchange="workflowBuilder.updateEmailConfig('${node.id}')" />
            </div>
            <div class="mb-3">
                <label class="form-label">Body Template</label>
                <textarea class="form-control" name="email_body_template" rows="5" placeholder="Submission by {submitter} has been approved." onchange="workflowBuilder.updateEmailConfig('${node.id}')">${this.escapeHtml(data.email_body_template || '')}</textarea>
            </div>
            <div class="mb-3">
                <label class="form-label">HTML Template Path</label>
                <input type="text" class="form-control" name="email_template_name" value="${this.escapeHtml(data.email_template_name || '')}" placeholder="emails/approval.html" onchange="workflowBuilder.updateEmailConfig('${node.id}')" />
            </div>
        `;
    }

    buildSubWorkflowProperties(node) {
        const data = node.data || {};

        // Build workflow options from this.workflowTargets
        let workflowOptions = '<option value="">-- Select a workflow --</option>';
        this.workflowTargets.forEach(target => {
            const selected = (data.sub_workflow_id == target.workflow_id) ? 'selected' : '';
            workflowOptions += `<option value="${target.workflow_id}" data-form-id="${target.form_id}" ${selected}>${this.escapeHtml(target.workflow_label)} (${target.field_count} fields)</option>`;
        });

        // Build count field options from this.fields
        let fieldOptions = '<option value="">-- Select a field --</option>';
        this.fields.forEach(f => {
            const selected = (data.count_field === f.field_name) ? 'selected' : '';
            fieldOptions += `<option value="${f.field_name}" ${selected}>${this.escapeHtml(f.field_label)} (${f.field_name})</option>`;
        });

        const targetSection = `
            <div class="mb-3">
                <label class="form-label"><strong>Target Workflow</strong></label>
                <select class="form-select" name="sub_workflow_id"
                        onchange="workflowBuilder.updateSubWorkflowConfig('${node.id}')">
                    ${workflowOptions}
                </select>
                <small class="text-muted">The workflow definition used for each sub-workflow instance</small>
            </div>

            <div class="mb-3">
                <label class="form-label"><strong>Section Label</strong></label>
                <input type="text" class="form-control" name="section_label"
                       value="${this.escapeHtml(data.section_label || '')}"
                       placeholder="e.g. Payment Approvals"
                       onchange="workflowBuilder.updateSubWorkflowConfig('${node.id}')" />
                <small class="text-muted">Heading shown to end users in approval history. If blank, uses the workflow name.</small>
            </div>

            <div class="mb-3">
                <label class="form-label"><strong>Count Field</strong></label>
                <select class="form-select" name="count_field"
                        onchange="workflowBuilder.updateSubWorkflowConfig('${node.id}')">
                    ${fieldOptions}
                </select>
                <small class="text-muted">Form field whose value determines how many sub-workflows to spawn</small>
            </div>

            <div class="mb-3">
                <label class="form-label"><strong>Label Template</strong></label>
                <input type="text" class="form-control" name="label_template"
                       value="${this.escapeHtml(data.label_template || 'Sub-workflow {index}')}"
                       onchange="workflowBuilder.updateSubWorkflowConfig('${node.id}')" />
                <small class="text-muted">Use {index} as placeholder (e.g. "Payment {index}")</small>
            </div>
        `;

        const launchSection = `
            <div class="mb-3">
                <label class="form-label"><strong>Trigger</strong></label>
                <select class="form-select" name="trigger"
                        onchange="workflowBuilder.updateSubWorkflowConfig('${node.id}')">
                    <option value="on_submission" ${data.trigger === 'on_submission' ? 'selected' : ''}>On Submission</option>
                    <option value="on_approval" ${data.trigger === 'on_approval' ? 'selected' : ''}>After Parent Approval</option>
                </select>
            </div>

            <div class="mb-3">
                <label class="form-label"><strong>Data Prefix</strong></label>
                <input type="text" class="form-control" name="data_prefix"
                       value="${this.escapeHtml(data.data_prefix || '')}"
                       onchange="workflowBuilder.updateSubWorkflowConfig('${node.id}')" />
                <small class="text-muted">Field prefix to scope data per instance (e.g. "payment" matches payment_type_1, payment_amount_1 …)</small>
            </div>

            <div class="mb-3">
                <div class="form-check form-switch">
                    <input class="form-check-input" type="checkbox" id="sub_wf_detached_${node.id}"
                           name="detached" ${data.detached ? 'checked' : ''}
                           onchange="workflowBuilder.updateSubWorkflowConfig('${node.id}')">
                    <label class="form-check-label" for="sub_wf_detached_${node.id}">
                        <strong>Detached</strong>
                    </label>
                </div>
                <small class="text-muted">When enabled, sub-workflows run independently and don't affect parent status</small>
            </div>

            <div class="mb-3">
                <div class="form-check form-switch">
                    <input class="form-check-input" type="checkbox" id="sub_wf_reject_parent_${node.id}"
                           name="reject_parent" ${data.reject_parent ? 'checked' : ''}
                           onchange="workflowBuilder.updateSubWorkflowConfig('${node.id}')">
                    <label class="form-check-label" for="sub_wf_reject_parent_${node.id}">
                        <strong>Reject Parent on Failure</strong>
                    </label>
                </div>
                <small class="text-muted">When enabled, rejecting any sub-workflow rejects the parent and cancels siblings</small>
            </div>
        `;

        return `
            <div class="alert alert-info">
                <i class="bi bi-info-circle"></i> Configure a sub-workflow that spawns child approval processes based on a form field value.
            </div>
            ${this.buildPropertySection('Workflow Target & Labels', targetSection, {
                icon: 'boxes',
                description: 'Choose which child workflow to launch and how it should appear to reviewers.',
            })}
            ${this.buildPropertySection('Launch & Parent Behavior', launchSection, {
                icon: 'arrow-repeat',
                description: 'Define when the child workflow runs and whether it can affect the parent workflow.',
            })}
        `;
    }

    updateSubWorkflowConfig(nodeId) {
        const node = this.nodes.find(n => n.id === nodeId);
        if (!node) return;

        const container = document.getElementById('propertiesContent');
        const subWfSelect = container.querySelector('select[name="sub_workflow_id"]');
        node.data.sub_workflow_id = subWfSelect.value ? parseInt(subWfSelect.value) : null;
        const selectedOption = subWfSelect.selectedOptions[0];
        node.data.sub_workflow_name = selectedOption && selectedOption.value ? selectedOption.text : '';
        node.data.sub_workflow_form_id = selectedOption && selectedOption.dataset.formId ? parseInt(selectedOption.dataset.formId) : null;

        node.data.section_label = container.querySelector('input[name="section_label"]').value;
        node.data.count_field = container.querySelector('select[name="count_field"]').value;
        node.data.label_template = container.querySelector('input[name="label_template"]').value;
        node.data.trigger = container.querySelector('select[name="trigger"]').value;
        node.data.data_prefix = container.querySelector('input[name="data_prefix"]').value;
        node.data.detached = container.querySelector(`#sub_wf_detached_${nodeId}`).checked;
        node.data.reject_parent = container.querySelector(`#sub_wf_reject_parent_${nodeId}`).checked;

        this.render();
        this.selectNode(nodeId);
    }

    buildEndProperties(node) {
        const data = node.data || {};
        return `
            <div class="alert alert-info">
                <i class="bi bi-info-circle"></i> This is the terminal node where the workflow ends.
            </div>
            <p class="text-muted">
                The workflow completes when it reaches this node. The final status is determined by
                which path led to this end node (e.g., approval path vs. rejection path).
            </p>
        `;
    }

    updateNodeProperty(nodeId, property, value) {
        const node = this.nodes.find(n => n.id === nodeId);
        if (node) {
            node.data[property] = value;
            this.render();
        }
    }

    updateFormSelection(nodeId, formId) {
        const node = this.nodes.find(n => n.id === nodeId);
        if (!node) return;

        // Find the selected form
        const selectedForm = this.forms.find(f => f.id == formId);
        if (!selectedForm) {
            // Clear form data if no form selected
            node.data.form_id = null;
            node.data.form_name = 'Select Form';
            node.data.form_builder_url = '#';
            node.data.field_count = 0;
            node.data.fields = [];
            node.data.has_more_fields = false;
        } else {
            // Update node with selected form data
            node.data.form_id = selectedForm.id;
            node.data.form_name = selectedForm.name;
            node.data.form_builder_url = `/admin/django_forms_workflows/formdefinition/${selectedForm.id}/builder/`;
            node.data.field_count = selectedForm.field_count;
            // Note: We don't load full field details here for performance
            // The backend will load them when needed
            node.data.fields = [];
            node.data.has_more_fields = selectedForm.field_count > 0;
        }

        // Re-render to update the node display and properties panel
        this.render();
        this.selectNode(nodeId); // Re-select to refresh properties panel
    }

    updateStageConfig(nodeId) {
        const node = this.nodes.find(n => n.id === nodeId);
        if (!node) return;

        const container = document.getElementById('propertiesContent');
        node.data.name = container.querySelector('input[name="name"]').value;
        node.data.order = parseInt(container.querySelector('input[name="order"]').value) || 1;
        node.data.approve_label = container.querySelector('input[name="approve_label"]').value;
        node.data.requires_manager_approval = container.querySelector(`#stage_requires_manager_${nodeId}`).checked;
        node.data.allow_send_back = container.querySelector(`#stage_allow_send_back_${nodeId}`).checked;
        node.data.allow_reassign = container.querySelector(`#stage_allow_reassign_${nodeId}`).checked;
        node.data.allow_edit_form_data = container.querySelector(`#stage_allow_edit_form_data_${nodeId}`).checked;
        node.data.assignee_form_field = container.querySelector('select[name="assignee_form_field"]').value;
        node.data.assignee_lookup_type = container.querySelector('select[name="assignee_lookup_type"]').value;
        node.data.validate_assignee_group = container.querySelector(`#stage_validate_assignee_group_${nodeId}`).checked;
        node.data.trigger_conditions = this.readNodeTriggerConditions(container);
        node.data.approval_groups = this.readStageApprovalGroupsFromPanel(
            container,
            nodeId,
            node.data.approval_groups || []
        );
        node.data.approval_fields = this.readStageApprovalFieldsFromPanel(container, nodeId);
        node.data.approval_logic = container.querySelector('select[name="approval_logic"]').value;

        this.render();
        this.selectNode(nodeId);
    }

    updateWorkflowSettings(nodeId) {
        const node = this.nodes.find(n => n.id === nodeId);
        if (!node) return;

        const container = document.getElementById('propertiesContent');

        // Numeric fields (empty → null)
        ['approval_deadline_days', 'send_reminder_after_days', 'auto_approve_after_days'].forEach(key => {
            const val = container.querySelector(`input[name="${key}"]`).value;
            node.data[key] = val ? parseInt(val) : null;
        });

        node.data.name_label = container.querySelector('input[name="name_label"]').value;
        node.data.notification_cadence = container.querySelector('select[name="notification_cadence"]').value;
        const cadenceDay = container.querySelector('input[name="notification_cadence_day"]').value;
        node.data.notification_cadence_day = cadenceDay ? parseInt(cadenceDay) : null;
        node.data.notification_cadence_time = container.querySelector('input[name="notification_cadence_time"]').value;
        node.data.notification_cadence_form_field = container.querySelector('select[name="notification_cadence_form_field"]').value;
        node.data.notification_rules = this.readNotificationRulesFromPanel(container);
        node.data.trigger_conditions = this.readNodeTriggerConditions(container);

        this.render();
        this.selectNode(nodeId);
    }

    readConditionsFromEditor(editorElement) {
        if (!editorElement) {
            return null;
        }

        const operatorElement = editorElement.querySelector('select[name="condition_group_operator"]');
        const rows = Array.from(editorElement.querySelectorAll('.trigger-condition-row'));
        const conditions = rows.map(row => {
            const operator = row.querySelector('select[name="condition_operator"]').value;
            const condition = {
                field: row.querySelector('select[name="condition_field"]').value,
                operator,
            };
            if (!['is_empty', 'not_empty'].includes(operator)) {
                condition.value = row.querySelector('input[name="condition_value"]').value;
            }
            return condition;
        }).filter(condition => condition.field);

        if (!conditions.length) {
            return null;
        }

        return {
            operator: operatorElement ? operatorElement.value : 'AND',
            conditions,
        };
    }

    readNodeTriggerConditions(container) {
        return this.readConditionsFromEditor(
            container.querySelector('.conditions-editor[data-editor-kind="node-trigger"]')
        );
    }

    readStageApprovalGroupsFromPanel(container, nodeId, existingGroups) {
        const groupSelect = container.querySelector(`#stage_groups_${nodeId}`);
        const selected = Array.from(groupSelect.selectedOptions).map(opt => ({
            id: parseInt(opt.value),
            name: opt.text,
        }));
        const existingOrdered = this.getNormalizedStageApprovalGroups(existingGroups || []);
        const existingMap = new Map(existingOrdered.map(group => [group.id, group]));

        const kept = existingOrdered.filter(group => selected.some(sel => sel.id === group.id));
        const appended = selected
            .filter(group => !existingMap.has(group.id))
            .map(group => ({ id: group.id, name: group.name }));

        return [...kept, ...appended].map((group, index) => ({
            id: group.id,
            name: group.name,
            position: index,
        }));
    }

    readStageApprovalFieldsFromPanel(container, nodeId) {
        const fieldSelect = container.querySelector(`#stage_fields_${nodeId}`);
        if (!fieldSelect) {
            return [];
        }

        return Array.from(fieldSelect.selectedOptions).map(option => {
            const fieldId = parseInt(option.value);
            const field = this.fields.find(entry => entry.id === fieldId);
            return {
                id: fieldId,
                field_name: field?.field_name || option.text,
                field_label: field?.field_label || option.text,
                field_type: field?.field_type || '',
                order: field?.order ?? 0,
            };
        });
    }

    moveStageApprovalGroup(nodeId, groupId, direction) {
        const node = this.nodes.find(n => n.id === nodeId);
        if (!node) return;

        const groups = this.getNormalizedStageApprovalGroups(node.data.approval_groups || []);
        const currentIndex = groups.findIndex(group => group.id === groupId);
        const targetIndex = currentIndex + direction;
        if (currentIndex < 0 || targetIndex < 0 || targetIndex >= groups.length) {
            return;
        }

        [groups[currentIndex], groups[targetIndex]] = [groups[targetIndex], groups[currentIndex]];
        node.data.approval_groups = groups.map((group, index) => ({ ...group, position: index }));
        this.render();
        this.selectNode(nodeId);
    }

    readNotificationRulesFromPanel(container) {
        return Array.from(container.querySelectorAll('.notification-rule-card')).map(card => {
            const stageNodeId = card.querySelector('select[name="notification_rule_stage"]').value;
            const notifyGroups = Array.from(card.querySelector('select[name="notification_rule_notify_groups"]').selectedOptions).map(opt => ({
                id: parseInt(opt.value),
                name: opt.text,
            }));
            return {
                rule_id: card.dataset.ruleId ? parseInt(card.dataset.ruleId) : null,
                stage_node_id: stageNodeId || '',
                event: card.querySelector('select[name="notification_rule_event"]').value,
                subject_template: card.querySelector('input[name="notification_rule_subject_template"]').value,
                notify_submitter: card.querySelector('input[name="notification_rule_notify_submitter"]').checked,
                email_field: card.querySelector('select[name="notification_rule_email_field"]').value,
                static_emails: card.querySelector('input[name="notification_rule_static_emails"]').value,
                notify_stage_assignees: card.querySelector('input[name="notification_rule_notify_stage_assignees"]').checked,
                notify_stage_groups: card.querySelector('input[name="notification_rule_notify_stage_groups"]').checked,
                notify_groups: notifyGroups,
                conditions: this.readConditionsFromEditor(
                    card.querySelector('.conditions-editor[data-editor-kind="notification-rule"]')
                ),
            };
        }).filter(rule => (
            rule.notify_submitter
            || rule.email_field
            || rule.static_emails
            || rule.notify_stage_assignees
            || rule.notify_stage_groups
            || rule.notify_groups.length > 0
            || rule.subject_template
            || (rule.conditions && rule.conditions.conditions && rule.conditions.conditions.length > 0)
        ));
    }

    addNotificationRule(nodeId) {
        const node = this.nodes.find(n => n.id === nodeId);
        if (!node) return;

        node.data.notification_rules = [...(node.data.notification_rules || []), this.getNotificationRuleState({})];
        this.render();
        this.selectNode(nodeId);
    }

    removeNotificationRule(nodeId, index) {
        const node = this.nodes.find(n => n.id === nodeId);
        if (!node) return;

        const rules = [...(node.data.notification_rules || [])];
        rules.splice(index, 1);
        node.data.notification_rules = rules;
        this.render();
        this.selectNode(nodeId);
    }

    addNotificationRuleCondition(nodeId, ruleIndex) {
        const node = this.nodes.find(n => n.id === nodeId);
        if (!node) return;

        const rules = [...(node.data.notification_rules || [])];
        const rule = this.getNotificationRuleState(rules[ruleIndex] || {});
        const state = this.getNormalizedTriggerConditions(rule.conditions);
        state.conditions.push({ field: '', operator: 'equals', value: '' });
        rules[ruleIndex] = { ...rule, conditions: state };
        node.data.notification_rules = rules;
        this.render();
        this.selectNode(nodeId);
    }

    removeNotificationRuleCondition(nodeId, ruleIndex, conditionIndex) {
        const node = this.nodes.find(n => n.id === nodeId);
        if (!node) return;

        const rules = [...(node.data.notification_rules || [])];
        const rule = this.getNotificationRuleState(rules[ruleIndex] || {});
        const state = this.getNormalizedTriggerConditions(rule.conditions);
        state.conditions.splice(conditionIndex, 1);
        rules[ruleIndex] = { ...rule, conditions: state.conditions.length ? state : null };
        node.data.notification_rules = rules;
        this.render();
        this.selectNode(nodeId);
    }

    updateNotificationRules(nodeId) {
        const node = this.nodes.find(n => n.id === nodeId);
        if (!node) return;

        const container = document.getElementById('propertiesContent');
        node.data.notification_rules = this.readNotificationRulesFromPanel(container);
        this.render();
        this.selectNode(nodeId);
    }

    addTriggerCondition(nodeId) {
        const node = this.nodes.find(n => n.id === nodeId);
        if (!node) return;

        const state = this.getNormalizedTriggerConditions(node.data.trigger_conditions);
        state.conditions.push({ field: '', operator: 'equals', value: '' });
        node.data.trigger_conditions = state;
        this.render();
        this.selectNode(nodeId);
    }

    removeTriggerCondition(nodeId, index) {
        const node = this.nodes.find(n => n.id === nodeId);
        if (!node) return;

        const state = this.getNormalizedTriggerConditions(node.data.trigger_conditions);
        state.conditions.splice(index, 1);
        node.data.trigger_conditions = state.conditions.length ? state : null;
        this.render();
        this.selectNode(nodeId);
    }

    updateNodeTriggerConditions(nodeId) {
        const node = this.nodes.find(n => n.id === nodeId);
        if (!node) return;

        const container = document.getElementById('propertiesContent');
        node.data.trigger_conditions = this.readNodeTriggerConditions(container);
        this.render();
        this.selectNode(nodeId);
    }

    updateActionConfig(nodeId) {
        const node = this.nodes.find(n => n.id === nodeId);
        if (!node) return;

        const container = document.getElementById('propertiesContent');
        node.data.name = container.querySelector('input[name="name"]').value;
        node.data.action_type = container.querySelector('select[name="action_type"]').value;
        node.data.trigger = container.querySelector('select[name="trigger"]').value;
        node.data.config = container.querySelector('textarea[name="config"]').value;

        this.render();
        this.selectNode(nodeId);
    }

    updateEmailConfig(nodeId) {
        const node = this.nodes.find(n => n.id === nodeId);
        if (!node) return;

        const container = document.getElementById('propertiesContent');
        node.data.name = container.querySelector('input[name="name"]').value;
        node.data.email_to = container.querySelector('input[name="email_to"]').value;
        node.data.email_to_field = container.querySelector('select[name="email_to_field"]').value;
        node.data.email_cc = container.querySelector('input[name="email_cc"]').value;
        node.data.email_cc_field = container.querySelector('select[name="email_cc_field"]').value;
        node.data.email_subject_template = container.querySelector('input[name="email_subject_template"]').value;
        node.data.email_body_template = container.querySelector('textarea[name="email_body_template"]').value;
        node.data.email_template_name = container.querySelector('input[name="email_template_name"]').value;
        node.data.trigger = container.querySelector('select[name="trigger"]').value;

        this.render();
        this.selectNode(nodeId);
    }



    getNodeTypeLabel(type) {
        const labels = {
            start: 'Start',
            form: 'Form Submission',
            workflow_settings: 'Workflow Settings',
            stage: 'Approval Stage',
            condition: 'Condition',
            action: 'Action',
            email: 'Email Notification',
            sub_workflow: 'Sub-Workflow',
            join: 'Join',
            end: 'End'
        };
        return labels[type] || type;
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    addNodeIssue(result, nodeId, severity, message) {
        if (!nodeId) return;
        if (!result.nodeIssues[nodeId]) {
            result.nodeIssues[nodeId] = { errors: [], warnings: [] };
        }
        result.nodeIssues[nodeId][severity].push(message);
        result[severity].push(message);
        if (severity === 'errors' && !result.firstErrorNodeId) {
            result.firstErrorNodeId = nodeId;
        }
    }

    refreshValidationState() {
        this.validationState = this.validateWorkflow();
        this.updateValidationDisplay();
        return this.validationState;
    }

    validateWorkflow() {
        const result = {
            errors: [],
            warnings: [],
            nodeIssues: {},
            firstErrorNodeId: null,
        };
        const fieldNames = new Set(this.fields.map(field => field.field_name));
        const fieldIds = new Set(this.fields.map(field => field.id));
        const groupIds = new Set(this.groups.map(group => group.id));
        const stageNodes = this.nodes.filter(node => node.type === 'stage');
        const settingsNode = this.nodes.find(node => node.type === 'workflow_settings');
        const stageNodeIds = new Set(stageNodes.map(node => node.id));
        const assignedApprovalFields = new Map();

        stageNodes.forEach((node, index) => {
            const data = node.data || {};
            const groups = (data.approval_groups || []).filter(group => group && group.id);
            const stageLabel = data.name || `Stage ${index + 1}`;

            if (!String(data.name || '').trim()) {
                this.addNodeIssue(result, node.id, 'errors', `Stage ${index + 1} is missing a name.`);
            }
            if (!(groups.length || data.requires_manager_approval || data.assignee_form_field)) {
                this.addNodeIssue(result, node.id, 'errors', `${stageLabel} needs approval groups, manager approval, or a dynamic assignee field.`);
            }
            if (data.assignee_form_field && !fieldNames.has(data.assignee_form_field)) {
                this.addNodeIssue(result, node.id, 'errors', `${stageLabel} uses an unknown assignee field: ${data.assignee_form_field}.`);
            }
            if (data.validate_assignee_group !== false && data.assignee_form_field && !groups.length) {
                this.addNodeIssue(result, node.id, 'errors', `${stageLabel} cannot validate assignee group membership without at least one approval group.`);
            }
            if (data.approval_logic === 'sequence' && groups.length < 2) {
                this.addNodeIssue(result, node.id, 'warnings', `${stageLabel} uses sequence logic with fewer than two approval groups.`);
            }

            groups.forEach(group => {
                if (!groupIds.has(group.id)) {
                    this.addNodeIssue(result, node.id, 'errors', `${stageLabel} references an unknown approval group: ${group.id}.`);
                }
            });

            (data.approval_fields || []).forEach(field => {
                const fieldId = field?.id;
                const fieldName = field?.field_name;
                const lookupKey = fieldId ? `id:${fieldId}` : `name:${fieldName}`;
                const label = field?.field_label || fieldName || fieldId;
                const exists = (fieldId && fieldIds.has(fieldId)) || (fieldName && fieldNames.has(fieldName));

                if (!exists) {
                    this.addNodeIssue(result, node.id, 'errors', `${stageLabel} references an unknown approval-only field: ${label}.`);
                    return;
                }

                if (assignedApprovalFields.has(lookupKey) && assignedApprovalFields.get(lookupKey) !== node.id) {
                    const otherStage = this.nodes.find(candidate => candidate.id === assignedApprovalFields.get(lookupKey));
                    const otherLabel = otherStage?.data?.name || 'another stage';
                    this.addNodeIssue(result, node.id, 'errors', `Approval-only field ${label} is already assigned to ${otherLabel}.`);
                } else {
                    assignedApprovalFields.set(lookupKey, node.id);
                }
            });
        });

        if (settingsNode) {
            const data = settingsNode.data || {};
            const cadence = data.notification_cadence || 'immediate';
            const cadenceDay = data.notification_cadence_day;

            if (cadence === 'weekly' && !(Number.isInteger(cadenceDay) && cadenceDay >= 0 && cadenceDay <= 6)) {
                this.addNodeIssue(result, settingsNode.id, 'errors', 'Weekly notification cadence requires a digest day between 0 and 6.');
            }
            if (cadence === 'monthly' && !(Number.isInteger(cadenceDay) && cadenceDay >= 1 && cadenceDay <= 31)) {
                this.addNodeIssue(result, settingsNode.id, 'errors', 'Monthly notification cadence requires a digest day between 1 and 31.');
            }
            if (cadence === 'form_field_date') {
                if (!data.notification_cadence_form_field) {
                    this.addNodeIssue(result, settingsNode.id, 'errors', 'On-date notification cadence requires a date field.');
                } else if (!fieldNames.has(data.notification_cadence_form_field)) {
                    this.addNodeIssue(result, settingsNode.id, 'errors', `Unknown notification cadence field: ${data.notification_cadence_form_field}.`);
                }
            }
            if (cadence !== 'weekly' && cadence !== 'monthly' && data.notification_cadence_day !== null && data.notification_cadence_day !== '') {
                this.addNodeIssue(result, settingsNode.id, 'warnings', 'Digest day is only used for weekly and monthly notification cadences.');
            }
            if (cadence !== 'form_field_date' && data.notification_cadence_form_field) {
                this.addNodeIssue(result, settingsNode.id, 'warnings', 'Date field is ignored unless cadence is “On Date From Form Field”.');
            }

            (data.notification_rules || []).forEach((rule, index) => {
                const ruleLabel = `Notification rule ${index + 1}`;
                const hasRecipients = Boolean(
                    rule.notify_submitter
                    || rule.email_field
                    || rule.static_emails
                    || rule.notify_stage_assignees
                    || rule.notify_stage_groups
                    || (rule.notify_groups || []).length
                );
                if (!hasRecipients) {
                    this.addNodeIssue(result, settingsNode.id, 'errors', `${ruleLabel} must define at least one recipient source.`);
                }
                if (rule.email_field && !fieldNames.has(rule.email_field)) {
                    this.addNodeIssue(result, settingsNode.id, 'errors', `${ruleLabel} references an unknown email field: ${rule.email_field}.`);
                }
                if (rule.stage_node_id && !stageNodeIds.has(rule.stage_node_id)) {
                    this.addNodeIssue(result, settingsNode.id, 'errors', `${ruleLabel} references a stage that is not present in the builder graph.`);
                }
                if ((rule.notify_stage_assignees || rule.notify_stage_groups) && !stageNodes.length) {
                    this.addNodeIssue(result, settingsNode.id, 'warnings', `${ruleLabel} uses stage-based recipients, but no approval stages are configured yet.`);
                }
            });
        }

        this.nodes.filter(node => node.type === 'email').forEach((node, index) => {
            const data = node.data || {};
            const label = data.name || `Email notification ${index + 1}`;
            if (!(data.email_to || data.email_to_field)) {
                this.addNodeIssue(result, node.id, 'errors', `${label} needs static recipients or a recipient field.`);
            }
            if (data.email_to_field && !fieldNames.has(data.email_to_field)) {
                this.addNodeIssue(result, node.id, 'errors', `${label} references an unknown recipient field: ${data.email_to_field}.`);
            }
            if (data.email_cc_field && !fieldNames.has(data.email_cc_field)) {
                this.addNodeIssue(result, node.id, 'errors', `${label} references an unknown CC field: ${data.email_cc_field}.`);
            }
        });

        this.nodes.filter(node => node.type === 'action').forEach((node, index) => {
            const data = node.data || {};
            if (typeof data.config === 'string' && data.config.trim()) {
                try {
                    JSON.parse(data.config);
                } catch (_error) {
                    this.addNodeIssue(result, node.id, 'errors', `${data.name || `Action ${index + 1}`} has invalid JSON configuration.`);
                }
            }
        });

        this.nodes.filter(node => node.type === 'sub_workflow').forEach((node, index) => {
            const data = node.data || {};
            const label = data.sub_workflow_name || `Sub-workflow ${index + 1}`;
            if (!data.sub_workflow_id) {
                this.addNodeIssue(result, node.id, 'errors', `${label} needs a target workflow.`);
            }
            if (data.count_field && !fieldNames.has(data.count_field)) {
                this.addNodeIssue(result, node.id, 'errors', `${label} references an unknown count field: ${data.count_field}.`);
            }
            if (data.detached && data.reject_parent) {
                this.addNodeIssue(result, node.id, 'warnings', `${label} is detached, so “Reject Parent on Failure” may not have any effect.`);
            }
        });

        return result;
    }

    getNodeIssues(nodeId) {
        return this.validationState.nodeIssues[nodeId] || { errors: [], warnings: [] };
    }

    usesDirectionalHandles(nodeType) {
        return ['stage', 'sub_workflow'].includes(nodeType);
    }

    buildNodeIssuesAlert(node) {
        const issues = this.getNodeIssues(node.id);
        if (!issues.errors.length && !issues.warnings.length) {
            return '';
        }

        const errorHtml = issues.errors.length ? `
            <div class="alert alert-danger py-2 px-3">
                <div class="fw-semibold mb-1"><i class="bi bi-exclamation-triangle"></i> Fix before saving</div>
                <ul class="small mb-0">
                    ${issues.errors.map(error => `<li>${this.escapeHtml(error)}</li>`).join('')}
                </ul>
            </div>
        ` : '';
        const warningHtml = issues.warnings.length ? `
            <div class="alert alert-warning py-2 px-3 ${issues.errors.length ? 'mt-2' : ''}">
                <div class="fw-semibold mb-1"><i class="bi bi-exclamation-circle"></i> Warnings</div>
                <ul class="small mb-0">
                    ${issues.warnings.map(warning => `<li>${this.escapeHtml(warning)}</li>`).join('')}
                </ul>
            </div>
        ` : '';
        return `${errorHtml}${warningHtml}`;
    }

    buildNodeIssueBadges(nodeId) {
        const issues = this.getNodeIssues(nodeId);
        if (!issues.errors.length && !issues.warnings.length) {
            return '';
        }

        return `
            <div class="node-issue-badges mt-2">
                ${issues.errors.length ? `<span class="badge bg-danger-subtle text-danger-emphasis">${issues.errors.length} error${issues.errors.length === 1 ? '' : 's'}</span>` : ''}
                ${issues.warnings.length ? `<span class="badge bg-warning-subtle text-warning-emphasis">${issues.warnings.length} warning${issues.warnings.length === 1 ? '' : 's'}</span>` : ''}
            </div>
        `;
    }

    buildPropertySection(title, innerHtml, options = {}) {
        const description = options.description ? `
            <p class="property-section-description">${this.escapeHtml(options.description)}</p>
        ` : '';
        const icon = options.icon ? `<i class="bi bi-${options.icon}"></i>` : '';
        return `
            <section class="property-section ${options.className || ''}">
                <div class="property-section-header">
                    <h6>${icon}<span>${this.escapeHtml(title)}</span></h6>
                    ${description}
                </div>
                <div class="property-section-body">
                    ${innerHtml}
                </div>
            </section>
        `;
    }

    render() {
        console.log('Rendering workflow with', this.nodes.length, 'nodes and', this.connections.length, 'connections');
        this.refreshValidationState();
        if (this.selectedConnection !== null && !this.connections[this.selectedConnection]) {
            this.selectedConnection = null;
        }
        this.updateWorkspaceBounds();
        this.renderNodes();
        this.renderConnections();
        this.applyTransform();
        this.updateConnectionSelectionUI();
        this.updateDirtyState();
    }

    renderNodes() {
        console.log('Rendering nodes...');
        // Remove existing nodes
        this.transformWrapper.querySelectorAll('.workflow-node').forEach(n => n.remove());

        // Render each node into the transform wrapper (alongside the SVG)
        const orderedNodes = [...this.nodes].sort((a, b) => {
            return (this.nodeStackOrder.get(a.id) || 0) - (this.nodeStackOrder.get(b.id) || 0);
        });
        orderedNodes.forEach(node => {
            console.log('Creating node element for:', node);
            const nodeEl = this.createNodeElement(node);
            this.transformWrapper.appendChild(nodeEl);
        });
        console.log('Nodes rendered');
    }

    createNodeElement(node) {
        // Ensure node.data exists (may be missing from saved workflow data)
        if (!node.data) {
            node.data = this.getDefaultNodeData(node.type);
        }

        const div = document.createElement('div');
        div.className = `workflow-node ${node.type}`;
        div.dataset.nodeId = node.id;
        const issues = this.getNodeIssues(node.id);
        if (issues.errors.length) {
            div.className += ' has-validation-error';
        } else if (issues.warnings.length) {
            div.className += ' has-validation-warning';
        }
        if (this.selectedNode === node.id) {
            div.className += ' selected';
        }
        if (this.draggingNodeId === node.id) {
            div.className += ' dragging';
        }
        div.style.left = `${node.x}px`;
        div.style.top = `${node.y}px`;
        div.dataset.nodeId = node.id;

        const icon = this.getNodeIcon(node.type);
        const label = node.data.step_name || node.data.name || this.getNodeTypeLabel(node.type);

        // Determine if node can be deleted
        // - start, workflow_settings: never deletable
        // - form: only deletable if it's an additional form (is_initial === false)
        // - stage: always deletable
        // - all others: deletable
        const canDelete = node.type !== 'start' &&
                         node.type !== 'workflow_settings' &&
                         node.type !== 'join' &&
                         !(node.type === 'form' && node.data.is_initial !== false);
        const directionalHandles = this.usesDirectionalHandles(node.type);
        const inputHandleTitle = directionalHandles
            ? 'Incoming connection'
            : 'Connect previous step here';
        const outputHandleTitle = directionalHandles
            ? 'Drag to next step'
            : 'Drag to connect next step';

        div.innerHTML = `
            <div class="node-header">
                <div class="node-icon ${node.type}">
                    <i class="bi bi-${icon}"></i>
                </div>
                <span>${this.escapeHtml(label)}</span>
            </div>
            <div class="node-content">
                ${this.getNodeDescription(node)}
                ${this.buildNodeIssueBadges(node.id)}
            </div>
            ${canDelete ? `
                <div class="node-actions">
                    <button class="btn btn-sm btn-outline-danger" onclick="workflowBuilder.deleteNode('${node.id}')">
                        <i class="bi bi-trash"></i>
                    </button>
                </div>
            ` : ''}
            <div class="connection-point input ${directionalHandles ? 'directional-handle' : ''}" data-node-id="${node.id}" data-point="input" title="${inputHandleTitle}"></div>
            <div class="connection-point output ${directionalHandles ? 'directional-handle' : ''}" data-node-id="${node.id}" data-point="output" title="${outputHandleTitle}"></div>
        `;

        // Add connection point event listeners
        const inputPoint = div.querySelector('.connection-point.input');
        const outputPoint = div.querySelector('.connection-point.output');

        if (outputPoint) {
            outputPoint.addEventListener('mousedown', (e) => {
                e.stopPropagation();
                this.startConnection(e, node.id, 'output');
            });
        }

        if (inputPoint) {
            inputPoint.addEventListener('mouseenter', (e) => {
                if (this.isConnecting) {
                    inputPoint.classList.add('is-connect-target');
                }
            });
            inputPoint.addEventListener('mouseleave', (e) => {
                inputPoint.classList.remove('is-connect-target');
            });
        }

        // Make node draggable
        div.addEventListener('mousedown', (e) => {
            if (e.target.closest('.node-actions')) return;
            if (e.target.closest('.connection-point')) return;
            if (e.target.closest('.form-edit-link')) return; // Don't interfere with form edit link

            this.selectNode(node.id);
            this.startDragNode(e, node);
        });

        return div;
    }

    getNodeIcon(type) {
        const icons = {
            start: 'play-circle',
            form: 'file-earmark-text',
            workflow_settings: 'gear',
            stage: 'layers',
            condition: 'diagram-3',
            action: 'lightning',
            email: 'envelope',
            sub_workflow: 'diagram-2',
            join: 'sign-merge-right',
            end: 'flag'
        };
        return icons[type] || 'circle';
    }

    getNodeDescription(node) {
        switch (node.type) {
            case 'start':
                return 'Workflow starts here';
            case 'form':
                const fieldCount = node.data.field_count || 0;
                const formName = node.data.form_name || 'Form';
                const isInitial = node.data.is_initial !== false;
                const isMultiStep = node.data.enable_multi_step && node.data.step_count > 0;

                // Show different description for initial vs additional forms
                if (!isInitial && !node.data.form_id) {
                    return '<span class="badge bg-secondary"><i class="bi bi-exclamation-circle"></i> No Form Selected</span><br><small class="text-muted">Select a form in properties</small>';
                }

                let badges = '';
                if (!isInitial) {
                    badges += '<span class="badge bg-info">Additional Step</span> ';
                }
                if (isMultiStep) {
                    badges += `<span class="badge bg-success"><i class="bi bi-list-ol"></i> ${node.data.step_count} Steps</span> `;
                }

                const badgeHtml = badges ? `${badges}<br>` : '';
                return `${badgeHtml}${fieldCount} field${fieldCount !== 1 ? 's' : ''} • <a href="${node.data.form_builder_url || '#'}" target="_blank" class="text-primary form-edit-link"><i class="bi bi-pencil-square"></i> Edit Form</a>`;
            case 'workflow_settings':
                const parts_ws = [];
                if (node.data.name_label) parts_ws.push(node.data.name_label);
                if (node.data.approval_deadline_days) parts_ws.push(`Deadline: ${node.data.approval_deadline_days}d`);
                if (node.data.notification_cadence && node.data.notification_cadence !== 'immediate') parts_ws.push(`Cadence: ${node.data.notification_cadence}`);
                if (node.data.notification_cadence_form_field && node.data.notification_cadence === 'form_field_date') parts_ws.push(`Date field: ${node.data.notification_cadence_form_field}`);
                if (node.data.notification_rules && node.data.notification_rules.length > 0) parts_ws.push(`Notifications: ${node.data.notification_rules.length}`);
                if (node.data.trigger_conditions && node.data.trigger_conditions.conditions && node.data.trigger_conditions.conditions.length > 0) parts_ws.push('Conditional');
                return parts_ws.length > 0 ?
                    `<small class="text-muted">${parts_ws.join(' • ')}</small>` :
                    '<small class="text-muted">Default settings</small>';
            case 'stage':
                const stageParts = [];
                if (node.data.requires_manager_approval) stageParts.push('Manager');
                if (node.data.allow_send_back) stageParts.push('Send Back target');
                if (node.data.allow_reassign) stageParts.push('Reassign');
                if (node.data.allow_edit_form_data) stageParts.push('Editable');
                if (node.data.assignee_form_field) stageParts.push(`Dynamic: ${node.data.assignee_form_field}`);
                if (node.data.approval_fields && node.data.approval_fields.length > 0) stageParts.push(`Stage fields: ${node.data.approval_fields.length}`);
                if (node.data.trigger_conditions && node.data.trigger_conditions.conditions && node.data.trigger_conditions.conditions.length > 0) stageParts.push('Conditional');
                if (node.data.approval_groups && node.data.approval_groups.length > 0) {
                    const gc = node.data.approval_groups.length;
                    stageParts.push(`${gc} group${gc > 1 ? 's' : ''} (${node.data.approval_logic || 'all'})`);
                }
                const label = node.data.approve_label ? ` • "${node.data.approve_label}"` : '';
                return stageParts.length > 0 ?
                    `<span class="badge bg-warning">Stage ${node.data.order || '?'}</span><br><small class="text-muted">${stageParts.join(' + ')}${label}</small>` :
                    `<span class="badge bg-secondary">Stage ${node.data.order || '?'}</span><br><small class="text-muted">No approvers configured</small>`;
            case 'condition':
                if (node.data.field && node.data.operator) {
                    const operatorSymbols = {
                        'equals': '=',
                        'not_equals': '≠',
                        'greater_than': '>',
                        'less_than': '<',
                        'greater_or_equal': '≥',
                        'less_or_equal': '≤',
                        'contains': 'contains',
                        'not_contains': 'not contains',
                        'is_empty': 'is empty',
                        'is_not_empty': 'is not empty'
                    };
                    const op = operatorSymbols[node.data.operator] || node.data.operator;
                    return `If ${node.data.field} ${op} ${node.data.value || ''}`;
                }
                return 'Configure condition';
            case 'action':
                return node.data.action_type ? `${node.data.action_type.toUpperCase()}: ${node.data.trigger || ''}` : 'Configure action';
            case 'email':
                if (node.data.email_to && node.data.email_to_field) return `Send to: ${node.data.email_to} + field ${node.data.email_to_field}`;
                if (node.data.email_to) return `Send to: ${node.data.email_to}`;
                if (node.data.email_to_field) return `Send to field: ${node.data.email_to_field}`;
                return 'Configure email';
            case 'join':
                return '<small class="text-muted">Parallel stages merge here</small>';
            case 'sub_workflow':
                const swParts = [];
                if (node.data.sub_workflow_name) swParts.push(node.data.sub_workflow_name);
                if (node.data.count_field) swParts.push(`Count: ${node.data.count_field}`);
                if (node.data.trigger) swParts.push(node.data.trigger === 'on_approval' ? 'After approval' : 'On submission');
                if (node.data.detached) swParts.push('Detached');
                if (node.data.reject_parent) swParts.push('Rejects parent');
                return swParts.length > 0 ?
                    `<span class="badge bg-info">Sub-Workflow</span><br><small class="text-muted">${swParts.join(' • ')}</small>` :
                    '<span class="badge bg-secondary">Sub-Workflow</span><br><small class="text-muted">Not configured</small>';
            case 'end':
                return 'Workflow end';
            default:
                return '';
        }
    }

    startDragNode(e, node) {
        this.isDraggingNode = true;
        this.draggingNodeId = node.id;
        this.bringNodeToFront(node.id);
        this.render();
        const startX = e.clientX;
        const startY = e.clientY;
        const nodeStartX = node.x;
        const nodeStartY = node.y;

        const onMouseMove = (e) => {
            // Divide by zoom so node movement matches cursor speed
            const dx = (e.clientX - startX) / this.zoom;
            const dy = (e.clientY - startY) / this.zoom;
            node.x = nodeStartX + dx;
            node.y = nodeStartY + dy;
            this.render();
        };

        const onMouseUp = () => {
            this.isDraggingNode = false;
            this.draggingNodeId = null;
            this.render();
            document.removeEventListener('mousemove', onMouseMove);
            document.removeEventListener('mouseup', onMouseUp);
        };

        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);
    }

    startConnection(e, nodeId, point) {
        if (point !== 'output') return; // Only start from output

        e.stopPropagation();
        e.preventDefault();
        this.isConnecting = true;
        this.connectionStart = { nodeId, point };

        console.log('Starting connection from node:', nodeId);

        const onMouseMove = (e) => {
            this.updateTempConnection(e);
        };

        const onMouseUp = (e) => {
            this.finishConnection(e);
            this.isConnecting = false;
            this.connectionStart = null;
            if (this.tempLine) {
                this.tempLine.remove();
                this.tempLine = null;
            }
            document.removeEventListener('mousemove', onMouseMove);
            document.removeEventListener('mouseup', onMouseUp);
        };

        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);
    }

    updateTempConnection(e) {
        const [x, y] = this.clientToCanvas(e.clientX, e.clientY);
        const startPoint = this.getConnectionPointPosition(this.connectionStart.nodeId, 'output');
        if (!startPoint) return;

        this.updateWorkspaceBounds([startPoint, { x, y }]);

        if (!this.tempLine) {
            this.tempLine = document.createElementNS('http://www.w3.org/2000/svg', 'path');
            this.tempLine.setAttribute('class', 'connection-line');
            this.tempLine.setAttribute('stroke-dasharray', '5,5');
            this.svg.appendChild(this.tempLine);
        }

        const path = this.createConnectionPath(
            startPoint.x, startPoint.y,
            x, y
        );
        this.tempLine.setAttribute('d', path);
    }

    finishConnection(e) {
        console.log('Finishing connection, event target:', e.target);
        const target = e.target.closest('.connection-point');
        console.log('Connection point target:', target);

        if (!target || target.dataset.point !== 'input') {
            console.log('Not a valid input connection point');
            return;
        }

        const toNodeId = target.dataset.nodeId;
        console.log('Connecting to node:', toNodeId);

        if (toNodeId === this.connectionStart.nodeId) {
            console.log('Cannot connect to self');
            return; // Can't connect to self
        }

        // Check if connection already exists
        const exists = this.connections.some(c =>
            c.from === this.connectionStart.nodeId && c.to === toNodeId
        );

        if (!exists) {
            console.log('Creating new connection');
            this.connections.push({
                from: this.connectionStart.nodeId,
                to: toNodeId
            });
            this.selectedConnection = this.connections.length - 1;
            this.updateConnectionSelectionUI();
            this.render();
        } else {
            console.log('Connection already exists');
        }
    }

    renderConnections() {
        // Remove existing connections
        this.svg.querySelectorAll('.connection-line:not([stroke-dasharray]), .connection-backdrop, .connection-hitbox').forEach(l => l.remove());

        // Render each connection
        this.connections.forEach((conn, index) => {
            const fromPoint = this.getConnectionPointPosition(conn.from, 'output');
            const toPoint = this.getConnectionPointPosition(conn.to, 'input');
            if (!fromPoint || !toPoint) return;

            const path = this.createConnectionPath(
                fromPoint.x, fromPoint.y,
                toPoint.x, toPoint.y
            );

            const backdrop = document.createElementNS('http://www.w3.org/2000/svg', 'path');
            backdrop.setAttribute('class', 'connection-backdrop');
            backdrop.setAttribute('d', path);
            this.svg.appendChild(backdrop);

            const hitbox = document.createElementNS('http://www.w3.org/2000/svg', 'path');
            hitbox.setAttribute('class', 'connection-hitbox');
            hitbox.setAttribute('d', path);

            const line = document.createElementNS('http://www.w3.org/2000/svg', 'path');
            line.setAttribute('class', 'connection-line');
            line.setAttribute('data-connection-index', index);
            line.setAttribute('d', path);

            const setHover = (isHovered) => {
                line.classList.toggle('hovered', isHovered);
                backdrop.classList.toggle('hovered', isHovered);
            };

            const selectConnection = (e) => {
                e.stopPropagation();
                this.selectConnection(index);
            };

            if (this.selectedConnection === index) {
                line.classList.add('selected');
                backdrop.classList.add('selected');
            }

            line.addEventListener('click', selectConnection);
            hitbox.addEventListener('click', selectConnection);
            line.addEventListener('mouseenter', () => setHover(true));
            hitbox.addEventListener('mouseenter', () => setHover(true));
            line.addEventListener('mouseleave', () => setHover(false));
            hitbox.addEventListener('mouseleave', () => setHover(false));

            this.svg.appendChild(line);
            this.svg.appendChild(hitbox);
        });
    }

    getConnectionPointPosition(nodeId, pointType) {
        const nodeElement = this.transformWrapper.querySelector(`.workflow-node[data-node-id="${nodeId}"]`);
        if (!nodeElement) return null;

        const pointElement = nodeElement.querySelector(`.connection-point.${pointType}`);
        if (!pointElement) return null;

        const wrapperRect = this.transformWrapper.getBoundingClientRect();
        const pointRect = pointElement.getBoundingClientRect();
        return {
            x: (pointRect.left - wrapperRect.left + pointRect.width / 2) / this.zoom,
            y: (pointRect.top - wrapperRect.top + pointRect.height / 2) / this.zoom,
        };
    }

    createConnectionPath(x1, y1, x2, y2) {
        const dx = x2 - x1;
        const curve = Math.min(220, Math.max(60, Math.abs(dx) * 0.45 + (dx < 0 ? 70 : 0)));
        const cx1 = x1 + curve;
        const cx2 = x2 - curve;

        return `M ${x1} ${y1} C ${cx1} ${y1}, ${cx2} ${y2}, ${x2} ${y2}`;
    }
}

