import { afterEach, describe, expect, it, vi } from 'vitest';
import { WorkflowBuilder } from '../../django_forms_workflows/static/django_forms_workflows/js/workflow-builder.js';

afterEach(() => {
  vi.restoreAllMocks();
  document.body.innerHTML = '';
});

describe('workflow builder autofix review', () => {
  it('retains a newly added notification rule when the panel is read', () => {
    const builder = Object.create(WorkflowBuilder.prototype);
    const container = document.createElement('div');
    container.innerHTML = `
      <div class="notification-rule-card">
        <select name="notification_rule_stage"><option value="" selected>Workflow</option></select>
        <select name="notification_rule_event"><option value="approval_request" selected>Approval</option></select>
        <input name="notification_rule_subject_template" value="">
        <input name="notification_rule_notify_submitter" type="checkbox">
        <select name="notification_rule_email_field"><option value="" selected>None</option></select>
        <input name="notification_rule_static_emails" value="">
        <input name="notification_rule_notify_stage_assignees" type="checkbox">
        <input name="notification_rule_notify_stage_groups" type="checkbox">
        <select name="notification_rule_notify_groups" multiple></select>
      </div>`;

    const rules = builder.readNotificationRulesFromPanel(container);

    expect(rules).toHaveLength(1);
    expect(rules[0].event).toBe('approval_request');
  });

  it('applies the final drag position when mouseup precedes the animation frame', () => {
    const builder = Object.create(WorkflowBuilder.prototype);
    const node = { id: 'stage-1', x: 10, y: 20 };
    builder.render = vi.fn();
    builder.bringNodeToFront = vi.fn();
    builder.clientToCanvas = (x, y) => [x, y];
    const requestFrame = vi.spyOn(window, 'requestAnimationFrame').mockReturnValue(42);
    const cancelFrame = vi.spyOn(window, 'cancelAnimationFrame').mockImplementation(() => {});

    builder.startDragNode({ button: 0, clientX: 20, clientY: 30, preventDefault: vi.fn() }, node);
    document.dispatchEvent(new MouseEvent('mousemove', { clientX: 50, clientY: 70 }));
    document.dispatchEvent(new MouseEvent('mouseup'));

    expect(requestFrame).toHaveBeenCalledTimes(1);
    expect(cancelFrame).toHaveBeenCalledWith(42);
    expect([node.x, node.y]).toEqual([40, 60]);
    expect(builder.isDraggingNode).toBe(false);
  });
});
