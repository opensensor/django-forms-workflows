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

