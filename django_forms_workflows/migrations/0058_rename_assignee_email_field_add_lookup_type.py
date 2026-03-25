"""
Rename assignee_email_field → assignee_form_field and add assignee_lookup_type.

This generalises the dynamic-assignee feature so a workflow stage can resolve
a form-field value to a system user via email, username, full-name match, or
LDAP lookup — not only by email address.

Existing data in assignee_email_field is preserved via the rename; the new
assignee_lookup_type defaults to "email" so current behaviour is unchanged.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("django_forms_workflows", "0057_add_currency_field_type"),
    ]

    operations = [
        # 1. Rename the column (preserves existing data)
        migrations.RenameField(
            model_name="workflowstage",
            old_name="assignee_email_field",
            new_name="assignee_form_field",
        ),
        # 2. Update help_text on the renamed field
        migrations.AlterField(
            model_name="workflowstage",
            name="assignee_form_field",
            field=models.CharField(
                blank=True,
                default="",
                help_text=(
                    "Form field slug whose submitted value identifies the assignee. "
                    "When set, the workflow engine resolves the assignee using the "
                    "lookup type below and assigns this stage's task directly to them "
                    "(bypassing the approval groups). Falls back to group assignment "
                    "if the field is empty or no matching user is found."
                ),
                max_length=200,
            ),
        ),
        # 3. Add validate_assignee_group flag
        migrations.AddField(
            model_name="workflowstage",
            name="validate_assignee_group",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "When a dynamic assignee is resolved from a form field, require "
                    "that the user belongs to at least one of this stage's approval "
                    "groups. If unchecked, any resolved user can be assigned regardless "
                    "of group membership."
                ),
            ),
        ),
        # 4. Add allow_reassign flag
        migrations.AddField(
            model_name="workflowstage",
            name="allow_reassign",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Allow the assigned approver (or any member of the stage's approval "
                    "groups) to reassign this task to another member of the same "
                    "approval groups."
                ),
            ),
        ),
        # 5. Add the lookup-type discriminator
        migrations.AddField(
            model_name="workflowstage",
            name="assignee_lookup_type",
            field=models.CharField(
                choices=[
                    ("email", "Email address"),
                    ("username", "Username (sAMAccountName)"),
                    ("full_name", "Full name (First Last)"),
                    ("ldap", "LDAP lookup by display name"),
                ],
                default="email",
                help_text=(
                    "How to resolve the form field value to a system user. "
                    "'Email' looks up by email address. "
                    "'Username' looks up by sAMAccountName/username. "
                    "'Full name' matches against first + last name. "
                    "'LDAP lookup' searches Active Directory by display name and "
                    "auto-provisions the Django user if not yet in the system."
                ),
                max_length=20,
            ),
        ),
    ]

