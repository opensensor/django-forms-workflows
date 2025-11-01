/**
 * Django Forms Workflows - Enhanced Client-Side Features
 * 
 * This module provides:
 * - Advanced conditional logic with AND/OR conditions
 * - Dynamic field validation with real-time feedback
 * - Progressive form disclosure (multi-step forms)
 * - Auto-save drafts
 * - Field dependencies and cascade updates
 */

class FormEnhancements {
    constructor(formElement, options = {}) {
        this.form = formElement;
        this.options = {
            autoSaveInterval: options.autoSaveInterval || 30000, // 30 seconds
            autoSaveEnabled: options.autoSaveEnabled !== false,
            validationDelay: options.validationDelay || 500, // ms
            multiStepEnabled: options.multiStepEnabled || false,
            conditionalRules: options.conditionalRules || [],
            fieldDependencies: options.fieldDependencies || [],
            validationRules: options.validationRules || [],
            ...options
        };
        
        this.autoSaveTimer = null;
        this.validationTimers = {};
        this.fieldValues = {};
        this.currentStep = 0;
        this.steps = [];
        
        this.init();
    }
    
    init() {
        // Initialize field tracking
        this.trackFieldChanges();
        
        // Setup conditional logic
        if (this.options.conditionalRules.length > 0) {
            this.setupConditionalLogic();
        }
        
        // Setup field dependencies
        if (this.options.fieldDependencies.length > 0) {
            this.setupFieldDependencies();
        }
        
        // Setup real-time validation
        if (this.options.validationRules.length > 0) {
            this.setupDynamicValidation();
        }
        
        // Setup multi-step forms
        if (this.options.multiStepEnabled) {
            this.setupMultiStepForm();
        }
        
        // Setup auto-save
        if (this.options.autoSaveEnabled) {
            this.setupAutoSave();
        }
        
        // Initial evaluation
        this.evaluateAllConditions();
    }
    
    /**
     * Track field changes for auto-save and validation
     */
    trackFieldChanges() {
        const fields = this.form.querySelectorAll('input, select, textarea');
        fields.forEach(field => {
            // Store initial value
            this.fieldValues[field.name] = this.getFieldValue(field);
            
            // Listen for changes
            field.addEventListener('input', (e) => this.handleFieldChange(e));
            field.addEventListener('change', (e) => this.handleFieldChange(e));
        });
    }
    
    /**
     * Handle field change events
     */
    handleFieldChange(event) {
        const field = event.target;
        const fieldName = field.name;
        const newValue = this.getFieldValue(field);
        
        // Update tracked value
        this.fieldValues[fieldName] = newValue;
        
        // Trigger conditional logic evaluation
        this.evaluateAllConditions();
        
        // Trigger field dependencies
        this.handleFieldDependencies(fieldName, newValue);
        
        // Trigger real-time validation
        this.validateField(field);
        
        // Reset auto-save timer
        if (this.options.autoSaveEnabled) {
            this.resetAutoSaveTimer();
        }
    }
    
    /**
     * Get field value (handles different input types)
     */
    getFieldValue(field) {
        if (field.type === 'checkbox') {
            return field.checked;
        } else if (field.type === 'radio') {
            const checked = this.form.querySelector(`input[name="${field.name}"]:checked`);
            return checked ? checked.value : null;
        } else if (field.multiple) {
            const values = Array.from(field.selectedOptions).map(opt => opt.value);
            return values.length > 0 ? values : null;
        }
        // Trim whitespace and return null if empty
        const value = field.value ? field.value.trim() : '';
        return value || null;
    }
    
