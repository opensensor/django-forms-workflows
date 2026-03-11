import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("django_forms_workflows", "0030_formfield_phone_type"),
    ]

    operations = [
        # 1. SubWorkflowDefinition
        migrations.CreateModel(
            name="SubWorkflowDefinition",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                (
                    "parent_workflow",
                    models.OneToOneField(
                        help_text="The parent workflow that spawns sub-workflows",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sub_workflow_config",
                        to="django_forms_workflows.workflowdefinition",
                    ),
                ),
                (
                    "sub_workflow",
                    models.ForeignKey(
                        help_text="Workflow definition used for each sub-workflow instance",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="used_as_sub_workflow",
                        to="django_forms_workflows.workflowdefinition",
                    ),
                ),
                (
                    "count_field",
                    models.CharField(
                        help_text="Form field name whose integer value determines how many sub-workflows to spawn (e.g. 'number_of_payments')",
                        max_length=100,
                    ),
                ),
                (
                    "label_template",
                    models.CharField(
                        default="Sub-workflow {index}",
                        help_text="Label for each instance — use {index} as placeholder (e.g. 'Payment {index}')",
                        max_length=100,
                    ),
                ),
                (
                    "trigger",
                    models.CharField(
                        choices=[
                            ("on_submission", "On Submission"),
                            ("on_approval", "After Parent Approval"),
                        ],
                        default="on_approval",
                        help_text="When to spawn sub-workflow instances",
                        max_length=20,
                    ),
                ),
                (
                    "data_prefix",
                    models.CharField(
                        blank=True,
                        help_text="Form field prefix to scope data per instance (e.g. 'payment' matches payment_type_1, payment_amount_1 …)",
                        max_length=100,
                    ),
                ),
            ],
            options={
                "verbose_name": "Sub-workflow Definition",
                "verbose_name_plural": "Sub-workflow Definitions",
            },
        ),
        # 2. SubWorkflowInstance
        migrations.CreateModel(
            name="SubWorkflowInstance",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                (
                    "parent_submission",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sub_workflows",
                        to="django_forms_workflows.formsubmission",
                    ),
                ),
                (
                    "definition",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="instances",
                        to="django_forms_workflows.subworkflowdefinition",
                    ),
                ),
                ("index", models.PositiveIntegerField(help_text="Which instance (1, 2, 3 …)")),
                ("label", models.CharField(max_length=200)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("in_progress", "In Progress"),
                            ("approved", "Approved"),
                            ("rejected", "Rejected"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "verbose_name": "Sub-workflow Instance",
                "verbose_name_plural": "Sub-workflow Instances",
                "ordering": ["index"],
                "unique_together": {("parent_submission", "definition", "index")},
            },
        ),
        # 3. FK on ApprovalTask
        migrations.AddField(
            model_name="approvaltask",
            name="sub_workflow_instance",
            field=models.ForeignKey(
                blank=True,
                help_text="Sub-workflow instance this task belongs to (sub-workflow tasks only)",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="approval_tasks",
                to="django_forms_workflows.subworkflowinstance",
            ),
        ),
    ]

