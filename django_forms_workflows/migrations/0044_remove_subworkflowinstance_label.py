from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("django_forms_workflows", "0043_fix_form_data_decimal_encoding"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="subworkflowinstance",
            name="label",
        ),
    ]

