/**
 * Undo/redo history for the Form Builder.
 *
 * Mixed onto FormBuilder.prototype in form-builder.js (Object.assign), not a
 * standalone class of its own — these methods operate on `this.fields`/
 * `this.undoStack`/`this.redoStack`/`this.maxUndoSteps`, which still live on
 * the single FormBuilder instance.
 */
export const historyMethods = {
    pushUndo() {
        this.undoStack.push(JSON.stringify(this.fields));
        if (this.undoStack.length > this.maxUndoSteps) {
            this.undoStack.shift();
        }
        this.redoStack = [];
    },

    undo() {
        if (this.undoStack.length === 0) return;
        this.redoStack.push(JSON.stringify(this.fields));
        this.fields = JSON.parse(this.undoStack.pop());
        this.renderCanvas();
        this.updatePreview();
    },

    redo() {
        if (this.redoStack.length === 0) return;
        this.undoStack.push(JSON.stringify(this.fields));
        this.fields = JSON.parse(this.redoStack.pop());
        this.renderCanvas();
        this.updatePreview();
    },
};
