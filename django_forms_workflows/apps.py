"""
Django Forms Workflows App Configuration
"""

from django.apps import AppConfig


class DjangoFormsWorkflowsConfig(AppConfig):
    """App configuration for Django Forms Workflows"""

    default_auto_field = "django.db.models.BigAutoField"
    name = "django_forms_workflows"
    verbose_name = "Forms Workflows"

    def ready(self):
        """
        Import signal handlers and perform app initialization.
        """
        # Import signals to register handlers
        from . import signals  # noqa: F401
