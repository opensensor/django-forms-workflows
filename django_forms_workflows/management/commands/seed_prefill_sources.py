"""
Management command to seed default prefill sources.

This creates the standard prefill sources that users can select from
when configuring form fields.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from django_forms_workflows.models import PrefillSource


class Command(BaseCommand):
    help = "Seed default prefill sources for form fields"

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("Seeding default prefill sources...")

        # Define default prefill sources
        sources = [
            # User model sources
            {
                "name": "Current User - Email",
                "source_type": "user",
                "source_key": "user.email",
                "description": "Email address of the logged-in user",
                "order": 10,
            },
            {
                "name": "Current User - First Name",
                "source_type": "user",
                "source_key": "user.first_name",
                "description": "First name of the logged-in user",
                "order": 20,
            },
            {
                "name": "Current User - Last Name",
                "source_type": "user",
                "source_key": "user.last_name",
                "description": "Last name of the logged-in user",
                "order": 30,
            },
            {
                "name": "Current User - Full Name",
                "source_type": "user",
                "source_key": "user.full_name",
                "description": "Full name of the logged-in user",
                "order": 40,
            },
            {
                "name": "Current User - Username",
                "source_type": "user",
                "source_key": "user.username",
                "description": "Username of the logged-in user",
                "order": 50,
            },
            # LDAP sources
            {
                "name": "LDAP - Department",
                "source_type": "ldap",
                "source_key": "ldap.department",
                "ldap_attribute": "department",
                "description": "Department from LDAP/Active Directory",
                "order": 100,
            },
            {
                "name": "LDAP - Job Title",
                "source_type": "ldap",
                "source_key": "ldap.title",
                "ldap_attribute": "title",
                "description": "Job title from LDAP/Active Directory",
                "order": 110,
            },
            {
                "name": "LDAP - Manager Name",
                "source_type": "ldap",
                "source_key": "ldap.manager",
                "ldap_attribute": "manager",
                "description": "Manager name from LDAP/Active Directory",
                "order": 120,
            },
            {
                "name": "LDAP - Manager Email",
                "source_type": "ldap",
                "source_key": "ldap.manager_email",
                "ldap_attribute": "manager_email",
                "description": "Manager email from LDAP/Active Directory",
                "order": 130,
            },
            {
                "name": "LDAP - Phone Number",
                "source_type": "ldap",
                "source_key": "ldap.phone",
                "ldap_attribute": "phone",
                "description": "Phone number from LDAP/Active Directory",
                "order": 140,
            },
            {
                "name": "LDAP - Employee ID",
                "source_type": "ldap",
                "source_key": "ldap.employee_id",
                "ldap_attribute": "employee_id",
                "description": "Employee ID from LDAP/Active Directory",
                "order": 150,
            },
            # System sources
            {
                "name": "Current Date",
                "source_type": "system",
                "source_key": "current_date",
                "description": "Today's date",
                "order": 200,
            },
            {
                "name": "Current Date & Time",
                "source_type": "system",
                "source_key": "current_datetime",
                "description": "Current date and time",
                "order": 210,
            },
            {
                "name": "Last Submission",
                "source_type": "system",
                "source_key": "last_submission",
                "description": "Copy value from last submission of this form",
                "order": 220,
            },
        ]

        created_count = 0
        updated_count = 0

        for source_data in sources:
            source, created = PrefillSource.objects.update_or_create(
                source_key=source_data["source_key"], defaults=source_data
            )

            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"  ✓ Created: {source.name}"))
            else:
                updated_count += 1
                self.stdout.write(self.style.WARNING(f"  ↻ Updated: {source.name}"))

        self.stdout.write(
            self.style.SUCCESS(
                f"\nCompleted! Created {created_count}, Updated {updated_count}"
            )
        )
        self.stdout.write(
            "\nYou can now add custom database prefill sources via Django Admin:"
        )
        self.stdout.write("  → Admin → Prefill Sources → Add Prefill Source")
