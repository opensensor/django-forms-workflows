import { describe, expect, it } from 'vitest';
import { createBuilderStore } from '../../django_forms_workflows/static/django_forms_workflows/js/form-builder-store.js';

describe('createBuilderStore', () => {
  it('is a factory, not a singleton — each call returns an independent store', () => {
    const a = createBuilderStore();
    const b = createBuilderStore();

    a.setFields([{ field_name: 'text_1' }]);

    expect(a.fields).toEqual([{ field_name: 'text_1' }]);
    expect(b.fields).toEqual([]);
    expect(a).not.toBe(b);
  });

  it('defaults to empty fields/formSteps and a fieldIdCounter of 1', () => {
    const store = createBuilderStore();

    expect(store.fields).toEqual([]);
    expect(store.formSteps).toEqual([]);
    expect(store.fieldIdCounter).toBe(1);
  });

  it('accepts initial state', () => {
    const store = createBuilderStore({
      fields: [{ field_name: 'text_1' }],
      formSteps: [{ title: 'Step 1', fields: ['text_1'] }],
      fieldIdCounter: 5,
    });

    expect(store.fields).toEqual([{ field_name: 'text_1' }]);
    expect(store.formSteps).toEqual([{ title: 'Step 1', fields: ['text_1'] }]);
    expect(store.fieldIdCounter).toBe(5);
  });
});

describe('BuilderStore.setFields / setFormSteps', () => {
  it('setFields updates state and emits fields-changed', () => {
    const store = createBuilderStore();
    let received = null;
    store.addEventListener('fields-changed', (e) => { received = e.detail.fields; });

    store.setFields([{ field_name: 'text_1' }]);

    expect(store.fields).toEqual([{ field_name: 'text_1' }]);
    expect(received).toEqual([{ field_name: 'text_1' }]);
  });

  it('setFormSteps updates state and emits form-steps-changed', () => {
    const store = createBuilderStore();
    let received = null;
    store.addEventListener('form-steps-changed', (e) => { received = e.detail.formSteps; });

    store.setFormSteps([{ title: 'Step 1', fields: [] }]);

    expect(store.formSteps).toEqual([{ title: 'Step 1', fields: [] }]);
    expect(received).toEqual([{ title: 'Step 1', fields: [] }]);
  });
});

describe('BuilderStore.nextFieldId', () => {
  it('returns prefix_counter and increments the counter', () => {
    const store = createBuilderStore({ fieldIdCounter: 1 });

    expect(store.nextFieldId('text')).toBe('text_1');
    expect(store.nextFieldId('text')).toBe('text_2');
    expect(store.fieldIdCounter).toBe(3);
  });
});

describe('BuilderStore.seedFieldIdCounterFromFields', () => {
  it('seeds the counter one past the highest existing numeric suffix', () => {
    const store = createBuilderStore();
    store.seedFieldIdCounterFromFields([
      { field_name: 'text_1' },
      { field_name: 'email_3' },
      { field_name: 'date_2' },
    ]);

    expect(store.fieldIdCounter).toBe(4);
  });

  it('defaults to 1 when there are no fields yet', () => {
    const store = createBuilderStore({ fieldIdCounter: 99 });
    store.seedFieldIdCounterFromFields([]);

    expect(store.fieldIdCounter).toBe(1);
  });

  it('ignores field names that do not end in a number', () => {
    const store = createBuilderStore();
    store.seedFieldIdCounterFromFields([
      { field_name: 'customer_email' },
      { field_name: 'text_5' },
    ]);

    expect(store.fieldIdCounter).toBe(6);
  });

  it('does not crash on a field with no field_name', () => {
    const store = createBuilderStore();
    store.seedFieldIdCounterFromFields([{}, { field_name: 'text_2' }]);

    expect(store.fieldIdCounter).toBe(3);
  });
});

describe('BuilderStore.snapshot / restore', () => {
  it('snapshot captures fields and formSteps together', () => {
    const store = createBuilderStore({
      fields: [{ field_name: 'a' }],
      formSteps: [{ title: 'Step 1', fields: ['a'] }],
    });

    expect(store.snapshot()).toEqual(
      JSON.stringify({ fields: [{ field_name: 'a' }], formSteps: [{ title: 'Step 1', fields: ['a'] }] })
    );
  });

  it('restore replaces fields and formSteps and emits both change events', () => {
    const store = createBuilderStore({ fields: [{ field_name: 'old' }], formSteps: [] });
    const fieldsChanged = [];
    const formStepsChanged = [];
    store.addEventListener('fields-changed', (e) => fieldsChanged.push(e.detail.fields));
    store.addEventListener('form-steps-changed', (e) => formStepsChanged.push(e.detail.formSteps));

    const snapshot = JSON.stringify({
      fields: [{ field_name: 'restored' }],
      formSteps: [{ title: 'Step 1', fields: ['restored'] }],
    });
    store.restore(snapshot);

    expect(store.fields).toEqual([{ field_name: 'restored' }]);
    expect(store.formSteps).toEqual([{ title: 'Step 1', fields: ['restored'] }]);
    expect(fieldsChanged).toEqual([[{ field_name: 'restored' }]]);
    expect(formStepsChanged).toEqual([[{ title: 'Step 1', fields: ['restored'] }]]);
  });
});
