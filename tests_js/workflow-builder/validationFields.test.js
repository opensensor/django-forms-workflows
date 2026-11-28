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
