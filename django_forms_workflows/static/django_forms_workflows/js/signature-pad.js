/**
 * Signature Pad — lightweight, responsive canvas-based signature capture.
 *
 * For every <input type="hidden" data-signature-field="FIELD_NAME"> this
 * script injects a visible canvas, a "Clear" button, and optional label /
 * help text.  When the user draws on the canvas the base64 PNG data URI is
 * written back to the hidden input so it is submitted with the form.
 *
 * The canvas fills 100% of its container width and uses a 2× backing store
 * on high-DPI screens for crisp signatures.
 *
 * Usage:  include this script on any page that renders a form with
 *         signature fields.  It auto-initialises on DOMContentLoaded.
 */
(function () {
    'use strict';

    // Logical (CSS) height of the signing area — the canvas will always be
    // as wide as its container and this many CSS-pixels tall.
    var CANVAS_CSS_HEIGHT = 140;

    function initSignaturePad(hiddenInput) {
        var fieldName = hiddenInput.getAttribute('data-signature-field');
        if (!fieldName) return;

        // Avoid double-initialisation
        if (hiddenInput.dataset.signatureInitialised) return;
        hiddenInput.dataset.signatureInitialised = '1';

        // ── Build wrapper DOM ──────────────────────────────────────────────
        var wrapper = document.createElement('div');
        wrapper.className = 'signature-pad-wrapper mb-3';

        // Label — reuse the existing <label> created by crispy-forms
        var existingLabel = document.querySelector('label[for="id_' + fieldName + '"]');
        if (!existingLabel) {
            var parent = hiddenInput.closest('.field-wrapper, .mb-3');
            if (parent) existingLabel = parent.querySelector('label');
        }

        var label = document.createElement('label');
        label.className = 'form-label';
        label.textContent = existingLabel ? existingLabel.textContent : 'Signature';
        if (hiddenInput.required) {
            var asterisk = document.createElement('span');
            asterisk.className = 'asteriskField';
            asterisk.textContent = ' *';
            label.appendChild(asterisk);
        }
        wrapper.appendChild(label);

        // Canvas container — will stretch to 100% of wrapper width via CSS
        var canvasContainer = document.createElement('div');
        canvasContainer.className = 'signature-pad-canvas-container';
        wrapper.appendChild(canvasContainer);

        var canvas = document.createElement('canvas');
        canvas.className = 'signature-pad-canvas';
        canvasContainer.appendChild(canvas);

        // Buttons
        var btnBar = document.createElement('div');
        btnBar.className = 'signature-pad-buttons';
        var clearBtn = document.createElement('button');
        clearBtn.type = 'button';
        clearBtn.className = 'btn btn-sm btn-outline-secondary';
        clearBtn.innerHTML = '<i class="bi bi-eraser"></i> Clear';
        btnBar.appendChild(clearBtn);
        wrapper.appendChild(btnBar);

        // Help text (from the form field's help_text)
        var helpText = hiddenInput.getAttribute('data-help-text');
        if (helpText) {
            var helpEl = document.createElement('div');
            helpEl.className = 'signature-pad-help';
            helpEl.textContent = helpText;
            wrapper.appendChild(helpEl);
        }

        // Insert the wrapper where the hidden input is, then nest the
        // hidden input inside so it stays grouped.
        hiddenInput.parentNode.insertBefore(wrapper, hiddenInput);
        wrapper.appendChild(hiddenInput);
        if (existingLabel) existingLabel.style.display = 'none';

        // ── Responsive canvas sizing ───────────────────────────────────────
        var ctx = canvas.getContext('2d');
        var dpr = window.devicePixelRatio || 1;

        function sizeCanvas() {
            var containerWidth = canvasContainer.clientWidth || 300;
            // Set the backing-store size (physical pixels)
            canvas.width  = containerWidth * dpr;
            canvas.height = CANVAS_CSS_HEIGHT * dpr;
            // Keep CSS size matched to container
            canvas.style.width  = '100%';
            canvas.style.height = CANVAS_CSS_HEIGHT + 'px';
            // Scale context so drawing coordinates match CSS pixels
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        }
        sizeCanvas();

        // Re-size on window resize (debounced)
        var resizeTimer;
        window.addEventListener('resize', function () {
            clearTimeout(resizeTimer);
            resizeTimer = setTimeout(function () {
                // Preserve current drawing
                var imageData = canvas.toDataURL('image/png');
                sizeCanvas();
                if (hasStrokes) {
                    var img = new Image();
                    img.onload = function () {
                        ctx.drawImage(img, 0, 0, canvasContainer.clientWidth, CANVAS_CSS_HEIGHT);
                    };
                    img.src = imageData;
                }
            }, 150);
        });

        // ── Drawing logic ──────────────────────────────────────────────────
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
                x: (clientX - rect.left) * (canvas.width / dpr / rect.width),
                y: (clientY - rect.top)  * (canvas.height / dpr / rect.height)
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
            ctx.clearRect(0, 0, canvas.width / dpr, canvas.height / dpr);
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

