/**
 * API client for the Workflow Builder: loading/saving the workflow
 * definition, plus save-status and dirty-tracking bookkeeping around those
 * two calls.
 *
 * Mixed onto WorkflowBuilder.prototype in workflow-builder.js
 * (Object.assign), not a standalone class of its own - these methods read/
 * write `this.nodes`/`this.connections`/`this.config` directly, plus call
 * back into validation/canvas methods (refreshValidationState/selectNode/
 * initializeNodeStackOrder/layoutNeedsNormalization/autoArrangeNodes/
 * setBuilderMessage) that still live on the single WorkflowBuilder
 * instance. Mirrors form-builder-api.js's shape/scope.
 */
export const apiMethods = {
    setSaveStatus(text, tone = 'neutral') {
        const status = document.getElementById('saveStatus');
        if (!status) return;
        status.textContent = text;
        status.dataset.tone = tone;
    },

    getWorkflowSnapshot() {
        return this.store.snapshot();
    },

    syncSavedWorkflowSnapshot() {
        this.lastSavedWorkflowSnapshot = this.getWorkflowSnapshot();
        this.updateDirtyState();
    },

    updateDirtyState() {
        this.isDirty = this.lastSavedWorkflowSnapshot !== null
            && this.getWorkflowSnapshot() !== this.lastSavedWorkflowSnapshot;
        this.updateDirtyIndicator();
    },

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
    },

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
                    this.store.seedNodeIdCounterFromNodes(this.nodes);
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
    },

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
    },
};