    /**
     * Setup advanced conditional logic with AND/OR conditions
     * 
     * Rule format:
     * {
     *   targetField: 'field_name',
     *   action: 'show|hide|require|unrequire|enable|disable',
     *   operator: 'AND|OR',
     *   conditions: [
     *     { field: 'field1', operator: 'equals|not_equals|contains|greater_than|less_than|in|not_in', value: 'value' },
     *     { field: 'field2', operator: 'equals', value: 'value2' }
     *   ]
     * }
     */
    setupConditionalLogic() {
        // Initial evaluation will be done in init()
        console.log(`Loaded ${this.options.conditionalRules.length} conditional rules`);
    }
    
    /**
     * Evaluate all conditional rules
     */
    evaluateAllConditions() {
        this.options.conditionalRules.forEach(rule => {
            this.evaluateConditionalRule(rule);
        });
    }
    
    /**
     * Evaluate a single conditional rule
     */
    evaluateConditionalRule(rule) {
        const operator = rule.operator || 'AND';
        let result;
        
        if (operator === 'AND') {
            result = rule.conditions.every(cond => this.evaluateCondition(cond));
        } else if (operator === 'OR') {
            result = rule.conditions.some(cond => this.evaluateCondition(cond));
        } else {
            console.error('Invalid operator:', operator);
            return;
        }
        
        // Apply action based on result
        this.applyConditionalAction(rule.targetField, rule.action, result);
    }
    
    /**
     * Evaluate a single condition
     */
    evaluateCondition(condition) {
        const fieldValue = this.fieldValues[condition.field];
        const compareValue = condition.value;
        
        switch (condition.operator) {
            case 'equals':
                return String(fieldValue) === String(compareValue);
            case 'not_equals':
                return String(fieldValue) !== String(compareValue);
            case 'contains':
                return String(fieldValue).includes(String(compareValue));
            case 'not_contains':
                return !String(fieldValue).includes(String(compareValue));
            case 'greater_than':
                return parseFloat(fieldValue) > parseFloat(compareValue);
            case 'less_than':
                return parseFloat(fieldValue) < parseFloat(compareValue);
            case 'greater_or_equal':
                return parseFloat(fieldValue) >= parseFloat(compareValue);
            case 'less_or_equal':
                return parseFloat(fieldValue) <= parseFloat(compareValue);
            case 'in':
                const inValues = Array.isArray(compareValue) ? compareValue : compareValue.split(',');
                return inValues.includes(String(fieldValue));
            case 'not_in':
                const notInValues = Array.isArray(compareValue) ? compareValue : compareValue.split(',');
                return !notInValues.includes(String(fieldValue));
            case 'is_empty':
                return !fieldValue || fieldValue === '' || (Array.isArray(fieldValue) && fieldValue.length === 0);
            case 'is_not_empty':
                return fieldValue && fieldValue !== '' && (!Array.isArray(fieldValue) || fieldValue.length > 0);
            case 'is_true':
                return fieldValue === true || fieldValue === 'true' || fieldValue === '1';
            case 'is_false':
                return fieldValue === false || fieldValue === 'false' || fieldValue === '0' || !fieldValue;
            default:
                console.error('Unknown operator:', condition.operator);
                return false;
        }
    }
    
    /**
     * Apply conditional action to target field
     */
    applyConditionalAction(targetFieldName, action, conditionMet) {
        const field = this.form.querySelector(`[name="${targetFieldName}"]`);
        if (!field) {
            console.warn('Target field not found:', targetFieldName);
            return;
        }
        
        // Find the field's container (usually a div with form-group or similar)
        const container = field.closest('.form-group, .mb-3, .field-wrapper') || field.parentElement;
        
        switch (action) {
            case 'show':
                container.style.display = conditionMet ? '' : 'none';
                break;
            case 'hide':
                container.style.display = conditionMet ? 'none' : '';
                break;
            case 'require':
                field.required = conditionMet;
                this.updateRequiredIndicator(field, conditionMet);
                break;
            case 'unrequire':
                field.required = !conditionMet;
                this.updateRequiredIndicator(field, !conditionMet);
                break;
            case 'enable':
                field.disabled = !conditionMet;
                break;
            case 'disable':
                field.disabled = conditionMet;
                break;
            default:
                console.error('Unknown action:', action);
        }
    }
    
