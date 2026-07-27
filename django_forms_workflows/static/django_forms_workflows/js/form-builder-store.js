/**
 * Single owner of Form Builder state, shared across extracted modules.
 * Factory (not a singleton) since admin inlines can put two builders on one
 * page. Extends EventTarget so modules can react to changes instead of
 * closing over the whole FormBuilder instance.
 */
export class BuilderStore extends EventTarget {
    constructor({ fields = [], formSteps = [], fieldIdCounter = 1 } = {}) {
        super();
        this.fields = fields;
        this.formSteps = formSteps;
        this.fieldIdCounter = fieldIdCounter;
    }

    setFields(fields) {
        this.fields = fields;
        this.dispatchEvent(new CustomEvent('fields-changed', { detail: { fields } }));
    }

    setFormSteps(formSteps) {
        this.formSteps = formSteps;
        this.dispatchEvent(new CustomEvent('form-steps-changed', { detail: { formSteps } }));
    }

    nextFieldId(prefix) {
        const id = `${prefix}_${this.fieldIdCounter}`;
        this.fieldIdCounter += 1;
        return id;
    }

    // Ports 445790f: seeds past existing field names so newly-generated
    // ones can't collide (call after loading fields from a form/template).
    seedFieldIdCounterFromFields(fields) {
        const highest = fields.reduce((max, field) => {
            const match = /_(\d+)$/.exec(field.field_name || '');
            return match ? Math.max(max, parseInt(match[1], 10)) : max;
        }, 0);
        this.fieldIdCounter = highest + 1;
    }

    snapshot() {
        return JSON.stringify({ fields: this.fields, formSteps: this.formSteps });
    }

    restore(snapshotJson) {
        const { fields, formSteps } = JSON.parse(snapshotJson);
        this.setFields(fields);
        this.setFormSteps(formSteps);
    }
}

export function createBuilderStore(initial) {
    return new BuilderStore(initial);
}
