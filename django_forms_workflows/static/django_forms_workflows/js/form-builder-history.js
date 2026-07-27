/**
 * Undo/redo history for the Form Builder.
 *
 * Mixed onto FormBuilder.prototype in form-builder.js (Object.assign), not a
 * standalone class of its own — these methods operate on `this.fields`/
 * `this.formSteps`/`this.undoStack`/`this.redoStack`/`this.maxUndoSteps`,
 * and call back into renderCanvas()/renderStepTabs()/updatePreview(), which
 * still live on the single FormBuilder instance.
 */
export const historyMethods = {
    pushUndo() {
        this.undoStack.push(this.snapshotHistoryState());
        if (this.undoStack.length > this.maxUndoSteps) {
            this.undoStack.shift();
        }
        this.redoStack = [];
    },

    // Snapshotting `fields` alone isn't enough: multi-step assignment
    // (`formSteps`) is keyed by field_name, so restoring `fields` without it
    // can leave a step referencing a field that no longer exists (or lose
    // the multi-step layout entirely) after an undo/redo.
    snapshotHistoryState() {
        return JSON.stringify({ fields: this.fields, formSteps: this.formSteps });
    },

    restoreHistoryState(snapshot) {
        const { fields, formSteps } = JSON.parse(snapshot);
        this.fields = fields;
        this.formSteps = formSteps;

        // Undo/redo previously always called renderCanvas(), even in
        // multi-step mode - restoring formSteps is pointless if the
        // re-render doesn't reflect it.
        const isMultiStep = document.getElementById('formEnableMultiStep')?.checked;
        if (isMultiStep) {
            this.renderStepTabs();
        } else {
            this.renderCanvas();
        }
        this.updatePreview();
    },

    undo() {
        if (this.undoStack.length === 0) return;
        this.redoStack.push(this.snapshotHistoryState());
        this.restoreHistoryState(this.undoStack.pop());
    },

    redo() {
        if (this.redoStack.length === 0) return;
        this.undoStack.push(this.snapshotHistoryState());
        this.restoreHistoryState(this.redoStack.pop());
    },
};
