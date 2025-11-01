/**
 * Visual Form Builder
 * 
 * Provides drag-and-drop interface for creating and editing forms
 * without code.
 */

class FormBuilder {
    constructor(config) {
        this.config = config;
        this.fields = [];
        this.currentFieldIndex = null;
        this.fieldIdCounter = 1;
        this.previewTimeout = null;
        this.draggingFieldType = null; // Track field type being dragged from palette
        this.dragPlaceholder = null; // Track the placeholder element
        this.isNewField = false; // Track if editing a newly created field
        this.formSteps = []; // Track multi-step configuration
        this.contextMenu = null; // Track context menu element

        this.init();
    }
    
    init() {
        this.setupFieldPalette();
        this.setupCanvas();
        this.setupEventListeners();

        // Load existing form if editing
        if (!this.config.isNew && this.config.formId && this.config.apiUrls.load) {
            this.loadForm();
        } else if (this.config.isNew) {
            // Show template selection modal for new forms
            this.showTemplateSelection();
        } else {
            // Generate initial preview for forms without fields
            this.updatePreview();
        }
    }
    
    setupFieldPalette() {
        const palette = document.getElementById('fieldPalette');

        this.fieldTypes = [
            { type: 'text', label: 'Text Input', icon: 'bi-input-cursor-text' },
            { type: 'email', label: 'Email', icon: 'bi-envelope' },
            { type: 'number', label: 'Number', icon: 'bi-123' },
            { type: 'textarea', label: 'Textarea', icon: 'bi-textarea-t' },
            { type: 'select', label: 'Select Dropdown', icon: 'bi-menu-button-wide' },
            { type: 'radio', label: 'Radio Buttons', icon: 'bi-ui-radios' },
            { type: 'checkbox_multiple', label: 'Checkboxes', icon: 'bi-ui-checks' },
            { type: 'checkbox', label: 'Single Checkbox', icon: 'bi-check-square' },
            { type: 'date', label: 'Date', icon: 'bi-calendar-date' },
            { type: 'time', label: 'Time', icon: 'bi-clock' },
            { type: 'datetime', label: 'Date & Time', icon: 'bi-calendar-event' },
            { type: 'file', label: 'File Upload', icon: 'bi-file-earmark-arrow-up' },
            { type: 'url', label: 'URL', icon: 'bi-link-45deg' },
            { type: 'phone', label: 'Phone Number', icon: 'bi-telephone' },
            { type: 'decimal', label: 'Decimal/Currency', icon: 'bi-currency-dollar' },
            { type: 'section', label: 'Section Header', icon: 'bi-layout-text-sidebar' },
        ];

        this.fieldTypes.forEach(fieldType => {
            const item = document.createElement('div');
            item.className = 'field-palette-item';
            item.dataset.fieldType = fieldType.type;
            item.innerHTML = `
                <i class="bi ${fieldType.icon}"></i>
                <span>${fieldType.label}</span>
            `;

            palette.appendChild(item);
        });

        // Setup SortableJS for palette to work with both single-step and multi-step canvases
        new Sortable(palette, {
            group: {
                name: 'step-fields',
                pull: 'clone',
                put: false
            },
            sort: false,
            animation: 150,
            // Keep native drag events for single-step canvas
            forceFallback: false,
            onStart: (evt) => {
                // Store the field type for native drag-drop handlers
                const fieldType = evt.item.dataset.fieldType;
                if (fieldType) {
                    this.draggingFieldType = fieldType;
                }
            },
            onEnd: (evt) => {
                // Clear the dragging field type
                this.draggingFieldType = null;
                this.cleanupDragPlaceholder();
            }
        });
    }
    
