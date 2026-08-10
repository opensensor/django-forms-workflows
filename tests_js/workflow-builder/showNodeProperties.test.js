import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { WorkflowBuilder } from '../../django_forms_workflows/static/django_forms_workflows/js/workflow-builder.js';
import { createWorkflowBuilderStore } from '../../django_forms_workflows/static/django_forms_workflows/js/workflow-builder-store.js';

// Regression coverage for the "on" boolean bug: showNodeProperties() attaches
// a generic change listener to every panel input as a backstop for fields
// without their own specific onchange handler (e.g. updateStageConfig).
// That generic listener used to forward e.target.value unconditionally,
// which for a checkbox is its static HTML value attribute ("on" by default)
// rather than its checked state — so toggling a checkbox re-clobbered it
// back to the literal string "on" right after a field-specific handler had
// just set the correct boolean, and Django's BooleanField rejected that
// string on save ("on" value must be either True or False).
function createInstance() {
  const instance = Object.create(WorkflowBuilder.prototype);
  instance.store = createWorkflowBuilderStore();
  instance.render = vi.fn();
  return instance;
}

function dispatchChange(el) {
  el.dispatchEvent(new Event('change', { bubbles: true }));
}

beforeEach(() => {
  document.body.innerHTML = '<div id="propertiesContent"></div>';
  vi.restoreAllMocks();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('WorkflowBuilder#showNodeProperties generic change listener', () => {
  it('stores a checkbox\'s checked state as a real boolean, not its "on" value attribute', () => {
    const instance = createInstance();
    const node = { id: 'node_1', type: 'stage', data: { requires_manager_approval: false } };
    instance.nodes = [node];
    instance.buildPropertiesForm = vi.fn(
      () => '<input type="checkbox" name="requires_manager_approval">'
    );

    instance.showNodeProperties(node);
    const checkbox = document.querySelector('input[name="requires_manager_approval"]');
    checkbox.checked = true;
    dispatchChange(checkbox);

    expect(node.data.requires_manager_approval).toBe(true);
  });

  it('stores an unchecked checkbox as false, not the string "on"', () => {
    const instance = createInstance();
    const node = { id: 'node_1', type: 'stage', data: { allow_send_back: true } };
    instance.nodes = [node];
    instance.buildPropertiesForm = vi.fn(
      () => '<input type="checkbox" name="allow_send_back" checked>'
    );

    instance.showNodeProperties(node);
    const checkbox = document.querySelector('input[name="allow_send_back"]');
    checkbox.checked = false;
    dispatchChange(checkbox);

    expect(node.data.allow_send_back).toBe(false);
  });

  it('still forwards the typed value for non-checkbox inputs', () => {
    const instance = createInstance();
    const node = { id: 'node_1', type: 'stage', data: { approve_label: '' } };
    instance.nodes = [node];
    instance.buildPropertiesForm = vi.fn(
      () => '<input type="text" name="approve_label" value="">'
    );

    instance.showNodeProperties(node);
    const input = document.querySelector('input[name="approve_label"]');
    input.value = 'Sign Off';
    dispatchChange(input);

    expect(node.data.approve_label).toBe('Sign Off');
  });
});
