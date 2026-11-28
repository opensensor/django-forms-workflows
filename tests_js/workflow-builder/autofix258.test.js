import { describe, expect, it, vi } from 'vitest';
import { WorkflowBuilder } from '../../django_forms_workflows/static/django_forms_workflows/js/workflow-builder.js';
import { createWorkflowBuilderStore } from '../../django_forms_workflows/static/django_forms_workflows/js/workflow-builder-store.js';

function renderRules(rules) {
  const builder = Object.create(WorkflowBuilder.prototype);
  builder.store = createWorkflowBuilderStore();
  builder.nodes = [];
  builder.fields = [];
  builder.groups = [];
  builder.buildConditionsEditor = vi.fn(() => '');
  const wrapper = document.createElement('div');
  wrapper.innerHTML = builder.buildNotificationRulesEditor({
    id: 'settings',
    data: { notification_rules: rules },
  });
  return { builder, wrapper };
}

describe('notification rule controls', () => {
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
    for (const name of ['stage', 'event', 'subject_template', 'email_field', 'static_emails']) {
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

describe('condition editor', () => {
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
