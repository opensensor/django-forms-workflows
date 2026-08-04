/**
 * Visual Form Builder
 *
 * Provides drag-and-drop interface for creating and editing forms
 * without code.
 */

import { historyMethods } from './form-builder-history.js';
import { apiMethods } from './form-builder-api.js';
import { propertyEditorMethods } from './form-builder-property-editor.js';
import { canvasMethods } from './form-builder-canvas.js';
import { createBuilderStore } from './form-builder-store.js';

export class FormBuilder {
    constructor(config) {
        this.config = config;
        this.store = createBuilderStore();
        this.fields = [];
        this.currentFieldIndex = null;
        this.fieldIdCounter = 1;
        this.previewTimeout = null;
        this.draggingFieldType = null; // Track field type being dragged from palette
        this.dragPlaceholder = null; // Track the placeholder element
        this.isNewField = false; // Track if editing a newly created field
        this.formSteps = []; // Track multi-step configuration
        this.contextMenu = null; // Track context menu element
        this.undoStack = []; // Undo history
        this.redoStack = []; // Redo history
        this.maxUndoSteps = 50;

        this.init();
    }

    // fields/formSteps live on this.store now (single source of truth for
    // history's undo/redo snapshots); these proxy the existing this.fields/
    // this.formSteps call sites throughout this file so they don't all need
    // to change in this pass.
    get fields() { return this.store.fields; }
    set fields(value) { this.store.setFields(value); }

    get formSteps() { return this.store.formSteps; }
    set formSteps(value) { this.store.setFormSteps(value); }

    get fieldIdCounter() { return this.store.fieldIdCounter; }
    set fieldIdCounter(value) { this.store.fieldIdCounter = value; }

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

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            // Ctrl+S / Cmd+S = Save
            if ((e.ctrlKey || e.metaKey) && e.key === 's') {
                e.preventDefault();
                this.saveForm();
            }
            // Ctrl+Z / Cmd+Z = Undo
            if ((e.ctrlKey || e.metaKey) && e.key === 'z' && !e.shiftKey) {
                e.preventDefault();
                this.undo();
            }
            // Ctrl+Shift+Z / Cmd+Shift+Z = Redo
            if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'z') {
                e.preventDefault();
                this.redo();
            }
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
}

Object.assign(FormBuilder.prototype, historyMethods, apiMethods, propertyEditorMethods, canvasMethods);
