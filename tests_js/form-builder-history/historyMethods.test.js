import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { historyMethods } from '../../django_forms_workflows/static/django_forms_workflows/js/form-builder-history.js';
import { createBuilderStore } from '../../django_forms_workflows/static/django_forms_workflows/js/form-builder-store.js';

function createContext(fields = [], formSteps = []) {
  return {
    store: createBuilderStore({ fields, formSteps }),
    undoStack: [],
    redoStack: [],
    maxUndoSteps: 50,
    renderCanvas: vi.fn(),
    renderStepTabs: vi.fn(),
    updatePreview: vi.fn(),
    ...historyMethods,
  };
}

function setMultiStep(checked) {
  document.body.innerHTML = `<input type="checkbox" id="formEnableMultiStep" ${checked ? 'checked' : ''}>`;
}

beforeEach(() => {
  setMultiStep(false);
});

afterEach(() => {
  document.body.innerHTML = '';
});

describe('historyMethods.pushUndo', () => {
  it('snapshots the store onto the undo stack and clears redo', () => {
    const ctx = createContext([{ field_name: 'a' }], [{ label: 'Step 1', fields: ['a'] }]);
    ctx.redoStack.push('stale-redo-snapshot');

    ctx.pushUndo();

    expect(ctx.undoStack).toEqual([ctx.store.snapshot()]);
    expect(ctx.redoStack).toEqual([]);
  });

  it('drops the oldest snapshot once maxUndoSteps is exceeded', () => {
    const ctx = createContext([]);
    ctx.maxUndoSteps = 2;
    ctx.undoStack = ['oldest', 'middle'];

    ctx.pushUndo();

    expect(ctx.undoStack).toEqual(['middle', ctx.store.snapshot()]);
  });
});

describe('historyMethods.undo', () => {
  it('does nothing when there is no undo history', () => {
    const ctx = createContext([{ field_name: 'current' }]);

    ctx.undo();

    expect(ctx.store.fields).toEqual([{ field_name: 'current' }]);
    expect(ctx.renderCanvas).not.toHaveBeenCalled();
    expect(ctx.renderStepTabs).not.toHaveBeenCalled();
    expect(ctx.updatePreview).not.toHaveBeenCalled();
  });

  it('restores the previous fields and formSteps snapshot and pushes the current one onto redo', () => {
    const ctx = createContext(
      [{ field_name: 'current' }],
      [{ label: 'Step 1', fields: ['current'] }]
    );
    const currentSnapshot = ctx.store.snapshot();
    ctx.undoStack = [
      JSON.stringify({ fields: [{ field_name: 'previous' }], formSteps: [] }),
    ];

    ctx.undo();

    expect(ctx.store.fields).toEqual([{ field_name: 'previous' }]);
    expect(ctx.store.formSteps).toEqual([]);
    expect(ctx.redoStack).toEqual([currentSnapshot]);
    expect(ctx.undoStack).toEqual([]);
    expect(ctx.renderCanvas).toHaveBeenCalledTimes(1);
    expect(ctx.renderStepTabs).not.toHaveBeenCalled();
    expect(ctx.updatePreview).toHaveBeenCalledTimes(1);
  });

  it('re-renders the step tabs instead of the single-step canvas when multi-step mode is on', () => {
    setMultiStep(true);
    const ctx = createContext([{ field_name: 'current' }], [{ label: 'Step 1', fields: [] }]);
    ctx.undoStack = [
      JSON.stringify({ fields: [{ field_name: 'previous' }], formSteps: [{ label: 'Step 1', fields: ['previous'] }] }),
    ];

    ctx.undo();

    expect(ctx.store.formSteps).toEqual([{ label: 'Step 1', fields: ['previous'] }]);
    expect(ctx.renderStepTabs).toHaveBeenCalledTimes(1);
    expect(ctx.renderCanvas).not.toHaveBeenCalled();
  });
});

describe('historyMethods.redo', () => {
  it('does nothing when there is no redo history', () => {
    const ctx = createContext([{ field_name: 'current' }]);

    ctx.redo();

    expect(ctx.store.fields).toEqual([{ field_name: 'current' }]);
    expect(ctx.renderCanvas).not.toHaveBeenCalled();
    expect(ctx.renderStepTabs).not.toHaveBeenCalled();
    expect(ctx.updatePreview).not.toHaveBeenCalled();
  });

  it('restores the next fields and formSteps snapshot and pushes the current one onto undo', () => {
    const ctx = createContext([{ field_name: 'current' }], []);
    const currentSnapshot = ctx.store.snapshot();
    ctx.redoStack = [
      JSON.stringify({ fields: [{ field_name: 'next' }], formSteps: [{ label: 'Step 1', fields: ['next'] }] }),
    ];

    ctx.redo();

    expect(ctx.store.fields).toEqual([{ field_name: 'next' }]);
    expect(ctx.store.formSteps).toEqual([{ label: 'Step 1', fields: ['next'] }]);
    expect(ctx.undoStack).toEqual([currentSnapshot]);
    expect(ctx.redoStack).toEqual([]);
    expect(ctx.renderCanvas).toHaveBeenCalledTimes(1);
    expect(ctx.updatePreview).toHaveBeenCalledTimes(1);
  });

  it('re-renders the step tabs instead of the single-step canvas when multi-step mode is on', () => {
    setMultiStep(true);
    const ctx = createContext([{ field_name: 'current' }], []);
    ctx.redoStack = [
      JSON.stringify({ fields: [{ field_name: 'next' }], formSteps: [{ label: 'Step 1', fields: ['next'] }] }),
    ];

    ctx.redo();

    expect(ctx.renderStepTabs).toHaveBeenCalledTimes(1);
    expect(ctx.renderCanvas).not.toHaveBeenCalled();
  });
});
