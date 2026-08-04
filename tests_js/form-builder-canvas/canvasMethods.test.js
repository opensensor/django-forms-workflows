import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { canvasMethods } from '../../django_forms_workflows/static/django_forms_workflows/js/form-builder-canvas.js';
import { historyMethods } from '../../django_forms_workflows/static/django_forms_workflows/js/form-builder-history.js';
import { createBuilderStore } from '../../django_forms_workflows/static/django_forms_workflows/js/form-builder-store.js';

function createContext({ fields = [], formSteps = [], fieldIdCounter = 1, config = {} } = {}) {
  return {
    store: createBuilderStore({ fields, formSteps, fieldIdCounter }),
    config,
    undoStack: [],
    redoStack: [],
    maxUndoSteps: 50,
    draggingFieldType: null,
    dragPlaceholder: null,
    contextMenu: null,
    // Real pushUndo (not a stub) - several assertions below check undoStack
    // contents directly, the way the pre-extraction tests did.
    pushUndo: historyMethods.pushUndo,
    editField: vi.fn(),
    updatePreview: vi.fn(),
    saveForm: vi.fn(),
    get fields() { return this.store.fields; },
    set fields(value) { this.store.setFields(value); },
    get formSteps() { return this.store.formSteps; },
    set formSteps(value) { this.store.setFormSteps(value); },
    get fieldIdCounter() { return this.store.fieldIdCounter; },
    set fieldIdCounter(value) { this.store.fieldIdCounter = value; },
    ...canvasMethods,
  };
}

// Captures every Sortable instance created via `new Sortable(...)` or
// `Sortable.create(...)`, so tests can invoke the config's onAdd/onUpdate/
// onStart/onEnd callbacks directly rather than pulling in the real library.
function stubSortable() {
  const instances = [];
  function Sortable(container, config) {
    instances.push({ container, config });
    return {};
  }
  Sortable.create = vi.fn((container, config) => {
    instances.push({ container, config });
    return {};
  });
  vi.stubGlobal('Sortable', Sortable);
  return instances;
}

function paletteItemElement(fieldType) {
  const el = document.createElement('div');
  el.className = 'field-palette-item';
  el.dataset.fieldType = fieldType;
  return el;
}

function fieldItemElement(fieldIndex) {
  const el = document.createElement('div');
  el.className = 'field-item';
  el.dataset.fieldIndex = String(fieldIndex);
  return el;
}

afterEach(() => {
  document.body.innerHTML = '';
  vi.unstubAllGlobals();
});

describe('canvasMethods.setupFieldPalette', () => {
  beforeEach(() => {
    document.body.innerHTML = '<div id="fieldPalette"></div>';
  });

  it('builds a flat fieldTypes list from the categorized field types and renders the palette', () => {
    stubSortable();
    const ctx = createContext();

    ctx.setupFieldPalette();

    expect(ctx.fieldTypeCategories.length).toBeGreaterThan(0);
    expect(ctx.fieldTypes.length).toBe(
      ctx.fieldTypeCategories.reduce((sum, cat) => sum + cat.types.length, 0)
    );
    expect(ctx.fieldTypes.some(ft => ft.type === 'text')).toBe(true);
    expect(document.getElementById('fieldPalette').children.length).toBeGreaterThan(0);
  });

  it('re-renders the palette, filtered, when the search input changes', () => {
    document.body.innerHTML = '<div id="fieldPalette"></div><input id="paletteSearch">';
    stubSortable();
    const ctx = createContext();
    ctx.setupFieldPalette();
    ctx.renderPalette = vi.fn();

    document.getElementById('paletteSearch').value = '  Email  ';
    document.getElementById('paletteSearch').dispatchEvent(new Event('input'));

    expect(ctx.renderPalette).toHaveBeenCalledWith('email');
  });

  it('tracks the dragged field type on Sortable onStart and clears it (plus the placeholder) on onEnd', () => {
    const instances = stubSortable();
    const ctx = createContext();
    ctx.cleanupDragPlaceholder = vi.fn();
    ctx.setupFieldPalette();
    const { config } = instances[0];

    config.onStart({ item: paletteItemElement('text') });
    expect(ctx.draggingFieldType).toBe('text');

    config.onEnd({});
    expect(ctx.draggingFieldType).toBeNull();
    expect(ctx.cleanupDragPlaceholder).toHaveBeenCalledTimes(1);
  });
});

describe('canvasMethods.renderPalette', () => {
  beforeEach(() => {
    document.body.innerHTML = '<div id="fieldPalette"></div>';
  });

  function ctxWithCategories() {
    const ctx = createContext();
    ctx.fieldTypeCategories = [
      { name: 'Basic', icon: 'bi-x', types: [{ type: 'text', label: 'Single Line Text', icon: 'bi-x' }] },
      { name: 'Selection', icon: 'bi-x', types: [{ type: 'select', label: 'Dropdown Select', icon: 'bi-x' }] },
    ];
    return ctx;
  }

  it('renders every category and item when there is no filter', () => {
    const ctx = ctxWithCategories();

    ctx.renderPalette('');

    const palette = document.getElementById('fieldPalette');
    expect(palette.querySelectorAll('.palette-category-header').length).toBe(2);
    expect(palette.querySelectorAll('.field-palette-item').length).toBe(2);
  });

  it('matches on label or type, case-insensitively, and hides categories with no matches', () => {
    const ctx = ctxWithCategories();

    ctx.renderPalette('select');

    const palette = document.getElementById('fieldPalette');
    expect(palette.querySelectorAll('.palette-category-header').length).toBe(1);
    expect(palette.querySelector('.field-palette-item').dataset.fieldType).toBe('select');
  });
});

