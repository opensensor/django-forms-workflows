(function () {
    "use strict";

    function getWorkflowSelectFor(stageSelect) {
        // Standalone admin: same form has <select name="workflow">.
        // Inline rows under FormDefinitionAdmin (nested via WorkflowDefinitionInline)
        // have <select name="workflows-N-...-workflow"> on the enclosing inline group.
        // Try same row first, then nearest fieldset, then form.
        var row = stageSelect.closest(".form-row, fieldset.module, .inline-related, form");
        while (row) {
            var direct = row.querySelector(
                'select[name="workflow"], select[name$="-workflow"]'
            );
            if (direct && direct !== stageSelect) {
                return direct;
            }
            if (row.tagName === "FORM") {
                break;
            }
            row = row.parentElement
                ? row.parentElement.closest(".form-row, fieldset.module, .inline-related, form")
                : null;
        }
        return null;
    }

    function applyFilter(stageSelect, workflowId) {
        var options = stageSelect.querySelectorAll("option");
        var wf = workflowId ? String(workflowId) : "";
        options.forEach(function (opt) {
            if (!opt.value) {
                opt.hidden = false;
                opt.disabled = false;
                return;
            }
            var optWf = opt.getAttribute("data-workflow-id");
            // Options without a data-workflow-id are shown unconditionally
            // (defensive: shouldn't happen for stage options).
            var matches = !wf || !optWf || optWf === wf;
            opt.hidden = !matches;
            opt.disabled = !matches;
        });
        // If the currently-selected stage no longer matches, clear it so the
        // user notices and re-picks a stage from the chosen workflow.
        if (wf && stageSelect.value) {
            var current = stageSelect.querySelector(
                'option[value="' + stageSelect.value + '"]'
            );
            if (current && current.hidden) {
                stageSelect.value = "";
                stageSelect.dispatchEvent(new Event("change", { bubbles: true }));
            }
        }
    }

    function hookStageSelect(stageSelect) {
        if (stageSelect.dataset.workflowFilterHooked === "1") {
            return;
        }
        stageSelect.dataset.workflowFilterHooked = "1";

        var workflowSelect = getWorkflowSelectFor(stageSelect);
        if (!workflowSelect) {
            // No workflow select on the form (e.g. inlines under
            // WorkflowDefinitionAdmin where the parent IS the workflow):
            // server-side filtering handles that case.
            return;
        }

        function refresh() {
            applyFilter(stageSelect, workflowSelect.value);
        }

        workflowSelect.addEventListener("change", refresh);
        refresh();
    }

    function scan(root) {
        (root || document)
            .querySelectorAll('select[name="stage"], select[name$="-stage"]')
            .forEach(hookStageSelect);
    }

    document.addEventListener("DOMContentLoaded", function () {
        scan(document);

        // Django's inline JS dispatches "formset:added" on the row that was
        // just added. Re-scan within that row so newly-added inline rules
        // get hooked up.
        document.addEventListener("formset:added", function (event) {
            var target = event.target || (event.detail && event.detail.formsetName);
            if (target && target.querySelectorAll) {
                scan(target);
            } else {
                scan(document);
            }
        });
    });
})();
