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
5. **Ensure tests pass**: `pytest`
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
├── tests/                      # Test suite
├── example_project/            # Example Django project
├── setup.py                    # Package configuration
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