describe('canvasMethods.setupCanvas', () => {
  beforeEach(() => {
    document.body.innerHTML = '<div id="formCanvas"></div>';
  });

  it('does not call addFieldAtPosition a second time on drop (Sortable\'s onAdd already handles insertion)', () => {
    stubSortable();
    const ctx = createContext();
    ctx.addFieldAtPosition = vi.fn();
    ctx.draggingFieldType = 'text';
    const canvas = document.getElementById('formCanvas');

    ctx.setupCanvas();
    canvas.dispatchEvent(new Event('drop', { bubbles: true, cancelable: true }));

    expect(ctx.addFieldAtPosition).not.toHaveBeenCalled();
  });

  it('still cleans up the drag placeholder and dragging class on drop', () => {
    stubSortable();
    const ctx = createContext();
    ctx.draggingFieldType = 'text';
    const canvas = document.getElementById('formCanvas');
    canvas.classList.add('dragging');
    ctx.dragPlaceholder = document.createElement('div');
    canvas.appendChild(ctx.dragPlaceholder);

    ctx.setupCanvas();
    canvas.dispatchEvent(new Event('drop', { bubbles: true, cancelable: true }));

    expect(ctx.dragPlaceholder).toBeNull();
    expect(canvas.classList.contains('dragging')).toBe(false);
  });

  it('Sortable onAdd inserts a new field from the palette and removes the clone', () => {
    const instances = stubSortable();
    const ctx = createContext();
    ctx.addFieldAtPosition = vi.fn();
    ctx.setupCanvas();
    const { config } = instances[0];
    const item = paletteItemElement('text');
    document.getElementById('formCanvas').appendChild(item);

    config.onAdd({ item, newIndex: 2 });

    expect(ctx.addFieldAtPosition).toHaveBeenCalledWith('text', 2);
    expect(item.parentNode).toBeNull();
  });

  it('Sortable onAdd reorders an existing field when the dropped item is not from the palette', () => {
    const instances = stubSortable();
    const ctx = createContext({ fields: [{ field_name: 'a' }, { field_name: 'b' }] });
    ctx.setupCanvas();
    const { config } = instances[0];
    const item = fieldItemElement(0);

    config.onAdd({ item, oldIndex: 0, newIndex: 1 });

    expect(ctx.fields.map(f => f.field_name)).toEqual(['b', 'a']);
    expect(ctx.updatePreview).toHaveBeenCalledTimes(1);
  });

  it('Sortable onAdd pushes an undo snapshot before reordering an existing field (regression: single-step canvas move used to skip history)', () => {
    const instances = stubSortable();
    const ctx = createContext({ fields: [{ field_name: 'a' }, { field_name: 'b' }] });
    ctx.setupCanvas();
    const { config } = instances[0];
    const item = fieldItemElement(0);

    config.onAdd({ item, oldIndex: 0, newIndex: 1 });

    expect(ctx.undoStack).toHaveLength(1);
    expect(JSON.parse(ctx.undoStack[0]).fields.map(f => f.field_name)).toEqual(['a', 'b']);
  });

  it('Sortable onUpdate reorders fields within the canvas', () => {
    const instances = stubSortable();
    const ctx = createContext({ fields: [{ field_name: 'a' }, { field_name: 'b' }] });
    ctx.setupCanvas();
    const { config } = instances[0];

    config.onUpdate({ oldIndex: 1, newIndex: 0 });

    expect(ctx.fields.map(f => f.field_name)).toEqual(['b', 'a']);
    expect(ctx.updatePreview).toHaveBeenCalledTimes(1);
  });

  it('Sortable onUpdate pushes an undo snapshot before reordering (regression: single-step canvas reorder used to skip history)', () => {
    const instances = stubSortable();
    const ctx = createContext({ fields: [{ field_name: 'a' }, { field_name: 'b' }] });
    ctx.setupCanvas();
    const { config } = instances[0];

    config.onUpdate({ oldIndex: 1, newIndex: 0 });

    expect(ctx.undoStack).toHaveLength(1);
    expect(JSON.parse(ctx.undoStack[0]).fields.map(f => f.field_name)).toEqual(['a', 'b']);
  });

  it('Sortable onStart/onEnd toggle the dragging class on the canvas', () => {
    const instances = stubSortable();
    const ctx = createContext();
    ctx.setupCanvas();
    const { config } = instances[0];
    const canvas = document.getElementById('formCanvas');

    config.onStart({});
    expect(canvas.classList.contains('dragging')).toBe(true);

    config.onEnd({});
    expect(canvas.classList.contains('dragging')).toBe(false);
  });
});

describe('canvasMethods.getDragAfterElement', () => {
  it('returns the element whose vertical midpoint is just below the cursor', () => {
    document.body.innerHTML = '<div id="formCanvas"></div>';
    const canvas = document.getElementById('formCanvas');
    const above = document.createElement('div');
    above.className = 'canvas-field';
    above.getBoundingClientRect = () => ({ top: 0, height: 100 });
    const below = document.createElement('div');
    below.className = 'canvas-field';
    below.getBoundingClientRect = () => ({ top: 100, height: 100 });
    canvas.append(above, below);
    const ctx = createContext();

    expect(ctx.getDragAfterElement(canvas, 120)).toBe(below);
  });

  it('returns undefined (append at the end) when the cursor is below every field', () => {
    document.body.innerHTML = '<div id="formCanvas"></div>';
    const canvas = document.getElementById('formCanvas');
    const only = document.createElement('div');
    only.className = 'canvas-field';
    only.getBoundingClientRect = () => ({ top: 0, height: 100 });
    canvas.appendChild(only);
    const ctx = createContext();

    expect(ctx.getDragAfterElement(canvas, 500)).toBeUndefined();
  });
});

describe('canvasMethods.cleanupDragPlaceholder', () => {
  it('removes the placeholder and clears the dragging class', () => {
    document.body.innerHTML = '<div id="formCanvas" class="dragging"></div>';
    const canvas = document.getElementById('formCanvas');
    const ctx = createContext();
    ctx.dragPlaceholder = document.createElement('div');
    canvas.appendChild(ctx.dragPlaceholder);

    ctx.cleanupDragPlaceholder();

    expect(ctx.dragPlaceholder).toBeNull();
    expect(canvas.classList.contains('dragging')).toBe(false);
  });

  it('is a no-op when there is no placeholder or canvas', () => {
    const ctx = createContext();
    expect(() => ctx.cleanupDragPlaceholder()).not.toThrow();
  });
});