    setupCanvas() {
        const canvas = document.getElementById('formCanvas');

        // Setup Sortable for drag-and-drop reordering
        this.sortable = Sortable.create(canvas, {
            group: {
                name: 'step-fields',
                pull: true,
                put: true
            },
            animation: 300,
            easing: 'cubic-bezier(0.4, 0, 0.2, 1)',
            ghostClass: 'sortable-ghost',
            dragClass: 'sortable-drag',
            handle: '.field-drag-handle',
            draggable: '.canvas-field', // Only canvas-field elements are draggable/sortable
            filter: '.canvas-drop-zone', // Exclude drop zone from sorting
            onStart: (evt) => {
                // Add dragging class for enhanced visual feedback
                canvas.classList.add('dragging');
            },
            onAdd: (evt) => {
                // Check if this is a new field from palette
                const isPaletteItem = evt.item.classList.contains('field-palette-item');

                if (isPaletteItem) {
                    // New field from palette
                    const fieldType = evt.item.dataset.fieldType;
                    if (fieldType) {
                        this.addFieldAtPosition(fieldType, evt.newIndex);
                        evt.item.remove(); // Remove the palette clone
                    }
                } else {
                    // Existing field moved - update order
                    const movedField = this.fields.splice(evt.oldIndex, 1)[0];
                    this.fields.splice(evt.newIndex, 0, movedField);
                    this.updateFieldOrders();
                    this.updatePreview();
                }
            },
            onUpdate: (evt) => {
                // Field reordered within canvas
                const movedField = this.fields.splice(evt.oldIndex, 1)[0];
                this.fields.splice(evt.newIndex, 0, movedField);
                this.updateFieldOrders();
                this.updatePreview();
            },
            onEnd: (evt) => {
                // Remove dragging class
                canvas.classList.remove('dragging');
            }
        });
        
        // Allow dropping from palette with visual feedback
        canvas.addEventListener('dragover', (e) => {
            e.preventDefault();

            // Check if we're dragging a new field from palette
            if (this.draggingFieldType) {
                e.dataTransfer.dropEffect = 'copy';

                // Add dragging class to canvas
                canvas.classList.add('dragging');

                // Find the element we're hovering over
                const afterElement = this.getDragAfterElement(canvas, e.clientY);

                // Create or update placeholder
                if (!this.dragPlaceholder) {
                    this.dragPlaceholder = document.createElement('div');
                    this.dragPlaceholder.className = 'canvas-field drag-placeholder';
                    this.dragPlaceholder.innerHTML = `
                        <div class="field-header">
                            <div class="field-label">
                                <i class="bi bi-plus-circle-fill me-2" style="color: #667eea;"></i>
                                New field will be inserted here
                            </div>
                        </div>
                    `;
                }

                // Insert placeholder at the correct position
                if (afterElement == null) {
                    // Append at the end (before drop zone)
                    const dropZone = canvas.querySelector('.canvas-drop-zone');
                    if (dropZone) {
                        canvas.insertBefore(this.dragPlaceholder, dropZone);
                    } else {
                        canvas.appendChild(this.dragPlaceholder);
                    }
                } else {
                    canvas.insertBefore(this.dragPlaceholder, afterElement);
                }
            } else {
                // Allow sortable to handle reordering
                e.dataTransfer.dropEffect = 'move';
            }
        });

        canvas.addEventListener('dragleave', (e) => {
            // Check if we're actually leaving the canvas (not just entering a child element)
            const rect = canvas.getBoundingClientRect();
            const x = e.clientX;
            const y = e.clientY;

            // If mouse is outside canvas bounds, remove placeholder
            if (this.draggingFieldType &&
                (x < rect.left || x > rect.right || y < rect.top || y > rect.bottom)) {
                this.cleanupDragPlaceholder();
            }
        });

        canvas.addEventListener('drop', (e) => {
            e.preventDefault();

            // Check if we're dropping a new field from palette
            if (this.draggingFieldType) {
                const fieldType = this.draggingFieldType;

                // Remove placeholder
                this.cleanupDragPlaceholder();

                // Calculate the position where to insert
                const afterElement = this.getDragAfterElement(canvas, e.clientY);
                let insertIndex = this.fields.length;

                if (afterElement) {
                    const afterIndex = parseInt(afterElement.dataset.index);
                    if (!isNaN(afterIndex)) {
                        insertIndex = afterIndex;
                    }
                }

                this.addFieldAtPosition(fieldType, insertIndex);
            }
        });
    }

    getDragAfterElement(container, y) {
        const draggableElements = [...container.querySelectorAll('.canvas-field:not(.drag-placeholder):not(.sortable-drag)')];

        return draggableElements.reduce((closest, child) => {
            const box = child.getBoundingClientRect();
            const offset = y - box.top - box.height / 2;

            if (offset < 0 && offset > closest.offset) {
                return { offset: offset, element: child };
            } else {
                return closest;
            }
        }, { offset: Number.NEGATIVE_INFINITY }).element;
    }

    cleanupDragPlaceholder() {
        // Remove the drag placeholder and clean up canvas state
        if (this.dragPlaceholder && this.dragPlaceholder.parentNode) {
            this.dragPlaceholder.parentNode.removeChild(this.dragPlaceholder);
            this.dragPlaceholder = null;
        }
        const canvas = document.getElementById('formCanvas');
        if (canvas) {
            canvas.classList.remove('dragging');
        }
    }

    addFieldAtPosition(fieldType, position) {
        const field = {
            id: `new_${this.fieldIdCounter++}`,
            order: position + 1,
            field_label: this.getDefaultLabel(fieldType),
            field_name: this.getDefaultName(fieldType),
            field_type: fieldType,
            required: false,
            help_text: '',
            placeholder: '',
            width: 'full',
            css_class: '',
            choices: '',
            default_value: '',
            prefill_source_id: null,
            prefill_source_config: {},
            validation: {
                min_value: null,
                max_value: null,
                min_length: null,
                max_length: null,
                regex_validation: '',
                regex_error_message: ''
            },
            conditional: {
                show_if_field: null,
                show_if_value: ''
            }
        };

        // Insert at the specified position
        this.fields.splice(position, 0, field);
        this.updateFieldOrders();
        this.renderCanvas();
        this.updatePreview();

        // Automatically open property editor for new field
        this.editField(position, true); // true = isNew
    }
    
    setupEventListeners() {
        // Save button
        document.getElementById('btnSave').addEventListener('click', () => {
            this.saveForm();
        });
        
        // Cancel button
        document.getElementById('btnCancel').addEventListener('click', () => {
            if (confirm('Are you sure you want to cancel? Unsaved changes will be lost.')) {
                window.location.href = '/admin/django_forms_workflows/formdefinition/';
            }
        });
        
        // Save field button in modal
        document.getElementById('btnSaveField').addEventListener('click', () => {
            this.saveFieldProperties();
        });
        
        // Auto-generate slug from name
        document.getElementById('formName').addEventListener('input', (e) => {
            const slug = e.target.value
                .toLowerCase()
                .replace(/[^a-z0-9]+/g, '-')
                .replace(/^-+|-+$/g, '');
            document.getElementById('formSlug').value = slug;
        });

        // Multi-step toggle
        const multiStepCheckbox = document.getElementById('formEnableMultiStep');

        if (multiStepCheckbox) {
            multiStepCheckbox.addEventListener('change', (e) => {
                this.toggleMultiStepMode(e.target.checked);
            });
        }

        // Add step tab button
        const addStepTabBtn = document.getElementById('btnAddStepTab');
        if (addStepTabBtn) {
            addStepTabBtn.addEventListener('click', () => {
                this.addStepTab();
            });
        }
    }
    
    addField(fieldType) {
        // Add field at the end
        this.addFieldAtPosition(fieldType, this.fields.length);
    }
    
