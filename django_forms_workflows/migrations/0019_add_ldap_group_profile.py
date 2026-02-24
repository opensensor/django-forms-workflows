from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("django_forms_workflows", "0018_add_form_category_parent"),
    ]

    operations = [
        migrations.CreateModel(
            name="LDAPGroupProfile",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "ldap_dn",
                    models.CharField(
                        blank=True,
                        help_text="Full Distinguished Name of this group in LDAP",
                        max_length=500,
                    ),
                ),
                (
                    "last_synced",
                    models.DateTimeField(
                        auto_now=True,
                        help_text="Last time this group was seen during an LDAP sync",
                    ),
                ),
                (
                    "group",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ldap_profile",
                        to="auth.group",
                    ),
                ),
            ],
            options={
                "verbose_name": "LDAP Group Profile",
                "verbose_name_plural": "LDAP Group Profiles",
            },
        ),
    ]

