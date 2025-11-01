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

        const fieldTypes = [
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

        fieldTypes.forEach(fieldType => {
            const item = document.createElement('div');
            item.className = 'field-palette-item';
            item.draggable = true;
            item.dataset.fieldType = fieldType.type;
            item.innerHTML = `
                <i class="bi ${fieldType.icon}"></i>
                <span>${fieldType.label}</span>
            `;

            item.addEventListener('dragstart', (e) => {
                e.dataTransfer.setData('fieldType', fieldType.type);
                e.dataTransfer.effectAllowed = 'copy';
                // Store the field type globally so we can access it in dragover
                this.draggingFieldType = fieldType.type;
            });

            item.addEventListener('dragend', (e) => {
                // Clear the dragging field type and clean up any placeholder
                this.draggingFieldType = null;
                this.cleanupDragPlaceholder();
            });

            palette.appendChild(item);
        });
    }
    
    setupCanvas() {
        const canvas = document.getElementById('formCanvas');

        // Setup Sortable for drag-and-drop reordering
        this.sortable = Sortable.create(canvas, {
            animation: 300,
            easing: 'cubic-bezier(0.4, 0, 0.2, 1)',
            ghostClass: 'sortable-ghost',
            dragClass: 'sortable-drag',
            handle: '.canvas-field',
            draggable: '.canvas-field', // Only canvas-field elements are draggable/sortable
            filter: '.canvas-drop-zone', // Exclude drop zone from sorting
            onStart: (evt) => {
                // Add dragging class for enhanced visual feedback
                canvas.classList.add('dragging');
            },
            onEnd: (evt) => {
                // Remove dragging class
                canvas.classList.remove('dragging');

                // Update field order
                const movedField = this.fields.splice(evt.oldIndex, 1)[0];
                this.fields.splice(evt.newIndex, 0, movedField);
                this.updateFieldOrders();
                this.updatePreview();
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
        this.editField(position);
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
        div.className = 'canvas-field';
        div.dataset.index = index;

        const requiredBadge = field.required ? '<span class="badge bg-danger ms-1" style="font-size: 0.65rem; padding: 0.15rem 0.35rem;">REQ</span>' : '';
        const fieldInfo = `<span class="text-muted" style="font-size: 0.75rem;">${field.field_name}</span>`;

        div.innerHTML = `
            <div class="field-header">
                <div>
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

        return div;
    }
    
    editField(index) {
        this.currentFieldIndex = index;
        const field = this.fields[index];
        
        // Build property form
        const form = this.buildPropertyForm(field);
        document.getElementById('fieldPropertyForm').innerHTML = form;
        
        // Show modal
        const modal = new bootstrap.Modal(document.getElementById('fieldPropertyModal'));
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
    
    saveFieldProperties() {
        if (this.currentFieldIndex === null) return;
        
        const field = this.fields[this.currentFieldIndex];
        
        // Update field properties from form
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
        
        // Close modal
        bootstrap.Modal.getInstance(document.getElementById('fieldPropertyModal')).hide();
        
        // Re-render
        this.renderCanvas();
        this.updatePreview();
    }
    
    deleteField(index) {
        if (confirm('Are you sure you want to delete this field?')) {
            this.fields.splice(index, 1);
            this.updateFieldOrders();
            this.renderCanvas();
            this.updatePreview();
        }
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

            // Load fields
            this.fields = data.fields || [];
            this.renderCanvas();
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
}

