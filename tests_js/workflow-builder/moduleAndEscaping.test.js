import { describe, expect, it } from 'vitest';
import { WorkflowBuilder } from '../../django_forms_workflows/static/django_forms_workflows/js/workflow-builder.js';

function createInstance() {
  return Object.create(WorkflowBuilder.prototype);
}

describe('WorkflowBuilder module wiring', () => {
  it('is importable as a real ES export (not just a classic-script global)', () => {
    expect(typeof WorkflowBuilder).toBe('function');
    expect(typeof WorkflowBuilder.prototype.getNodeDescription).toBe('function');
    expect(typeof WorkflowBuilder.prototype.buildFormProperties).toBe('function');
  });
});

describe('WorkflowBuilder#getNodeDescription — escaping regression', () => {
  const payload = '"><script>alert(1)</script>';

  it('escapes workflow_settings name_label/notification_cadence/notification_cadence_form_field', () => {
    const instance = createInstance();
    const node = {
      type: 'workflow_settings',
      data: {
        name_label: payload,
        notification_cadence: 'form_field_date',
        notification_cadence_form_field: payload,
      },
    };

    const html = instance.getNodeDescription(node);

    expect(html).not.toContain('<script>alert');
  });

  it('escapes stage assignee_form_field, approval_logic, and approve_label', () => {
    const instance = createInstance();
    const node = {
      type: 'stage',
      data: {
        assignee_form_field: payload,
        approval_logic: payload,
        approval_groups: [{ id: 1 }],
        approve_label: payload,
      },
    };

    const html = instance.getNodeDescription(node);

    expect(html).not.toContain('<script>alert');
  });

  it('escapes condition field/operator/value', () => {
    const instance = createInstance();
    const node = {
      type: 'condition',
      data: { field: payload, operator: payload, value: payload },
    };

    const html = instance.getNodeDescription(node);

    expect(html).not.toContain('<script>alert');
  });

  it('escapes action action_type/trigger', () => {
    const instance = createInstance();
    const node = {
      type: 'action',
      data: { action_type: payload, trigger: payload },
    };

    const html = instance.getNodeDescription(node);

    expect(html).not.toContain('<script>alert');
  });

  it('escapes email email_to/email_to_field', () => {
    const instance = createInstance();
    const node = {
      type: 'email',
      data: { email_to: payload, email_to_field: payload },
    };

    const html = instance.getNodeDescription(node);

    expect(html).not.toContain('<script>alert');
  });

  it('escapes sub_workflow sub_workflow_name/count_field', () => {
    const instance = createInstance();
    const node = {
      type: 'sub_workflow',
      data: { sub_workflow_name: payload, count_field: payload },
    };

    const html = instance.getNodeDescription(node);

    expect(html).not.toContain('<script>alert');
  });
});

describe('WorkflowBuilder#buildFormProperties — escaping regression', () => {
  it('escapes field.name, field.type, and field.prefill_source in the field list', () => {
    const instance = createInstance();
    const payload = '"><script>alert(1)</script>';
    const node = {
      id: 'form_1',
      data: {
        is_initial: true,
        form_name: 'Test Form',
        field_count: 1,
        fields: [
          {
            label: payload,
            name: payload,
            type: payload,
            prefill_source: payload,
          },
        ],
        has_more_fields: false,
      },
    };

    const html = instance.buildFormProperties(node);

    expect(html).not.toContain('<script>alert');
  });
});
