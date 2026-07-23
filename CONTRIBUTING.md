# Contributing to Django Forms Workflows

Thank you for your interest in contributing! This document provides guidelines and instructions for contributing.

## Code of Conduct

This project adheres to a code of conduct. By participating, you are expected to uphold this code. Please report unacceptable behavior to the project maintainers.

## How Can I Contribute?

### Reporting Bugs

Before creating bug reports, please check the issue tracker to avoid duplicates. When creating a bug report, include:

- **Clear title and description**
- **Steps to reproduce** the issue
- **Expected behavior** vs **actual behavior**
- **Django version**, **Python version**, and **package version**
- **Error messages** and **stack traces**
- **Configuration** (sanitized, no secrets!)

### Suggesting Enhancements

Enhancement suggestions are tracked as GitHub issues. When creating an enhancement suggestion, include:

- **Clear title and description**
- **Use case** - why is this enhancement needed?
- **Proposed solution** - how should it work?
- **Alternatives considered**
- **Examples** from other projects (if applicable)

### Pull Requests

1. **Fork the repository** and create your branch from `main`
2. **Make your changes** following the coding standards
3. **Add tests** for new functionality
4. **Update documentation** as needed
5. **Ensure tests pass**: `pytest` (and `npm test` if you touched front-end js`)
6. **Ensure code quality**: `black .`, `flake8`, `isort .`
7. **Commit with clear messages**
8. **Push to your fork** and submit a pull request

## Development Setup

### 1. Clone the Repository

```bash
git clone https://github.com/opensensor/django-forms-workflows.git
cd django-forms-workflows
```

### 2. Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Development Dependencies

```bash
pip install -e ".[dev,all]"
```

### 4. Run Tests

```bash
pytest
```

### 5. Run Code Quality Checks

```bash
# Format code
black .

# Sort imports
isort .

# Lint code
flake8

# Type checking
mypy django_forms_workflows
```

### 6. (Optional) Install JS Test Tooling

Only needed if you're changing the visual Form/Workflow Builder's client-side
JS (`django_forms_workflows/static/django_forms_workflows/js/`). Requires
Node.js 20+ / npm — an `.nvmrc` is committed at the repo root, so `nvm use`
picks the right version automatically if you have nvm installed.

```bash
npm install
npm test          # run once
npm run test:watch  # re-run on change, useful while iterating
```

Test files live in `tests_js/`, its own top-level directory paralleling
`tests/`. Within it, one subfolder per source file under
`django_forms_workflows/static/django_forms_workflows/js/`, each holding one test 
file per method/behavior under test.

There's a `helpers/` subfolder for anything shared across that
source file's tests (e.g. `tests_js/form-builder/helpers/loadFormBuilderClass.js`,
which loads the real, un-exported class for testing — see the example below).

## Coding Standards

### Python Style

- Follow [PEP 8](https://www.python.org/dev/peps/pep-0008/)
- Use [Black](https://black.readthedocs.io/) for formatting
- Use [isort](https://pycqa.github.io/isort/) for import sorting
- Maximum line length: 100 characters

### Django Conventions

- Follow [Django coding style](https://docs.djangoproject.com/en/dev/internals/contributing/writing-code/coding-style/)
- Use Django's built-in features when possible
- Avoid reinventing the wheel

### JavaScript Style

- Vanilla JS, no framework or bundler dependency — native ES modules
  (`<script type="module">`) only
- New client-side logic for the visual builders should be added as an
  importable module with a corresponding Vitest test under
  `tests_js/form-builder/` or `tests_js/workflow-builder/` (as appropriate),
  rather than appended to the existing `form-builder.js`/`workflow-builder.js`
  monoliths

### Documentation

- **Docstrings** for all public modules, classes, and functions
- **Type hints** for function parameters and return values
- **Comments** for complex logic
- **README updates** for new features
- **Changelog entries** for all changes

### Testing

- **Unit tests** for all new functionality
- **Integration tests** for workflows
- **Test coverage** should not decrease
- **Test naming**: `test_<what>_<condition>_<expected>`

Example:
```python
def test_form_submission_with_approval_creates_tasks():
    """Test that submitting a form with approval workflow creates approval tasks."""
    # Arrange
    form = FormDefinition.objects.create(...)
    workflow = WorkflowDefinition.objects.create(...)
    
    # Act
    submission = FormSubmission.objects.create(...)
    
    # Assert
    assert submission.approval_tasks.count() > 0
```

JS changes under `django_forms_workflows/static/django_forms_workflows/js/`
follow the same "add tests with the change" expectation, via Vitest (see
"Development Setup" above). One file per method/behavior under test, in the
matching `tests_js/<source-name>/` folder — e.g.
`tests_js/form-builder/addFieldAtPosition.test.js`:

```js
import { describe, expect, it, vi } from 'vitest';
import { loadFormBuilderClass } from './helpers/loadFormBuilderClass.js';

describe('FormBuilder#addFieldAtPosition', () => {
  it('inserts correctly on an empty canvas, when SortableJS reports an out-of-range drop position', () => {
    // Arrange / Act / Assert
  });
});
```

`form-builder.js`/`workflow-builder.js` are loaded as classic `<script>`
tags, not ES modules, so their classes have no `export` —  For now, `loadFormBuilderClass()`
(and its future `loadWorkflowBuilderClass()` counterpart) evaluates the real,
unmodified source in a function scope and returns the class from it, rather
than duplicating any logic in the test.

## Project Structure

```
django-forms-workflows/
├── django_forms_workflows/      # Main package
│   ├── __init__.py
│   ├── models.py               # Core models
│   ├── admin.py                # Django admin configuration
│   ├── views.py                # Views
│   ├── forms.py                # Form classes
│   ├── urls.py                 # URL configuration
│   ├── data_sources/           # Data source abstraction
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── user_source.py
│   │   ├── ldap_source.py
│   │   └── database_source.py
│   ├── templates/              # Templates
│   ├── static/                 # Static files
│   ├── migrations/             # Database migrations
│   └── management/             # Management commands
├── docs/                       # Documentation
├── tests/                      # Python test suite (pytest)
├── tests_js/                   # JS test suite (Vitest); one subfolder per source file, e.g. tests_js/form-builder/
├── example_project/            # Example Django project
├── pyproject.toml               # Package configuration
├── package.json                # JS test tooling (Vitest) — dev-only, no runtime JS deps
├── vitest.config.js
├── README.md
├── LICENSE
├── CHANGELOG.md
└── CONTRIBUTING.md
```

## Adding a New Data Source

To add a new data source:

1. Create a new file in `django_forms_workflows/data_sources/`
2. Subclass `DataSource`
3. Implement `get_value()` method
4. Register in `__init__.py`

Example:

```python
# django_forms_workflows/data_sources/api_source.py

from .base import DataSource
import requests

class APIDataSource(DataSource):
    def get_value(self, user, field_name, **kwargs):
        api_url = kwargs.get('api_url')
        response = requests.get(f"{api_url}/{field_name}")
        return response.json().get('value')
    
    def is_available(self):
        return True
```

```python
# django_forms_workflows/data_sources/__init__.py

from .api_source import APIDataSource

registry.register('api', APIDataSource)
```

## Release Process

1. Update version in `__init__.py` and `setup.py`
2. Update `CHANGELOG.md`
3. Create a git tag: `git tag v0.2.0`
4. Push tag: `git push origin v0.2.0`
5. Build package: `python setup.py sdist bdist_wheel`
6. Upload to PyPI: `twine upload dist/*`

## Questions?

Feel free to open an issue or start a discussion on GitHub!

## License

By contributing, you agree that your contributions will be licensed under the GNU Lesser General Public License v3.0 (LGPLv3).

