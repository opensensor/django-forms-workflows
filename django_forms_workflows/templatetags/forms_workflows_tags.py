"""
Custom template tags and filters for django_forms_workflows.
"""

from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """
    Get an item from a dictionary by key.

    Usage in templates:
        {{ my_dict|get_item:key_variable }}

    This is useful when you need to access a dictionary value
    using a variable as the key, which isn't possible with
    standard Django template syntax.
    """
    if dictionary is None:
        return None
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    return None


@register.inclusion_tag(
    "django_forms_workflows/form_categories.html",
    takes_context=True,
)
def render_form_categories(
    context, grouped_forms, form_url_name="forms_workflows:form_submit"
):
    """
    Render a Bootstrap 5 accordion of forms grouped by category.

    Usage::

        {% load forms_workflows_tags %}
        {% render_form_categories grouped_forms %}

        {# Override the submit URL name for projects that use a different namespace: #}
        {% render_form_categories grouped_forms form_url_name="form_submit" %}

    ``grouped_forms`` must be an iterable of ``(FormCategory | None, [FormDefinition, ...])``
    tuples as produced by the ``form_list`` view.

    ``form_url_name`` is the Django URL name used to build the "Fill Out Form" link.
    Defaults to ``forms_workflows:form_submit`` (the package's own namespace).
    """
    return {
        "grouped_forms": grouped_forms,
        "form_url_name": form_url_name,
        # Forward request so the inclusion template can call {% url %} correctly
        "request": context.get("request"),
    }