    /**
     * Update required indicator (asterisk) for a field
     */
    updateRequiredIndicator(field, isRequired) {
        const label = this.form.querySelector(`label[for="${field.id}"]`);
        if (!label) return;
        
        const asterisk = label.querySelector('.required-asterisk');
        if (isRequired && !asterisk) {
            const span = document.createElement('span');
            span.className = 'required-asterisk text-danger';
            span.textContent = ' *';
            label.appendChild(span);
        } else if (!isRequired && asterisk) {
            asterisk.remove();
        }
    }
    
    /**
     * Setup field dependencies for cascade updates
     * 
     * Dependency format:
     * {
     *   sourceField: 'field_name',
     *   targetField: 'dependent_field_name',
     *   handler: function(sourceValue, targetField) { ... }
     *   or
     *   apiEndpoint: '/api/get-options/',
     *   valueMapping: { param: 'sourceField' }
     * }
     */
    setupFieldDependencies() {
        console.log(`Loaded ${this.options.fieldDependencies.length} field dependencies`);
    }
    
    /**
     * Handle field dependencies when a field changes
     */
    handleFieldDependencies(fieldName, value) {
        const dependencies = this.options.fieldDependencies.filter(dep => dep.sourceField === fieldName);

        dependencies.forEach(dep => {
            const targetField = this.form.querySelector(`[name="${dep.targetField}"]`);
            if (!targetField) return;

            if (dep.handler && typeof dep.handler === 'function') {
                // Custom handler
                dep.handler(value, targetField, this);
            } else if (dep.apiEndpoint) {
                // API-based dependency
                this.fetchDependentOptions(dep, value, targetField);
            }
        });
    }

    /**
     * Fetch dependent field options from API
     */
    async fetchDependentOptions(dependency, sourceValue, targetField) {
        try {
            const params = new URLSearchParams();
            if (dependency.valueMapping) {
                Object.entries(dependency.valueMapping).forEach(([param, field]) => {
                    params.append(param, field === dependency.sourceField ? sourceValue : this.fieldValues[field]);
                });
            } else {
                params.append('value', sourceValue);
            }

            const response = await fetch(`${dependency.apiEndpoint}?${params}`);
            const data = await response.json();

            if (data.success && data.options) {
                this.updateFieldOptions(targetField, data.options);
            }
        } catch (error) {
            console.error('Error fetching dependent options:', error);
        }
    }

    /**
     * Update field options (for select/radio/checkbox fields)
     */
    updateFieldOptions(field, options) {
        if (field.tagName === 'SELECT') {
            // Clear existing options
            field.innerHTML = '';

            // Add new options
            options.forEach(opt => {
                const option = document.createElement('option');
                option.value = opt.value;
                option.textContent = opt.label;
                field.appendChild(option);
            });
        } else if (field.type === 'radio' || field.type === 'checkbox') {
            // Handle radio/checkbox groups
            const container = field.closest('.form-group, .mb-3, .field-wrapper');
            if (!container) return;

            // Find all radio/checkbox inputs with the same name
            const inputs = container.querySelectorAll(`input[name="${field.name}"]`);
            inputs.forEach(input => input.parentElement.remove());

            // Add new options
            options.forEach(opt => {
                const wrapper = document.createElement('div');
                wrapper.className = 'form-check';
                wrapper.innerHTML = `
                    <input class="form-check-input" type="${field.type}" name="${field.name}"
                           id="${field.name}_${opt.value}" value="${opt.value}">
                    <label class="form-check-label" for="${field.name}_${opt.value}">
                        ${opt.label}
                    </label>
                `;
                container.appendChild(wrapper);
            });
        }
    }

