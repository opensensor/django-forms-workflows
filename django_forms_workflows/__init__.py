"""
Django Forms Workflows
Enterprise-grade, database-driven form builder with approval workflows
"""

try:
    from importlib.metadata import version as _pkg_version

    __version__ = _pkg_version("django-forms-workflows")
except Exception:
    # Package not yet installed (e.g. local checkout without pip install -e .)
    __version__ = "unknown"

__author__ = "Django Forms Workflows Contributors"
__license__ = "LGPL-3.0-only"

default_app_config = "django_forms_workflows.apps.DjangoFormsWorkflowsConfig"
