/**
 * API client for the Form Builder: loading/saving the form definition,
 * generating the live preview, and the template picker.
 *
 * Mixed onto FormBuilder.prototype in form-builder.js (Object.assign), not a
 * standalone class of its own - these methods read/write a large number of
 * page DOM fields directly, plus `this.fields`/`this.formSteps`/`this.config`,
 * and call back into canvas-render methods (renderCanvas/renderStepTabs/
 * toggleMultiStepMode) that still live on the single FormBuilder instance.
 */
export const apiMethods = {
    updatePreview() {
        // Debounce preview updates to avoid too many API calls
        if (this.previewTimeout) {
            clearTimeout(this.previewTimeout);
        }

        this.previewTimeout = setTimeout(() => {
            this.generatePreview();
        }, 500); // Wait 500ms after last change
    },

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
    },

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

            // Load success page settings
            document.getElementById('formSuccessMessage').value = data.success_message || '';
            document.getElementById('formSuccessRedirectUrl').value = data.success_redirect_url || '';
            document.getElementById('formSuccessRedirectRules').value = data.success_redirect_rules ? JSON.stringify(data.success_redirect_rules) : '';

            // Load payment settings
            document.getElementById('formPaymentEnabled').checked = data.payment_enabled || false;
            if (data.payment_enabled) document.getElementById('paymentSettings').style.display = '';
            // Populate provider dropdown
            const providerSelect = document.getElementById('formPaymentProvider');
            providerSelect.innerHTML = '<option value="">-- Select --</option>';
            (this.config.paymentProviders || []).forEach(([val, label]) => {
                const opt = document.createElement('option');
                opt.value = val;
                opt.textContent = label;
                if (val === data.payment_provider) opt.selected = true;
                providerSelect.appendChild(opt);
            });
            document.getElementById('formPaymentAmountType').value = data.payment_amount_type || 'fixed';
            if (data.payment_fixed_amount) document.getElementById('formPaymentFixedAmount').value = data.payment_fixed_amount;
            if (data.payment_amount_field) document.getElementById('formPaymentAmountField').value = data.payment_amount_field;
            document.getElementById('formPaymentCurrency').value = data.payment_currency || 'usd';
            if (data.payment_description_template) document.getElementById('formPaymentDescription').value = data.payment_description_template;

            // Load submission controls
            if (data.close_date) document.getElementById('formCloseDate').value = data.close_date.slice(0, 16);
            if (data.max_submissions) document.getElementById('formMaxSubmissions').value = data.max_submissions;
            document.getElementById('formOnePerUser').checked = data.one_per_user || false;
            document.getElementById('formEnableCaptcha').checked = data.enable_captcha || false;
            document.getElementById('formEmbedEnabled').checked = data.embed_enabled || false;

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
    },

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
            success_message: document.getElementById('formSuccessMessage').value.trim(),
            success_redirect_url: document.getElementById('formSuccessRedirectUrl').value.trim(),
            success_redirect_rules: (() => { try { const v = document.getElementById('formSuccessRedirectRules').value.trim(); return v ? JSON.parse(v) : null; } catch(e) { return null; } })(),
            payment_enabled: document.getElementById('formPaymentEnabled').checked,
            payment_provider: document.getElementById('formPaymentProvider').value,
            payment_amount_type: document.getElementById('formPaymentAmountType').value,
            payment_fixed_amount: document.getElementById('formPaymentFixedAmount').value || null,
            payment_amount_field: document.getElementById('formPaymentAmountField').value,
            payment_currency: document.getElementById('formPaymentCurrency').value,
            payment_description_template: document.getElementById('formPaymentDescription').value,
            close_date: document.getElementById('formCloseDate').value || null,
            max_submissions: parseInt(document.getElementById('formMaxSubmissions').value) || null,
            one_per_user: document.getElementById('formOnePerUser').checked,
            enable_captcha: document.getElementById('formEnableCaptcha').checked,
            embed_enabled: document.getElementById('formEmbedEnabled').checked,
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
    },

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
    },

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
    },
};