    /**
     * Setup dynamic field validation
     *
     * Validation rule format:
     * {
     *   field: 'field_name',
     *   rules: [
     *     { type: 'required', message: 'This field is required' },
     *     { type: 'email', message: 'Invalid email' },
     *     { type: 'min', value: 5, message: 'Minimum 5 characters' },
     *     { type: 'max', value: 100, message: 'Maximum 100 characters' },
     *     { type: 'pattern', value: /regex/, message: 'Invalid format' },
     *     { type: 'custom', validator: function(value) { return true/false; }, message: 'Custom error' }
     *   ]
     * }
     */
    setupDynamicValidation() {
        console.log(`Loaded ${this.options.validationRules.length} validation rules`);
    }

    /**
     * Validate a field with debouncing
     */
    validateField(field) {
        const fieldName = field.name;

        // Clear existing timer
        if (this.validationTimers[fieldName]) {
            clearTimeout(this.validationTimers[fieldName]);
        }

        // Set new timer
        this.validationTimers[fieldName] = setTimeout(() => {
            this.performFieldValidation(field);
        }, this.options.validationDelay);
    }

    /**
     * Perform actual field validation
     */
    performFieldValidation(field) {
        const fieldName = field.name;
        const value = this.getFieldValue(field);
        const rules = this.options.validationRules.find(r => r.field === fieldName);

        if (!rules || !rules.rules) return;

        // Clear previous errors
        this.clearFieldError(field);

        // Validate each rule
        for (const rule of rules.rules) {
            const isValid = this.validateRule(value, rule);
            if (!isValid) {
                this.showFieldError(field, rule.message);
                return; // Stop at first error
            }
        }

        // Show success indicator
        this.showFieldSuccess(field);
    }

    /**
     * Validate a single rule
     */
    validateRule(value, rule) {
        switch (rule.type) {
            case 'required':
                return value !== null && value !== undefined && value !== '' &&
                       (!Array.isArray(value) || value.length > 0);
            case 'email':
                return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
            case 'url':
                try {
                    new URL(value);
                    return true;
                } catch {
                    return false;
                }
            case 'min':
                return String(value).length >= rule.value;
            case 'max':
                return String(value).length <= rule.value;
            case 'min_value':
                return parseFloat(value) >= parseFloat(rule.value);
            case 'max_value':
                return parseFloat(value) <= parseFloat(rule.value);
            case 'pattern':
                return new RegExp(rule.value).test(value);
            case 'custom':
                return rule.validator(value);
            default:
                return true;
        }
    }

    /**
     * Show field error
     */
    showFieldError(field, message) {
        field.classList.add('is-invalid');
        field.classList.remove('is-valid');

        const container = field.closest('.form-group, .mb-3, .field-wrapper') || field.parentElement;
        let errorDiv = container.querySelector('.invalid-feedback');

        if (!errorDiv) {
            errorDiv = document.createElement('div');
            errorDiv.className = 'invalid-feedback';
            field.parentElement.appendChild(errorDiv);
        }

        errorDiv.textContent = message;
        errorDiv.style.display = 'block';
    }

    /**
     * Show field success
     */
    showFieldSuccess(field) {
        field.classList.remove('is-invalid');
        field.classList.add('is-valid');

        const container = field.closest('.form-group, .mb-3, .field-wrapper') || field.parentElement;
        const errorDiv = container.querySelector('.invalid-feedback');
        if (errorDiv) {
            errorDiv.style.display = 'none';
        }
    }

    /**
     * Clear field error
     */
    clearFieldError(field) {
        field.classList.remove('is-invalid', 'is-valid');

        const container = field.closest('.form-group, .mb-3, .field-wrapper') || field.parentElement;
        const errorDiv = container.querySelector('.invalid-feedback');
        if (errorDiv) {
            errorDiv.style.display = 'none';
        }
    }

