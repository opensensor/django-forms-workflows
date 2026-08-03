 * Property editor for the Form Builder: the field-properties modal (Basic/
 * Conditional Logic/Validation/Dependencies tabs) and saving those changes
 * back onto the field.
 *
 * Mixed onto FormBuilder.prototype in form-builder.js (Object.assign), not a
 * standalone class of its own - these methods read/write a large number of
 * page DOM fields directly, plus `this.fields`/`this.currentFieldIndex`/
 * `this.isNewField`/`this.config`, and call back into
 * deleteFieldSilently()/escapeHtml()/renderCanvas()/updatePreview(), which
 * still live on the single FormBuilder instance.
 */
export const propertyEditorMethods = {
    editField(index, isNew = false) {
        this.currentFieldIndex = index;
        this.isNewField = isNew;
        const field = this.fields[index];

        // Build property form
        const form = this.buildPropertyForm(field);
        document.getElementById('fieldPropertyForm').innerHTML = form;
        this.initializePropertyFormTabs(field);

        // Show modal
        const modalElement = document.getElementById('fieldPropertyModal');
        const modal = new bootstrap.Modal(modalElement);

        // Handle modal close/cancel - remove field if it's new and not saved
        const handleModalClose = () => {
            if (this.isNewField) {
                // Field was not saved, remove it
                this.deleteFieldSilently(this.currentFieldIndex);
            }
            this.isNewField = false;
            // Remove event listener to avoid memory leaks
            modalElement.removeEventListener('hidden.bs.modal', handleModalClose);
        };

        // Add event listener for modal close
        modalElement.addEventListener('hidden.bs.modal', handleModalClose);

        modal.show();
    },

    buildPropertyForm(field) {
        const prefillOptions = this.config.prefillSources.map(source =>
            `<option value="${source.id}" ${field.prefill_source_id === source.id ? 'selected' : ''}>
                ${this.escapeHtml(source.name)}
            </option>`
        ).join('');

        const widthChoices = [
            { value: 'full', label: 'Full Width' },
            { value: 'half', label: 'Half (50%)' },
            { value: 'third', label: 'One Third (33%)' },
            { value: 'fourth', label: 'One Quarter (25%)' }
        ];
        const widthOptions = widthChoices.map(w =>
            `<option value="${w.value}" ${field.width === w.value ? 'selected' : ''}>${w.label}</option>`
        ).join('');

        return `
            <!-- Tabs Navigation -->
            <ul class="nav nav-tabs mb-3" role="tablist">
                <li class="nav-item" role="presentation">
                    <button class="nav-link active" id="basic-tab" data-bs-toggle="tab" data-bs-target="#basic-panel" type="button" role="tab">
                        <i class="bi bi-gear"></i> Basic
                    </button>
                </li>
                <li class="nav-item" role="presentation">
                    <button class="nav-link" id="conditional-tab" data-bs-toggle="tab" data-bs-target="#conditional-panel" type="button" role="tab">
                        <i class="bi bi-diagram-3"></i> Conditional Logic
                    </button>
                </li>
                <li class="nav-item" role="presentation">
                    <button class="nav-link" id="validation-tab" data-bs-toggle="tab" data-bs-target="#validation-panel" type="button" role="tab">
                        <i class="bi bi-check-circle"></i> Validation
                    </button>
                </li>
                <li class="nav-item" role="presentation">
                    <button class="nav-link" id="dependencies-tab" data-bs-toggle="tab" data-bs-target="#dependencies-panel" type="button" role="tab">
                        <i class="bi bi-link-45deg"></i> Dependencies
                    </button>
                </li>
            </ul>

            <!-- Tabs Content -->
            <div class="tab-content">
                <!-- Basic Tab -->
                <div class="tab-pane fade show active" id="basic-panel" role="tabpanel">
                    ${this.buildBasicPropertiesTab(field, prefillOptions, widthOptions)}
                </div>

                <!-- Conditional Logic Tab -->
                <div class="tab-pane fade" id="conditional-panel" role="tabpanel">
                    ${this.buildConditionalLogicTab(field)}
                </div>

                <!-- Validation Tab -->
                <div class="tab-pane fade" id="validation-panel" role="tabpanel">
                    ${this.buildValidationTab(field)}
                </div>

                <!-- Dependencies Tab -->
                <div class="tab-pane fade" id="dependencies-panel" role="tabpanel">
                    ${this.buildDependenciesTab(field)}
                </div>
            </div>
        `;
    },

    buildBasicPropertiesTab(field, prefillOptions, widthOptions) {
        return `
            <div class="row g-3">
                <div class="col-md-6">
                    <label class="form-label">Field Label <span class="text-danger">*</span></label>
                    <input type="text" class="form-control" id="propFieldLabel" value="${this.escapeHtml(field.field_label)}" required>
                </div>
                <div class="col-md-6">
                    <label class="form-label">Field Name <span class="text-danger">*</span></label>
                    <input type="text" class="form-control" id="propFieldName" value="${this.escapeHtml(field.field_name)}" required>
                </div>
                <div class="col-md-6">
                    <label class="form-label">Field Type</label>
                    <input type="text" class="form-control" value="${this.escapeHtml(field.field_type)}" disabled>
                </div>
                <div class="col-md-6">
                    <label class="form-label">Width</label>
                    <select class="form-select" id="propWidth">
                        ${widthOptions}
                    </select>
                </div>
                <div class="col-12">
                    <div class="form-check">
                        <input class="form-check-input" type="checkbox" id="propRequired" ${field.required ? 'checked' : ''}>
                        <label class="form-check-label" for="propRequired">Required Field</label>
                    </div>
                </div>
                <div class="col-12">
                    <label class="form-label">Help Text</label>
                    <input type="text" class="form-control" id="propHelpText" value="${this.escapeHtml(field.help_text)}">
                    <div class="form-check mt-1">
                        <input class="form-check-input" type="checkbox" id="propShowHelpTextInDetail" ${field.show_help_text_in_detail ? 'checked' : ''}>
                        <label class="form-check-label small text-muted" for="propShowHelpTextInDetail">
                            Also show this help text next to the value in the submission/approval detail view (use for attestation / consent statements on initials fields).
                        </label>
                    </div>
                </div>
                <div class="col-12">
                    <label class="form-label">Placeholder</label>
                    <input type="text" class="form-control" id="propPlaceholder" value="${this.escapeHtml(field.placeholder)}">
                </div>
                ${['select', 'radio', 'checkbox_multiple', 'multiselect', 'multiselect_list', 'checkboxes'].includes(field.field_type) ? `
                <div class="col-12">
                    <label class="form-label">Choices (one per line)</label>
                    <textarea class="form-control" id="propChoices" rows="4">${this.escapeHtml(field.choices)}</textarea>
                    <small class="text-muted">Enter each option on a new line. Use <code>value|Label</code> format for separate values and display text.</small>
                </div>
                ` : ''}
                ${field.field_type === 'calculated' ? `
                <div class="col-12">
                    <label class="form-label">Formula</label>
                    <input type="text" class="form-control font-monospace" id="propDefaultValue" value="${this.escapeHtml(field.default_value)}" placeholder="e.g. {field_a} + {field_b}">
                    <small class="text-muted">Use <code>{field_name}</code> to reference other fields. Evaluated live on the client and re-validated on the server.</small>
                </div>
                ` : ''}
                ${field.field_type === 'display_text' ? `
                <div class="col-12">
                    <label class="form-label">Display Content (Markdown)</label>
                    <textarea class="form-control font-monospace" id="propDefaultValue" rows="6">${this.escapeHtml(field.default_value || '')}</textarea>
                    <small class="text-muted">Supports Markdown: **bold**, *italic*, [links](url), lists, etc. This text is shown read-only on the form.</small>
                </div>
                ` : ''}
                ${field.field_type === 'rating' ? `
                <div class="col-md-6">
                    <label class="form-label">Max Stars</label>
                    <input type="number" class="form-control" id="propMaxValue" value="${field.validation?.max_value || 5}" min="3" max="10">
                    <small class="text-muted">Number of stars to display (3-10)</small>
                </div>
                ` : ''}
                ${field.field_type === 'slider' ? `
                <div class="col-md-4">
                    <label class="form-label">Min Value</label>
                    <input type="number" class="form-control" id="propMinValue" value="${field.validation?.min_value || 0}">
                </div>
                <div class="col-md-4">
                    <label class="form-label">Max Value</label>
                    <input type="number" class="form-control" id="propMaxValue" value="${field.validation?.max_value || 100}">
                </div>
                <div class="col-md-4">
                    <label class="form-label">Step</label>
                    <input type="number" class="form-control" id="propDefaultValue" value="${this.escapeHtml(field.default_value || '1')}" min="0.01">
                    <small class="text-muted">Increment value</small>
                </div>
                ` : ''}
                ${field.field_type === 'matrix' ? `
                <div class="col-12">
                    <label class="form-label">Matrix Configuration (JSON)</label>
                    <textarea class="form-control font-monospace" id="propChoices" rows="5">${this.escapeHtml(typeof field.choices === 'object' ? JSON.stringify(field.choices, null, 2) : (field.choices || '{"rows": ["Row 1", "Row 2"], "columns": ["Col A", "Col B", "Col C"]}'))}</textarea>
                    <small class="text-muted">Define rows and columns as JSON: <code>{"rows": [...], "columns": [...]}</code></small>
                </div>
                ` : ''}
                <div class="col-12">
                    <label class="form-label">Prefill Source</label>
                    <select class="form-select" id="propPrefillSource">
                        <option value="">None</option>
                        ${prefillOptions}
                    </select>
                </div>
                ${['select', 'radio', 'checkbox_multiple', 'multiselect', 'multiselect_list', 'checkboxes'].includes(field.field_type) ? `
                <div class="col-12">
                    <label class="form-label">Shared Option List</label>
                    <select class="form-select" id="propSharedOptionList">
                        <option value="">None (use inline choices)</option>
                        ${(this.config.sharedOptionLists || []).map(ol =>
                            '<option value="' + ol.id + '"' + (field.shared_option_list_id === ol.id ? ' selected' : '') + '>' +
                            this.escapeHtml(ol.name) + ' (' + ol.itemCount + ' options)</option>'
                        ).join('')}
                    </select>
                    <small class="text-muted">Centrally managed list — updates apply to all forms using it.</small>
                </div>
                ` : ''}
                <div class="col-12">
                    <label class="form-label">CSS Class</label>
                    <input type="text" class="form-control" id="propCssClass" value="${this.escapeHtml(field.css_class)}">
                </div>
                <div class="col-12">
                    <label class="form-label">Approval Step</label>
                    <select class="form-select" id="propApprovalStep">
                        <option value="" ${!field.approval_step ? 'selected' : ''}>None (Student-facing)</option>
                        <option value="1" ${field.approval_step === 1 ? 'selected' : ''}>Step 1</option>
                        <option value="2" ${field.approval_step === 2 ? 'selected' : ''}>Step 2</option>
                        <option value="3" ${field.approval_step === 3 ? 'selected' : ''}>Step 3</option>
                        <option value="4" ${field.approval_step === 4 ? 'selected' : ''}>Step 4</option>
                    </select>
                    <small class="text-muted">Assign to an approval step for sequential approval workflows</small>
                </div>
            </div>
        `;
    },

    buildConditionalLogicTab(field) {
        // Initialize conditional_rules if not present
        if (!field.conditional_rules) {
            field.conditional_rules = null;
        }

        const conditionalRulesJson = field.conditional_rules ? JSON.stringify(field.conditional_rules, null, 2) : '';

        // Get list of other fields for dropdown
        const otherFields = this.fields.filter(f => f.field_name !== field.field_name);
        const fieldOptions = otherFields.map(f =>
            `<option value="${f.field_name}">${this.escapeHtml(f.field_label)} (${f.field_name})</option>`
        ).join('');

        return `
            <div class="row g-3">
                <div class="col-12">
                    <div class="alert alert-info small">
                        <i class="bi bi-info-circle"></i>
                        <strong>Conditional Logic</strong> allows you to show/hide or require/unrequire this field based on other field values.
                    </div>
                </div>

                <div class="col-12">
                    <div class="form-check form-switch">
                        <input class="form-check-input" type="checkbox" id="propEnableConditional" ${field.conditional_rules ? 'checked' : ''}>
                        <label class="form-check-label" for="propEnableConditional">Enable Conditional Logic</label>
                    </div>
                </div>

                <div id="conditionalRulesContainer" style="display: ${field.conditional_rules ? 'block' : 'none'};">
                    <div class="col-12">
                        <label class="form-label">Logical Operator</label>
                        <select class="form-select" id="propConditionalOperator">
                            <option value="AND" ${field.conditional_rules?.operator === 'AND' ? 'selected' : ''}>AND (all conditions must be true)</option>
                            <option value="OR" ${field.conditional_rules?.operator === 'OR' ? 'selected' : ''}>OR (any condition can be true)</option>
                        </select>
                    </div>

                    <div class="col-12">
                        <label class="form-label">Action</label>
                        <select class="form-select" id="propConditionalAction">
                            <option value="show" ${field.conditional_rules?.action === 'show' ? 'selected' : ''}>Show field</option>
                            <option value="hide" ${field.conditional_rules?.action === 'hide' ? 'selected' : ''}>Hide field</option>
                            <option value="require" ${field.conditional_rules?.action === 'require' ? 'selected' : ''}>Make required</option>
                            <option value="unrequire" ${field.conditional_rules?.action === 'unrequire' ? 'selected' : ''}>Make optional</option>
                            <option value="enable" ${field.conditional_rules?.action === 'enable' ? 'selected' : ''}>Enable field</option>
                            <option value="disable" ${field.conditional_rules?.action === 'disable' ? 'selected' : ''}>Disable field</option>
                        </select>
                    </div>

                    <div class="col-12">
                        <label class="form-label">Conditions</label>
                        <div id="conditionsList"></div>
                        <button type="button" class="btn btn-sm btn-outline-primary mt-2" id="btnAddCondition">
                            <i class="bi bi-plus-circle"></i> Add Condition
                        </button>
                    </div>

                    <div class="col-12">
                        <label class="form-label">JSON Preview (Advanced)</label>
                        <textarea class="form-control font-monospace small" id="propConditionalRulesJson" rows="6">${this.escapeHtml(conditionalRulesJson)}</textarea>
                        <small class="text-muted">You can edit the JSON directly for advanced configurations</small>
                    </div>
                </div>
            </div>
        `;
    },

    buildValidationTab(field) {
        // Initialize validation_rules if not present
        if (!field.validation_rules) {
            field.validation_rules = [];
        }

        const validationRulesJson = field.validation_rules.length > 0 ? JSON.stringify(field.validation_rules, null, 2) : '';

        return `
            <div class="row g-3">
                <div class="col-12">
                    <div class="alert alert-info small">
                        <i class="bi bi-info-circle"></i>
                        <strong>Validation Rules</strong> provide real-time client-side validation with custom error messages.
                    </div>
                </div>

                <div class="col-12">
                    <label class="form-label">Validation Rules</label>
                    <div id="validationRulesList"></div>
                    <button type="button" class="btn btn-sm btn-outline-primary mt-2" id="btnAddValidation">
                        <i class="bi bi-plus-circle"></i> Add Validation Rule
                    </button>
                </div>

                <div class="col-12">
                    <label class="form-label">JSON Preview (Advanced)</label>
                    <textarea class="form-control font-monospace small" id="propValidationRulesJson" rows="6">${this.escapeHtml(validationRulesJson)}</textarea>
                    <small class="text-muted">You can edit the JSON directly for advanced configurations</small>
                </div>
            </div>
        `;
    },

    buildDependenciesTab(field) {
        // Initialize field_dependencies if not present
        if (!field.field_dependencies) {
            field.field_dependencies = [];
        }

        const dependenciesJson = field.field_dependencies.length > 0 ? JSON.stringify(field.field_dependencies, null, 2) : '';

        // Get list of other fields for dropdown
        const otherFields = this.fields.filter(f => f.field_name !== field.field_name);
        const fieldOptions = otherFields.map(f =>
            `<option value="${f.field_name}">${this.escapeHtml(f.field_label)} (${f.field_name})</option>`
        ).join('');

        return `
            <div class="row g-3">
                <div class="col-12">
                    <div class="alert alert-info small">
                        <i class="bi bi-info-circle"></i>
                        <strong>Field Dependencies</strong> allow this field's options to update based on other field values (cascade updates).
                    </div>
                </div>

                <div class="col-12">
                    <label class="form-label">Dependencies</label>
                    <div id="dependenciesList"></div>
                    <button type="button" class="btn btn-sm btn-outline-primary mt-2" id="btnAddDependency">
                        <i class="bi bi-plus-circle"></i> Add Dependency
                    </button>
                </div>

                <div class="col-12">
                    <label class="form-label">JSON Preview (Advanced)</label>
                    <textarea class="form-control font-monospace small" id="propDependenciesJson" rows="6">${this.escapeHtml(dependenciesJson)}</textarea>
                    <small class="text-muted">You can edit the JSON directly for advanced configurations</small>
                </div>
            </div>
        `;
    },

    initializePropertyFormTabs(field) {
        // Wires up the interactive bits of the Conditional Logic, Validation,
        // and Dependencies tabs.
        const enableConditional = document.getElementById('propEnableConditional');
        const conditionalRulesContainer = document.getElementById('conditionalRulesContainer');
        if (enableConditional && conditionalRulesContainer) {
            enableConditional.addEventListener('change', (e) => {
                conditionalRulesContainer.style.display = e.target.checked ? 'block' : 'none';
            });
        }
        this.initializeConditionsList(field.conditional_rules?.conditions || []);
        this.initializeValidationRulesList(field.validation_rules || []);
        this.initializeDependenciesList(field.field_dependencies || []);
    },

    initializeConditionsList(conditions) {
        const container = document.getElementById('conditionsList');
        if (!container) return;

        container.innerHTML = '';
        conditions.forEach((condition, index) => {
            this.addConditionRow(condition, index);
        });

        // Add event listener for add button
        const btnAdd = document.getElementById('btnAddCondition');
        if (btnAdd) {
            btnAdd.addEventListener('click', () => this.addConditionRow({}, conditions.length));
        }
    },

    addConditionRow(condition, index) {
        const container = document.getElementById('conditionsList');
        if (!container) return;

        const otherFields = this.fields.filter(f => f.field_name !== this.fields[this.currentFieldIndex].field_name);
        const fieldOptions = otherFields.map(f =>
            `<option value="${f.field_name}" ${condition.field === f.field_name ? 'selected' : ''}>${this.escapeHtml(f.field_label)}</option>`
        ).join('');

        const row = document.createElement('div');
        row.className = 'card mb-2';
        row.innerHTML = `
            <div class="card-body p-2">
                <div class="row g-2">
                    <div class="col-md-4">
                        <select class="form-select form-select-sm condition-field" data-index="${index}">
                            <option value="">Select field...</option>
                            ${fieldOptions}
                        </select>
                    </div>
                    <div class="col-md-3">
                        <select class="form-select form-select-sm condition-operator" data-index="${index}">
                            <option value="equals" ${condition.operator === 'equals' ? 'selected' : ''}>Equals</option>
                            <option value="not_equals" ${condition.operator === 'not_equals' ? 'selected' : ''}>Not Equals</option>
                            <option value="contains" ${condition.operator === 'contains' ? 'selected' : ''}>Contains</option>
                            <option value="not_contains" ${condition.operator === 'not_contains' ? 'selected' : ''}>Not Contains</option>
                            <option value="greater_than" ${condition.operator === 'greater_than' ? 'selected' : ''}>Greater Than</option>
                            <option value="less_than" ${condition.operator === 'less_than' ? 'selected' : ''}>Less Than</option>
                            <option value="is_empty" ${condition.operator === 'is_empty' ? 'selected' : ''}>Is Empty</option>
                            <option value="not_empty" ${condition.operator === 'not_empty' || condition.operator === 'is_not_empty' ? 'selected' : ''}>Is Not Empty</option>
                        </select>
                    </div>
                    <div class="col-md-4">
                        <input type="text" class="form-control form-control-sm condition-value" data-index="${index}"
                               value="${this.escapeHtml(condition.value || '')}" placeholder="Value">
                    </div>
                    <div class="col-md-1">
                        <button type="button" class="btn btn-sm btn-outline-danger" onclick="this.closest('.card').remove()">
                            <i class="bi bi-trash"></i>
                        </button>
                    </div>
                </div>
            </div>
        `;
        container.appendChild(row);
    },

    initializeValidationRulesList(rules) {
        const container = document.getElementById('validationRulesList');
        if (!container) return;

        container.innerHTML = '';
        rules.forEach((rule, index) => {
            this.addValidationRuleRow(rule, index);
        });

        // Add event listener for add button
        const btnAdd = document.getElementById('btnAddValidation');
        if (btnAdd) {
            btnAdd.addEventListener('click', () => this.addValidationRuleRow({}, rules.length));
        }
    },

    addValidationRuleRow(rule, index) {
        const container = document.getElementById('validationRulesList');
        if (!container) return;

        const row = document.createElement('div');
        row.className = 'card mb-2';
        row.innerHTML = `
            <div class="card-body p-2">
                <div class="row g-2">
                    <div class="col-md-3">
                        <select class="form-select form-select-sm validation-type" data-index="${index}">
                            <option value="required" ${rule.type === 'required' ? 'selected' : ''}>Required</option>
                            <option value="email" ${rule.type === 'email' ? 'selected' : ''}>Email</option>
                            <option value="url" ${rule.type === 'url' ? 'selected' : ''}>URL</option>
                            <option value="min" ${rule.type === 'min' ? 'selected' : ''}>Min Length</option>
                            <option value="max" ${rule.type === 'max' ? 'selected' : ''}>Max Length</option>
                            <option value="pattern" ${rule.type === 'pattern' ? 'selected' : ''}>Pattern (Regex)</option>
                            <option value="min_value" ${rule.type === 'min_value' ? 'selected' : ''}>Min Value</option>
                            <option value="max_value" ${rule.type === 'max_value' ? 'selected' : ''}>Max Value</option>
                        </select>
                    </div>
                    <div class="col-md-3">
                        <input type="text" class="form-control form-control-sm validation-value" data-index="${index}"
                               value="${this.escapeHtml(rule.value || '')}" placeholder="Value (if needed)">
                    </div>
                    <div class="col-md-5">
                        <input type="text" class="form-control form-control-sm validation-message" data-index="${index}"
                               value="${this.escapeHtml(rule.message || '')}" placeholder="Error message">
                    </div>
                    <div class="col-md-1">
                        <button type="button" class="btn btn-sm btn-outline-danger" onclick="this.closest('.card').remove()">
                            <i class="bi bi-trash"></i>
                        </button>
                    </div>
                </div>
            </div>
        `;
        container.appendChild(row);
    },

    initializeDependenciesList(dependencies) {
        const container = document.getElementById('dependenciesList');
        if (!container) return;

        container.innerHTML = '';
        dependencies.forEach((dep, index) => {
            this.addDependencyRow(dep, index);
        });

        // Add event listener for add button
        const btnAdd = document.getElementById('btnAddDependency');
        if (btnAdd) {
            btnAdd.addEventListener('click', () => this.addDependencyRow({}, dependencies.length));
        }
    },

    addDependencyRow(dependency, index) {
        const container = document.getElementById('dependenciesList');
        if (!container) return;

        const otherFields = this.fields.filter(f => f.field_name !== this.fields[this.currentFieldIndex].field_name);
        const fieldOptions = otherFields.map(f =>
            `<option value="${f.field_name}" ${dependency.sourceField === f.field_name ? 'selected' : ''}>${this.escapeHtml(f.field_label)}</option>`
        ).join('');

        const row = document.createElement('div');
        row.className = 'card mb-2';
        row.innerHTML = `
            <div class="card-body p-2">
                <div class="row g-2">
                    <div class="col-md-5">
                        <label class="form-label small mb-1">Source Field</label>
                        <select class="form-select form-select-sm dependency-source" data-index="${index}">
                            <option value="">Select field...</option>
                            ${fieldOptions}
                        </select>
                    </div>
                    <div class="col-md-6">
                        <label class="form-label small mb-1">API Endpoint</label>
                        <input type="text" class="form-control form-control-sm dependency-endpoint" data-index="${index}"
                               value="${this.escapeHtml(dependency.apiEndpoint || '')}" placeholder="/api/get-options/">
                    </div>
                    <div class="col-md-1 d-flex align-items-end">
                        <button type="button" class="btn btn-sm btn-outline-danger" onclick="this.closest('.card').remove()">
                            <i class="bi bi-trash"></i>
                        </button>
                    </div>
                </div>
            </div>
        `;
        container.appendChild(row);
    },

    saveFieldProperties() {
        if (this.currentFieldIndex === null) return;

        const field = this.fields[this.currentFieldIndex];

        // Update basic field properties
        field.field_label = document.getElementById('propFieldLabel').value;
        field.field_name = document.getElementById('propFieldName').value;
        field.required = document.getElementById('propRequired').checked;
        field.help_text = document.getElementById('propHelpText').value;
        const showHelpCheckbox = document.getElementById('propShowHelpTextInDetail');
        field.show_help_text_in_detail = showHelpCheckbox ? showHelpCheckbox.checked : false;
        field.placeholder = document.getElementById('propPlaceholder').value;
        field.width = document.getElementById('propWidth').value;
        field.css_class = document.getElementById('propCssClass').value;

        const prefillSelect = document.getElementById('propPrefillSource');
        field.prefill_source_id = prefillSelect.value ? parseInt(prefillSelect.value) : null;

        const sharedListSelect = document.getElementById('propSharedOptionList');
        field.shared_option_list_id = sharedListSelect && sharedListSelect.value ? parseInt(sharedListSelect.value) : null;

        // Save approval step
        const approvalStepSelect = document.getElementById('propApprovalStep');
        field.approval_step = approvalStepSelect.value ? parseInt(approvalStepSelect.value) : null;

        const choicesEl = document.getElementById('propChoices');
        if (choicesEl) {
            field.choices = choicesEl.value;
        }

        const defaultValueEl = document.getElementById('propDefaultValue');
        if (defaultValueEl) {
            field.default_value = defaultValueEl.value;
        }

        // Save min/max values for rating, slider, etc.
        const minValEl = document.getElementById('propMinValue');
        if (minValEl) {
            if (!field.validation) field.validation = {};
            field.validation.min_value = minValEl.value ? parseFloat(minValEl.value) : null;
        }
        const maxValEl = document.getElementById('propMaxValue');
        if (maxValEl) {
            if (!field.validation) field.validation = {};
            field.validation.max_value = maxValEl.value ? parseFloat(maxValEl.value) : null;
        }

        // For matrix, try to parse choices as JSON
        if (field.field_type === 'matrix' && choicesEl) {
            try {
                field.choices = JSON.parse(choicesEl.value);
            } catch (e) {
                // Keep as string if not valid JSON
            }
        }

        // Save conditional logic
        const enableConditional = document.getElementById('propEnableConditional');
        if (enableConditional && enableConditional.checked) {
            const conditions = [];
            document.querySelectorAll('.condition-field').forEach((el, index) => {
                const fieldName = el.value;
                const operator = document.querySelector(`.condition-operator[data-index="${index}"]`).value;
                const value = document.querySelector(`.condition-value[data-index="${index}"]`).value;

                if (fieldName && operator) {
                    conditions.push({ field: fieldName, operator, value });
                }
            });

            if (conditions.length > 0) {
                field.conditional_rules = {
                    operator: document.getElementById('propConditionalOperator').value,
                    action: document.getElementById('propConditionalAction').value,
                    conditions: conditions
                };
            } else {
                field.conditional_rules = null;
            }

            // Also check if JSON was edited directly
            const jsonEl = document.getElementById('propConditionalRulesJson');
            if (jsonEl && jsonEl.value.trim()) {
                try {
                    field.conditional_rules = JSON.parse(jsonEl.value);
                } catch (e) {
                    console.warn('Invalid conditional rules JSON, using UI values');
                }
            }
        } else {
            field.conditional_rules = null;
        }

        // Save validation rules
        const validationRules = [];
        document.querySelectorAll('.validation-type').forEach((el, index) => {
            const type = el.value;
            const value = document.querySelector(`.validation-value[data-index="${index}"]`)?.value;
            const message = document.querySelector(`.validation-message[data-index="${index}"]`)?.value;

            if (type) {
                const rule = { type };
                if (value) rule.value = value;
                if (message) rule.message = message;
                validationRules.push(rule);
            }
        });
        field.validation_rules = validationRules.length > 0 ? validationRules : null;

        // Also check if JSON was edited directly
        const validationJsonEl = document.getElementById('propValidationRulesJson');
        if (validationJsonEl && validationJsonEl.value.trim()) {
            try {
                field.validation_rules = JSON.parse(validationJsonEl.value);
            } catch (e) {
                console.warn('Invalid validation rules JSON, using UI values');
            }
        }

        // Save field dependencies
        const dependencies = [];
        document.querySelectorAll('.dependency-source').forEach((el, index) => {
            const sourceField = el.value;
            const endpoint = document.querySelector(`.dependency-endpoint[data-index="${index}"]`)?.value;

            if (sourceField && endpoint) {
                dependencies.push({
                    sourceField: sourceField,
                    targetField: field.field_name,
                    apiEndpoint: endpoint
                });
            }
        });
        field.field_dependencies = dependencies.length > 0 ? dependencies : null;

        // Also check if JSON was edited directly
        const dependenciesJsonEl = document.getElementById('propDependenciesJson');
        if (dependenciesJsonEl && dependenciesJsonEl.value.trim()) {
            try {
                field.field_dependencies = JSON.parse(dependenciesJsonEl.value);
            } catch (e) {
                console.warn('Invalid dependencies JSON, using UI values');
            }
        }

        // Mark field as saved (no longer new)
        this.isNewField = false;

        // Close modal
        bootstrap.Modal.getInstance(document.getElementById('fieldPropertyModal')).hide();

        // Re-render
        this.renderCanvas();
        this.updatePreview();
    },
};