describe('canvasMethods.addFieldAtPosition', () => {
  it('inserts correctly on an empty canvas, when SortableJS reports an out-of-range drop position', () => {
    const ctx = createContext();
    ctx.renderCanvas = vi.fn();

    ctx.addFieldAtPosition('text', 1);

    expect(ctx.fields).toHaveLength(1);
    expect(ctx.editField).toHaveBeenCalledWith(0, true);
  });

  it('inserts at the requested position when it is already in range', () => {
    const ctx = createContext({ fields: [{ field_name: 'existing' }] });
    ctx.renderCanvas = vi.fn();

    ctx.addFieldAtPosition('text', 0);

    expect(ctx.fields).toHaveLength(2);
    expect(ctx.fields[1].field_name).toBe('existing');
    expect(ctx.editField).toHaveBeenCalledWith(0, true);
  });

  it('derives the id and the default field_name from the same counter value (regression: id used to be one ahead of field_name)', () => {
    const ctx = createContext({ fieldIdCounter: 5 });
    ctx.renderCanvas = vi.fn();

    ctx.addFieldAtPosition('text', 0);

    expect(ctx.fields[0].id).toBe('new_5');
    expect(ctx.fields[0].field_name).toBe('text_5');
  });

  it('pushes an undo snapshot before inserting', () => {
    const ctx = createContext();
    ctx.renderCanvas = vi.fn();

    ctx.addFieldAtPosition('text', 0);

    expect(ctx.undoStack).toHaveLength(1);
  });
});

describe('canvasMethods.addField', () => {
  it('delegates to addFieldAtPosition, appending at the end', () => {
    const ctx = createContext({ fields: [{ field_name: 'a' }] });
    ctx.addFieldAtPosition = vi.fn();

    ctx.addField('text');

    expect(ctx.addFieldAtPosition).toHaveBeenCalledWith('text', 1);
  });
});

describe('canvasMethods.duplicateField', () => {
  it('clones the field with a new id/name/label, inserted right after the original', () => {
    const ctx = createContext({ fields: [{ id: 'f1', field_name: 'a', field_label: 'A', order: 1 }] });
    ctx.renderCanvas = vi.fn();

    ctx.duplicateField(0);

    expect(ctx.fields).toHaveLength(2);
    expect(ctx.fields[1].field_name).toBe('a_copy');
    expect(ctx.fields[1].field_label).toBe('A (Copy)');
    expect(ctx.fields[1].id).not.toBe('f1');
  });

  it('also inserts the clone into the original\'s step, right after it, in multi-step mode', () => {
    const ctx = createContext({
      fields: [{ field_name: 'a' }, { field_name: 'b' }],
      formSteps: [{ title: 'Step 1', fields: ['a', 'b'] }],
    });
    document.body.innerHTML = '<input type="checkbox" id="formEnableMultiStep" checked>';
    ctx.renderStepTabs = vi.fn();

    ctx.duplicateField(0);

    expect(ctx.formSteps[0].fields).toEqual(['a', 'a_copy', 'b']);
    expect(ctx.renderStepTabs).toHaveBeenCalledTimes(1);
  });

  it('re-renders the single-step canvas and preview when not in multi-step mode', () => {
    const ctx = createContext({ fields: [{ field_name: 'a' }] });
    ctx.renderCanvas = vi.fn();

    ctx.duplicateField(0);

    expect(ctx.renderCanvas).toHaveBeenCalledTimes(1);
    expect(ctx.updatePreview).toHaveBeenCalledTimes(1);
  });

  it('pushes an undo snapshot before duplicating', () => {
    const ctx = createContext({ fields: [{ field_name: 'a' }] });
    ctx.renderCanvas = vi.fn();

    ctx.duplicateField(0);

    expect(ctx.undoStack).toHaveLength(1);
  });
});

describe('canvasMethods.getDefaultLabel / getDefaultName', () => {
  it('returns a human-readable label for known types and a generic fallback otherwise', () => {
    const ctx = createContext();

    expect(ctx.getDefaultLabel('email')).toBe('Email Address');
    expect(ctx.getDefaultLabel('totally_unknown')).toBe('Field');
  });

  it('builds a name from the field type and the current (not-yet-incremented) counter', () => {
    const ctx = createContext({ fieldIdCounter: 7 });

    expect(ctx.getDefaultName('text')).toBe('text_7');
    expect(ctx.fieldIdCounter).toBe(7); // reading the name must not itself advance the counter
  });
});

describe('canvasMethods.renderCanvas / createFieldElement', () => {
  beforeEach(() => {
    document.body.innerHTML = '<div id="formCanvas"></div><div id="fieldCount"></div>';
  });

  it('shows the empty-canvas placeholder and a "0 fields" count when there are no fields', () => {
    const ctx = createContext();

    ctx.renderCanvas();

    expect(document.querySelector('.empty-canvas')).not.toBeNull();
    expect(document.getElementById('fieldCount').textContent).toBe('0 fields');
  });

  it('renders one element per field plus a trailing drop zone, and updates the count', () => {
    const ctx = createContext({ fields: [{ field_name: 'a', field_label: 'A', field_type: 'text' }, { field_name: 'b', field_label: 'B', field_type: 'text' }] });

    ctx.renderCanvas();

    const canvas = document.getElementById('formCanvas');
    expect(canvas.querySelectorAll('.field-item').length).toBe(2);
    expect(canvas.querySelector('.canvas-drop-zone')).not.toBeNull();
    expect(document.getElementById('fieldCount').textContent).toBe('2 fields');
  });

  it('renders a section field with the section-specific class/badge', () => {
    const ctx = createContext();

    const el = ctx.createFieldElement({ field_type: 'section', field_label: 'My Section' }, 0);

    expect(el.className).toContain('canvas-section');
    expect(el.querySelector('.section-badge')).not.toBeNull();
  });

  it('escapes the field label before rendering it', () => {
    const ctx = createContext();

    const el = ctx.createFieldElement({ field_type: 'text', field_name: 'f', field_label: '<img src=x onerror=alert(1)>' }, 0);

    expect(el.innerHTML).not.toContain('<img src=x onerror=alert(1)>');
    expect(el.innerHTML).toContain(ctx.escapeHtml('<img src=x onerror=alert(1)>'));
  });

  it('routes right-click on a rendered field to showFieldContextMenu with its index', () => {
    const ctx = createContext();
    ctx.showFieldContextMenu = vi.fn();
    const el = ctx.createFieldElement({ field_type: 'text', field_name: 'f', field_label: 'F' }, 3);
    document.body.appendChild(el);

    el.dispatchEvent(new MouseEvent('contextmenu', { bubbles: true, cancelable: true }));

    expect(ctx.showFieldContextMenu).toHaveBeenCalledWith(expect.anything(), 3);
  });
});

