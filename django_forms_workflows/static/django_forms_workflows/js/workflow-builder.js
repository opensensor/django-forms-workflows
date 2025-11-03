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

        console.log('Rendering workflow...');
        this.render();
        console.log('Workflow builder initialized');
    }
    
    setupCanvas() {
        this.canvas = document.getElementById('workflowCanvas');
        this.svg = document.getElementById('connectionsSvg');
        
        // Make canvas droppable
        this.canvas.addEventListener('dragover', (e) => {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'copy';
        });
        
        this.canvas.addEventListener('drop', (e) => {
            e.preventDefault();
            const nodeType = e.dataTransfer.getData('nodeType');
            if (nodeType) {
                const rect = this.canvas.getBoundingClientRect();
                const x = e.clientX - rect.left + this.canvas.scrollLeft;
                const y = e.clientY - rect.top + this.canvas.scrollTop;
                this.createNode(nodeType, x, y);
            }
        });
        
        // Click on canvas to deselect
        this.canvas.addEventListener('click', (e) => {
            if (e.target === this.canvas) {
                this.deselectAll();
            }
        });
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
            } else {
                console.error('Failed to load workflow:', data.error);
            }
        } catch (error) {
            console.error('Error loading workflow:', error);
        }
    }
    
    async saveWorkflow() {
        const saveBtn = document.getElementById('btnSave');
        const originalText = saveBtn.innerHTML;
        saveBtn.disabled = true;
        saveBtn.innerHTML = '<i class="bi bi-hourglass-split"></i> Saving...';
        document.getElementById('saveStatus').textContent = 'Saving...';

        const workflowData = {
            form_id: this.config.formId,
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
                throw new Error(result.error || 'Failed to save workflow');
            }

            document.getElementById('saveStatus').textContent = 'Saved successfully';
            alert('Workflow saved successfully!');
            setTimeout(() => {
                document.getElementById('saveStatus').textContent = 'Ready';
            }, 2000);
        } catch (error) {
            console.error('Error saving workflow:', error);
            alert('Failed to save workflow: ' + error.message);
            document.getElementById('saveStatus').textContent = 'Error saving';
        } finally {
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
        this.render();
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
                    is_initial: false,  // Mark as additional form node
                };
            case 'approval':
                return {
                    approval_type: 'group',
                    step_name: 'Approval Step',
                    group_id: null,
                    logic: 'any'
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
                    to: '',
                    subject: '',
                    template: '',
                    trigger: 'on_approve'
                };
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
        const node = this.nodes.find(n => n.id === nodeId);
        if (node) {
            this.showNodeProperties(node);
        }
        this.render();
    }
    
    deselectAll() {
        this.selectedNode = null;
        this.selectedConnection = null;
        this.showEmptyProperties();
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
                <i class="bi bi-info-circle" style="font-size: 2rem; color: #dee2e6;"></i>
                <p>Select a node to edit its properties</p>
            </div>
        `;
    }
    
    buildPropertiesForm(node) {
        let html = `<h6 class="mb-3">${this.getNodeTypeLabel(node.type)}</h6>`;

        switch (node.type) {
            case 'start':
                html += '<p class="text-muted">This is the workflow start point.</p>';
                break;

            case 'form':
                html += this.buildFormProperties(node);
                break;

            case 'approval_config':
                html += this.buildApprovalConfigProperties(node);
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

            case 'end':
                html += this.buildEndProperties(node);
                break;
        }

        return html;
    }
    
    buildApprovalConfigProperties(node) {
        const data = node.data || {};
        const approvalGroups = data.approval_groups || [];
        const selectedGroupIds = approvalGroups.map(g => g.id);

        let html = `
            <div class="alert alert-info">
                <i class="bi bi-info-circle"></i> Configure approval requirements for this workflow.
            </div>

            <div class="mb-3">
                <div class="form-check form-switch">
                    <input class="form-check-input" type="checkbox" id="requires_manager_approval"
                           name="requires_manager_approval" ${data.requires_manager_approval ? 'checked' : ''}
                           onchange="workflowBuilder.updateApprovalConfig('${node.id}')">
                    <label class="form-check-label" for="requires_manager_approval">
                        <i class="bi bi-person-badge"></i> <strong>Require Manager Approval</strong>
                    </label>
                </div>
                <small class="text-muted d-block mt-1">
                    When enabled, the submitter's manager must approve the request.
                </small>
            </div>

            <hr />

            <div class="mb-3">
                <label class="form-label">
                    <i class="bi bi-people"></i> <strong>Approval Groups</strong>
                </label>
                <small class="text-muted d-block mb-2">
                    Select groups that can approve this workflow.
                </small>
                <select class="form-select" id="approval_groups" name="approval_groups" multiple size="6"
                        style="width: 100%; min-height: 140px;"
                        onchange="workflowBuilder.updateApprovalConfig('${node.id}')">
        `;

        this.groups.forEach(group => {
            const selected = selectedGroupIds.includes(group.id) ? 'selected' : '';
            html += `<option value="${group.id}" ${selected}>${this.escapeHtml(group.name)}</option>`;
        });

        html += `
                </select>
                <small class="text-muted d-block mt-1">
                    Hold Ctrl/Cmd to select multiple groups.
                </small>
            </div>

            <div class="mb-3" id="approval_logic_container" style="${approvalGroups.length > 0 ? '' : 'display:none;'}">
                <label class="form-label">Approval Logic</label>
                <select class="form-select" name="approval_logic"
                        onchange="workflowBuilder.updateApprovalConfig('${node.id}')">
                    <option value="any" ${data.approval_logic === 'any' ? 'selected' : ''}>
                        Any (OR)
                    </option>
                    <option value="all" ${data.approval_logic === 'all' ? 'selected' : ''}>
                        All (AND)
                    </option>
                    <option value="sequence" ${data.approval_logic === 'sequence' ? 'selected' : ''}>
                        Sequential
                    </option>
                </select>
                <small class="text-muted d-block mt-1">
                    <strong>Any:</strong> First approver completes the step (OR logic)<br>
                    <strong>All:</strong> All approvers must approve (AND logic)<br>
                    <strong>Sequential:</strong> Approvers must approve in order
                </small>
            </div>

            <hr />

            <div class="alert ${data.is_implicit ? 'alert-success' : 'alert-warning'} mb-0">
                <i class="bi bi-${data.is_implicit ? 'check-circle' : 'hourglass-split'}"></i>
                <strong>Current Status:</strong>
                ${data.is_implicit ? 'Implicit Approval (auto-approved on submission)' : 'Explicit Approval Required'}
            </div>
        `;

        return html;
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
        const data = node.data || {};
        return `
            <div class="mb-3">
                <label class="form-label">Condition Name</label>
                <input type="text" class="form-control" name="name" value="${this.escapeHtml(data.name || 'Condition')}" placeholder="e.g., Check Amount" />
            </div>
            <div class="mb-3">
                <label class="form-label">Field to Check</label>
                <select class="form-select" name="field">
                    <option value="">Select field...</option>
                    ${this.fields.map(f => `
                        <option value="${f.field_name}" ${data.field === f.field_name ? 'selected' : ''}>${this.escapeHtml(f.field_label)}</option>
                    `).join('')}
                </select>
            </div>
            <div class="mb-3">
                <label class="form-label">Operator</label>
                <select class="form-select" name="operator">
                    <option value="equals" ${data.operator === 'equals' ? 'selected' : ''}>Equals (=)</option>
                    <option value="not_equals" ${data.operator === 'not_equals' ? 'selected' : ''}>Not Equals (≠)</option>
                    <option value="greater_than" ${data.operator === 'greater_than' ? 'selected' : ''}>Greater Than (&gt;)</option>
                    <option value="less_than" ${data.operator === 'less_than' ? 'selected' : ''}>Less Than (&lt;)</option>
                    <option value="greater_or_equal" ${data.operator === 'greater_or_equal' ? 'selected' : ''}>Greater or Equal (≥)</option>
                    <option value="less_or_equal" ${data.operator === 'less_or_equal' ? 'selected' : ''}>Less or Equal (≤)</option>
                    <option value="contains" ${data.operator === 'contains' ? 'selected' : ''}>Contains</option>
                    <option value="not_contains" ${data.operator === 'not_contains' ? 'selected' : ''}>Does Not Contain</option>
                    <option value="is_empty" ${data.operator === 'is_empty' ? 'selected' : ''}>Is Empty</option>
                    <option value="is_not_empty" ${data.operator === 'is_not_empty' ? 'selected' : ''}>Is Not Empty</option>
                </select>
            </div>
            <div class="mb-3">
                <label class="form-label">Compare Value</label>
                <input type="text" class="form-control" name="value" value="${this.escapeHtml(data.value || '')}" placeholder="Value to compare against" />
                <small class="text-muted">Leave empty for "is empty" / "is not empty" operators</small>
            </div>
            <hr class="my-3" />
            <p class="text-muted small mb-2">
                <i class="bi bi-info-circle"></i> Connect the output to different nodes for TRUE and FALSE paths
            </p>
        `;
    }
    
    buildActionProperties(node) {
        const data = node.data || {};
        return `
            <div class="mb-3">
                <label class="form-label">Action Name</label>
                <input type="text" class="form-control" name="name" value="${this.escapeHtml(data.name || '')}" placeholder="e.g., Update User Record" />
            </div>
            <div class="mb-3">
                <label class="form-label">Action Type</label>
                <select class="form-select" name="action_type">
                    <option value="database" ${data.action_type === 'database' ? 'selected' : ''}>Database Update</option>
                    <option value="ldap" ${data.action_type === 'ldap' ? 'selected' : ''}>LDAP Update</option>
                    <option value="api" ${data.action_type === 'api' ? 'selected' : ''}>API Call</option>
                    <option value="custom" ${data.action_type === 'custom' ? 'selected' : ''}>Custom Handler</option>
                </select>
            </div>
            <div class="mb-3">
                <label class="form-label">When to Execute</label>
                <select class="form-select" name="trigger">
                    <option value="on_submit" ${data.trigger === 'on_submit' ? 'selected' : ''}>On Submission</option>
                    <option value="on_approve" ${data.trigger === 'on_approve' ? 'selected' : ''}>On Approval</option>
                    <option value="on_reject" ${data.trigger === 'on_reject' ? 'selected' : ''}>On Rejection</option>
                    <option value="on_complete" ${data.trigger === 'on_complete' ? 'selected' : ''}>On Complete</option>
                </select>
            </div>
            <hr class="my-3" />
            <div class="mb-3">
                <label class="form-label">Configuration (JSON)</label>
                <textarea class="form-control font-monospace" name="config" rows="4" placeholder='{"table": "users", "field": "status", "value": "approved"}'>${this.escapeHtml(JSON.stringify(data.config || {}, null, 2))}</textarea>
                <small class="text-muted">Action-specific configuration in JSON format</small>
            </div>
        `;
    }

    buildEmailProperties(node) {
        const data = node.data || {};
        return `
            <div class="mb-3">
                <label class="form-label">Email Name</label>
                <input type="text" class="form-control" name="name" value="${this.escapeHtml(data.name || '')}" placeholder="e.g., Approval Notification" />
            </div>
            <div class="mb-3">
                <label class="form-label">Recipients</label>
                <input type="text" class="form-control" name="to" value="${this.escapeHtml(data.to || '')}" placeholder="email@example.com or {field_name}" />
                <small class="text-muted">Use {field_name} to reference form fields, or enter email addresses</small>
            </div>
            <div class="mb-3">
                <label class="form-label">Subject</label>
                <input type="text" class="form-control" name="subject" value="${this.escapeHtml(data.subject || '')}" placeholder="Your request has been approved" />
            </div>
            <div class="mb-3">
                <label class="form-label">Email Template</label>
                <select class="form-select" name="template">
                    <option value="">Select template...</option>
                    <option value="approval_notification" ${data.template === 'approval_notification' ? 'selected' : ''}>Approval Notification</option>
                    <option value="rejection_notification" ${data.template === 'rejection_notification' ? 'selected' : ''}>Rejection Notification</option>
                    <option value="submission_confirmation" ${data.template === 'submission_confirmation' ? 'selected' : ''}>Submission Confirmation</option>
                    <option value="custom" ${data.template === 'custom' ? 'selected' : ''}>Custom Template</option>
                </select>
            </div>
            <div class="mb-3">
                <label class="form-label">When to Send</label>
                <select class="form-select" name="trigger">
                    <option value="on_submit" ${data.trigger === 'on_submit' ? 'selected' : ''}>On Submission</option>
                    <option value="on_approve" ${data.trigger === 'on_approve' ? 'selected' : ''}>On Approval</option>
                    <option value="on_reject" ${data.trigger === 'on_reject' ? 'selected' : ''}>On Rejection</option>
                    <option value="on_complete" ${data.trigger === 'on_complete' ? 'selected' : ''}>On Complete</option>
                </select>
            </div>
        `;
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

    updateApprovalConfig(nodeId) {
        const node = this.nodes.find(n => n.id === nodeId);
        if (!node) return;

        // Get form values
        const requiresManager = document.getElementById('requires_manager_approval').checked;
        const groupSelect = document.getElementById('approval_groups');
        const selectedGroups = Array.from(groupSelect.selectedOptions).map(opt => ({
            id: parseInt(opt.value),
            name: opt.text
        }));
        const approvalLogic = document.querySelector('select[name="approval_logic"]').value;

        // Update node data
        node.data.requires_manager_approval = requiresManager;
        node.data.approval_groups = selectedGroups;
        node.data.approval_logic = approvalLogic;
        node.data.is_implicit = !requiresManager && selectedGroups.length === 0;

        // Show/hide approval logic based on group selection
        const logicContainer = document.getElementById('approval_logic_container');
        if (logicContainer) {
            logicContainer.style.display = selectedGroups.length > 0 ? '' : 'none';
        }

        // Re-render to update the node display and properties panel
        this.render();
        this.selectNode(nodeId); // Re-select to refresh properties panel
    }
    
    getNodeTypeLabel(type) {
        const labels = {
            start: 'Start',
            form: 'Form Submission',
            approval_config: 'Approval Configuration',
            approval: 'Approval Step',
            condition: 'Condition',
            action: 'Action',
            email: 'Email Notification',
            end: 'End'
        };
        return labels[type] || type;
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    render() {
        console.log('Rendering workflow with', this.nodes.length, 'nodes and', this.connections.length, 'connections');
        this.renderNodes();
        this.renderConnections();
    }

    renderNodes() {
        console.log('Rendering nodes...');
        // Remove existing nodes
        this.canvas.querySelectorAll('.workflow-node').forEach(n => n.remove());

        // Render each node
        this.nodes.forEach(node => {
            console.log('Creating node element for:', node);
            const nodeEl = this.createNodeElement(node);
            this.canvas.appendChild(nodeEl);
        });
        console.log('Nodes rendered');
    }
    
    createNodeElement(node) {
        const div = document.createElement('div');
        div.className = `workflow-node ${node.type}`;
        if (this.selectedNode === node.id) {
            div.className += ' selected';
        }
        div.style.left = `${node.x}px`;
        div.style.top = `${node.y}px`;
        div.dataset.nodeId = node.id;

        const icon = this.getNodeIcon(node.type);
        const label = node.data.step_name || node.data.name || this.getNodeTypeLabel(node.type);

        // Determine if node can be deleted
        // - start: never deletable
        // - approval_config: never deletable
        // - form: only deletable if it's an additional form (is_initial === false)
        // - all others: deletable
        const canDelete = node.type !== 'start' &&
                         node.type !== 'approval_config' &&
                         !(node.type === 'form' && node.data.is_initial !== false);

        div.innerHTML = `
            <div class="node-header">
                <div class="node-icon ${node.type}">
                    <i class="bi bi-${icon}"></i>
                </div>
                <span>${this.escapeHtml(label)}</span>
            </div>
            <div class="node-content">
                ${this.getNodeDescription(node)}
            </div>
            ${canDelete ? `
                <div class="node-actions">
                    <button class="btn btn-sm btn-outline-danger" onclick="workflowBuilder.deleteNode('${node.id}')">
                        <i class="bi bi-trash"></i>
                    </button>
                </div>
            ` : ''}
            <div class="connection-point input" data-node-id="${node.id}" data-point="input"></div>
            <div class="connection-point output" data-node-id="${node.id}" data-point="output"></div>
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
                    inputPoint.style.background = '#28a745';
                    inputPoint.style.transform = 'translateY(-50%) scale(1.5)';
                }
            });
            inputPoint.addEventListener('mouseleave', (e) => {
                inputPoint.style.background = '#667eea';
                inputPoint.style.transform = 'translateY(-50%) scale(1)';
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
            approval_config: 'shield-check',
            approval: 'person-check',
            condition: 'diagram-3',
            action: 'lightning',
            email: 'envelope',
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
            case 'approval_config':
                if (node.data.is_implicit) {
                    return '<span class="badge bg-success"><i class="bi bi-check-circle"></i> Implicit Approval</span><br><small class="text-muted">Auto-approved on submission</small>';
                } else {
                    const parts = [];
                    if (node.data.requires_manager_approval) {
                        parts.push('Manager');
                    }
                    if (node.data.approval_groups && node.data.approval_groups.length > 0) {
                        const groupCount = node.data.approval_groups.length;
                        const logic = node.data.approval_logic || 'any';
                        parts.push(`${groupCount} group${groupCount > 1 ? 's' : ''} (${logic})`);
                    }
                    return `<span class="badge bg-warning"><i class="bi bi-hourglass-split"></i> Requires Approval</span><br><small class="text-muted">${parts.join(' + ')}</small>`;
                }
            case 'approval':
                if (node.data.approval_type === 'manager') {
                    return 'Manager approval required';
                } else if (node.data.group_id) {
                    const group = this.groups.find(g => g.id == node.data.group_id);
                    return group ? `Group: ${group.name}` : 'Select group';
                }
                return 'Configure approval';
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
                return node.data.to ? `Send to: ${node.data.to}` : 'Configure email';
            case 'end':
                return 'Workflow end';
            default:
                return '';
        }
    }

    startDragNode(e, node) {
        this.isDraggingNode = true;
        const startX = e.clientX;
        const startY = e.clientY;
        const nodeStartX = node.x;
        const nodeStartY = node.y;

        const onMouseMove = (e) => {
            const dx = e.clientX - startX;
            const dy = e.clientY - startY;
            node.x = nodeStartX + dx;
            node.y = nodeStartY + dy;
            this.render();
        };

        const onMouseUp = () => {
            this.isDraggingNode = false;
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
        const rect = this.canvas.getBoundingClientRect();
        const x = e.clientX - rect.left + this.canvas.scrollLeft;
        const y = e.clientY - rect.top + this.canvas.scrollTop;

        const startNode = this.nodes.find(n => n.id === this.connectionStart.nodeId);
        if (!startNode) return;

        if (!this.tempLine) {
            this.tempLine = document.createElementNS('http://www.w3.org/2000/svg', 'path');
            this.tempLine.setAttribute('class', 'connection-line');
            this.tempLine.setAttribute('stroke-dasharray', '5,5');
            this.svg.appendChild(this.tempLine);
        }

        const path = this.createConnectionPath(
            startNode.x + 180, startNode.y + 40,
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
            this.render();
        } else {
            console.log('Connection already exists');
        }
    }

    renderConnections() {
        // Remove existing connections
        this.svg.querySelectorAll('.connection-line:not([stroke-dasharray])').forEach(l => l.remove());

        // Render each connection
        this.connections.forEach((conn, index) => {
            const fromNode = this.nodes.find(n => n.id === conn.from);
            const toNode = this.nodes.find(n => n.id === conn.to);

            if (!fromNode || !toNode) return;

            const line = document.createElementNS('http://www.w3.org/2000/svg', 'path');
            line.setAttribute('class', 'connection-line');
            line.setAttribute('data-connection-index', index);
            line.style.cursor = 'pointer';

            const path = this.createConnectionPath(
                fromNode.x + 180, fromNode.y + 40,
                toNode.x, toNode.y + 40
            );
            line.setAttribute('d', path);

            // Add click handler to delete connection
            line.addEventListener('click', (e) => {
                e.stopPropagation();
                if (confirm('Delete this connection?')) {
                    this.connections.splice(index, 1);
                    this.render();
                }
            });

            // Add hover effect
            line.addEventListener('mouseenter', () => {
                line.style.stroke = '#dc3545';
                line.style.strokeWidth = '3';
            });

            line.addEventListener('mouseleave', () => {
                line.style.stroke = '';
                line.style.strokeWidth = '';
            });

            this.svg.appendChild(line);
        });
    }

    createConnectionPath(x1, y1, x2, y2) {
        const dx = x2 - x1;
        const dy = y2 - y1;
        const cx1 = x1 + Math.abs(dx) / 2;
        const cx2 = x2 - Math.abs(dx) / 2;

        return `M ${x1} ${y1} C ${cx1} ${y1}, ${cx2} ${y2}, ${x2} ${y2}`;
    }
}

