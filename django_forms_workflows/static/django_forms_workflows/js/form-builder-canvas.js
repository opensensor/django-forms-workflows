/**
 * Canvas and drag-drop controller for the Form Builder: the field palette,
 * the single-step and multi-step canvases (SortableJS wiring, native
 * HTML5 drag-drop for palette-to-canvas drops), field CRUD, canvas/step
 * rendering, and the field context menu.
 *
 * Mixed onto FormBuilder.prototype in form-builder.js (Object.assign), not a
 * standalone class of its own - these methods read/write `this.fields`/
 * `this.formSteps` (proxied onto `this.store`), plus a number of
 * FormBuilder-owned DOM/drag-state fields (`this.draggingFieldType`,
 * `this.dragPlaceholder`, `this.contextMenu`, `this.fieldTypes`/
 * `this.fieldTypeCategories`), and call back into
 * pushUndo()/updatePreview()/saveForm()/editField(), which still live on
 * historyMethods/apiMethods/propertyEditorMethods respectively - all mixed
 * onto the same FormBuilder instance, so `this.*` resolves regardless of
 * which module a given method came from.
 */
export const canvasMethods = {
    setupFieldPalette() {
        const palette = document.getElementById('fieldPalette');

        this.fieldTypeCategories = [
            {
                name: 'Basic Inputs',
                icon: 'bi-input-cursor-text',
                types: [
                    { type: 'text', label: 'Single Line Text', icon: 'bi-input-cursor-text' },
                    { type: 'textarea', label: 'Multi-line Text', icon: 'bi-textarea-t' },
                    { type: 'email', label: 'Email Address', icon: 'bi-envelope' },
                    { type: 'phone', label: 'Phone Number', icon: 'bi-telephone' },
                    { type: 'url', label: 'Website URL', icon: 'bi-link-45deg' },
                    { type: 'number', label: 'Whole Number', icon: 'bi-123' },
                    { type: 'decimal', label: 'Decimal Number', icon: 'bi-hash' },
                    { type: 'currency', label: 'Currency ($)', icon: 'bi-currency-dollar' },
                ]
            },
            {
                name: 'Selection',
                icon: 'bi-ui-checks',
                types: [
                    { type: 'select', label: 'Dropdown Select', icon: 'bi-menu-button-wide' },
                    { type: 'radio', label: 'Radio Buttons', icon: 'bi-ui-radios' },
                    { type: 'checkbox', label: 'Single Checkbox', icon: 'bi-check-square' },
                    { type: 'multiselect', label: 'Checkboxes (Multi)', icon: 'bi-ui-checks' },
                    { type: 'multiselect_list', label: 'Multi-Select List', icon: 'bi-list-check' },
                    { type: 'checkboxes', label: 'Checkbox Group', icon: 'bi-ui-checks-grid' },
                    { type: 'country', label: 'Country Picker', icon: 'bi-globe' },
                    { type: 'us_state', label: 'US State Picker', icon: 'bi-geo-alt' },
                ]
            },
            {
                name: 'Date & Time',
                icon: 'bi-calendar',
                types: [
                    { type: 'date', label: 'Date', icon: 'bi-calendar-date' },
                    { type: 'time', label: 'Time', icon: 'bi-clock' },
                    { type: 'datetime', label: 'Date & Time', icon: 'bi-calendar-event' },
                ]
            },
            {
                name: 'Uploads & Media',
                icon: 'bi-cloud-upload',
                types: [
                    { type: 'file', label: 'File Upload', icon: 'bi-file-earmark-arrow-up' },
                    { type: 'multifile', label: 'Multi-File Upload', icon: 'bi-files' },
                    { type: 'spreadsheet', label: 'Spreadsheet Upload', icon: 'bi-file-earmark-spreadsheet' },
                    { type: 'signature', label: 'Signature', icon: 'bi-pen' },
                ]
            },
            {
                name: 'Advanced',
                icon: 'bi-lightning',
                types: [
                    { type: 'calculated', label: 'Calculated / Formula', icon: 'bi-calculator' },
                    { type: 'hidden', label: 'Hidden Field', icon: 'bi-eye-slash' },
                    { type: 'rating', label: 'Rating (Stars)', icon: 'bi-star' },
                    { type: 'slider', label: 'Slider', icon: 'bi-sliders' },
                    { type: 'matrix', label: 'Matrix / Grid', icon: 'bi-grid-3x3' },
                    { type: 'address', label: 'Address', icon: 'bi-house-door' },
                ]
            },
            {
                name: 'Layout',
                icon: 'bi-layout-split',
                types: [
                    { type: 'section', label: 'Section Header', icon: 'bi-layout-text-sidebar' },
                    { type: 'display_text', label: 'Display Text', icon: 'bi-card-text' },
                ]
            }
        ];

        // Build flat fieldTypes list for backward compatibility
        this.fieldTypes = [];
        this.fieldTypeCategories.forEach(cat => {
            cat.types.forEach(ft => this.fieldTypes.push(ft));
        });

        // Render categorized palette
        this.renderPalette('');

        // Setup search
        const searchInput = document.getElementById('paletteSearch');
        if (searchInput) {
            searchInput.addEventListener('input', (e) => {
                this.renderPalette(e.target.value.toLowerCase().trim());
            });
        }

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
    },

    renderPalette(filter) {
        const palette = document.getElementById('fieldPalette');
        // Remove all items but keep the search (which is in the panel-header)
        palette.innerHTML = '';

        this.fieldTypeCategories.forEach(cat => {
            const matchingTypes = cat.types.filter(ft =>
                !filter || ft.label.toLowerCase().includes(filter) || ft.type.toLowerCase().includes(filter)
            );
            if (matchingTypes.length === 0) return;

            // Category header
            const header = document.createElement('div');
            header.className = 'palette-category-header';
            header.innerHTML = `
                <i class="bi ${cat.icon}"></i>
                <span>${cat.name}</span>
                <span class="badge bg-secondary rounded-pill ms-auto">${matchingTypes.length}</span>
            `;
            palette.appendChild(header);

            matchingTypes.forEach(fieldType => {
                const item = document.createElement('div');
                item.className = 'field-palette-item';
                item.dataset.fieldType = fieldType.type;
                item.innerHTML = `
                    <i class="bi ${fieldType.icon}"></i>
                    <span>${fieldType.label}</span>
                `;
                palette.appendChild(item);
            });
        });
    },

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
            draggable: '.field-item', // Both .canvas-field and .canvas-section elements
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
                    this.pushUndo();
                    const movedField = this.fields.splice(evt.oldIndex, 1)[0];
                    this.fields.splice(evt.newIndex, 0, movedField);
                    this.updateFieldOrders();
                    this.updatePreview();
                }
            },
            onUpdate: (evt) => {
                // Field reordered within canvas
                this.pushUndo();
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


            this.cleanupDragPlaceholder();
        });
    },

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
    },

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
    },

    addFieldAtPosition(fieldType, position) {
        this.pushUndo();
        // field_name must be read before nextFieldId() advances the counter,
        // so the id and the name it's derived from carry the same number -
        // matching handleFieldDroppedToStep's order, which already does this.
        const fieldName = this.getDefaultName(fieldType);
        const field = {
            id: this.store.nextFieldId('new'),
            order: position + 1,
            field_label: this.getDefaultLabel(fieldType),
            field_name: fieldName,
            field_type: fieldType,
            required: false,
            help_text: '',
            show_help_text_in_detail: false,
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

        const insertIndex = Math.min(position, this.fields.length);
        this.fields.splice(insertIndex, 0, field);
        this.updateFieldOrders();
        this.renderCanvas();
        this.updatePreview();

        // Automatically open property editor for new field
        this.editField(insertIndex, true); // true = isNew
    },

    addField(fieldType) {
        // Add field at the end
        this.addFieldAtPosition(fieldType, this.fields.length);
    },

    duplicateField(index) {
        this.pushUndo();
        const original = this.fields[index];
        const clone = JSON.parse(JSON.stringify(original));
        clone.id = this.store.nextFieldId('new');
        clone.field_name = original.field_name + '_copy';
        clone.field_label = original.field_label + ' (Copy)';
        clone.order = index + 2;

        this.fields.splice(index + 1, 0, clone);
        this.updateFieldOrders();

        // Also add to step if in multi-step mode
        if (this.formSteps && this.formSteps.length > 0) {
            this.formSteps.forEach(step => {
                if (step.fields) {
                    const pos = step.fields.indexOf(original.field_name);
                    if (pos !== -1) {
                        step.fields.splice(pos + 1, 0, clone.field_name);
                    }
                }
            });
        }

        const isMultiStep = document.getElementById('formEnableMultiStep')?.checked;
        if (isMultiStep) {
            this.renderStepTabs();
        } else {
            this.renderCanvas();
        }
        this.updatePreview();
    },

    getDefaultLabel(fieldType) {
        const labels = {
            'text': 'Text Field',
            'email': 'Email Address',
            'number': 'Number',
            'textarea': 'Text Area',
            'select': 'Select Option',
            'radio': 'Radio Choice',
            'multiselect': 'Checkboxes',
            'multiselect_list': 'Multi-Select',
            'checkbox': 'Checkbox',
            'checkboxes': 'Checkbox Group',
            'checkbox_multiple': 'Checkboxes',
            'date': 'Date',
            'time': 'Time',
            'datetime': 'Date and Time',
            'file': 'File Upload',
            'multifile': 'File Uploads',
            'url': 'Website URL',
            'phone': 'Phone Number',
            'decimal': 'Decimal',
            'currency': 'Amount',
            'hidden': 'Hidden Field',
            'section': 'Section Header',
            'calculated': 'Calculated Field',
            'spreadsheet': 'Spreadsheet Upload',
            'country': 'Country',
            'us_state': 'State',
            'signature': 'Signature',
            'rating': 'Rating',
            'matrix': 'Matrix',
            'address': 'Address',
            'slider': 'Slider'
        };
        return labels[fieldType] || 'Field';
    },

    getDefaultName(fieldType) {
        return fieldType + '_' + this.fieldIdCounter;
    },

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
    },

    createFieldElement(field, index) {
        const div = document.createElement('div');
        div.dataset.index = index;
        div.dataset.fieldIndex = index;

        if (field.field_type === 'section') {
            // Section header — render as a prominent divider
            div.className = 'canvas-section field-item';
            div.innerHTML = `
                <div class="field-header field-drag-handle" style="cursor: move;">
                    <div>
                        <i class="bi bi-grip-vertical me-2 text-muted"></i>
                        <i class="bi bi-layout-text-sidebar me-1"></i>
                        <span class="field-label">${this.escapeHtml(field.field_label)}</span>
                    </div>
                    <div class="field-actions">
                        <span class="field-type-badge section-badge">section</span>
                        <button class="btn btn-sm btn-outline-primary btn-field-action" onclick="formBuilder.editField(${index})" title="Edit section">
                            <i class="bi bi-pencil"></i>
                        </button>
                        <button class="btn btn-sm btn-outline-secondary btn-field-action" onclick="formBuilder.duplicateField(${index})" title="Duplicate section">
                            <i class="bi bi-copy"></i>
                        </button>
                        <button class="btn btn-sm btn-outline-danger btn-field-action" onclick="formBuilder.deleteField(${index})" title="Delete section">
                            <i class="bi bi-trash"></i>
                        </button>
                    </div>
                </div>
            `;
        } else {
            // Regular field
            div.className = 'canvas-field field-item';
            const requiredBadge = field.required ? '<span class="badge bg-danger ms-1" style="font-size: 0.65rem; padding: 0.15rem 0.35rem;">REQ</span>' : '';
            const fieldInfo = `<span class="text-muted" style="font-size: 0.75rem;">${field.field_name}</span>`;
            const widthBadge = field.width && field.width !== 'full' ? `<span class="badge bg-secondary ms-1" style="font-size: 0.6rem;">${field.width}</span>` : '';

            div.innerHTML = `
                <div class="field-header field-drag-handle" style="cursor: move;">
                    <div>
                        <i class="bi bi-grip-vertical me-2 text-muted"></i>
                        <span class="field-label">${this.escapeHtml(field.field_label)}</span>
                        ${requiredBadge}${widthBadge}
                        <span class="ms-2">${fieldInfo}</span>
                    </div>
                    <div class="field-actions">
                        <span class="field-type-badge">${field.field_type}</span>
                        <button class="btn btn-sm btn-outline-primary btn-field-action" onclick="formBuilder.editField(${index})" title="Edit field">
                            <i class="bi bi-pencil"></i>
                        </button>
                        <button class="btn btn-sm btn-outline-secondary btn-field-action" onclick="formBuilder.duplicateField(${index})" title="Duplicate field">
                            <i class="bi bi-copy"></i>
                        </button>
                        <button class="btn btn-sm btn-outline-danger btn-field-action" onclick="formBuilder.deleteField(${index})" title="Delete field">
                            <i class="bi bi-trash"></i>
                        </button>
                    </div>
                </div>
            `;
        }

        // Add context menu handler for multi-step mode
        div.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            this.showFieldContextMenu(e, index);
        });

        return div;
    },

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

            this.updatePreview();
        } else {
            // Switch to single-step mode
            singleCanvas.style.display = 'block';
            multiCanvas.style.display = 'none';
            if (stepTabsControls) stepTabsControls.style.display = 'none';

            // Move all fields back to main canvas
            this.moveAllFieldsToMainCanvas();
        }
    },

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
    },

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
    },

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
    },

    handleFieldDroppedToStep(fieldType, stepIndex, position) {
        // Create a new field when dropped from palette
        const fieldConfig = this.fieldTypes.find(ft => ft.type === fieldType);
        if (!fieldConfig) return;

        this.pushUndo();

        const fieldName = this.getDefaultName(fieldType);
        const newField = {
            id: this.store.nextFieldId('new'),
            field_type: fieldType,
            field_name: fieldName,
            field_label: this.getDefaultLabel(fieldType),
            required: false,
            help_text: '',
            show_help_text_in_detail: false,
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

        // Reorder this.fields to match step order *before* rendering - every
        // step's data-field-index is derived from this.fields' current index,
        // so rendering first and reordering after leaves stale indices behind
        // on any step whose fields shifted position in the flattened array.
        this.updateFieldOrderFromSteps();
        this.renderFieldsInSteps();
        this.updatePreview();

        // Automatically open property editor for new field
        const fieldIndex = this.fields.findIndex(f => f.field_name === fieldName);
        this.editField(fieldIndex, true); // true = isNew
    },

    addStepTab() {
        const newIndex = this.formSteps.length;
        this.formSteps.push({
            title: `Step ${newIndex + 1}`,
            fields: []
        });
        this.renderStepTabs();
    },

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
    },

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
    },

    handleFieldMovedToStep(fieldElement, stepIndex) {
        const fieldIndex = parseInt(fieldElement.dataset.fieldIndex);
        const field = this.fields[fieldIndex];

        if (!field) return;

        this.pushUndo();

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

        // Reorder this.fields to match step order *before* rendering - every
        // step's data-field-index is derived from this.fields' current index,
        // so rendering first and reordering after leaves stale indices behind
        // on any step whose fields shifted position in the flattened array.
        this.updateFieldOrderFromSteps();
        this.renderFieldsInSteps();

        // Update preview
        this.updatePreview();
    },

    updateFieldOrderInStep(stepIndex) {
        const canvas = document.getElementById(`step-canvas-${stepIndex}`);
        if (!canvas) return;

        this.pushUndo();

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

        // Reorder this.fields to match, then re-render every step so
        // data-field-index stays in sync everywhere - a reorder in this step
        // can shift indices for fields in other steps too, since this.fields
        // is one flattened array, not scoped per step.
        this.updateFieldOrderFromSteps();
        this.renderFieldsInSteps();
        this.updatePreview();
    },

    updateStepFieldCount(stepIndex) {
        const panel = document.getElementById(`step-panel-${stepIndex}`);
        if (panel) {
            const badge = panel.querySelector('.badge');
            if (badge) {
                const count = this.formSteps[stepIndex].fields ? this.formSteps[stepIndex].fields.length : 0;
                badge.textContent = `${count} fields`;
            }
        }
    },

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
    },

    renderFieldsInSteps() {
        // Render fields in their respective steps
        this.formSteps.forEach((step, stepIndex) => {
            this.renderSingleStep(stepIndex);
        });
    },

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
    },

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
        this.updatePreview();
    },

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
    },

    deleteField(index) {
        if (confirm('Are you sure you want to delete this field?')) {
            this.pushUndo();
            this.deleteFieldSilently(index);
        }
    },

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
    },

    updateFieldOrders() {
        this.fields.forEach((field, index) => {
            field.order = index + 1;
        });
    },

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    },

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
    },

    hideFieldContextMenu() {
        if (this.contextMenu) {
            this.contextMenu.remove();
            this.contextMenu = null;
        }
    },

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
    },
};