describe('canvasMethods.toggleMultiStepMode', () => {
  beforeEach(() => {
    document.body.innerHTML = '<div id="singleStepCanvas"></div><div id="multiStepCanvas"></div>';
  });

  it('refreshes the live preview when enabling multi-step', () => {
    const ctx = createContext({ fields: [{ field_name: 'a' }], formSteps: [] });
    ctx.renderStepTabs = vi.fn();

    ctx.toggleMultiStepMode(true);

    expect(ctx.updatePreview).toHaveBeenCalledTimes(1);
  });

  it('refreshes both the canvas and the live preview when disabling multi-step', () => {
    const ctx = createContext({ fields: [{ field_name: 'a' }], formSteps: [{ title: 'Step 1', fields: ['a'] }] });
    ctx.renderCanvas = vi.fn();

    ctx.toggleMultiStepMode(false);

    expect(ctx.renderCanvas).toHaveBeenCalledTimes(1);
    expect(ctx.updatePreview).toHaveBeenCalledTimes(1);
  });
});

describe('canvasMethods.renderStepTabs', () => {
  beforeEach(() => {
    document.body.innerHTML = '<div id="stepTabContent"></div>';
  });

  it('renders one step card per step, escaping the title, and disables removal when only one step exists', () => {
    stubSortable();
    const ctx = createContext({
      fields: [],
      formSteps: [{ title: '<b>Step 1</b>', fields: [] }],
    });

    ctx.renderStepTabs();

    const content = document.getElementById('stepTabContent');
    expect(content.querySelectorAll('.step-card').length).toBe(1);
    // The title must never be parsed as markup - no <b> element should
    // exist anywhere in the rendered output, whether it landed in the
    // input's value attribute or the "Drag fields here for..." text.
    expect(content.querySelector('b')).toBeNull();
    expect(content.querySelector('.step-canvas p').innerHTML).toContain(ctx.escapeHtml('<b>Step 1</b>'));
    expect(content.querySelector('button[onclick^="formBuilder.removeStepTab"]').disabled).toBe(true);
  });

  it('leaves the remove button enabled when there is more than one step', () => {
    stubSortable();
    const ctx = createContext({
      fields: [],
      formSteps: [{ title: 'Step 1', fields: [] }, { title: 'Step 2', fields: [] }],
    });

    ctx.renderStepTabs();

    const buttons = document.querySelectorAll('button[onclick^="formBuilder.removeStepTab"]');
    expect(Array.from(buttons).every(b => !b.disabled)).toBe(true);
  });
});

describe('canvasMethods.setupStepCanvasSortable / setupStepCanvasDragDrop', () => {
  beforeEach(() => {
    document.body.innerHTML = '<div id="step-canvas-0"></div>';
  });

  it('routes a palette drop to handleFieldDroppedToStep and an existing-field drop to handleFieldMovedToStep', () => {
    const instances = stubSortable();
    const ctx = createContext();
    ctx.handleFieldDroppedToStep = vi.fn();
    ctx.handleFieldMovedToStep = vi.fn();

    ctx.setupStepCanvasSortable(0);
    const { config } = instances[0];

    const paletteItem = paletteItemElement('text');
    document.getElementById('step-canvas-0').appendChild(paletteItem);
    config.onAdd({ item: paletteItem, newIndex: 1 });
    expect(ctx.handleFieldDroppedToStep).toHaveBeenCalledWith('text', 0, 1);
    expect(paletteItem.parentNode).toBeNull();

    const fieldItem = fieldItemElement(2);
    config.onAdd({ item: fieldItem });
    expect(ctx.handleFieldMovedToStep).toHaveBeenCalledWith(fieldItem, 0);
  });

  it('routes a Sortable reorder within the step to updateFieldOrderInStep', () => {
    const instances = stubSortable();
    const ctx = createContext();
    ctx.updateFieldOrderInStep = vi.fn();

    ctx.setupStepCanvasSortable(0);
    instances[0].config.onUpdate({});

    expect(ctx.updateFieldOrderInStep).toHaveBeenCalledWith(0);
  });

  it('native drop from the palette (fallback path) also routes to handleFieldDroppedToStep', () => {
    const ctx = createContext();
    ctx.handleFieldDroppedToStep = vi.fn();
    ctx.setupStepCanvasDragDrop(0);
    const canvas = document.getElementById('step-canvas-0');

    const dropEvent = new Event('drop', { bubbles: true, cancelable: true });
    dropEvent.dataTransfer = { getData: () => 'text' };
    canvas.dispatchEvent(dropEvent);

    expect(ctx.handleFieldDroppedToStep).toHaveBeenCalledWith('text', 0);
  });
});

