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
  it('keeps unknown saved fields visible for correction', () => {
    const builder = Object.create(WorkflowBuilder.prototype);
    builder.fields = [{ field_name: 'known', field_label: 'Known' }];
    const markup = builder.buildConditionsEditor({
      title: 'Trigger conditions',
      conditions: { field: 'removed', operator: 'equals', value: 'ready' },
      onChangeHandler: '',
      editorKind: 'trigger',
    });
    const wrapper = document.createElement('div');
    wrapper.innerHTML = markup;

    expect(wrapper.querySelector('select[name="condition_field"]').value).toBe('removed');
    expect(wrapper.querySelector('option[data-invalid="true"]').textContent).toContain('removed');
  });

  it('does not render malformed stage order as markup', () => {
    const builder = Object.create(WorkflowBuilder.prototype);
    const description = builder.getNodeDescription({ type: 'stage', data: { order: '1<script>' } });

    expect(description).toContain('Stage ?');
    expect(description).not.toContain('<script>');
    expect(description).not.toContain('1<script>');
  });

  it('accepts saved single conditions, including the server default operator', () => {
    const builder = Object.create(WorkflowBuilder.prototype);
    builder.fields = [{ field_name: 'notes' }];

    expect(builder.validateConditionGroup({ field: 'notes', value: 'ready' }, 'Trigger conditions')).toEqual([]);
    expect(builder.validateConditionGroup({ field: 'notes', operator: 'contains', value: 'ready' }, 'Trigger conditions')).toEqual([]);
    expect(builder.validateConditionGroup({ operator: 'equals', value: 'ready' }, 'Trigger conditions'))
      .toEqual(['Trigger conditions: conditions must be a list.']);
  });

  it.each([
    { operator: 'contains', condition: { field: 'notes', operator: 'contains', value: '' } },
    { operator: 'equals', condition: { field: 'notes', operator: 'equals', value: '' } },
    { operator: 'not_equals', condition: { field: 'notes', operator: 'not_equals', value: '' } },
    { operator: 'gt', condition: { field: 'notes', operator: 'gt', value: '' } },
    { operator: 'gte', condition: { field: 'notes', operator: 'gte', value: '' } },
    { operator: 'lt', condition: { field: 'notes', operator: 'lt', value: '' } },
    { operator: 'lte', condition: { field: 'notes', operator: 'lte', value: '' } },
    { operator: 'in', condition: { field: 'notes', operator: 'in', value: '' } },
    { operator: 'is_empty', condition: { field: 'notes', operator: 'is_empty' } },
    { operator: 'not_empty', condition: { field: 'notes', operator: 'not_empty' } },
  ])('accepts supported operator $operator', ({ condition }) => {
    const builder = Object.create(WorkflowBuilder.prototype);
    builder.fields = [{ field_name: 'notes' }];
    const group = { operator: 'AND', conditions: [condition] };

    expect(builder.validateConditionGroup(group, 'Trigger conditions')).toEqual([]);
  });

  it('reports an unknown field and preserves an invalid match mode for correction', () => {
    const builder = Object.create(WorkflowBuilder.prototype);
    builder.fields = [{ field_name: 'notes', field_label: 'Notes' }];
    const group = { operator: 'XOR', conditions: [{ field: 'removed', operator: 'equals', value: 'ready' }] };

    expect(builder.validateConditionGroup(group, 'Trigger conditions')).toEqual(expect.arrayContaining([
      expect.stringContaining('match mode must be AND or OR'),
      expect.stringContaining('references unknown field "removed"'),
    ]));
    const wrapper = document.createElement('div');
    wrapper.innerHTML = builder.buildConditionsEditor({
      title: 'Trigger conditions', conditions: group, onChangeHandler: '', editorKind: 'trigger',
    });
    expect(wrapper.querySelector('select[name="condition_group_operator"]').value).toBe('XOR');
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
