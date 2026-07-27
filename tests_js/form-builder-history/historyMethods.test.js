import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { historyMethods } from '../../django_forms_workflows/static/django_forms_workflows/js/form-builder-history.js';

function createContext(fields = [], formSteps = []) {
  return {
    fields,
    formSteps,
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

describe('historyMethods.snapshotHistoryState', () => {
  it('snapshots both fields and formSteps together', () => {
    const ctx = createContext([{ field_name: 'a' }], [{ label: 'Step 1', fields: ['a'] }]);

    expect(ctx.snapshotHistoryState()).toEqual(
      JSON.stringify({ fields: [{ field_name: 'a' }], formSteps: [{ label: 'Step 1', fields: ['a'] }] })
    );
  });
});

describe('historyMethods.pushUndo', () => {
  it('snapshots the current fields and formSteps onto the undo stack and clears redo', () => {
    const ctx = createContext([{ field_name: 'a' }], [{ label: 'Step 1', fields: ['a'] }]);
    ctx.redoStack.push('stale-redo-snapshot');

    ctx.pushUndo();

    expect(ctx.undoStack).toEqual([ctx.snapshotHistoryState()]);
    expect(ctx.redoStack).toEqual([]);
  });

  it('drops the oldest snapshot once maxUndoSteps is exceeded', () => {
    const ctx = createContext([]);
    ctx.maxUndoSteps = 2;
    ctx.undoStack = ['oldest', 'middle'];

    ctx.pushUndo();

    expect(ctx.undoStack).toEqual(['middle', ctx.snapshotHistoryState()]);
  });
});

describe('historyMethods.undo', () => {
  it('does nothing when there is no undo history', () => {
    const ctx = createContext([{ field_name: 'current' }]);

    ctx.undo();

    expect(ctx.fields).toEqual([{ field_name: 'current' }]);
    expect(ctx.renderCanvas).not.toHaveBeenCalled();
    expect(ctx.renderStepTabs).not.toHaveBeenCalled();
    expect(ctx.updatePreview).not.toHaveBeenCalled();
  });

  it('restores the previous fields and formSteps snapshot and pushes the current one onto redo', () => {
    const ctx = createContext(
      [{ field_name: 'current' }],
      [{ label: 'Step 1', fields: ['current'] }]
    );
    const currentSnapshot = ctx.snapshotHistoryState();
    ctx.undoStack = [
      JSON.stringify({ fields: [{ field_name: 'previous' }], formSteps: [] }),
    ];

    ctx.undo();

    expect(ctx.fields).toEqual([{ field_name: 'previous' }]);
    expect(ctx.formSteps).toEqual([]);
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

    expect(ctx.formSteps).toEqual([{ label: 'Step 1', fields: ['previous'] }]);
    expect(ctx.renderStepTabs).toHaveBeenCalledTimes(1);
    expect(ctx.renderCanvas).not.toHaveBeenCalled();
  });
});

describe('historyMethods.redo', () => {
  it('does nothing when there is no redo history', () => {
    const ctx = createContext([{ field_name: 'current' }]);

    ctx.redo();

    expect(ctx.fields).toEqual([{ field_name: 'current' }]);
    expect(ctx.renderCanvas).not.toHaveBeenCalled();
    expect(ctx.renderStepTabs).not.toHaveBeenCalled();
    expect(ctx.updatePreview).not.toHaveBeenCalled();
  });

  it('restores the next fields and formSteps snapshot and pushes the current one onto undo', () => {
    const ctx = createContext([{ field_name: 'current' }], []);
    const currentSnapshot = ctx.snapshotHistoryState();
    ctx.redoStack = [
      JSON.stringify({ fields: [{ field_name: 'next' }], formSteps: [{ label: 'Step 1', fields: ['next'] }] }),
    ];

    ctx.redo();

    expect(ctx.fields).toEqual([{ field_name: 'next' }]);
    expect(ctx.formSteps).toEqual([{ label: 'Step 1', fields: ['next'] }]);
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
