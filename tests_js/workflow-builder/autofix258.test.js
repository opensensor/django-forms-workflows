import { describe, expect, it, vi } from 'vitest';
import { WorkflowBuilder } from '../../django_forms_workflows/static/django_forms_workflows/js/workflow-builder.js';
import { createWorkflowBuilderStore } from '../../django_forms_workflows/static/django_forms_workflows/js/workflow-builder-store.js';

function renderRules(rules, renderConditions = false, fields = []) {
  const builder = Object.create(WorkflowBuilder.prototype);
  builder.store = createWorkflowBuilderStore();
  builder.nodes = [];
  builder.fields = fields;
  builder.groups = [];
  if (!renderConditions) builder.buildConditionsEditor = vi.fn(() => '');
  const wrapper = document.createElement('div');
  wrapper.innerHTML = builder.buildNotificationRulesEditor({
    id: 'settings',
    data: { notification_rules: rules },
  });
  return { builder, wrapper };
}

describe('notification rule controls', () => {
  it('renders email field names as text and attribute values', () => {
    const fieldName = 'email"><img src=x onerror=alert(1)>';
    const { wrapper } = renderRules(
      [{ event: 'approval_request', email_field: fieldName }], false,
      [{ field_name: fieldName, field_label: fieldName }],
    );

    expect(wrapper.querySelector('img')).toBeNull();
    expect(wrapper.querySelector('select[name="notification_rule_email_field"] option[selected]').value)
      .toBe(fieldName);
  });

  it('uses unique condition control IDs across multiple rules', () => {
    const conditions = { operator: 'AND', conditions: [{ field: '', operator: 'equals', value: '' }] };
    const { wrapper } = renderRules([
      { event: 'approval_request', conditions },
      { event: 'stage_decision', conditions },
    ], true);
    const controls = [...wrapper.querySelectorAll('.conditions-editor [id]')];

    expect(controls.length).toBeGreaterThan(2);
    expect(new Set(controls.map(control => control.id)).size).toBe(controls.length);
    controls.forEach(control => {
      expect(wrapper.querySelector(`label[for="${control.id}"]`)).not.toBeNull();
    });
  });

  it('associates each checkbox label with its own rule', () => {
    const { wrapper } = renderRules([{ event: 'approval_request' }, { event: 'stage_decision' }]);
    const boxes = [...wrapper.querySelectorAll('input[name^="notification_rule_notify_"]')];

    expect(boxes).toHaveLength(6);
    expect(new Set(boxes.map(box => box.id)).size).toBe(boxes.length);
    boxes.forEach(box => {
      expect(wrapper.querySelector(`label[for="${box.id}"]`)).not.toBeNull();
    });
  });

  it('associates each scope, event, and subject label with its own rule', () => {
    const { wrapper } = renderRules([{ event: 'approval_request' }, { event: 'stage_decision' }]);
    for (const name of ['stage', 'event', 'subject_template', 'email_field', 'static_emails', 'notify_groups']) {
      const controls = [...wrapper.querySelectorAll(`[name="notification_rule_${name}"]`)];
      expect(controls).toHaveLength(2);
      expect(new Set(controls.map(control => control.id)).size).toBe(2);
      controls.forEach(control => {
        expect(wrapper.querySelector(`label[for="${control.id}"]`)).not.toBeNull();
      });
    }
  });

  it('ignores an untouched placeholder and retains it once configured', () => {
    const { builder, wrapper } = renderRules([]);

    expect(builder.readNotificationRulesFromPanel(wrapper)).toEqual([]);
    wrapper.querySelector('input[name="notification_rule_notify_submitter"]').checked = true;
    const rules = builder.readNotificationRulesFromPanel(wrapper);
    expect(rules).toHaveLength(1);
    expect(rules[0].notify_submitter).toBe(true);
  });

  it('retains a placeholder when its event is changed', () => {
    const { builder, wrapper } = renderRules([]);
    const event = wrapper.querySelector('select[name="notification_rule_event"]');
    event.value = 'stage_decision';

    expect(builder.readNotificationRulesFromPanel(wrapper)[0].event).toBe('stage_decision');
  });
});

describe('approval properties', () => {
  it('renders once when approval type rebuilds the properties panel', () => {
    const builder = Object.create(WorkflowBuilder.prototype);
    builder.store = createWorkflowBuilderStore();
    const node = { id: 'approval-1', type: 'approval', data: { approval_type: 'manager' } };
    builder.nodes = [node];
    builder.showEmptyProperties = vi.fn();
    builder.refreshValidationState = vi.fn();
    builder.showNodeProperties = vi.fn();
    builder.updateConnectionSelectionUI = vi.fn();
    builder.render = vi.fn();

    builder.updateNodeProperty(node.id, 'approval_type', 'group');

    expect(node.data.approval_type).toBe('group');
    expect(builder.showNodeProperties).toHaveBeenCalledWith(node);
    expect(builder.render).toHaveBeenCalledTimes(1);
  });

  it('refreshes the panel when the approval type changes', () => {
    const builder = Object.create(WorkflowBuilder.prototype);
    builder.store = createWorkflowBuilderStore();
    const node = { id: 'approval-1', type: 'approval', data: { approval_type: 'manager' } };
    builder.nodes = [node];
    builder.render = vi.fn();
    builder.selectNode = vi.fn();

    builder.updateNodeProperty(node.id, 'approval_type', 'group');

    expect(node.data.approval_type).toBe('group');
    expect(builder.selectNode).toHaveBeenCalledWith(node.id);
  });
});

describe('condition editor', () => {
  it('keeps malformed saved condition rows editable without throwing', () => {
    const builder = Object.create(WorkflowBuilder.prototype);
    const state = builder.getNormalizedTriggerConditions({
      operator: 7,
      conditions: [null, { field: 123, operator: false, value: 'ready' }],
    });

    expect(state).toEqual({
      operator: 'AND',
      conditions: [
        { field: '', operator: 'equals', value: '' },
        { field: '', operator: 'equals', value: 'ready' },
      ],
    });
  });

  it('retains a partially filled row for validation', () => {
    const builder = Object.create(WorkflowBuilder.prototype);
    const editor = document.createElement('div');
    editor.innerHTML = `
      <div class="trigger-condition-row">
        <select name="condition_field"><option value="" selected>Choose field</option></select>
        <select name="condition_operator"><option value="equals" selected>Equals</option></select>
        <input name="condition_value" value="test">
      </div>`;

    expect(builder.readConditionsFromEditor(editor)).toEqual({
      operator: 'AND',
      conditions: [{ field: '', operator: 'equals', value: 'test' }],
    });
  });
});
