from django.conf import settings
from django.db import models


class LDAPLookupEnabledForm(models.Model):
    """Test double for the host project's optional form configuration."""

    form = models.OneToOneField(
        "django_forms_workflows.FormDefinition",
        on_delete=models.CASCADE,
        related_name="ldap_lookup_config",
    )
    enabled_at = models.DateTimeField(auto_now_add=True)
    enabled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    notes = models.CharField(max_length=200, blank=True)

    class Meta:
        app_label = "workflows"

    def __str__(self):
        return f"LDAP lookup enabled for: {self.form}"
