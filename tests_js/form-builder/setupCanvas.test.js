import { beforeEach, describe, expect, it, vi } from 'vitest';
import { FormBuilder } from '../../django_forms_workflows/static/django_forms_workflows/js/form-builder.js';

// setupCanvas() calls Sortable.create(...) before registering its own drop
// listener; stub it out rather than pulling in the real SortableJS
// dependency, since this test only exercises the manual listener, not
// SortableJS's own onAdd behavior.
function createInstance(FormBuilder) {
  global.Sortable = { create: vi.fn(() => ({})) };

  const instance = Object.create(FormBuilder.prototype);
  instance.fields = [];
  instance.dragPlaceholder = null;
  instance.addFieldAtPosition = vi.fn();
  return instance;
}

describe('FormBuilder#setupCanvas — drop handler', () => {
  let canvas;

  beforeEach(() => {
    document.body.innerHTML = '<div id="formCanvas"></div>';
    canvas = document.getElementById('formCanvas');
  });

  it('does not call addFieldAtPosition a second time on drop (Sortable\'s onAdd already handles insertion)', () => {
    const instance = createInstance(FormBuilder);
    instance.draggingFieldType = 'text';

    instance.setupCanvas();
    canvas.dispatchEvent(new Event('drop', { bubbles: true, cancelable: true }));

    expect(instance.addFieldAtPosition).not.toHaveBeenCalled();
  });

  it('still cleans up the drag placeholder and dragging class on drop', () => {
    const instance = createInstance(FormBuilder);
    instance.draggingFieldType = 'text';
    canvas.classList.add('dragging');
    instance.dragPlaceholder = document.createElement('div');
    canvas.appendChild(instance.dragPlaceholder);

    instance.setupCanvas();
    canvas.dispatchEvent(new Event('drop', { bubbles: true, cancelable: true }));

    expect(instance.dragPlaceholder).toBeNull();
    expect(canvas.classList.contains('dragging')).toBe(false);
  });
});