describe('canvasMethods.handleFieldDroppedToStep', () => {
  function createDropContext() {
    return createContext({ formSteps: [{ title: 'Step 1', fields: [] }] });
  }

  beforeEach(() => {
    document.body.innerHTML = '<div id="step-canvas-0"></div>';
  });

  it('pushes an undo snapshot before adding the field', () => {
    const ctx = createDropContext();
    ctx.fieldTypes = [{ type: 'text' }];
    ctx.renderFieldsInSteps = vi.fn();

    ctx.handleFieldDroppedToStep('text', 0);

    expect(ctx.undoStack).toHaveLength(1);
    expect(JSON.parse(ctx.undoStack[0]).fields).toEqual([]);
  });

  it('adds the field to both this.fields and the target step', () => {
    const ctx = createDropContext();
    ctx.fieldTypes = [{ type: 'text' }];
    ctx.renderFieldsInSteps = vi.fn();

    ctx.handleFieldDroppedToStep('text', 0);

    expect(ctx.fields).toHaveLength(1);
    expect(ctx.formSteps[0].fields).toEqual([ctx.fields[0].field_name]);
  });

  it('does nothing when the field type is unknown', () => {
    const ctx = createDropContext();
    ctx.fieldTypes = [{ type: 'text' }];

    ctx.handleFieldDroppedToStep('bogus', 0);

    expect(ctx.undoStack).toHaveLength(0);
    expect(ctx.fields).toHaveLength(0);
  });

  it('reorders this.fields to match the step position when dropped before an existing field, not just appended', () => {
    const ctx = createContext({
      fields: [{ field_name: 'existing' }],
      formSteps: [{ title: 'Step 1', fields: ['existing'] }],
    });
    ctx.fieldTypes = [{ type: 'text' }];
    ctx.renderFieldsInSteps = vi.fn();

    ctx.handleFieldDroppedToStep('text', 0, 0);

    expect(ctx.formSteps[0].fields[0]).not.toBe('existing');
    expect(ctx.fields.map(f => f.field_name)).toEqual(ctx.formSteps[0].fields);
  });

  it('opens the property editor for the newly-added field even after this.fields gets reordered', () => {
    const ctx = createContext({
      fields: [{ field_name: 'existing' }],
      formSteps: [{ title: 'Step 1', fields: ['existing'] }],
    });
    ctx.fieldTypes = [{ type: 'text' }];
    ctx.renderFieldsInSteps = vi.fn();

    ctx.handleFieldDroppedToStep('text', 0, 0);

    const newFieldIndex = ctx.fields.findIndex(f => f.field_name !== 'existing');
    expect(ctx.editField).toHaveBeenCalledWith(newFieldIndex, true);
  });
});

describe('canvasMethods.addStepTab / removeStepTab / updateStepTitle', () => {
  it('appends a new, sequentially-titled step and re-renders the tabs', () => {
    const ctx = createContext({ formSteps: [{ title: 'Step 1', fields: [] }] });
    ctx.renderStepTabs = vi.fn();

    ctx.addStepTab();

    expect(ctx.formSteps).toHaveLength(2);
    expect(ctx.formSteps[1]).toEqual({ title: 'Step 2', fields: [] });
    expect(ctx.renderStepTabs).toHaveBeenCalledTimes(1);
  });

  it('refuses to remove the last remaining step', () => {
    vi.stubGlobal('alert', vi.fn());
    const ctx = createContext({ formSteps: [{ title: 'Step 1', fields: [] }] });
    ctx.renderStepTabs = vi.fn();

    ctx.removeStepTab(0);

    expect(ctx.formSteps).toHaveLength(1);
    expect(alert).toHaveBeenCalled();
  });

  it('moves the removed step\'s fields to step 0 and removes it, once confirmed', () => {
    vi.stubGlobal('confirm', vi.fn(() => true));
    const ctx = createContext({
      formSteps: [{ title: 'Step 1', fields: ['a'] }, { title: 'Step 2', fields: ['b'] }],
    });
    ctx.renderStepTabs = vi.fn();

    ctx.removeStepTab(1);

    expect(ctx.formSteps).toEqual([{ title: 'Step 1', fields: ['a', 'b'] }]);
    expect(ctx.renderStepTabs).toHaveBeenCalledTimes(1);
  });

  it('leaves formSteps untouched when removal is not confirmed', () => {
    vi.stubGlobal('confirm', vi.fn(() => false));
    const ctx = createContext({
      formSteps: [{ title: 'Step 1', fields: ['a'] }, { title: 'Step 2', fields: ['b'] }],
    });
    ctx.renderStepTabs = vi.fn();

    ctx.removeStepTab(1);

    expect(ctx.formSteps).toHaveLength(2);
    expect(ctx.renderStepTabs).not.toHaveBeenCalled();
  });

  it('updates the step title in state and, escaped, in the DOM tab if present', () => {
    document.body.innerHTML = `
      <div id="step-tab-0"><i class="bi"></i><button></button></div>
    `;
    const ctx = createContext({ formSteps: [{ title: 'Old', fields: [] }] });

    ctx.updateStepTitle(0, '<b>New</b>');

    expect(ctx.formSteps[0].title).toBe('<b>New</b>');
    const tab = document.getElementById('step-tab-0');
    expect(tab.innerHTML).not.toContain('<b>New</b>');
    expect(tab.innerHTML).toContain(ctx.escapeHtml('<b>New</b>'));
  });

  it('does not throw when the corresponding DOM tab is absent', () => {
    const ctx = createContext({ formSteps: [{ title: 'Old', fields: [] }] });
    expect(() => ctx.updateStepTitle(0, 'New')).not.toThrow();
    expect(ctx.formSteps[0].title).toBe('New');
  });
});

