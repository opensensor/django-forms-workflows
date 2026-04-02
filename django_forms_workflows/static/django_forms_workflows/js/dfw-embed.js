/**
 * Django Forms Workflows — Embeddable Form Loader
 *
 * Drop this script tag on any webpage to embed a form:
 *
 *   <script src="https://server/static/django_forms_workflows/js/dfw-embed.js"
 *     data-form="contact-us"
 *     data-server="https://server"
 *   ></script>
 *
 * Attributes:
 *   data-form       (required) Form slug
 *   data-server     (required) Base URL of the DFW server
 *   data-target     CSS selector of container (default: insert after script tag)
 *   data-on-submit  Global function name called on successful submission
 *   data-on-load    Global function name called when form has loaded
 *   data-theme      "light" (default) or "dark"
 *   data-accent-color  Hex color for primary buttons (e.g., "#ff6600")
 *   data-min-height Minimum iframe height in px (default: 300)
 *   data-loading-text  Text shown while loading (default: "Loading form...")
 */
(function () {
    'use strict';

    // Find our own script tag
    var script = document.currentScript;
    if (!script) {
        // Fallback for older browsers
        var scripts = document.getElementsByTagName('script');
        script = scripts[scripts.length - 1];
    }

    var formSlug = script.getAttribute('data-form');
    var server = script.getAttribute('data-server');

    if (!formSlug || !server) {
        console.error('[dfw-embed] data-form and data-server attributes are required.');
        return;
    }

    // Read optional attributes
    var targetSelector = script.getAttribute('data-target');
    var onSubmitFn = script.getAttribute('data-on-submit');
    var onLoadFn = script.getAttribute('data-on-load');
    var theme = script.getAttribute('data-theme') || '';
    var accentColor = script.getAttribute('data-accent-color') || '';
    var minHeight = parseInt(script.getAttribute('data-min-height')) || 300;
    var loadingText = script.getAttribute('data-loading-text') || 'Loading form...';

    // Validate server is a proper HTTP(S) URL to prevent script injection
    var sanitisedServer;
    try {
        var parsedServer = new URL(server);
        if (parsedServer.protocol !== 'https:' && parsedServer.protocol !== 'http:') {
            console.error('[dfw-embed] data-server must be an http(s) URL');
            return;
        }
        sanitisedServer = parsedServer.origin;
    } catch (e) {
        console.error('[dfw-embed] Invalid data-server URL:', e.message);
        return;
    }

    // Build embed URL using validated origin
    var embedUrl = sanitisedServer + '/forms/' + encodeURIComponent(formSlug) + '/embed/';
    var params = [];
    if (theme) params.push('theme=' + encodeURIComponent(theme));
    if (accentColor) params.push('accent_color=' + encodeURIComponent(accentColor));
    if (params.length) embedUrl += '?' + params.join('&');

    // Create container
    var container = document.createElement('div');
    container.className = 'dfw-embed-container';
    container.style.cssText = 'width:100%;position:relative;';

    // Loading indicator
    var loading = document.createElement('div');
    loading.textContent = loadingText;
    loading.style.cssText = 'text-align:center;padding:2rem;color:#6c757d;font-family:sans-serif;font-size:0.9rem;';
    container.appendChild(loading);

    // Create iframe
    var iframe = document.createElement('iframe');
    iframe.src = embedUrl;
    iframe.style.cssText = 'width:100%;border:none;overflow:hidden;display:none;min-height:' + minHeight + 'px;';
    iframe.setAttribute('scrolling', 'no');
    iframe.setAttribute('allowtransparency', 'true');
    iframe.setAttribute('title', 'Form: ' + formSlug);
    container.appendChild(iframe);

    // Insert into DOM
    if (targetSelector) {
        var target = document.querySelector(targetSelector);
        if (target) {
            target.appendChild(container);
        } else {
            console.error('[dfw-embed] Target element not found:', targetSelector);
            script.parentNode.insertBefore(container, script.nextSibling);
        }
    } else {
        script.parentNode.insertBefore(container, script.nextSibling);
    }

    // Use the already-validated origin for message validation
    var serverOrigin = sanitisedServer;

    // Listen for postMessage events from the iframe
    window.addEventListener('message', function (event) {
        // Validate origin
        if (event.origin !== serverOrigin) return;

        var data = event.data;
        if (!data || !data.type || data.formSlug !== formSlug) return;

        switch (data.type) {
            case 'dfw:loaded':
                loading.style.display = 'none';
                iframe.style.display = 'block';
                if (onLoadFn && typeof window[onLoadFn] === 'function') {
                    window[onLoadFn](data);
                }
                break;

            case 'dfw:resize':
                if (data.height) {
                    iframe.style.height = Math.max(data.height + 20, minHeight) + 'px';
                }
                break;

            case 'dfw:submitted':
                if (onSubmitFn && typeof window[onSubmitFn] === 'function') {
                    window[onSubmitFn](data);
                }
                break;
        }
    });
})();
