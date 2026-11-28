import { afterEach, describe, expect, it, vi } from 'vitest';
import { WorkflowBuilder } from '../../django_forms_workflows/static/django_forms_workflows/js/workflow-builder.js';
import { createWorkflowBuilderStore } from '../../django_forms_workflows/static/django_forms_workflows/js/workflow-builder-store.js';

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
    builder.store = createWorkflowBuilderStore();
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

  it('moves only the dragged node and its incident paths during a frame', () => {
    const builder = Object.create(WorkflowBuilder.prototype);
    builder.store = createWorkflowBuilderStore();
    const node = { id: 'a', x: 10, y: 20 };
    builder.connections = [{ from: 'a', to: 'b' }, { from: 'c', to: 'b' }];
    builder.transformWrapper = document.createElement('div');
    builder.transformWrapper.innerHTML = '<div class="workflow-node" data-node-id="a"></div>';
    builder.svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    for (const [index, cls] of [[0, 'connection-backdrop'], [0, 'connection-line'], [0, 'connection-hitbox'], [1, 'connection-line']]) {
      const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      path.setAttribute('class', cls);
      path.setAttribute('data-connection-index', index);
      path.setAttribute('d', 'original');
      builder.svg.appendChild(path);
    }
    builder.getConnectionPointPosition = vi.fn((id, point) =>
      id === 'a' && point === 'output' ? { x: 30, y: 40 } : { x: 100, y: 50 });
    builder.render = vi.fn();
    builder.bringNodeToFront = vi.fn();
    builder.clientToCanvas = (x, y) => [x, y];
    let frame;
    vi.spyOn(window, 'requestAnimationFrame').mockImplementation(callback => { frame = callback; return 42; });

    builder.startDragNode({ button: 0, clientX: 20, clientY: 30, preventDefault: vi.fn() }, node);
    document.dispatchEvent(new MouseEvent('mousemove', { clientX: 50, clientY: 70 }));
    frame();

    expect(builder.render).toHaveBeenCalledTimes(1);
    expect([node.x, node.y]).toEqual([40, 60]);
    expect(builder.transformWrapper.firstElementChild.style.left).toBe('40px');
    expect(builder.transformWrapper.firstElementChild.style.top).toBe('60px');
    const expectedPath = builder.createConnectionPath(60, 80, 100, 50);
    expect([...builder.svg.querySelectorAll('[data-connection-index="0"]')].map(path => path.getAttribute('d')))
      .toEqual([expectedPath, expectedPath, expectedPath]);
    expect(builder.svg.querySelector('[data-connection-index="1"]').getAttribute('d')).toBe('original');
    expect(builder.getConnectionPointPosition).toHaveBeenCalledTimes(2);

    document.dispatchEvent(new MouseEvent('mouseup'));
    expect(builder.render).toHaveBeenCalledTimes(2);
  });
});
