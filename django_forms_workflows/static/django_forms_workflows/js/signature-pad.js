/**
 * Signature Pad — lightweight canvas-based signature capture.
 *
 * For every <input type="hidden" data-signature-field="FIELD_NAME"> this
 * script injects a visible canvas, a "Clear" button, and optional label /
 * help text.  When the user draws on the canvas the base64 PNG data URI is
 * written back to the hidden input so it is submitted with the form.
 *
 * Usage:  include this script on any page that renders a form with
 *         signature fields.  It auto-initialises on DOMContentLoaded.
 */
(function () {
    'use strict';

    function initSignaturePad(hiddenInput) {
        var fieldName = hiddenInput.getAttribute('data-signature-field');
        if (!fieldName) return;

        // Avoid double-initialisation
        if (hiddenInput.dataset.signatureInitialised) return;
        hiddenInput.dataset.signatureInitialised = '1';

        // ── Build wrapper DOM ──────────────────────────────────────────────
        var wrapper = document.createElement('div');
        wrapper.className = 'signature-pad-wrapper mb-3';

        // Label (pulled from the hidden input's associated <label> if any)
        var existingLabel = document.querySelector('label[for="id_' + fieldName + '"]');
        if (!existingLabel) {
            // Crispy forms may not produce a label for hidden inputs, so we
            // look for one in the parent .mb-3 / .field-wrapper container.
            var parent = hiddenInput.closest('.field-wrapper, .mb-3');
            if (parent) existingLabel = parent.querySelector('label');
        }

        var label = document.createElement('label');
        label.className = 'form-label';
        label.textContent = existingLabel ? existingLabel.textContent : 'Signature';
        if (hiddenInput.required) {
            var asterisk = document.createElement('span');
            asterisk.className = 'text-danger';
            asterisk.textContent = ' *';
            label.appendChild(asterisk);
        }
        wrapper.appendChild(label);

        // Canvas container (gives the border / background)
        var canvasContainer = document.createElement('div');
        canvasContainer.className = 'signature-pad-canvas-container';
        wrapper.appendChild(canvasContainer);

        var canvas = document.createElement('canvas');
        canvas.width = 500;
        canvas.height = 160;
        canvas.className = 'signature-pad-canvas';
        canvasContainer.appendChild(canvas);

        // Buttons
        var btnBar = document.createElement('div');
        btnBar.className = 'signature-pad-buttons mt-1';
        var clearBtn = document.createElement('button');
        clearBtn.type = 'button';
        clearBtn.className = 'btn btn-sm btn-outline-secondary';
        clearBtn.innerHTML = '<i class="bi bi-eraser"></i> Clear';
        btnBar.appendChild(clearBtn);
        wrapper.appendChild(btnBar);

        // Help text
        var helpText = hiddenInput.getAttribute('data-help-text');
        if (helpText) {
            var helpEl = document.createElement('div');
            helpEl.className = 'form-text text-muted';
            helpEl.textContent = helpText;
            wrapper.appendChild(helpEl);
        }

        // Insert the wrapper right before the hidden input
        hiddenInput.parentNode.insertBefore(wrapper, hiddenInput);
        // Move the hidden input inside the wrapper so it stays grouped
        wrapper.appendChild(hiddenInput);
        // Hide the original label (if any) since we created our own
        if (existingLabel) existingLabel.style.display = 'none';

        // ── Drawing logic ──────────────────────────────────────────────────
        var ctx = canvas.getContext('2d');
        var drawing = false;
        var hasStrokes = false;

        function getPos(e) {
            var rect = canvas.getBoundingClientRect();
            var clientX, clientY;
            if (e.touches && e.touches.length) {
                clientX = e.touches[0].clientX;
                clientY = e.touches[0].clientY;
            } else {
                clientX = e.clientX;
                clientY = e.clientY;
            }
            return {
                x: (clientX - rect.left) * (canvas.width / rect.width),
                y: (clientY - rect.top) * (canvas.height / rect.height)
            };
        }

        function startDraw(e) {
            e.preventDefault();
            drawing = true;
            var pos = getPos(e);
            ctx.beginPath();
            ctx.moveTo(pos.x, pos.y);
        }

        function draw(e) {
            if (!drawing) return;
            e.preventDefault();
            var pos = getPos(e);
            ctx.lineWidth = 2;
            ctx.lineCap = 'round';
            ctx.lineJoin = 'round';
            ctx.strokeStyle = '#000';
            ctx.lineTo(pos.x, pos.y);
            ctx.stroke();
            hasStrokes = true;
        }

        function endDraw(e) {
            if (!drawing) return;
            e.preventDefault();
            drawing = false;
            ctx.closePath();
            // Write the data URI into the hidden input
            if (hasStrokes) {
                hiddenInput.value = canvas.toDataURL('image/png');
            }
        }

        // Mouse events
        canvas.addEventListener('mousedown', startDraw);
        canvas.addEventListener('mousemove', draw);
        canvas.addEventListener('mouseup', endDraw);
        canvas.addEventListener('mouseleave', endDraw);
        // Touch events (mobile)
        canvas.addEventListener('touchstart', startDraw, { passive: false });
        canvas.addEventListener('touchmove', draw, { passive: false });
        canvas.addEventListener('touchend', endDraw);
        canvas.addEventListener('touchcancel', endDraw);

        // Clear button
        clearBtn.addEventListener('click', function () {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            hiddenInput.value = '';
            hasStrokes = false;
        });
    }

    // ── Auto-init on load ──────────────────────────────────────────────────
    function initAll() {
        document.querySelectorAll('input[data-signature-field]').forEach(initSignaturePad);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initAll);
    } else {
        initAll();
    }
})();

