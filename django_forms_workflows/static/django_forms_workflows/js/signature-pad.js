/**
 * Signature Pad — lightweight, responsive canvas-based signature capture
 * with Draw and Type modes.
 *
 * For every <input type="hidden" data-signature-field="FIELD_NAME"> this
 * script injects a visible canvas with a Draw / Type toggle, a "Clear"
 * button, and optional label / help text.
 *
 * **Draw mode** — freehand drawing on an HTML canvas.
 * **Type mode** — type a name and choose from several handwriting-style
 *   fonts; the text is rendered onto the canvas so the stored value is
 *   always a base64 PNG data URI regardless of input method.
 *
 * The canvas fills 100 % of its container width and uses a 2× backing
 * store on high-DPI screens for crisp output.
 *
 * Usage:  include this script on any page that renders a form with
 *         signature fields.  It auto-initialises on DOMContentLoaded.
 */
(function () {
    'use strict';

    var CANVAS_CSS_HEIGHT = 140;

    // ── Typed-signature font families ──────────────────────────────────
    // We load cursive / handwriting Google Fonts dynamically the first
    // time a signature field is initialised.
    var FONTS = [
        { family: 'Dancing Script',   label: 'Elegant' },
        { family: 'Great Vibes',      label: 'Formal' },
        { family: 'Caveat',           label: 'Casual' },
        { family: 'Sacramento',       label: 'Classic' },
    ];
    var fontsLoaded = false;

    function loadGoogleFonts() {
        if (fontsLoaded) return;
        fontsLoaded = true;
        var families = FONTS.map(function (f) {
            return f.family.replace(/ /g, '+');
        }).join('&family=');
        var link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = 'https://fonts.googleapis.com/css2?family=' + families + '&display=swap';
        document.head.appendChild(link);
    }

    // ── Helpers ────────────────────────────────────────────────────────
    function el(tag, cls, attrs) {
        var e = document.createElement(tag);
        if (cls) e.className = cls;
        if (attrs) Object.keys(attrs).forEach(function (k) { e.setAttribute(k, attrs[k]); });
        return e;
    }

    function initSignaturePad(hiddenInput) {
        var fieldName = hiddenInput.getAttribute('data-signature-field');
        if (!fieldName) return;
        if (hiddenInput.dataset.signatureInitialised) return;
        hiddenInput.dataset.signatureInitialised = '1';

        loadGoogleFonts();

        // ── State ──────────────────────────────────────────────────────────
        var mode = 'draw';          // 'draw' | 'type'
        var drawing = false;
        var hasStrokes = false;
        var currentFont = FONTS[0].family;
        var typedName = '';

        // ── Build wrapper DOM ──────────────────────────────────────────────
        var wrapper = el('div', 'signature-pad-wrapper mb-3');

        // Label
        var existingLabel = document.querySelector('label[for="id_' + fieldName + '"]');
        if (!existingLabel) {
            var parentEl = hiddenInput.closest('.field-wrapper, .mb-3');
            if (parentEl) existingLabel = parentEl.querySelector('label');
        }
        var label = el('label', 'form-label');
        label.textContent = existingLabel ? existingLabel.textContent : 'Signature';
        if (hiddenInput.required) {
            var asterisk = el('span', 'asteriskField');
            asterisk.textContent = ' *';
            label.appendChild(asterisk);
        }
        wrapper.appendChild(label);

        // ── Draw / Type toggle ─────────────────────────────────────────────
        var modeBar = el('div', 'signature-mode-toggle btn-group btn-group-sm mb-2');
        modeBar.setAttribute('role', 'group');

        var drawBtn = el('button', 'btn btn-outline-primary active');
        drawBtn.type = 'button';
        drawBtn.innerHTML = '<i class="bi bi-pencil"></i> Draw';
        modeBar.appendChild(drawBtn);

        var typeBtn = el('button', 'btn btn-outline-primary');
        typeBtn.type = 'button';
        typeBtn.innerHTML = '<i class="bi bi-keyboard"></i> Type';
        modeBar.appendChild(typeBtn);
        wrapper.appendChild(modeBar);

        // ── Canvas (shared by both modes) ──────────────────────────────────
        var canvasContainer = el('div', 'signature-pad-canvas-container');
        // Inline styles as reinforcement for border visibility
        canvasContainer.style.border = '2px solid #6c757d';
        canvasContainer.style.borderRadius = '0.5rem';
        canvasContainer.style.background = '#fafbfc';
        canvasContainer.style.cursor = 'crosshair';
        canvasContainer.style.touchAction = 'none';
        canvasContainer.style.display = 'block';
        canvasContainer.style.width = '100%';
        wrapper.appendChild(canvasContainer);

        var canvas = el('canvas', 'signature-pad-canvas');
        canvasContainer.appendChild(canvas);

        // ── Type-mode controls (hidden initially) ──────────────────────────
        var typeControls = el('div', 'signature-type-controls');
        typeControls.style.display = 'none';

        var nameInput = el('input', 'form-control form-control-sm mb-2', {
            type: 'text',
            placeholder: 'Type your full name\u2026',
            autocomplete: 'off',
        });
        typeControls.appendChild(nameInput);

        var fontRow = el('div', 'signature-font-options d-flex flex-wrap gap-2');
        FONTS.forEach(function (f, idx) {
            var fontBtn = el('button', 'btn btn-sm ' + (idx === 0 ? 'btn-primary' : 'btn-outline-secondary') + ' signature-font-btn');
            fontBtn.type = 'button';
            fontBtn.style.fontFamily = "'" + f.family + "', cursive";
            fontBtn.style.fontSize = '1.1rem';
            fontBtn.textContent = f.label;
            fontBtn.dataset.font = f.family;
            fontRow.appendChild(fontBtn);
        });
        typeControls.appendChild(fontRow);
        wrapper.appendChild(typeControls);

        // ── Buttons bar ────────────────────────────────────────────────────
        var btnBar = el('div', 'signature-pad-buttons');
        var clearBtn = el('button', 'btn btn-sm btn-outline-secondary');
        clearBtn.type = 'button';
        clearBtn.innerHTML = '<i class="bi bi-eraser"></i> Clear';
        btnBar.appendChild(clearBtn);
        wrapper.appendChild(btnBar);

        // Help text
        var helpText = hiddenInput.getAttribute('data-help-text');
        if (helpText) {
            var helpEl = el('div', 'signature-pad-help');
            helpEl.textContent = helpText;
            wrapper.appendChild(helpEl);
        }

        // Insert wrapper
        hiddenInput.parentNode.insertBefore(wrapper, hiddenInput);
        wrapper.appendChild(hiddenInput);
        if (existingLabel) existingLabel.style.display = 'none';

        // ── Canvas sizing ──────────────────────────────────────────────────
        var ctx = canvas.getContext('2d');
        var dpr = window.devicePixelRatio || 1;

        function sizeCanvas() {
            var w = canvasContainer.clientWidth || 300;
            canvas.width  = w * dpr;
            canvas.height = CANVAS_CSS_HEIGHT * dpr;
            canvas.style.width  = '100%';
            canvas.style.height = CANVAS_CSS_HEIGHT + 'px';
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        }
        sizeCanvas();

        var resizeTimer;
        window.addEventListener('resize', function () {
            clearTimeout(resizeTimer);
            resizeTimer = setTimeout(function () {
                var imageData = canvas.toDataURL('image/png');
                sizeCanvas();
                if (mode === 'type' && typedName) {
                    renderTypedSignature();
                } else if (hasStrokes) {
                    var img = new Image();
                    img.onload = function () {
                        ctx.drawImage(img, 0, 0, canvasContainer.clientWidth, CANVAS_CSS_HEIGHT);
                    };
                    img.src = imageData;
                }
            }, 150);
        });

        // ── Drawing logic (Draw mode) ──────────────────────────────────────
        function getPos(e) {
            var rect = canvas.getBoundingClientRect();
            var cx, cy;
            if (e.touches && e.touches.length) {
                cx = e.touches[0].clientX;
                cy = e.touches[0].clientY;
            } else {
                cx = e.clientX;
                cy = e.clientY;
            }
            return {
                x: (cx - rect.left) * (canvas.width / dpr / rect.width),
                y: (cy - rect.top)  * (canvas.height / dpr / rect.height)
            };
        }

        function startDraw(e) {
            if (mode !== 'draw') return;
            e.preventDefault();
            drawing = true;
            var pos = getPos(e);
            ctx.beginPath();
            ctx.moveTo(pos.x, pos.y);
        }
        function draw(e) {
            if (!drawing || mode !== 'draw') return;
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
            if (hasStrokes) hiddenInput.value = canvas.toDataURL('image/png');
        }

        canvas.addEventListener('mousedown', startDraw);
        canvas.addEventListener('mousemove', draw);
        canvas.addEventListener('mouseup', endDraw);
        canvas.addEventListener('mouseleave', endDraw);
        canvas.addEventListener('touchstart', startDraw, { passive: false });
        canvas.addEventListener('touchmove', draw, { passive: false });
        canvas.addEventListener('touchend', endDraw);
        canvas.addEventListener('touchcancel', endDraw);

        // ── Typed-signature rendering ──────────────────────────────────────
        function renderTypedSignature() {
            var w = canvasContainer.clientWidth || 300;
            ctx.clearRect(0, 0, w, CANVAS_CSS_HEIGHT);
            if (!typedName) {
                hiddenInput.value = '';
                return;
            }
            // Size text to fit — start large and shrink if needed
            var fontSize = 48;
            var minFontSize = 20;
            ctx.font = fontSize + 'px "' + currentFont + '", cursive';
            while (ctx.measureText(typedName).width > w * 0.88 && fontSize > minFontSize) {
                fontSize -= 2;
                ctx.font = fontSize + 'px "' + currentFont + '", cursive';
            }
            ctx.fillStyle = '#000';
            ctx.textBaseline = 'middle';
            ctx.textAlign = 'center';
            ctx.fillText(typedName, w / 2, CANVAS_CSS_HEIGHT / 2);
            hiddenInput.value = canvas.toDataURL('image/png');
        }

        // ── Mode switching ─────────────────────────────────────────────────
        function setMode(newMode) {
            mode = newMode;
            drawBtn.classList.toggle('active', mode === 'draw');
            drawBtn.classList.toggle('btn-primary', mode === 'draw');
            drawBtn.classList.toggle('btn-outline-primary', mode !== 'draw');
            typeBtn.classList.toggle('active', mode === 'type');
            typeBtn.classList.toggle('btn-primary', mode === 'type');
            typeBtn.classList.toggle('btn-outline-primary', mode !== 'type');
            typeControls.style.display = mode === 'type' ? 'block' : 'none';
            canvasContainer.style.cursor = mode === 'draw' ? 'crosshair' : 'default';
            clearSignature();
            if (mode === 'type') nameInput.focus();
        }

        drawBtn.addEventListener('click', function () { setMode('draw'); });
        typeBtn.addEventListener('click', function () { setMode('type'); });

        // Font selection
        fontRow.addEventListener('click', function (e) {
            var btn = e.target.closest('.signature-font-btn');
            if (!btn) return;
            currentFont = btn.dataset.font;
            fontRow.querySelectorAll('.signature-font-btn').forEach(function (b) {
                b.classList.remove('btn-primary');
                b.classList.add('btn-outline-secondary');
            });
            btn.classList.remove('btn-outline-secondary');
            btn.classList.add('btn-primary');
            if (typedName) renderTypedSignature();
        });

        // Re-render as user types
        nameInput.addEventListener('input', function () {
            typedName = nameInput.value.trim();
            renderTypedSignature();
        });

        // ── Clear ──────────────────────────────────────────────────────────
        function clearSignature() {
            var w = canvasContainer.clientWidth || 300;
            ctx.clearRect(0, 0, w, CANVAS_CSS_HEIGHT);
            hiddenInput.value = '';
            hasStrokes = false;
            typedName = '';
            nameInput.value = '';
        }

        clearBtn.addEventListener('click', clearSignature);
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