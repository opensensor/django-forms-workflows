import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const SOURCE_PATH = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '../../../django_forms_workflows/static/django_forms_workflows/js/form-builder.js',
);

// form-builder.js is loaded by the app as a classic <script> tag (not an ES
// module), so its class isn't importable directly. Evaluate the real,
// unmodified source inside a Function body — which gets its own scope we can
// `return FormBuilder` out of — rather than duplicating its logic in tests.
//
// Resolve the path via node:url's fileURLToPath rather than
// `new URL(..., import.meta.url)` — under the jsdom test environment, the
// global `URL` constructor is jsdom's own browser-spec implementation, and
// Node's fs functions don't recognize a URL built from it as a proper
// file:// URL.
export function loadFormBuilderClass() {
  const source = readFileSync(SOURCE_PATH, 'utf-8');
  return new Function(`${source}\nreturn FormBuilder;`)();
}