    /**
     * Setup multi-step form with progress indicators
     *
     * Steps are defined by data-step attributes on field containers
     * or by the steps option: [{ title: 'Step 1', fields: ['field1', 'field2'] }]
     */
    setupMultiStepForm() {
        console.log('Setting up multi-step form', this.options);

        // If steps are defined in options, use them
        if (this.options.steps && this.options.steps.length > 0) {
            this.steps = this.options.steps;
            console.log('Using configured steps:', this.steps);
        } else {
            // Auto-detect steps from data-step attributes
            this.detectSteps();
            console.log('Auto-detected steps:', this.steps);
        }

        if (this.steps.length === 0) {
            console.warn('No steps defined for multi-step form');
            return;
        }

        console.log(`Creating multi-step form with ${this.steps.length} steps`);

        // Create progress indicator
        this.createProgressIndicator();

        // Create navigation buttons
        this.createStepNavigation();

        // Show first step
        this.showStep(0);
    }

    /**
     * Auto-detect steps from data-step attributes
     */
    detectSteps() {
        const stepElements = this.form.querySelectorAll('[data-step]');
        const stepMap = new Map();

        stepElements.forEach(el => {
            const stepNum = parseInt(el.dataset.step);
            const stepTitle = el.dataset.stepTitle || `Step ${stepNum}`;

            if (!stepMap.has(stepNum)) {
                stepMap.set(stepNum, { title: stepTitle, elements: [] });
            }
            stepMap.get(stepNum).elements.push(el);
        });

        // Convert to array and sort
        this.steps = Array.from(stepMap.entries())
            .sort((a, b) => a[0] - b[0])
            .map(([num, data]) => data);
    }

    /**
     * Create progress indicator
     */
    createProgressIndicator() {
        const progressContainer = document.createElement('div');
        progressContainer.className = 'form-progress mb-4';
        progressContainer.innerHTML = `
            <div class="progress" style="height: 30px;">
                <div class="progress-bar progress-bar-striped" role="progressbar"
                     style="width: 0%;" id="formProgressBar">
                    Step 1 of ${this.steps.length}
                </div>
            </div>
            <div class="step-indicators mt-3 d-flex justify-content-between">
                ${this.steps.map((step, i) => `
                    <div class="step-indicator ${i === 0 ? 'active' : ''}" data-step="${i}">
                        <div class="step-number">${i + 1}</div>
                        <div class="step-title">${step.title}</div>
                    </div>
                `).join('')}
            </div>
        `;

        // Insert at the beginning of the form
        this.form.insertBefore(progressContainer, this.form.firstChild);

        // Add CSS for step indicators
        this.addProgressStyles();
    }

    /**
     * Add CSS styles for progress indicators
     */
    addProgressStyles() {
        if (document.getElementById('form-progress-styles')) return;

        const style = document.createElement('style');
        style.id = 'form-progress-styles';
        style.textContent = `
            .step-indicator {
                text-align: center;
                flex: 1;
                opacity: 0.5;
                transition: opacity 0.3s;
            }
            .step-indicator.active {
                opacity: 1;
                font-weight: bold;
            }
            .step-indicator.completed {
                opacity: 0.8;
                color: #28a745;
            }
            .step-number {
                width: 30px;
                height: 30px;
                border-radius: 50%;
                background: #e9ecef;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                margin-bottom: 5px;
                font-weight: bold;
                font-size: 0.875rem;
            }
            .step-indicator.active .step-number {
                background: #0d6efd;
                color: white;
            }
            .step-indicator.completed .step-number {
                background: #28a745;
                color: white;
            }
            .step-title {
                font-size: 0.75rem;
            }
            .step-navigation {
                margin-top: 1.5rem;
                padding-top: 1.5rem;
                border-top: 1px solid #dee2e6;
            }
            .step-navigation .btn {
                min-width: 120px;
            }
        `;
        document.head.appendChild(style);
    }