    getDefaultLabel(fieldType) {
        const labels = {
            'text': 'Text Field',
            'email': 'Email Address',
            'number': 'Number',
            'textarea': 'Text Area',
            'select': 'Select Option',
            'radio': 'Radio Choice',
            'checkbox_multiple': 'Checkboxes',
            'checkbox': 'Checkbox',
            'date': 'Date',
            'time': 'Time',
            'datetime': 'Date and Time',
            'file': 'File Upload',
            'url': 'Website URL',
            'phone': 'Phone Number',
            'decimal': 'Amount',
            'section': 'Section Header'
        };
        return labels[fieldType] || 'Field';
    }
    
    getDefaultName(fieldType) {
        return fieldType + '_' + this.fieldIdCounter;
    }
    
    renderCanvas() {
        const canvas = document.getElementById('formCanvas');

        if (this.fields.length === 0) {
            canvas.innerHTML = `
                <div class="empty-canvas">
                    <i class="bi bi-inbox"></i>
                    <p>Drag fields from the left palette to start building your form</p>
                </div>
            `;
            document.getElementById('fieldCount').textContent = '0 fields';
            return;
        }

        canvas.innerHTML = '';
        this.fields.forEach((field, index) => {
            const fieldEl = this.createFieldElement(field, index);
            canvas.appendChild(fieldEl);
        });

        // Add a drop zone at the bottom for easier dragging
        const dropZone = document.createElement('div');
        dropZone.className = 'canvas-drop-zone';
        dropZone.innerHTML = `
            <div class="drop-zone-content">
                <i class="bi bi-arrow-down-circle"></i>
                <span>Drag fields from the left palette to add them here</span>
            </div>
        `;
        canvas.appendChild(dropZone);

        document.getElementById('fieldCount').textContent = `${this.fields.length} field${this.fields.length !== 1 ? 's' : ''}`;
    }
    
