from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("django_forms_workflows", "0095_notificationrule_cc_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="notificationlog",
            name="cc_emails",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Comma-separated CC addresses included on this send.",
            ),
        ),
        migrations.AddField(
            model_name="notificationlog",
            name="bcc_emails",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Comma-separated BCC addresses included on this send.",
            ),
        ),
    ]