    /**
     * Create step navigation buttons
     */
    createStepNavigation() {
        const navContainer = document.createElement('div');
        navContainer.className = 'step-navigation d-flex justify-content-between align-items-center gap-2';
        navContainer.innerHTML = `
            <button type="button" class="btn btn-secondary" id="btnPrevStep" style="display: none;">
                <i class="bi bi-arrow-left"></i> Previous
            </button>
            <div class="flex-grow-1"></div>
            <button type="button" class="btn btn-primary" id="btnNextStep">
                Next <i class="bi bi-arrow-right"></i>
            </button>
        `;

        // Find the submit button and insert navigation before it
        const submitButton = this.form.querySelector('[type="submit"]');
        if (submitButton) {
            submitButton.style.display = 'none'; // Hide until last step
            submitButton.parentElement.insertBefore(navContainer, submitButton);

            // Also add Save Draft button if enabled
            if (this.options.enableAutoSave) {
                const saveDraftBtn = document.createElement('button');
                saveDraftBtn.type = 'button';
                saveDraftBtn.className = 'btn btn-outline-secondary';
                saveDraftBtn.id = 'btnSaveDraft';
                saveDraftBtn.innerHTML = '<i class="bi bi-save"></i> Save Draft';
                saveDraftBtn.addEventListener('click', () => this.saveDraft());
                navContainer.appendChild(saveDraftBtn);
            }
        } else {
            this.form.appendChild(navContainer);
        }

        // Add event listeners
        document.getElementById('btnPrevStep').addEventListener('click', () => this.previousStep());
        document.getElementById('btnNextStep').addEventListener('click', () => this.nextStep());
    }

    /**
     * Show a specific step
     */
    showStep(stepIndex) {
        if (stepIndex < 0 || stepIndex >= this.steps.length) return;

        this.currentStep = stepIndex;
        const step = this.steps[stepIndex];

        console.log(`Showing step ${stepIndex + 1}:`, step);

        // Hide all steps
        this.steps.forEach((s, i) => {
            if (s.elements) {
                s.elements.forEach(el => el.style.display = 'none');
            } else if (s.fields) {
                s.fields.forEach(fieldName => {
                    const field = this.form.querySelector(`[name="${fieldName}"]`);
                    if (field) {
                        const container = field.closest('.field-wrapper, .form-group, .mb-3') || field.parentElement;
                        if (container) {
                            container.style.display = 'none';
                            console.log(`Hiding field: ${fieldName}`);
                        } else {
                            console.warn(`No container found for field: ${fieldName}`);
                        }
                    } else {
                        console.warn(`Field not found: ${fieldName}`);
                    }
                });
            }
        });

        // Show current step
        if (step.elements) {
            step.elements.forEach(el => el.style.display = '');
        } else if (step.fields) {
            step.fields.forEach(fieldName => {
                const field = this.form.querySelector(`[name="${fieldName}"]`);
                if (field) {
                    const container = field.closest('.field-wrapper, .form-group, .mb-3') || field.parentElement;
                    if (container) {
                        container.style.display = '';
                        console.log(`Showing field: ${fieldName}`);
                    }
                }
            });
        }

        // Update progress bar
        const progress = ((stepIndex + 1) / this.steps.length) * 100;
        const progressBar = document.getElementById('formProgressBar');
        if (progressBar) {
            progressBar.style.width = `${progress}%`;
            progressBar.textContent = `Step ${stepIndex + 1} of ${this.steps.length}`;
        }

        // Update step indicators
        document.querySelectorAll('.step-indicator').forEach((indicator, i) => {
            indicator.classList.remove('active', 'completed');
            if (i < stepIndex) {
                indicator.classList.add('completed');
            } else if (i === stepIndex) {
                indicator.classList.add('active');
            }
        });

        // Update navigation buttons
        const prevBtn = document.getElementById('btnPrevStep');
        const nextBtn = document.getElementById('btnNextStep');
        const submitBtn = this.form.querySelector('[type="submit"]');

        if (prevBtn) prevBtn.style.display = stepIndex === 0 ? 'none' : '';
        if (nextBtn) nextBtn.style.display = stepIndex === this.steps.length - 1 ? 'none' : '';
        if (submitBtn) submitBtn.style.display = stepIndex === this.steps.length - 1 ? '' : 'none';
    }

