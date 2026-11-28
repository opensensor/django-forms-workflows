import { describe, expect, it } from 'vitest';
import { WorkflowBuilder } from '../../django_forms_workflows/static/django_forms_workflows/js/workflow-builder.js';
import { createWorkflowBuilderStore } from '../../django_forms_workflows/static/django_forms_workflows/js/workflow-builder-store.js';

describe('approval field validation', () => {
  it('detects one field assigned by ID and name to different stages', () => {
    const builder = Object.create(WorkflowBuilder.prototype);
    builder.store = createWorkflowBuilderStore();
    builder.fields = [{ id: 7, field_name: 'notes', field_label: 'Notes' }];
    builder.groups = [];
    builder.forms = [];
    builder.workflowTargets = [];
    builder.nodes = [
      {
        id: 'stage-1', type: 'stage', data: {
          name: 'First', requires_manager_approval: true,
          approval_fields: [{ id: 7, field_name: 'notes' }],
        },
      },
      {
        id: 'stage-2', type: 'stage', data: {
          name: 'Second', requires_manager_approval: true,
          approval_fields: [{ field_name: 'notes' }],
        },
      },
    ];

    const errors = builder.validateWorkflow().errors;

    expect(errors.filter(error => error.includes('already assigned to First'))).toHaveLength(1);
  });
});

describe('condition validation', () => {
  it('accepts supported operators and empty string comparison values', () => {
    const builder = Object.create(WorkflowBuilder.prototype);
    const group = { operator: 'AND', conditions: [{ field: 'notes', operator: 'in', value: '' }] };

    expect(builder.validateConditionGroup(group, 'Trigger conditions')).toEqual([]);
  });

  it('puts malformed conditions into the builder validation state', () => {
    const builder = Object.create(WorkflowBuilder.prototype);
    builder.store = createWorkflowBuilderStore();
    builder.fields = [];
    builder.groups = [];
    builder.forms = [];
    builder.workflowTargets = [];
    builder.nodes = [{
      id: 'settings', type: 'workflow_settings', data: {
        trigger_conditions: { operator: 'AND', conditions: [{ field: '', operator: 'greater_than', value: 2 }] },
      },
    }];

    const result = builder.validateWorkflow();

    expect(result.nodeIssues.settings.errors).toEqual(expect.arrayContaining([
      expect.stringContaining('has no field selected'),
      expect.stringContaining('has an unknown operator'),
    ]));
  });
});