describe('canvasMethods.handleFieldMovedToStep', () => {
  function createInstance({ fields, formSteps }) {
    return createContext({ fields, formSteps });
  }

  it('moves the field name out of its source step and into the target step at the dropped DOM position', () => {
    const ctx = createInstance({
      fields: [{ field_name: 'a' }, { field_name: 'b' }, { field_name: 'c' }],
      formSteps: [{ title: 'Step 1', fields: ['a', 'b'] }, { title: 'Step 2', fields: ['c'] }],
    });
    ctx.renderFieldsInSteps = vi.fn();
    document.body.innerHTML = '<div id="step-canvas-1"></div>';
    const canvas = document.getElementById('step-canvas-1');
    const cEl = fieldItemElement(2);
    const aEl = fieldItemElement(0);
    canvas.appendChild(cEl);
    canvas.appendChild(aEl);

    ctx.handleFieldMovedToStep(aEl, 1);

    expect(ctx.formSteps[0].fields).toEqual(['b']);
    expect(ctx.formSteps[1].fields).toEqual(['c', 'a']);
  });

  it('reorders this.fields to match the new cross-step order (regression: preview used to keep the stale array order)', () => {
    const ctx = createInstance({
      fields: [{ field_name: 'a' }, { field_name: 'b' }, { field_name: 'c' }],
      formSteps: [{ title: 'Step 1', fields: ['a', 'b'] }, { title: 'Step 2', fields: ['c'] }],
    });
    ctx.renderFieldsInSteps = vi.fn();
    document.body.innerHTML = '<div id="step-canvas-1"></div>';
    const canvas = document.getElementById('step-canvas-1');
    const cEl = fieldItemElement(2);
    const aEl = fieldItemElement(0);
    canvas.appendChild(cEl);
    canvas.appendChild(aEl);

    ctx.handleFieldMovedToStep(aEl, 1);

    expect(ctx.fields.map(f => f.field_name)).toEqual(['b', 'c', 'a']);
  });

  it('does nothing when the dragged element has no matching field', () => {
    const ctx = createInstance({
      fields: [{ field_name: 'a' }],
      formSteps: [{ title: 'Step 1', fields: ['a'] }],
    });
    ctx.renderFieldsInSteps = vi.fn();
    const orphanEl = fieldItemElement(99);

    ctx.handleFieldMovedToStep(orphanEl, 0);

    expect(ctx.formSteps[0].fields).toEqual(['a']);
    expect(ctx.renderFieldsInSteps).not.toHaveBeenCalled();
  });

  it('pushes an undo snapshot before moving the field, so Ctrl+Z can restore the pre-move step assignment', () => {
    const ctx = createInstance({
      fields: [{ field_name: 'a' }, { field_name: 'b' }, { field_name: 'c' }],
      formSteps: [{ title: 'Step 1', fields: ['a', 'b'] }, { title: 'Step 2', fields: ['c'] }],
    });
    ctx.renderFieldsInSteps = vi.fn();
    document.body.innerHTML = '<div id="step-canvas-1"></div>';
    const canvas = document.getElementById('step-canvas-1');
    const cEl = fieldItemElement(2);
    const aEl = fieldItemElement(0);
    canvas.appendChild(cEl);
    canvas.appendChild(aEl);

    ctx.handleFieldMovedToStep(aEl, 1);

    expect(ctx.undoStack).toHaveLength(1);
    expect(JSON.parse(ctx.undoStack[0])).toEqual({
      fields: [{ field_name: 'a' }, { field_name: 'b' }, { field_name: 'c' }],
      formSteps: [{ title: 'Step 1', fields: ['a', 'b'] }, { title: 'Step 2', fields: ['c'] }],
    });
  });

  it('does not push an undo snapshot when the dragged element has no matching field', () => {
    const ctx = createInstance({
      fields: [{ field_name: 'a' }],
      formSteps: [{ title: 'Step 1', fields: ['a'] }],
    });
    const orphanEl = fieldItemElement(99);

    ctx.handleFieldMovedToStep(orphanEl, 0);

    expect(ctx.undoStack).toHaveLength(0);
  });
});

describe('canvasMethods.updateFieldOrderInStep', () => {
  function setStepCanvasOrder(stepIndex, fieldIndexesInOrder) {
    document.body.innerHTML = `<div id="step-canvas-${stepIndex}"></div>`;
    const canvas = document.getElementById(`step-canvas-${stepIndex}`);
    fieldIndexesInOrder.forEach((fieldIndex) => canvas.appendChild(fieldItemElement(fieldIndex)));
  }

  it('rewrites the step field order from the DOM order and refreshes the preview', () => {
    const ctx = createContext({
      fields: [{ field_name: 'a' }, { field_name: 'b' }],
      formSteps: [{ title: 'Step 1', fields: ['a', 'b'] }],
    });
    ctx.renderFieldsInSteps = vi.fn();
    setStepCanvasOrder(0, [1, 0]);

    ctx.updateFieldOrderInStep(0);

    expect(ctx.formSteps[0].fields).toEqual(['b', 'a']);
    expect(ctx.updatePreview).toHaveBeenCalledTimes(1);
  });

  it('reorders this.fields to match the new step order, not just formSteps (regression: preview used to keep the stale array order)', () => {
    const ctx = createContext({
      fields: [{ field_name: 'a' }, { field_name: 'b' }],
      formSteps: [{ title: 'Step 1', fields: ['a', 'b'] }],
    });
    ctx.renderFieldsInSteps = vi.fn();
    setStepCanvasOrder(0, [1, 0]);

    ctx.updateFieldOrderInStep(0);

    expect(ctx.fields.map(f => f.field_name)).toEqual(['b', 'a']);
  });

  it('pushes an undo snapshot before reordering, so Ctrl+Z can restore the pre-drag order', () => {
    const ctx = createContext({
      fields: [{ field_name: 'a' }, { field_name: 'b' }],
      formSteps: [{ title: 'Step 1', fields: ['a', 'b'] }],
    });
    ctx.renderFieldsInSteps = vi.fn();
    setStepCanvasOrder(0, [1, 0]);

    ctx.updateFieldOrderInStep(0);

    expect(ctx.undoStack).toHaveLength(1);
    expect(JSON.parse(ctx.undoStack[0])).toEqual({
      fields: [{ field_name: 'a' }, { field_name: 'b' }],
      formSteps: [{ title: 'Step 1', fields: ['a', 'b'] }],
    });
  });
});