    /**
     * Go to next step
     */
    nextStep() {
        // Validate current step before proceeding
        if (!this.validateCurrentStep()) {
            return;
        }

        if (this.currentStep < this.steps.length - 1) {
            this.showStep(this.currentStep + 1);
        }
    }

    /**
     * Go to previous step
     */
    previousStep() {
        if (this.currentStep > 0) {
            this.showStep(this.currentStep - 1);
        }
    }

    /**
     * Validate current step
     */
    validateCurrentStep() {
        const step = this.steps[this.currentStep];
        let isValid = true;
        let firstInvalidField = null;

        // Get fields in current step
        let fields = [];
        if (step.elements) {
            step.elements.forEach(el => {
                fields.push(...el.querySelectorAll('input, select, textarea'));
            });
        } else if (step.fields) {
            step.fields.forEach(fieldName => {
                const field = this.form.querySelector(`[name="${fieldName}"]`);
                if (field) fields.push(field);
            });
        }

        // Validate each field
        fields.forEach(field => {
            // Clear previous errors first
            this.clearFieldError(field);

            if (field.required && !this.getFieldValue(field)) {
                this.showFieldError(field, 'This field is required');
                isValid = false;
                if (!firstInvalidField) firstInvalidField = field;
            } else if (field.value) {
                // Only validate non-empty optional fields
                this.performFieldValidation(field);
                if (field.classList.contains('is-invalid')) {
                    isValid = false;
                    if (!firstInvalidField) firstInvalidField = field;
                }
            }
        });

        // If validation failed, scroll to first invalid field and show alert
        if (!isValid && firstInvalidField) {
            firstInvalidField.focus();
            firstInvalidField.scrollIntoView({ behavior: 'smooth', block: 'center' });

            // Show alert message
            this.showValidationAlert('Please fill in all required fields before continuing.');
        }

        return isValid;
    }

    /**
     * Setup auto-save functionality
     */
    setupAutoSave() {
        // Check if we have a save endpoint
        if (!this.options.autoSaveEndpoint) {
            console.warn('Auto-save enabled but no endpoint specified');
            return;
        }

        // Add auto-save indicator
        this.createAutoSaveIndicator();

        // Start auto-save timer
        this.resetAutoSaveTimer();

        // Save on form submit
        this.form.addEventListener('submit', (e) => {
            // Clear auto-save timer
            if (this.autoSaveTimer) {
                clearTimeout(this.autoSaveTimer);
            }
        });
    }

    /**
     * Create auto-save indicator
     */
    createAutoSaveIndicator() {
        const indicator = document.createElement('div');
        indicator.id = 'autoSaveIndicator';
        indicator.className = 'auto-save-indicator';
        indicator.innerHTML = `
            <small class="text-muted">
                <i class="bi bi-cloud-check"></i>
                <span id="autoSaveStatus">Auto-save enabled</span>
            </small>
        `;

        // Add CSS
        if (!document.getElementById('auto-save-styles')) {
            const style = document.createElement('style');
            style.id = 'auto-save-styles';
            style.textContent = `
                .auto-save-indicator {
                    position: fixed;
                    bottom: 20px;
                    right: 20px;
                    background: white;
                    padding: 10px 15px;
                    border-radius: 5px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                    z-index: 1000;
                }
                .auto-save-indicator.saving {
                    background: #fff3cd;
                }
                .auto-save-indicator.saved {
                    background: #d1e7dd;
                }
                .auto-save-indicator.error {
                    background: #f8d7da;
                }
            `;
            document.head.appendChild(style);
        }

        document.body.appendChild(indicator);
    }