    createFieldElement(field, index) {
        const div = document.createElement('div');
        div.className = 'canvas-field field-item';
        div.dataset.index = index;
        div.dataset.fieldIndex = index;

        const requiredBadge = field.required ? '<span class="badge bg-danger ms-1" style="font-size: 0.65rem; padding: 0.15rem 0.35rem;">REQ</span>' : '';
        const fieldInfo = `<span class="text-muted" style="font-size: 0.75rem;">${field.field_name}</span>`;

        div.innerHTML = `
            <div class="field-header field-drag-handle" style="cursor: move;">
                <div>
                    <i class="bi bi-grip-vertical me-2 text-muted"></i>
                    <span class="field-label">${this.escapeHtml(field.field_label)}</span>
                    ${requiredBadge}
                    <span class="ms-2">${fieldInfo}</span>
                </div>
                <div class="field-actions">
                    <span class="field-type-badge">${field.field_type}</span>
                    <button class="btn btn-sm btn-outline-primary btn-field-action" onclick="formBuilder.editField(${index})" title="Edit field">
                        <i class="bi bi-pencil"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-danger btn-field-action" onclick="formBuilder.deleteField(${index})" title="Delete field">
                        <i class="bi bi-trash"></i>
                    </button>
                </div>
            </div>
        `;

        // Add context menu handler for multi-step mode
        div.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            this.showFieldContextMenu(e, index);
        });

        return div;
    }
    
    editField(index, isNew = false) {
        this.currentFieldIndex = index;
        this.isNewField = isNew;
        const field = this.fields[index];

        // Build property form
        const form = this.buildPropertyForm(field);
        document.getElementById('fieldPropertyForm').innerHTML = form;

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
    }
    
    buildPropertyForm(field) {
        const prefillOptions = this.config.prefillSources.map(source =>
            `<option value="${source.id}" ${field.prefill_source_id === source.id ? 'selected' : ''}>
                ${this.escapeHtml(source.name)}
            </option>`
        ).join('');

        const widthOptions = ['full', 'half', 'third'].map(w =>
            `<option value="${w}" ${field.width === w ? 'selected' : ''}>${w.charAt(0).toUpperCase() + w.slice(1)}</option>`
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
    }

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
                    <input type="text" class="form-control" value="${field.field_type}" disabled>
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
                </div>
                <div class="col-12">
                    <label class="form-label">Placeholder</label>
                    <input type="text" class="form-control" id="propPlaceholder" value="${this.escapeHtml(field.placeholder)}">
                </div>
                ${field.field_type === 'select' || field.field_type === 'radio' || field.field_type === 'checkbox_multiple' ? `
                <div class="col-12">
                    <label class="form-label">Choices (one per line)</label>
                    <textarea class="form-control" id="propChoices" rows="4">${this.escapeHtml(field.choices)}</textarea>
                </div>
                ` : ''}
                <div class="col-12">
                    <label class="form-label">Prefill Source</label>
                    <select class="form-select" id="propPrefillSource">
                        <option value="">None</option>
                        ${prefillOptions}
                    </select>
                </div>
                <div class="col-12">
                    <label class="form-label">CSS Class</label>
                    <input type="text" class="form-control" id="propCssClass" value="${this.escapeHtml(field.css_class)}">
                </div>
            </div>
        `;
    }

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

            <script>
                // Toggle conditional rules container
                document.getElementById('propEnableConditional').addEventListener('change', function(e) {
                    document.getElementById('conditionalRulesContainer').style.display = e.target.checked ? 'block' : 'none';
                });

                // Initialize conditions list
                window.formBuilder.initializeConditionsList(${JSON.stringify(field.conditional_rules?.conditions || [])});
            </script>
        `;
    }

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

            <script>
                // Initialize validation rules list
                window.formBuilder.initializeValidationRulesList(${JSON.stringify(field.validation_rules || [])});
            </script>
        `;
    }

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

            <script>
                // Initialize dependencies list
                window.formBuilder.initializeDependenciesList(${JSON.stringify(field.field_dependencies || [])});
            </script>
        `;
    }

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
    }

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
                            <option value="is_not_empty" ${condition.operator === 'is_not_empty' ? 'selected' : ''}>Is Not Empty</option>
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
    }

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
    }

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
    }

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
    }

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
    }

    toggleMultiStepMode(enabled) {
        const singleCanvas = document.getElementById('singleStepCanvas');
        const multiCanvas = document.getElementById('multiStepCanvas');
        const stepTabsControls = document.getElementById('stepTabsControls');

        if (enabled) {
            // Switch to multi-step mode
            singleCanvas.style.display = 'none';
            multiCanvas.style.display = 'block';
            if (stepTabsControls) stepTabsControls.style.display = 'block';

            // Initialize steps if not present
            if (!this.formSteps || this.formSteps.length === 0) {
                this.formSteps = [
                    { title: 'Step 1', fields: [] }
                ];
            }

            // Render step tabs
            this.renderStepTabs();

            // Move all fields to first step if they're not assigned
            this.organizeFieldsIntoSteps();
        } else {
            // Switch to single-step mode
            singleCanvas.style.display = 'block';
            multiCanvas.style.display = 'none';
            if (stepTabsControls) stepTabsControls.style.display = 'none';

            // Move all fields back to main canvas
            this.moveAllFieldsToMainCanvas();
        }
    }

    renderStepTabs() {
        const contentContainer = document.getElementById('stepTabContent');

        if (!contentContainer) return;

        contentContainer.innerHTML = '';

        this.formSteps.forEach((step, index) => {
            // Create step card (no tabs, just stacked vertically)
            const stepCard = document.createElement('div');
            stepCard.className = 'step-card mb-3';
            stepCard.innerHTML = `
                <div class="step-card-header">
                    <div class="d-flex justify-content-between align-items-center">
                        <div class="d-flex align-items-center gap-2 flex-grow-1">
                            <span class="step-number">${index + 1}</span>
                            <input type="text" class="form-control step-title-input"
                                   value="${this.escapeHtml(step.title)}"
                                   placeholder="Step Title"
                                   onchange="formBuilder.updateStepTitle(${index}, this.value)">
                        </div>
                        <div class="d-flex align-items-center gap-2">
                            <span class="badge bg-info">${step.fields ? step.fields.length : 0} fields</span>
                            <button type="button" class="btn btn-sm btn-outline-danger"
                                    onclick="formBuilder.removeStepTab(${index})"
                                    ${this.formSteps.length === 1 ? 'disabled' : ''}
                                    title="Remove step">
                                <i class="bi bi-trash"></i>
                            </button>
                        </div>
                    </div>
                </div>
                <div class="step-canvas" id="step-canvas-${index}" data-step-index="${index}">
                    <div class="empty-canvas">
                        <i class="bi bi-inbox"></i>
                        <p>Drag fields here for ${this.escapeHtml(step.title)}</p>
                    </div>
                </div>
            `;
            contentContainer.appendChild(stepCard);

            // Setup sortable for this step canvas
            this.setupStepCanvasSortable(index);

            // Setup drag-and-drop from palette
            this.setupStepCanvasDragDrop(index);
        });

        // Render fields in their respective steps
        this.renderFieldsInSteps();
    }

    setupStepCanvasSortable(stepIndex) {
        const canvas = document.getElementById(`step-canvas-${stepIndex}`);
        if (!canvas) return;

        new Sortable(canvas, {
            group: {
                name: 'step-fields',
                pull: true,
                put: true
            },
            animation: 150,
            handle: '.field-drag-handle',
            draggable: '.field-item', // Only field-item elements can be dragged
            filter: '.empty-canvas', // Exclude empty canvas placeholder
            ghostClass: 'field-ghost',
            dragClass: 'field-dragging',
            chosenClass: 'field-chosen',
            onAdd: (evt) => {
                // Check if this is a new field from palette or moved from another step
                const isPaletteItem = evt.item.classList.contains('field-palette-item');

                if (isPaletteItem) {
                    // New field from palette
                    const fieldType = evt.item.dataset.fieldType;
                    if (fieldType) {
                        this.handleFieldDroppedToStep(fieldType, stepIndex, evt.newIndex);
                        evt.item.remove(); // Remove the palette clone
                    }
                } else {
                    // Existing field moved from another canvas
                    this.handleFieldMovedToStep(evt.item, stepIndex);
                }
            },
            onUpdate: (evt) => {
                this.updateFieldOrderInStep(stepIndex);
            },
            onRemove: (evt) => {
                // Field was moved to another step, handled by onAdd of target
            }
        });
    }

    setupStepCanvasDragDrop(stepIndex) {
        const canvas = document.getElementById(`step-canvas-${stepIndex}`);
        if (!canvas) return;

        // Allow dropping from palette
        canvas.addEventListener('dragover', (e) => {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'copy';
            canvas.classList.add('drag-over');
        });

        canvas.addEventListener('dragleave', (e) => {
            if (e.target === canvas) {
                canvas.classList.remove('drag-over');
            }
        });

        canvas.addEventListener('drop', (e) => {
            e.preventDefault();
            canvas.classList.remove('drag-over');

            const fieldType = e.dataTransfer.getData('fieldType');
            if (fieldType) {
                // Field dropped from palette
                this.handleFieldDroppedToStep(fieldType, stepIndex);
            }
        });
    }

    handleFieldDroppedToStep(fieldType, stepIndex, position) {
        // Create a new field when dropped from palette
        const fieldConfig = this.fieldTypes.find(ft => ft.type === fieldType);
        if (!fieldConfig) return;

        const fieldName = this.getDefaultName(fieldType);
        const newField = {
            id: `new_${this.fieldIdCounter++}`,
            field_type: fieldType,
            field_name: fieldName,
            field_label: this.getDefaultLabel(fieldType),
            required: false,
            help_text: '',
            placeholder: '',
            choices: '',
            width: 'full',
            css_class: '',
            prefill_source_id: null,
            order: this.fields.length,
            conditional_rules: null,
            validation_rules: null,
            field_dependencies: null,
            default_value: '',
            prefill_source_config: {},
            validation: {
                min_value: null,
                max_value: null,
                min_length: null,
                max_length: null,
                regex_validation: '',
                regex_error_message: ''
            },
            conditional: {
                show_if_field: null,
                show_if_value: ''
            }
        };

        this.fields.push(newField);

        // Add to step's field list
        if (!this.formSteps[stepIndex].fields) {
            this.formSteps[stepIndex].fields = [];
        }

        // Insert at the correct position
        if (position !== undefined && position < this.formSteps[stepIndex].fields.length) {
            this.formSteps[stepIndex].fields.splice(position, 0, fieldName);
        } else {
            this.formSteps[stepIndex].fields.push(fieldName);
        }

        // Re-render this step
        this.renderSingleStep(stepIndex);
        this.updatePreview();

        // Automatically open property editor for new field
        const fieldIndex = this.fields.length - 1;
        this.editField(fieldIndex, true); // true = isNew
    }

    addStepTab() {
        const newIndex = this.formSteps.length;
        this.formSteps.push({
            title: `Step ${newIndex + 1}`,
            fields: []
        });
        this.renderStepTabs();
    }

    removeStepTab(index) {
        if (this.formSteps.length === 1) {
            alert('Cannot remove the last step. Disable multi-step mode instead.');
            return;
        }

        if (confirm(`Remove "${this.formSteps[index].title}"? Fields in this step will be moved to Step 1.`)) {
            // Move fields from this step to step 0
            const fieldsToMove = this.formSteps[index].fields || [];
            this.formSteps[0].fields = [...(this.formSteps[0].fields || []), ...fieldsToMove];

            // Remove the step
            this.formSteps.splice(index, 1);

            // Re-render
            this.renderStepTabs();
        }
    }

    updateStepTitle(index, newTitle) {
        if (this.formSteps[index]) {
            this.formSteps[index].title = newTitle;
            // Update tab text
            const tab = document.querySelector(`#step-tab-${index}`);
            if (tab) {
                const icon = tab.querySelector('i').outerHTML;
                const deleteBtn = tab.querySelector('button').outerHTML;
                tab.innerHTML = `${icon} ${this.escapeHtml(newTitle)} ${deleteBtn}`;
            }
        }
    }

    handleFieldMovedToStep(fieldElement, stepIndex) {
        const fieldIndex = parseInt(fieldElement.dataset.fieldIndex);
        const field = this.fields[fieldIndex];

        if (!field) return;

        // Find which step the field was in before
        let sourceStepIndex = -1;
        this.formSteps.forEach((step, idx) => {
            if (step.fields && step.fields.includes(field.field_name)) {
                sourceStepIndex = idx;
            }
        });

        // Remove field from all steps
        this.formSteps.forEach(step => {
            if (step.fields) {
                step.fields = step.fields.filter(name => name !== field.field_name);
            }
        });

        // Add to target step at the correct position
        if (!this.formSteps[stepIndex].fields) {
            this.formSteps[stepIndex].fields = [];
        }

        // Get the position from the DOM
        const canvas = document.getElementById(`step-canvas-${stepIndex}`);
        const fieldElements = canvas.querySelectorAll('.field-item');
        let insertPosition = this.formSteps[stepIndex].fields.length;

        fieldElements.forEach((el, idx) => {
            if (el === fieldElement) {
                insertPosition = idx;
            }
        });

        this.formSteps[stepIndex].fields.splice(insertPosition, 0, field.field_name);

        // Re-render both source and target steps
        if (sourceStepIndex !== -1 && sourceStepIndex !== stepIndex) {
            this.renderSingleStep(sourceStepIndex);
        }
        this.renderSingleStep(stepIndex);

        // Update preview
        this.updatePreview();
    }

    updateFieldOrderInStep(stepIndex) {
        const canvas = document.getElementById(`step-canvas-${stepIndex}`);
        if (!canvas) return;

        const fieldElements = canvas.querySelectorAll('.field-item');
        const fieldNames = [];

        fieldElements.forEach(el => {
            const fieldIndex = parseInt(el.dataset.fieldIndex);
            const field = this.fields[fieldIndex];
            if (field) {
                fieldNames.push(field.field_name);
            }
        });

        this.formSteps[stepIndex].fields = fieldNames;
    }

    updateStepFieldCount(stepIndex) {
        const panel = document.getElementById(`step-panel-${stepIndex}`);
        if (panel) {
            const badge = panel.querySelector('.badge');
            if (badge) {
                const count = this.formSteps[stepIndex].fields ? this.formSteps[stepIndex].fields.length : 0;
                badge.textContent = `${count} fields`;
            }
        }
    }

    organizeFieldsIntoSteps() {
        // Assign all fields to their respective steps based on formSteps configuration
        // If a field isn't assigned to any step, put it in step 0
        const assignedFields = new Set();

        this.formSteps.forEach(step => {
            if (step.fields) {
                step.fields.forEach(fieldName => assignedFields.add(fieldName));
            }
        });

        // Add unassigned fields to first step
        this.fields.forEach(field => {
            if (!assignedFields.has(field.field_name)) {
                if (!this.formSteps[0].fields) {
                    this.formSteps[0].fields = [];
                }
                this.formSteps[0].fields.push(field.field_name);
            }
        });

        this.renderFieldsInSteps();
    }

    renderFieldsInSteps() {
        // Render fields in their respective steps
        this.formSteps.forEach((step, stepIndex) => {
            this.renderSingleStep(stepIndex);
        });
    }

    renderSingleStep(stepIndex) {
        const step = this.formSteps[stepIndex];
        const canvas = document.getElementById(`step-canvas-${stepIndex}`);
        if (!canvas) return;

        canvas.innerHTML = '';

        if (!step.fields || step.fields.length === 0) {
            canvas.innerHTML = `
                <div class="empty-canvas">
                    <i class="bi bi-inbox"></i>
                    <p>Drag fields here for ${this.escapeHtml(step.title)}</p>
                </div>
            `;
            this.updateStepFieldCount(stepIndex);
            return;
        }

        step.fields.forEach(fieldName => {
            const fieldIndex = this.fields.findIndex(f => f.field_name === fieldName);
            if (fieldIndex !== -1) {
                const fieldElement = this.createFieldElement(this.fields[fieldIndex], fieldIndex);
                canvas.appendChild(fieldElement);
            }
        });

        this.updateStepFieldCount(stepIndex);
    }

    moveAllFieldsToMainCanvas() {
        // Collect all fields from all steps
        const allFields = [];
        this.formSteps.forEach(step => {
            if (step.fields) {
                allFields.push(...step.fields);
            }
        });

        // Re-render main canvas
        this.renderCanvas();
    }

    updateFieldOrderFromSteps() {
        // Update field order based on step order
        // Fields should be ordered by step, then by position within step
        const orderedFields = [];

        this.formSteps.forEach(step => {
            if (step.fields) {
                step.fields.forEach(fieldName => {
                    const field = this.fields.find(f => f.field_name === fieldName);
                    if (field) {
                        orderedFields.push(field);
                    }
                });
            }
        });

        // Update this.fields with new order
        this.fields = orderedFields;

        // Update order property
        this.fields.forEach((field, index) => {
            field.order = index;
        });
    }



    saveFieldProperties() {
        if (this.currentFieldIndex === null) return;

        const field = this.fields[this.currentFieldIndex];

        // Update basic field properties
        field.field_label = document.getElementById('propFieldLabel').value;
        field.field_name = document.getElementById('propFieldName').value;
        field.required = document.getElementById('propRequired').checked;
        field.help_text = document.getElementById('propHelpText').value;
        field.placeholder = document.getElementById('propPlaceholder').value;
        field.width = document.getElementById('propWidth').value;
        field.css_class = document.getElementById('propCssClass').value;

        const prefillSelect = document.getElementById('propPrefillSource');
        field.prefill_source_id = prefillSelect.value ? parseInt(prefillSelect.value) : null;

        const choicesEl = document.getElementById('propChoices');
        if (choicesEl) {
            field.choices = choicesEl.value;
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
    }

    deleteField(index) {
        if (confirm('Are you sure you want to delete this field?')) {
            this.deleteFieldSilently(index);
        }
    }

    deleteFieldSilently(index) {
        // Delete field without confirmation (used when canceling new field)
        const fieldToDelete = this.fields[index];

        // Remove from fields array
        this.fields.splice(index, 1);

        // Remove from step fields if in multi-step mode
        if (this.formSteps && this.formSteps.length > 0) {
            this.formSteps.forEach(step => {
                if (step.fields) {
                    const fieldIndex = step.fields.indexOf(fieldToDelete.field_name);
                    if (fieldIndex !== -1) {
                        step.fields.splice(fieldIndex, 1);
                    }
                }
            });
        }

        this.updateFieldOrders();

        // Re-render appropriate canvas
        const isMultiStep = document.getElementById('formEnableMultiStep')?.checked;
        if (isMultiStep) {
            this.renderStepTabs();
        } else {
            this.renderCanvas();
        }

        this.updatePreview();
    }
    
    updateFieldOrders() {
        this.fields.forEach((field, index) => {
            field.order = index + 1;
        });
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    updatePreview() {
        // Debounce preview updates to avoid too many API calls
        if (this.previewTimeout) {
            clearTimeout(this.previewTimeout);
        }

        this.previewTimeout = setTimeout(() => {
            this.generatePreview();
        }, 500); // Wait 500ms after last change
    }

    async generatePreview() {
        const preview = document.getElementById('formPreview');

        // Show loading state
        preview.innerHTML = `
            <div class="text-center text-muted py-4">
                <div class="spinner-border spinner-border-sm" role="status">
                    <span class="visually-hidden">Loading...</span>
                </div>
                <p class="small mt-2">Generating preview...</p>
            </div>
        `;

        try {
            // Gather form data
            const formData = {
                name: document.getElementById('formName').value || 'Untitled Form',
                slug: document.getElementById('formSlug').value || 'untitled-form',
                description: document.getElementById('formDescription').value || '',
                instructions: document.getElementById('formInstructions').value || '',
                is_active: document.getElementById('formIsActive').checked,
                requires_login: document.getElementById('formRequiresLogin').checked,
                allow_save_draft: document.getElementById('formAllowDraft').checked,
                allow_withdrawal: document.getElementById('formAllowWithdrawal').checked,
                fields: this.fields
            };

            // Call preview API
            const response = await fetch(this.config.apiUrls.preview, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.config.csrfToken
                },
                body: JSON.stringify(formData)
            });

            if (!response.ok) {
                const errorText = await response.text();
                console.error('Preview API error:', response.status, errorText);
                throw new Error(`Server error: ${response.status}`);
            }

            const data = await response.json();

            if (data.success) {
                preview.innerHTML = data.html;
            } else {
                console.error('Preview generation failed:', data.error);
                throw new Error(data.error || 'Unknown error');
            }

        } catch (error) {
            console.error('Preview error:', error);

            // If there are no fields, show a helpful message
            if (this.fields.length === 0) {
                preview.innerHTML = `
                    <div class="alert alert-info small">
                        <i class="bi bi-info-circle"></i>
                        <strong>No fields yet</strong><br>
                        Drag fields from the palette to get started
                    </div>
                `;
            } else {
                preview.innerHTML = `
                    <div class="alert alert-warning small">
                        <i class="bi bi-exclamation-triangle"></i>
                        <strong>Preview unavailable</strong><br>
                        ${this.fields.length} field(s) configured<br>
                        <small class="text-muted">${error.message}</small>
                    </div>
                `;
            }
        }
    }
    
    async loadForm() {
        try {
            const response = await fetch(this.config.apiUrls.load, {
                method: 'GET',
                headers: {
                    'X-CSRFToken': this.config.csrfToken
                }
            });

            if (!response.ok) {
                throw new Error('Failed to load form');
            }

            const data = await response.json();

            // Populate form settings
            document.getElementById('formName').value = data.name || '';
            document.getElementById('formSlug').value = data.slug || '';
            document.getElementById('formDescription').value = data.description || '';
            document.getElementById('formInstructions').value = data.instructions || '';
            document.getElementById('formIsActive').checked = data.is_active;
            document.getElementById('formRequiresLogin').checked = data.requires_login;
            document.getElementById('formAllowDraft').checked = data.allow_save_draft;
            document.getElementById('formAllowWithdrawal').checked = data.allow_withdrawal;

            // Load client-side enhancement settings
            document.getElementById('formEnableAutoSave').checked = data.enable_auto_save !== false;
            document.getElementById('formAutoSaveInterval').value = data.auto_save_interval || 30;
            document.getElementById('formEnableMultiStep').checked = data.enable_multi_step || false;
            this.formSteps = data.form_steps || [];

            // Load fields
            this.fields = data.fields || [];

            // If multi-step is enabled, switch to multi-step mode
            if (data.enable_multi_step) {
                this.toggleMultiStepMode(true);
            } else {
                this.renderCanvas();
            }

            this.updatePreview();

            document.getElementById('saveStatus').textContent = 'Loaded successfully';
        } catch (error) {
            console.error('Error loading form:', error);
            alert('Failed to load form: ' + error.message);
        }
    }

    async saveForm() {
        // Validate form settings
        const formName = document.getElementById('formName').value.trim();
        const formSlug = document.getElementById('formSlug').value.trim();

        if (!formName) {
            alert('Please enter a form name');
            return;
        }

        if (!formSlug) {
            alert('Please enter a form slug');
            return;
        }

        // If in multi-step mode, update field order from step canvases
        const isMultiStep = document.getElementById('formEnableMultiStep').checked;
        if (isMultiStep) {
            this.updateFieldOrderFromSteps();
        }

        // Build form data
        const formData = {
            id: this.config.formId,
            name: formName,
            slug: formSlug,
            description: document.getElementById('formDescription').value.trim(),
            instructions: document.getElementById('formInstructions').value.trim(),
            is_active: document.getElementById('formIsActive').checked,
            requires_login: document.getElementById('formRequiresLogin').checked,
            allow_save_draft: document.getElementById('formAllowDraft').checked,
            allow_withdrawal: document.getElementById('formAllowWithdrawal').checked,
            enable_auto_save: document.getElementById('formEnableAutoSave').checked,
            auto_save_interval: parseInt(document.getElementById('formAutoSaveInterval').value) || 30,
            enable_multi_step: isMultiStep,
            form_steps: this.formSteps || [],
            fields: this.fields
        };

        // Show saving status
        const saveBtn = document.getElementById('btnSave');
        const originalText = saveBtn.innerHTML;
        saveBtn.disabled = true;
        saveBtn.innerHTML = '<i class="bi bi-hourglass-split"></i> Saving...';
        document.getElementById('saveStatus').textContent = 'Saving...';

        try {
            const response = await fetch(this.config.apiUrls.save, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.config.csrfToken
                },
                body: JSON.stringify(formData)
            });

            const result = await response.json();

            if (!response.ok || !result.success) {
                throw new Error(result.error || 'Failed to save form');
            }

            // Update field IDs with the mapping from backend
            if (result.field_id_mapping) {
                this.fields.forEach(field => {
                    const oldId = String(field.id);
                    if (result.field_id_mapping[oldId]) {
                        field.id = result.field_id_mapping[oldId];
                    }
                });

                // Re-render to update the UI with new IDs
                const isMultiStep = document.getElementById('formEnableMultiStep')?.checked;
                if (isMultiStep) {
                    this.renderStepTabs();
                } else {
                    this.renderCanvas();
                }
            }

            document.getElementById('saveStatus').textContent = 'Saved successfully';

            // If this was a new form, redirect to edit mode
            if (this.config.isNew && result.form_id) {
                setTimeout(() => {
                    window.location.href = `/admin/django_forms_workflows/formdefinition/${result.form_id}/builder/`;
                }, 1000);
            } else {
                // Show success message
                setTimeout(() => {
                    document.getElementById('saveStatus').textContent = 'All changes saved';
                }, 2000);
            }
        } catch (error) {
            console.error('Error saving form:', error);
            alert('Failed to save form: ' + error.message);
            document.getElementById('saveStatus').textContent = 'Error saving';
        } finally {
            saveBtn.disabled = false;
            saveBtn.innerHTML = originalText;
        }
    }

    async showTemplateSelection() {
        const modal = new bootstrap.Modal(document.getElementById('templateSelectionModal'));
        const templateList = document.getElementById('templateList');

        // Load templates
        try {
            const response = await fetch(this.config.apiUrls.templates);
            const data = await response.json();

            if (data.success && data.templates.length > 0) {
                // Group templates by category
                const grouped = {};
                data.templates.forEach(template => {
                    if (!grouped[template.category_display]) {
                        grouped[template.category_display] = [];
                    }
                    grouped[template.category_display].push(template);
                });

                // Render templates
                let html = '';
                for (const [category, templates] of Object.entries(grouped)) {
                    html += `<div class="col-12"><h6 class="text-muted">${category}</h6></div>`;
                    templates.forEach(template => {
                        html += `
                            <div class="col-md-4">
                                <div class="card template-card h-100" style="cursor: pointer;" data-template-id="${template.id}">
                                    <div class="card-body">
                                        <h6 class="card-title">${this.escapeHtml(template.name)}</h6>
                                        <p class="card-text small text-muted">${this.escapeHtml(template.description)}</p>
                                        <div class="d-flex justify-content-between align-items-center">
                                            <small class="text-muted">
                                                <i class="bi bi-people"></i> Used ${template.usage_count} times
                                            </small>
                                            <button class="btn btn-sm btn-primary">Use Template</button>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        `;
                    });
                }
                templateList.innerHTML = html;

                // Add click handlers
                document.querySelectorAll('.template-card').forEach(card => {
                    card.addEventListener('click', () => {
                        const templateId = card.dataset.templateId;
                        this.loadTemplate(templateId);
                        modal.hide();
                    });
                });
            } else {
                templateList.innerHTML = `
                    <div class="col-12 text-center py-5">
                        <p class="text-muted">No templates available</p>
                    </div>
                `;
            }
        } catch (error) {
            console.error('Error loading templates:', error);
            templateList.innerHTML = `
                <div class="col-12 text-center py-5">
                    <p class="text-danger">Failed to load templates</p>
                </div>
            `;
        }

        // Handle "Start with Blank Form" button
        document.getElementById('btnStartBlank').onclick = () => {
            modal.hide();
        };

        modal.show();
    }

    async loadTemplate(templateId) {
        try {
            const url = this.config.apiUrls.loadTemplate.replace('{id}', templateId);
            const response = await fetch(url);
            const data = await response.json();

            if (data.success && data.template_data) {
                const templateData = data.template_data;

                // Populate form settings
                document.getElementById('formName').value = templateData.name || '';
                document.getElementById('formSlug').value = templateData.slug || '';
                document.getElementById('formDescription').value = templateData.description || '';
                document.getElementById('formInstructions').value = templateData.instructions || '';
                document.getElementById('formIsActive').checked = templateData.is_active !== false;
                document.getElementById('formRequiresLogin').checked = templateData.requires_login !== false;
                document.getElementById('formAllowDraft').checked = templateData.allow_save_draft !== false;
                document.getElementById('formAllowWithdrawal').checked = templateData.allow_withdrawal !== false;

                // Load fields
                this.fields = templateData.fields || [];
                this.renderCanvas();
                this.updatePreview();

                // Show success message
                alert('Template loaded successfully! You can now customize the form.');
            } else {
                throw new Error('Invalid template data');
            }
        } catch (error) {
            console.error('Error loading template:', error);
            alert('Failed to load template: ' + error.message);
        }
    }

    showFieldContextMenu(event, fieldIndex) {
        // Only show context menu in multi-step mode
        const isMultiStep = document.getElementById('formEnableMultiStep')?.checked;
        if (!isMultiStep || !this.formSteps || this.formSteps.length <= 1) {
            return; // Don't show menu if not in multi-step mode or only one step
        }

        // Remove any existing context menu
        this.hideFieldContextMenu();

        // Create context menu
        const menu = document.createElement('div');
        menu.className = 'field-context-menu';
        menu.style.position = 'fixed';
        menu.style.left = `${event.clientX}px`;
        menu.style.top = `${event.clientY}px`;
        menu.style.zIndex = '10000';

        // Build menu items
        let menuHTML = '<div class="context-menu-header">Move to Step:</div>';

        this.formSteps.forEach((step, stepIndex) => {
            menuHTML += `
                <div class="context-menu-item" onclick="formBuilder.moveFieldToStepFromMenu(${fieldIndex}, ${stepIndex})">
                    <i class="bi bi-arrow-right-circle me-2"></i>
                    ${this.escapeHtml(step.title)}
                </div>
            `;
        });

        menu.innerHTML = menuHTML;
        document.body.appendChild(menu);
        this.contextMenu = menu;

        // Close menu when clicking outside
        setTimeout(() => {
            document.addEventListener('click', () => this.hideFieldContextMenu(), { once: true });
        }, 10);
    }

    hideFieldContextMenu() {
        if (this.contextMenu) {
            this.contextMenu.remove();
            this.contextMenu = null;
        }
    }

    moveFieldToStepFromMenu(fieldIndex, targetStepIndex) {
        this.hideFieldContextMenu();

        const field = this.fields[fieldIndex];
        if (!field) return;

        // Find which step the field is currently in
        let sourceStepIndex = -1;
        this.formSteps.forEach((step, idx) => {
            if (step.fields && step.fields.includes(field.field_name)) {
                sourceStepIndex = idx;
            }
        });

        // If already in target step, do nothing
        if (sourceStepIndex === targetStepIndex) {
            return;
        }

        // Remove field from all steps
        this.formSteps.forEach(step => {
            if (step.fields) {
                step.fields = step.fields.filter(name => name !== field.field_name);
            }
        });

        // Add to target step
        if (!this.formSteps[targetStepIndex].fields) {
            this.formSteps[targetStepIndex].fields = [];
        }
        this.formSteps[targetStepIndex].fields.push(field.field_name);

        // Re-render both steps
        if (sourceStepIndex !== -1) {
            this.renderSingleStep(sourceStepIndex);
        }
        this.renderSingleStep(targetStepIndex);

        // Update preview
        this.updatePreview();
    }
}

