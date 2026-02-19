"""
Context processors for django_forms_workflows.
"""

from django.conf import settings


def forms_workflows(request):
    """
    Inject package-level settings into every template context.

    Adds:
        site_name (str): Human-readable name of the site, used in page
            titles, the navbar brand, and the footer.  Configured via::

                FORMS_WORKFLOWS = {
                    'SITE_NAME': 'My Organisation Workflows',
                    ...
                }

            Defaults to ``"Django Forms Workflows"`` when not set.
    """
    fw_settings = getattr(settings, "FORMS_WORKFLOWS", {})
    return {
        "site_name": fw_settings.get("SITE_NAME", "Django Forms Workflows"),
    }
