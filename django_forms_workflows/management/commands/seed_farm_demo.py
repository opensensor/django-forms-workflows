import json
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand
from django.db import transaction

from django_forms_workflows.models import (
    FormDefinition,
    FormField,
    PostSubmissionAction,
    PrefillSource,
    WorkflowDefinition,
)


class Command(BaseCommand):
    help = "Seed farm-themed demo users, groups, forms, and workflows. Safe to run multiple times."

    @transaction.atomic
    def handle(self, *args, **options):
        # Groups
        group_names = [
            "Barn Managers",
            "Field Crew",
            "Equipment Operators",
            "Farm Owners",
        ]
        groups = {}
        for name in group_names:
            g, _ = Group.objects.get_or_create(name=name)
            groups[name] = g
        self.stdout.write(
            self.style.SUCCESS(f"Ensured groups: {', '.join(group_names)}")
        )

        # Users
        users_spec = [
            {
                "username": "farmer_brown",
                "email": "farmer.brown@example.com",
                "first_name": "Farmer",
                "last_name": "Brown",
                "is_staff": True,
                "is_superuser": True,
                "groups": ["Barn Managers", "Farm Owners"],
            },
            {
                "username": "farmer_jane",
                "email": "farmer.jane@example.com",
                "first_name": "Farmer",
                "last_name": "Jane",
                "groups": ["Field Crew"],
            },
            {
                "username": "mechanic_mike",
                "email": "mike.mechanic@example.com",
                "first_name": "Mechanic",
                "last_name": "Mike",
                "groups": ["Equipment Operators"],
            },
            {
                "username": "owner_olive",
                "email": "olive.owner@example.com",
                "first_name": "Owner",
                "last_name": "Olive",
                "groups": ["Farm Owners"],
            },
        ]

        created_users = []
        for spec in users_spec:
            user, created = User.objects.get_or_create(
                username=spec["username"],
                defaults={
                    "email": spec.get("email", ""),
                    "first_name": spec.get("first_name", ""),
                    "last_name": spec.get("last_name", ""),
                    "is_staff": spec.get("is_staff", False),
                    "is_superuser": spec.get("is_superuser", False),
                },
            )
            if created:
                user.set_password("farm123")
                user.save()
            # Ensure attributes in case the user existed
            updated = False
            for attr in (
                "email",
                "first_name",
                "last_name",
                "is_staff",
                "is_superuser",
            ):
                val = spec.get(attr, getattr(user, attr))
                if getattr(user, attr) != val:
                    setattr(user, attr, val)
                    updated = True
            if updated:
                user.save()
            # Groups
            user.groups.clear()
            for gname in spec.get("groups", []):
                user.groups.add(groups[gname])
            created_users.append(user.username)
        self.stdout.write(
            self.style.SUCCESS(
                f"Users ready: {', '.join(created_users)} (password: farm123)"
            )
        )

        # Forms and Workflows
        # 1) Equipment Repair Request (any approver, escalates over $1000)
        fd1, created = FormDefinition.objects.get_or_create(
            slug="equipment-repair",
            defaults={
                "name": "Equipment Repair Request",
                "description": "Report equipment issues and request repairs.",
                "instructions": "Describe the problem and include an estimate if known.",
            },
        )
        if created:
            self.stdout.write(
                self.style.SUCCESS("Created form: Equipment Repair Request")
            )
        if fd1.fields.count() == 0:
            FormField.objects.bulk_create(
                [
                    FormField(
                        form_definition=fd1,
                        field_name="equipment_name",
                        field_label="Equipment",
                        field_type="text",
                        required=True,
                        order=1,
                        placeholder="e.g., Tractor #12",
                    ),
                    FormField(
                        form_definition=fd1,
                        field_name="issue_description",
                        field_label="Issue Description",
                        field_type="textarea",
                        required=True,
                        order=2,
                    ),
                    FormField(
                        form_definition=fd1,
                        field_name="cost_estimate",
                        field_label="Estimated Cost",
                        field_type="decimal",
                        required=False,
                        order=3,
                    ),
                    FormField(
                        form_definition=fd1,
                        field_name="priority",
                        field_label="Priority",
                        field_type="select",
                        required=True,
                        order=4,
                        choices=[
                            {"value": "low", "label": "Low"},
                            {"value": "medium", "label": "Medium"},
                            {"value": "high", "label": "High"},
                        ],
                    ),
                ]
            )
            self.stdout.write(
                self.style.SUCCESS("Added fields for Equipment Repair Request")
            )
        wf1, _ = WorkflowDefinition.objects.get_or_create(
            form_definition=fd1,
            defaults={
                "requires_approval": True,
                "approval_logic": "any",
                "approval_deadline_days": 7,
                "send_reminder_after_days": 3,
            },
        )
        # Ensure associations and settings
        wf1.requires_approval = True
        wf1.approval_logic = "any"
        wf1.approval_deadline_days = 7
        wf1.send_reminder_after_days = 3
        wf1.escalation_field = "cost_estimate"
        wf1.escalation_threshold = Decimal("1000.00")
        wf1.save()
        wf1.approval_groups.set(
            [groups["Barn Managers"], groups["Equipment Operators"]]
        )
        wf1.escalation_groups.set([groups["Farm Owners"]])
        self.stdout.write(
            self.style.SUCCESS("Configured workflow for Equipment Repair Request")
        )

        # 2) Barn Maintenance Request (all must approve)
        fd2, created = FormDefinition.objects.get_or_create(
            slug="barn-maintenance",
            defaults={
                "name": "Barn Maintenance Request",
                "description": "Request maintenance work in the barn.",
                "instructions": "Provide details and preferred date.",
            },
        )
        if created:
            self.stdout.write(
                self.style.SUCCESS("Created form: Barn Maintenance Request")
            )
        if fd2.fields.count() == 0:
            FormField.objects.bulk_create(
                [
                    FormField(
                        form_definition=fd2,
                        field_name="maintenance_date",
                        field_label="Preferred Date",
                        field_type="date",
                        required=True,
                        order=1,
                    ),
                    FormField(
                        form_definition=fd2,
                        field_name="area",
                        field_label="Area/Equipment",
                        field_type="text",
                        required=True,
                        order=2,
                    ),
                    FormField(
                        form_definition=fd2,
                        field_name="details",
                        field_label="Details",
                        field_type="textarea",
                        required=True,
                        order=3,
                    ),
                ]
            )
            self.stdout.write(
                self.style.SUCCESS("Added fields for Barn Maintenance Request")
            )
        wf2, _ = WorkflowDefinition.objects.get_or_create(
            form_definition=fd2,
            defaults={
                "requires_approval": True,
                "approval_logic": "all",
                "approval_deadline_days": 5,
                "send_reminder_after_days": 2,
            },
        )
        wf2.requires_approval = True
        wf2.approval_logic = "all"
        wf2.approval_deadline_days = 5
        wf2.send_reminder_after_days = 2
        wf2.save()
        wf2.approval_groups.set([groups["Field Crew"], groups["Barn Managers"]])
        self.stdout.write(
            self.style.SUCCESS("Configured workflow for Barn Maintenance Request")
        )

        # 3) Harvest Report (no approval)
        fd3, created = FormDefinition.objects.get_or_create(
            slug="harvest-report",
            defaults={
                "name": "Harvest Report",
                "description": "Record daily harvest totals.",
                "instructions": "Log crops and quantities harvested today.",
            },
        )
        if created:
            self.stdout.write(self.style.SUCCESS("Created form: Harvest Report"))
        if fd3.fields.count() == 0:
            FormField.objects.bulk_create(
                [
                    FormField(
                        form_definition=fd3,
                        field_name="date",
                        field_label="Date",
                        field_type="date",
                        required=True,
                        order=1,
                    ),
                    FormField(
                        form_definition=fd3,
                        field_name="crop",
                        field_label="Crop",
                        field_type="text",
                        required=True,
                        order=2,
                    ),
                    FormField(
                        form_definition=fd3,
                        field_name="quantity",
                        field_label="Quantity (lbs)",
                        field_type="number",
                        required=True,
                        order=3,
                    ),
                ]
            )
            self.stdout.write(self.style.SUCCESS("Added fields for Harvest Report"))

        # 4) Farmer Contact Update (showcases prefill functionality)
        fd4, created = FormDefinition.objects.get_or_create(
            slug="farmer-contact-update",
            defaults={
                "name": "Farmer Contact Update",
                "description": "Update your contact information on file.",
                "instructions": "Review and update your contact details. Fields are pre-filled with your current information.",
            },
        )
        if created:
            self.stdout.write(self.style.SUCCESS("Created form: Farmer Contact Update"))

        # Get prefill sources
        try:
            prefill_email = PrefillSource.objects.get(source_key="user.email")
            prefill_first_name = PrefillSource.objects.get(source_key="user.first_name")
            prefill_last_name = PrefillSource.objects.get(source_key="user.last_name")
            prefill_current_date = PrefillSource.objects.get(source_key="current_date")
        except PrefillSource.DoesNotExist:
            self.stdout.write(
                self.style.WARNING(
                    "Prefill sources not found. Run 'python manage.py seed_prefill_sources' first."
                )
            )
            prefill_email = None
            prefill_first_name = None
            prefill_last_name = None
            prefill_current_date = None

        if fd4.fields.count() == 0:
            fields_to_create = [
                FormField(
                    form_definition=fd4,
                    field_name="section_personal",
                    field_label="Personal Information",
                    field_type="section",
                    order=1,
                ),
                FormField(
                    form_definition=fd4,
                    field_name="first_name",
                    field_label="First Name",
                    field_type="text",
                    required=True,
                    order=2,
                    width="half",
                    help_text="Auto-filled from your account",
                    prefill_source_config=prefill_first_name,
                ),
                FormField(
                    form_definition=fd4,
                    field_name="last_name",
                    field_label="Last Name",
                    field_type="text",
                    required=True,
                    order=3,
                    width="half",
                    help_text="Auto-filled from your account",
                    prefill_source_config=prefill_last_name,
                ),
                FormField(
                    form_definition=fd4,
                    field_name="email",
                    field_label="Email Address",
                    field_type="email",
                    required=True,
                    order=4,
                    help_text="Auto-filled from your account",
                    prefill_source_config=prefill_email,
                ),
                FormField(
                    form_definition=fd4,
                    field_name="section_contact",
                    field_label="Contact Details",
                    field_type="section",
                    order=5,
                ),
                FormField(
                    form_definition=fd4,
                    field_name="phone",
                    field_label="Phone Number",
                    field_type="text",
                    required=False,
                    order=6,
                    placeholder="(555) 123-4567",
                ),
                FormField(
                    form_definition=fd4,
                    field_name="address",
                    field_label="Mailing Address",
                    field_type="textarea",
                    required=False,
                    order=7,
                ),
                FormField(
                    form_definition=fd4,
                    field_name="update_date",
                    field_label="Update Date",
                    field_type="date",
                    required=True,
                    order=8,
                    help_text="Auto-filled with today's date",
                    prefill_source_config=prefill_current_date,
                ),
            ]
            FormField.objects.bulk_create(fields_to_create)
            self.stdout.write(
                self.style.SUCCESS(
                    "Added fields for Farmer Contact Update (with prefill)"
                )
            )

        # Add post-submission action example for Farmer Contact Update
        # This demonstrates how to update an external system after form submission
        action, created = PostSubmissionAction.objects.get_or_create(
            form_definition=fd4,
            name="Log Contact Update to API",
            defaults={
                "action_type": "api",
                "trigger": "on_submit",
                "description": "Send contact update to external logging API (demo)",
                "is_active": False,  # Disabled by default since it's just a demo
                "order": 1,
                "api_endpoint": "https://httpbin.org/post",
                "api_method": "POST",
                "api_headers": {
                    "Content-Type": "application/json",
                    "X-Demo-Header": "FarmDemo",
                },
                "api_body_template": json.dumps(
                    {
                        "event": "contact_update",
                        "user": "{username}",
                        "email": "{email}",
                        "phone": "{phone}",
                        "timestamp": "{update_date}",
                    },
                    indent=2,
                ),
                "fail_silently": True,
                "retry_on_failure": False,
            },
        )
        if created:
            self.stdout.write(
                self.style.SUCCESS("Created demo post-submission action (API call)")
            )

        # Add database update action to update User model
        db_action, created = PostSubmissionAction.objects.get_or_create(
            form_definition=fd4,
            name="Update User Profile",
            defaults={
                "action_type": "database",
                "trigger": "on_submit",
                "description": "Update user profile in database when contact info is submitted",
                "is_active": True,  # Enabled for demo
                "order": 2,
                "db_alias": "default",
                "db_schema": "",  # SQLite doesn't use schemas
                "db_table": "auth_user",
                "db_lookup_field": "id",
                "db_user_field": "id",
                "db_field_mappings": [
                    {"form_field": "first_name", "db_column": "first_name"},
                    {"form_field": "last_name", "db_column": "last_name"},
                    {"form_field": "email", "db_column": "email"},
                ],
                "fail_silently": False,
                "retry_on_failure": True,
                "max_retries": 3,
            },
        )
        if created:
            self.stdout.write(
                self.style.SUCCESS(
                    "Created demo post-submission action (Database update)"
                )
            )

        self.stdout.write(self.style.SUCCESS("\n🌾 Farm demo seed complete! 🌾"))
        self.stdout.write("\nAvailable forms:")
        self.stdout.write(
            "  1. Equipment Repair Request - Showcases escalation workflow"
        )
        self.stdout.write(
            "  2. Barn Maintenance Request - Showcases 'all must approve' workflow"
        )
        self.stdout.write("  3. Harvest Report - No approval required")
        self.stdout.write(
            "  4. Farmer Contact Update - Showcases prefill & post-submission actions"
        )
        self.stdout.write("\nLogin with any user (password: farm123):")
        self.stdout.write("  • farmer_brown (admin)")
        self.stdout.write("  • farmer_jane")
        self.stdout.write("  • mechanic_mike")
        self.stdout.write("  • owner_olive")
        self.stdout.write("\nPost-submission actions:")
        self.stdout.write("  • Update User Profile - Updates auth_user table (ENABLED)")
        self.stdout.write(
            "  • API Call - Log contact updates to external API (disabled)"
        )
        self.stdout.write("  View in Admin → Post-Submission Actions")
