from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("django_forms_workflows", "0096_notificationlog_cc_bcc_emails"),
    ]

    operations = [
        migrations.AddField(
            model_name="notificationlog",
            name="rfc2822_message_id",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                help_text="Message-ID stamped on the MIME message; join key to the Gmail delivery log.",
                max_length=255,
            ),
        ),
        migrations.AddField(
            model_name="notificationlog",
            name="delivery_state",
            field=models.CharField(
                choices=[
                    ("unconfirmed", "Unconfirmed"),
                    ("delivered", "Delivered"),
                    ("bounced", "Bounced"),
                    ("retried", "Retried"),
                    ("exhausted", "Exhausted (retries spent)"),
                ],
                db_index=True,
                default="unconfirmed",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="notificationlog",
            name="delivery_checked_at",
            field=models.DateTimeField(
                blank=True,
                help_text="Last time delivery reconciliation examined this row.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="notificationlog",
            name="delivery_detail",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Reconciliation outcome detail (smtp code / relay error / reason).",
                max_length=500,
            ),
        ),
        migrations.AddIndex(
            model_name="notificationlog",
            index=models.Index(
                fields=["status", "delivery_state", "created_at"],
                name="notiflog_recon_idx",
            ),
        ),
    ]
