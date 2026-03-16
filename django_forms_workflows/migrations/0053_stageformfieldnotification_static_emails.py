from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("django_forms_workflows", "0052_dynamic_assignee_and_form_field_notifications"),
    ]

    operations = [
        # Allow email_field to be blank — rules may now use only static_emails
        migrations.AlterField(
            model_name="stageformfieldnotification",
            name="email_field",
            field=models.CharField(
                blank=True,
                default="",
                help_text=(
                    "Slug of the form field whose value is the recipient email address. "
                    "The value is read from the submission's form_data at send time. "
                    "Leave blank if you only need static recipients."
                ),
                max_length=200,
            ),
        ),
        # Add static_emails for fixed addresses notified on every matching submission
        migrations.AddField(
            model_name="stageformfieldnotification",
            name="static_emails",
            field=models.CharField(
                blank=True,
                default="",
                help_text=(
                    "Comma-separated list of fixed email addresses to notify. "
                    "These recipients are always included regardless of form data. "
                    "Can be combined with Email Field to notify both static and dynamic addresses."
                ),
                max_length=1000,
            ),
        ),
    ]

