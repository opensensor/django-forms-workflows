import { describe, expect, it, vi } from 'vitest';
import { historyMethods } from '../../django_forms_workflows/static/django_forms_workflows/js/form-builder-history.js';

function createContext(fields = []) {
  return {
    fields,
    undoStack: [],
    redoStack: [],
    maxUndoSteps: 50,
    renderCanvas: vi.fn(),
    updatePreview: vi.fn(),
    ...historyMethods,
  };
}

describe('historyMethods.pushUndo', () => {
  it('snapshots the current fields onto the undo stack and clears redo', () => {
    const ctx = createContext([{ field_name: 'a' }]);
    ctx.redoStack.push('stale-redo-snapshot');

    ctx.pushUndo();

    expect(ctx.undoStack).toEqual([JSON.stringify([{ field_name: 'a' }])]);
    expect(ctx.redoStack).toEqual([]);
  });

  it('drops the oldest snapshot once maxUndoSteps is exceeded', () => {
    const ctx = createContext([]);
    ctx.maxUndoSteps = 2;
    ctx.undoStack = ['oldest', 'middle'];

    ctx.pushUndo();

    expect(ctx.undoStack).toEqual(['middle', JSON.stringify([])]);
  });
});

describe('historyMethods.undo', () => {
  it('does nothing when there is no undo history', () => {
    const ctx = createContext([{ field_name: 'current' }]);

    ctx.undo();

    expect(ctx.fields).toEqual([{ field_name: 'current' }]);
    expect(ctx.renderCanvas).not.toHaveBeenCalled();
    expect(ctx.updatePreview).not.toHaveBeenCalled();
  });

  it('restores the previous fields snapshot and pushes the current one onto redo', () => {
    const ctx = createContext([{ field_name: 'current' }]);
    ctx.undoStack = [JSON.stringify([{ field_name: 'previous' }])];

    ctx.undo();

    expect(ctx.fields).toEqual([{ field_name: 'previous' }]);
    expect(ctx.redoStack).toEqual([JSON.stringify([{ field_name: 'current' }])]);
    expect(ctx.undoStack).toEqual([]);
    expect(ctx.renderCanvas).toHaveBeenCalledTimes(1);
    expect(ctx.updatePreview).toHaveBeenCalledTimes(1);
  });
});

describe('historyMethods.redo', () => {
  it('does nothing when there is no redo history', () => {
    const ctx = createContext([{ field_name: 'current' }]);

    ctx.redo();

    expect(ctx.fields).toEqual([{ field_name: 'current' }]);
    expect(ctx.renderCanvas).not.toHaveBeenCalled();
    expect(ctx.updatePreview).not.toHaveBeenCalled();
  });

  it('restores the next fields snapshot and pushes the current one onto undo', () => {
    const ctx = createContext([{ field_name: 'current' }]);
    ctx.redoStack = [JSON.stringify([{ field_name: 'next' }])];

    ctx.redo();

    expect(ctx.fields).toEqual([{ field_name: 'next' }]);
    expect(ctx.undoStack).toEqual([JSON.stringify([{ field_name: 'current' }])]);
    expect(ctx.redoStack).toEqual([]);
    expect(ctx.renderCanvas).toHaveBeenCalledTimes(1);
    expect(ctx.updatePreview).toHaveBeenCalledTimes(1);
  });
});
