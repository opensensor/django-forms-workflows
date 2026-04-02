/**
 * DFW Forms — Admin settings page JS.
 */
(function () {
    'use strict';

    document.addEventListener('DOMContentLoaded', function () {
        var btn = document.getElementById('dfw-test-connection');
        var result = document.getElementById('dfw-test-result');
        if (!btn || !result) return;

        btn.addEventListener('click', function () {
            var input = document.getElementById('dfw_forms_server_url');
            var server = (input ? input.value : '').replace(/\/+$/, '');

            if (!server) {
                result.textContent = 'Please enter a server URL first.';
                result.className = 'error';
                return;
            }

            result.textContent = 'Testing...';
            result.className = '';
            btn.disabled = true;

            var testUrl = server + '/static/django_forms_workflows/js/dfw-embed.js';

            fetch(testUrl, { method: 'HEAD', mode: 'no-cors' })
                .then(function () {
                    // no-cors mode returns opaque response, so any non-error means reachable
                    result.textContent = 'Connection successful — server is reachable.';
                    result.className = 'success';
                })
                .catch(function () {
                    result.textContent = 'Could not reach the server. Check the URL and try again.';
                    result.className = 'error';
                })
                .finally(function () {
                    btn.disabled = false;
                });
        });
    });
})();
