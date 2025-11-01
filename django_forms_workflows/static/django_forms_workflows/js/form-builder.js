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
        
        this.init();
    }
    
    init() {
        this.setupFieldPalette();
        this.setupCanvas();
        this.setupEventListeners();

        // Load existing form if editing
        if (!this.config.isNew && this.config.formId && this.config.apiUrls.load) {
            this.loadForm();
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
            });
            
            palette.appendChild(item);
        });
    }
    
    setupCanvas() {
        const canvas = document.getElementById('formCanvas');
        
        // Setup Sortable for drag-and-drop reordering
        this.sortable = Sortable.create(canvas, {
            animation: 150,
            ghostClass: 'sortable-ghost',
            dragClass: 'sortable-drag',
            handle: '.canvas-field',
            onEnd: (evt) => {
                // Update field order
                const movedField = this.fields.splice(evt.oldIndex, 1)[0];
                this.fields.splice(evt.newIndex, 0, movedField);
                this.updateFieldOrders();
                this.updatePreview();
            }
        });
        
        // Allow dropping from palette
        canvas.addEventListener('dragover', (e) => {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'copy';
        });
        
        canvas.addEventListener('drop', (e) => {
            e.preventDefault();
            const fieldType = e.dataTransfer.getData('fieldType');
            if (fieldType) {
                this.addField(fieldType);
            }
        });
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
        const field = {
            id: `new_${this.fieldIdCounter++}`,
            order: this.fields.length + 1,
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
        
        this.fields.push(field);
        this.renderCanvas();
        this.updatePreview();
        
        // Automatically open property editor for new field
        this.editField(this.fields.length - 1);
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
        
        document.getElementById('fieldCount').textContent = `${this.fields.length} field${this.fields.length !== 1 ? 's' : ''}`;
    }
    
    createFieldElement(field, index) {
        const div = document.createElement('div');
        div.className = 'canvas-field';
        div.dataset.index = index;
        
        const requiredBadge = field.required ? '<span class="badge bg-danger ms-2">Required</span>' : '';
        const helpText = field.help_text ? `<div class="text-muted small mt-1">${this.escapeHtml(field.help_text)}</div>` : '';
        
        div.innerHTML = `
            <div class="field-header">
                <div>
                    <span class="field-label">${this.escapeHtml(field.field_label)}</span>
                    ${requiredBadge}
                </div>
                <div class="field-actions">
                    <span class="field-type-badge">${field.field_type}</span>
                    <button class="btn btn-sm btn-outline-primary btn-field-action" onclick="formBuilder.editField(${index})">
                        <i class="bi bi-pencil"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-danger btn-field-action" onclick="formBuilder.deleteField(${index})">
                        <i class="bi bi-trash"></i>
                    </button>
                </div>
            </div>
            ${helpText}
            <div class="text-muted small">Field name: ${field.field_name}</div>
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
        // For now, just show field count
        // TODO: Implement actual form preview using API
        const preview = document.getElementById('formPreview');
        preview.innerHTML = `
            <div class="alert alert-info">
                <strong>Preview</strong><br>
                ${this.fields.length} field(s) configured
            </div>
        `;
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
}

