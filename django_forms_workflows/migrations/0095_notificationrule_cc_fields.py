from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("django_forms_workflows", "0094_formfield_show_help_text_in_detail"),
    ]

    operations = [
        migrations.AddField(
            model_name="notificationrule",
            name="cc_email_field",
            field=models.CharField(
                blank=True,
                default="",
                help_text=(
                    "Form field slug whose submitted value is a CC email "
                    "address. Resolved from form_data at send time "
                    "(varies per submission)."
                ),
                max_length=200,
            ),
        ),
        migrations.AddField(
            model_name="notificationrule",
            name="cc_static_emails",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Comma-separated fixed CC email addresses.",
                max_length=1000,
            ),
        ),
    ]
