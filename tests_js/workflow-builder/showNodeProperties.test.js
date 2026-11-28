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
  instance.validationState = { nodeIssues: {} };
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
    const node = { id: 'node_1', type: 'condition', data: { requires_manager_approval: false } };
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
    const node = { id: 'node_1', type: 'condition', data: { allow_send_back: true } };
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
    const node = { id: 'node_1', type: 'condition', data: { approve_label: '' } };
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

  it('does not overwrite values managed by a specialized change handler', () => {
    const instance = createInstance();
    const node = { id: 'node_1', type: 'condition', data: { approval_groups: [{ id: 1 }] } };
    instance.nodes = [node];
    instance.buildPropertiesForm = vi.fn(
      () => '<select name="approval_groups" onchange="void 0"><option value="1" selected>Reviewers</option></select>'
    );
    const updateProperty = vi.spyOn(instance, 'updateNodeProperty');

    instance.showNodeProperties(node);
    dispatchChange(document.querySelector('[name="approval_groups"]'));

    expect(updateProperty).not.toHaveBeenCalled();
    expect(node.data.approval_groups).toEqual([{ id: 1 }]);
  });
});

describe('WorkflowBuilder stage editor', () => {
  it('assigns saved text through input properties without injecting markup', () => {
    const instance = createInstance();
    const node = {
      id: `stage'" onclick="alert(1)`,
      type: 'stage',
      data: { name: 'Review" autofocus onfocus="alert(1)', approve_label: 'Sign "Off"', order: 2 },
    };
    instance.nodes = [node];
    instance.groups = [];
    instance.fields = [];

    instance.showNodeProperties(node);

    expect(document.querySelector('[name="name"]').value).toBe(node.data.name);
    expect(document.querySelector('[name="approve_label"]').value).toBe(node.data.approve_label);
    expect(document.querySelector('[name="name"]').hasAttribute('autofocus')).toBe(false);
    expect(document.querySelector('[name="name"]').hasAttribute('onfocus')).toBe(false);
    expect(document.querySelector('[name="name"]').hasAttribute('onclick')).toBe(false);
  });

  it('preserves group roles and approval field arrays on a stage change', () => {
    const instance = createInstance();
    const node = {
      id: 'stage_1',
      type: 'stage',
      data: {
        name: 'Review',
        approval_groups: [
          { id: 1, name: 'Reviewers', role: 'approval', position: 0 },
          { id: 1, name: 'Reviewers', role: 'validation', position: 1 },
        ],
        approval_fields: [{ id: 2, field_name: 'notes' }],
      },
    };
    instance.nodes = [node];
    instance.groups = [{ id: 1, name: 'Reviewers' }];
    instance.fields = [{ id: 2, field_name: 'notes', field_label: 'Notes' }];
    instance.selectNode = vi.fn();

    instance.showNodeProperties(node);
    const input = document.querySelector('[name="name"]');
    input.value = 'Updated';
    dispatchChange(input);

    expect(node.data.name).toBe('Updated');
    expect(node.data.approval_groups.map(group => group.role)).toEqual(['approval', 'validation']);
    expect(node.data.approval_fields.map(field => field.id)).toEqual([2]);
  });

  it('selects an approval field restored by field name', () => {
    const instance = createInstance();
    const node = {
      id: 'stage_1', type: 'stage',
      data: { name: 'Review', approval_fields: [{ field_name: 'notes' }] },
    };
    instance.nodes = [node];
    instance.fields = [{ id: 2, field_name: 'notes', field_label: 'Notes' }];
    instance.groups = [];

    instance.showNodeProperties(node);

    expect(document.querySelector('select[name="approval_fields"] option[value="2"]').selected).toBe(true);
  });

  it('rejects invalid stage order without changing node data', () => {
    const instance = createInstance();
    const node = { id: 'stage_1', type: 'stage', data: { name: 'Review', order: 1 } };
    instance.nodes = [node];
    instance.fields = [];
    instance.groups = [];
    instance.selectNode = vi.fn();
    instance.showNodeProperties(node);
    document.querySelector('input[name="name"]').value = 'Changed';
    const order = document.querySelector('input[name="order"]');
    order.value = '0';

    dispatchChange(order);

    expect(node.data.name).toBe('Review');
    expect(node.data.order).toBe(1);
    expect(order.validationMessage).toContain('Stage order must be an integer');

    order.value = '2';
    instance.updateStageConfig(node.id);
    expect(node.data.order).toBe(2);
    expect(order.validationMessage).toBe('');
  });
});

describe('WorkflowBuilder workflow settings editor', () => {
  it('does not partly update settings when a digest day is invalid', () => {
    const instance = createInstance();
    instance.fields = [];
    instance.groups = [];
    const node = { id: 'settings', type: 'workflow_settings', data: {
      notification_cadence: 'weekly', notification_cadence_day: 0,
      approval_deadline_days: 2,
    } };
    instance.nodes = [node];
    instance.selectNode = vi.fn();
    instance.showNodeProperties(node);

    document.querySelector('[name="approval_deadline_days"]').value = '5';
    const digestDay = document.querySelector('[name="notification_cadence_day"]');
    digestDay.value = '7';
    dispatchChange(digestDay);

    expect(node.data.approval_deadline_days).toBe(2);
    expect(node.data.notification_cadence_day).toBe(0);
    expect(digestDay.validationMessage).toContain('Notification cadence day');
    expect(instance.selectNode).not.toHaveBeenCalled();
  });

  it('keeps weekly day zero visible and omits unsupported daily cadence', () => {
    const instance = createInstance();
    instance.fields = [];
    instance.groups = [];
    const node = { id: 'settings', type: 'workflow_settings', data: { notification_cadence: 'weekly', notification_cadence_day: 0 } };
    instance.nodes = [node];
    instance.selectNode = vi.fn();

    instance.showNodeProperties(node);

    expect(document.querySelector('[name="notification_cadence_day"]').value).toBe('0');
    expect(document.querySelector('option[value="daily"]')).toBeNull();

    const label = document.querySelector('[name="name_label"]');
    label.value = 'Updated track';
    instance.updateWorkflowSettings(node.id);
    expect(node.data.notification_cadence_day).toBe(0);
  });
});