describe('multi-step field-index sync across steps (regression)', () => {
  // Regression coverage for a bug found after the this.fields/formSteps sync
  // fix: reordering this.fields *after* rendering (or only re-rendering the
  // touched step) left other steps' data-field-index attributes pointing at
  // the wrong entries once this.fields' array order changed underneath them.
  function setupStepCanvases(stepIndexes) {
    document.body.innerHTML = stepIndexes.map(i => `<div id="step-canvas-${i}"></div>`).join('');
  }

  it('keeps every rendered field-item across every step pointing at the right field after a cross-step add', () => {
    const ctx = createContext({
      fields: [{ field_name: 'a', field_label: 'A', field_type: 'text' }, { field_name: 'b', field_label: 'B', field_type: 'text' }],
      formSteps: [{ title: 'Step 1', fields: ['a'] }, { title: 'Step 2', fields: ['b'] }],
    });
    ctx.fieldTypes = [{ type: 'text' }];
    setupStepCanvases([0, 1]);

    ctx.handleFieldDroppedToStep('text', 0, 0);

    document.querySelectorAll('.field-item').forEach(el => {
      const idx = parseInt(el.dataset.fieldIndex);
      const field = ctx.fields[idx];
      expect(field).toBeDefined();
      expect(el.querySelector('.field-label').textContent).toBe(field.field_label);
    });
  });

  it('does not corrupt formSteps/this.fields when a step is reordered right after a cross-step field-index shift', () => {
    const ctx = createContext({
      fields: [{ field_name: 'a', field_label: 'A', field_type: 'text' }, { field_name: 'b', field_label: 'B', field_type: 'text' }],
      formSteps: [{ title: 'Step 1', fields: ['a'] }, { title: 'Step 2', fields: ['b'] }],
    });
    ctx.fieldTypes = [{ type: 'text' }];
    setupStepCanvases([0, 1]);

    ctx.handleFieldDroppedToStep('text', 0, 0);
    ctx.updateFieldOrderInStep(0);

    const allNames = ctx.fields.map(f => f.field_name);
    expect(new Set(allNames).size).toBe(allNames.length);
    expect(allNames).toHaveLength(3);
    expect(ctx.formSteps[1].fields).toEqual(['b']);
  });
});

describe('canvasMethods.updateStepFieldCount', () => {
  it('writes the step\'s field count into its panel badge', () => {
    document.body.innerHTML = '<div id="step-panel-0"><span class="badge"></span></div>';
    const ctx = createContext({ formSteps: [{ title: 'Step 1', fields: ['a', 'b'] }] });

    ctx.updateStepFieldCount(0);

    expect(document.querySelector('#step-panel-0 .badge').textContent).toBe('2 fields');
  });

  it('does not throw when the panel is absent', () => {
    const ctx = createContext({ formSteps: [{ title: 'Step 1', fields: [] }] });
    expect(() => ctx.updateStepFieldCount(0)).not.toThrow();
  });
});

describe('canvasMethods.organizeFieldsIntoSteps / renderFieldsInSteps / renderSingleStep', () => {
  it('assigns every field not already listed in some step to step 0', () => {
    const ctx = createContext({
      fields: [{ field_name: 'a' }, { field_name: 'b' }],
      formSteps: [{ title: 'Step 1', fields: ['a'] }],
    });
    ctx.renderFieldsInSteps = vi.fn();

    ctx.organizeFieldsIntoSteps();

    expect(ctx.formSteps[0].fields).toEqual(['a', 'b']);
    expect(ctx.renderFieldsInSteps).toHaveBeenCalledTimes(1);
  });

  it('renderFieldsInSteps renders every step by delegating to renderSingleStep', () => {
    const ctx = createContext({ formSteps: [{ title: 'Step 1', fields: [] }, { title: 'Step 2', fields: [] }] });
    ctx.renderSingleStep = vi.fn();

    ctx.renderFieldsInSteps();

    expect(ctx.renderSingleStep).toHaveBeenCalledTimes(2);
    expect(ctx.renderSingleStep).toHaveBeenCalledWith(0);
    expect(ctx.renderSingleStep).toHaveBeenCalledWith(1);
  });

  it('renderSingleStep shows an escaped empty-state message when the step has no fields', () => {
    document.body.innerHTML = '<div id="step-canvas-0"></div>';
    const ctx = createContext({ formSteps: [{ title: '<i>Step 1</i>', fields: [] }] });

    ctx.renderSingleStep(0);

    const canvas = document.getElementById('step-canvas-0');
    expect(canvas.innerHTML).not.toContain('<i>Step 1</i>');
    expect(canvas.innerHTML).toContain(ctx.escapeHtml('<i>Step 1</i>'));
  });

  it('renderSingleStep renders each of the step\'s fields, looked up by name', () => {
    document.body.innerHTML = '<div id="step-canvas-0"></div>';
    const ctx = createContext({
      fields: [{ field_name: 'a', field_label: 'A', field_type: 'text' }],
      formSteps: [{ title: 'Step 1', fields: ['a'] }],
    });

    ctx.renderSingleStep(0);

    expect(document.querySelectorAll('#step-canvas-0 .field-item').length).toBe(1);
  });
});

describe('canvasMethods.moveAllFieldsToMainCanvas', () => {
  it('refreshes both the canvas and the live preview', () => {
    const ctx = createContext({ formSteps: [{ title: 'Step 1', fields: ['a'] }] });
    ctx.renderCanvas = vi.fn();

    ctx.moveAllFieldsToMainCanvas();

    expect(ctx.renderCanvas).toHaveBeenCalledTimes(1);
    expect(ctx.updatePreview).toHaveBeenCalledTimes(1);
  });
});

describe('canvasMethods.updateFieldOrderFromSteps', () => {
  it('reorders this.fields to step order (step by step, field by field within each step) and renumbers order', () => {
    const ctx = createContext({
      fields: [{ field_name: 'a', order: 0 }, { field_name: 'b', order: 1 }, { field_name: 'c', order: 2 }],
      formSteps: [{ title: 'Step 1', fields: ['c', 'a'] }, { title: 'Step 2', fields: ['b'] }],
    });

    ctx.updateFieldOrderFromSteps();

    expect(ctx.fields.map(f => f.field_name)).toEqual(['c', 'a', 'b']);
    expect(ctx.fields.map(f => f.order)).toEqual([0, 1, 2]);
  });
});

