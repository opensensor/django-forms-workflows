/**
 * Undo/redo history for the Form Builder.
 *
 * Mixed onto FormBuilder.prototype in form-builder.js (Object.assign), not a
 * standalone class of its own — these methods operate on `this.store`
 * (snapshot/restore) plus `this.undoStack`/`this.redoStack`/
 * `this.maxUndoSteps`, and call back into
 * renderCanvas()/renderStepTabs()/updatePreview(), which still live on the
 * single FormBuilder instance.
 */
export const historyMethods = {
    pushUndo() {
        this.undoStack.push(this.store.snapshot());
        if (this.undoStack.length > this.maxUndoSteps) {
            this.undoStack.shift();
        }
        this.redoStack = [];
    },

    restoreHistoryState(snapshot) {
        this.store.restore(snapshot);

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
        this.redoStack.push(this.store.snapshot());
        this.restoreHistoryState(this.undoStack.pop());
    },

    redo() {
        if (this.redoStack.length === 0) return;
        this.undoStack.push(this.store.snapshot());
        this.restoreHistoryState(this.redoStack.pop());
    },
};
