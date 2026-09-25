from django.apps import AppConfig


class LDAPLookupTestAppConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "tests.ldap_lookup_test_app"
    label = "workflows"