describe('canvasMethods.deleteField / deleteFieldSilently / updateFieldOrders', () => {
  it('deleteField pushes undo and deletes only when confirmed', () => {
    vi.stubGlobal('confirm', vi.fn(() => true));
    const ctx = createContext({ fields: [{ field_name: 'a' }] });
    ctx.renderCanvas = vi.fn();

    ctx.deleteField(0);

    expect(ctx.undoStack).toHaveLength(1);
    expect(ctx.fields).toHaveLength(0);
  });

  it('deleteField does nothing when the confirmation is declined', () => {
    vi.stubGlobal('confirm', vi.fn(() => false));
    const ctx = createContext({ fields: [{ field_name: 'a' }] });

    ctx.deleteField(0);

    expect(ctx.undoStack).toHaveLength(0);
    expect(ctx.fields).toHaveLength(1);
  });

  it('deleteFieldSilently removes the field from this.fields and from every step that referenced it', () => {
    const ctx = createContext({
      fields: [{ field_name: 'a' }, { field_name: 'b' }],
      formSteps: [{ title: 'Step 1', fields: ['a', 'b'] }],
    });
    ctx.renderStepTabs = vi.fn();
    document.body.innerHTML = '<input type="checkbox" id="formEnableMultiStep" checked>';

    ctx.deleteFieldSilently(0);

    expect(ctx.fields.map(f => f.field_name)).toEqual(['b']);
    expect(ctx.formSteps[0].fields).toEqual(['b']);
    expect(ctx.renderStepTabs).toHaveBeenCalledTimes(1);
  });

  it('deleteFieldSilently re-renders the single-step canvas when not in multi-step mode', () => {
    const ctx = createContext({ fields: [{ field_name: 'a' }] });
    ctx.renderCanvas = vi.fn();

    ctx.deleteFieldSilently(0);

    expect(ctx.renderCanvas).toHaveBeenCalledTimes(1);
    expect(ctx.updatePreview).toHaveBeenCalledTimes(1);
  });

  it('updateFieldOrders renumbers order 1-based, matching array position', () => {
    const ctx = createContext({ fields: [{ field_name: 'a', order: 99 }, { field_name: 'b', order: 1 }] });

    ctx.updateFieldOrders();

    expect(ctx.fields.map(f => f.order)).toEqual([1, 2]);
  });
});

describe('canvasMethods.escapeHtml', () => {
  it('escapes HTML-significant characters', () => {
    const ctx = createContext();

    expect(ctx.escapeHtml('<script>alert(1)</script>')).not.toContain('<script>');
  });
});

describe('canvasMethods.showFieldContextMenu / hideFieldContextMenu / moveFieldToStepFromMenu', () => {
  it('does not show a menu outside multi-step mode', () => {
    document.body.innerHTML = '<input type="checkbox" id="formEnableMultiStep">';
    const ctx = createContext({ formSteps: [{ title: 'Step 1', fields: [] }, { title: 'Step 2', fields: [] }] });

    ctx.showFieldContextMenu({ clientX: 1, clientY: 1 }, 0);

    expect(document.querySelector('.field-context-menu')).toBeNull();
  });

  it('does not show a menu when there is only one step, even in multi-step mode', () => {
    document.body.innerHTML = '<input type="checkbox" id="formEnableMultiStep" checked>';
    const ctx = createContext({ formSteps: [{ title: 'Step 1', fields: [] }] });

    ctx.showFieldContextMenu({ clientX: 1, clientY: 1 }, 0);

    expect(document.querySelector('.field-context-menu')).toBeNull();
  });

  it('renders one escaped menu item per step and closes any previous menu first', () => {
    document.body.innerHTML = '<input type="checkbox" id="formEnableMultiStep" checked>';
    const ctx = createContext({ formSteps: [{ title: '<b>Step 1</b>', fields: [] }, { title: 'Step 2', fields: [] }] });

    ctx.showFieldContextMenu({ clientX: 5, clientY: 5 }, 0);
    const firstMenu = ctx.contextMenu;
    ctx.showFieldContextMenu({ clientX: 5, clientY: 5 }, 0);

    expect(document.querySelectorAll('.field-context-menu').length).toBe(1);
    expect(firstMenu.parentNode).toBeNull();
    expect(ctx.contextMenu.querySelectorAll('.context-menu-item').length).toBe(2);
    expect(ctx.contextMenu.innerHTML).not.toContain('<b>Step 1</b>');
    expect(ctx.contextMenu.innerHTML).toContain(ctx.escapeHtml('<b>Step 1</b>'));
  });

  it('hideFieldContextMenu removes the menu and clears the reference', () => {
    const ctx = createContext();
    ctx.contextMenu = document.createElement('div');
    document.body.appendChild(ctx.contextMenu);

    ctx.hideFieldContextMenu();

    expect(ctx.contextMenu).toBeNull();
    expect(document.body.children.length).toBe(0);
  });

  it('moveFieldToStepFromMenu moves the field into the target step and re-renders both steps', () => {
    const ctx = createContext({
      fields: [{ field_name: 'a' }],
      formSteps: [{ title: 'Step 1', fields: ['a'] }, { title: 'Step 2', fields: [] }],
    });
    ctx.renderSingleStep = vi.fn();

    ctx.moveFieldToStepFromMenu(0, 1);

    expect(ctx.formSteps[0].fields).toEqual([]);
    expect(ctx.formSteps[1].fields).toEqual(['a']);
    expect(ctx.renderSingleStep).toHaveBeenCalledWith(0);
    expect(ctx.renderSingleStep).toHaveBeenCalledWith(1);
    expect(ctx.updatePreview).toHaveBeenCalledTimes(1);
  });

  it('moveFieldToStepFromMenu does nothing when the field is already in the target step', () => {
    const ctx = createContext({
      fields: [{ field_name: 'a' }],
      formSteps: [{ title: 'Step 1', fields: ['a'] }, { title: 'Step 2', fields: [] }],
    });
    ctx.renderSingleStep = vi.fn();

    ctx.moveFieldToStepFromMenu(0, 0);

    expect(ctx.renderSingleStep).not.toHaveBeenCalled();
    expect(ctx.updatePreview).not.toHaveBeenCalled();
  });
});