    /**
     * Reset auto-save timer
     */
    resetAutoSaveTimer() {
        if (this.autoSaveTimer) {
            clearTimeout(this.autoSaveTimer);
        }

        this.autoSaveTimer = setTimeout(() => {
            this.performAutoSave();
        }, this.options.autoSaveInterval);
    }

    /**
     * Perform auto-save
     */
    async performAutoSave() {
        const indicator = document.getElementById('autoSaveIndicator');
        const status = document.getElementById('autoSaveStatus');

        if (indicator) {
            indicator.className = 'auto-save-indicator saving';
            status.innerHTML = '<i class="bi bi-cloud-upload"></i> Saving...';
        }

        try {
            const formData = new FormData(this.form);
            const data = {};

            // Convert FormData to JSON
            for (const [key, value] of formData.entries()) {
                if (data[key]) {
                    // Handle multiple values (checkboxes, multi-select)
                    if (Array.isArray(data[key])) {
                        data[key].push(value);
                    } else {
                        data[key] = [data[key], value];
                    }
                } else {
                    data[key] = value;
                }
            }

            const response = await fetch(this.options.autoSaveEndpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                body: JSON.stringify(data)
            });

            if (response.ok) {
                if (indicator) {
                    indicator.className = 'auto-save-indicator saved';
                    status.innerHTML = '<i class="bi bi-cloud-check"></i> Saved';

                    // Reset to normal after 3 seconds
                    setTimeout(() => {
                        indicator.className = 'auto-save-indicator';
                        status.innerHTML = '<i class="bi bi-cloud-check"></i> Auto-save enabled';
                    }, 3000);
                }
            } else {
                throw new Error('Save failed');
            }
        } catch (error) {
            console.error('Auto-save error:', error);
            if (indicator) {
                indicator.className = 'auto-save-indicator error';
                status.innerHTML = '<i class="bi bi-exclamation-triangle"></i> Save failed';
            }
        }

        // Reset timer for next auto-save
        this.resetAutoSaveTimer();
    }

    /**
     * Show validation alert message
     */
    showValidationAlert(message) {
        // Remove any existing alert
        const existingAlert = this.form.querySelector('.validation-alert');
        if (existingAlert) {
            existingAlert.remove();
        }

        // Create alert element
        const alert = document.createElement('div');
        alert.className = 'alert alert-danger validation-alert d-flex align-items-center';
        alert.setAttribute('role', 'alert');
        alert.innerHTML = `
            <i class="bi bi-exclamation-triangle-fill me-2"></i>
            <div>${message}</div>
        `;

        // Insert at the top of the form
        this.form.insertBefore(alert, this.form.firstChild);

        // Auto-remove after 5 seconds
        setTimeout(() => {
            alert.style.transition = 'opacity 0.3s';
            alert.style.opacity = '0';
            setTimeout(() => alert.remove(), 300);
        }, 5000);
    }

    /**
     * Get CSRF token from cookie or meta tag
     */
    getCSRFToken() {
        // Try to get from cookie
        const cookieValue = document.cookie
            .split('; ')
            .find(row => row.startsWith('csrftoken='))
            ?.split('=')[1];

        if (cookieValue) return cookieValue;

        // Try to get from meta tag
        const metaTag = document.querySelector('meta[name="csrf-token"]');
        if (metaTag) return metaTag.content;

        // Try to get from form input
        const input = this.form.querySelector('input[name="csrfmiddlewaretoken"]');
        if (input) return input.value;

        return '';
    }

    /**
     * Destroy the form enhancements (cleanup)
     */
    destroy() {
        // Clear timers
        if (this.autoSaveTimer) {
            clearTimeout(this.autoSaveTimer);
        }

        Object.values(this.validationTimers).forEach(timer => {
            clearTimeout(timer);
        });

        // Remove auto-save indicator
        const indicator = document.getElementById('autoSaveIndicator');
        if (indicator) {
            indicator.remove();
        }
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = FormEnhancements;
}

