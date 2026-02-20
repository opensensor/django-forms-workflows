"""
Management command: seed_pcn_form

Creates a sample HR Payroll Change Notification (PCN) form with a single
staged approval workflow that requires BOTH the HR and Payroll groups to
approve (all-must-approve parallel stage).

Safe to run multiple times — uses get_or_create throughout.
"""

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand
from django.db import transaction

from django_forms_workflows.models import (
    FormCategory,
    FormDefinition,
    FormField,
    WorkflowDefinition,
    WorkflowStage,
)


class Command(BaseCommand):
    help = (
        "Seed a sample HR Payroll Change Notification (PCN) form with a staged "
        "workflow requiring both HR and Payroll approval. Safe to run multiple times."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        # ── Groups ─────────────────────────────────────────────────────────
        group_hr, _ = Group.objects.get_or_create(name="HR")
        group_payroll, _ = Group.objects.get_or_create(name="Payroll")
        group_employees, _ = Group.objects.get_or_create(name="Employees")
        self.stdout.write(self.style.SUCCESS("Ensured groups: HR, Payroll, Employees"))

        # ── Demo users ──────────────────────────────────────────────────────
        users_spec = [
            {
                "username": "hr_reviewer",
                "first_name": "Harper",
                "last_name": "Rivers",
                "email": "hr.reviewer@example.com",
                "groups": [group_hr],
            },
            {
                "username": "payroll_reviewer",
                "first_name": "Perry",
                "last_name": "Rollins",
                "email": "payroll.reviewer@example.com",
                "groups": [group_payroll],
            },
            {
                "username": "employee_demo",
                "first_name": "Emma",
                "last_name": "Ployee",
                "email": "employee.demo@example.com",
                "groups": [group_employees],
            },
        ]
        for spec in users_spec:
            user, created = User.objects.get_or_create(
                username=spec["username"],
                defaults={
                    "first_name": spec["first_name"],
                    "last_name": spec["last_name"],
                    "email": spec["email"],
                },
            )
            if created:
                user.set_password("pcn123")
                user.save()
            user.groups.set(spec["groups"])
        self.stdout.write(
            self.style.SUCCESS(
                "Users ready: hr_reviewer, payroll_reviewer, employee_demo (password: pcn123)"
            )
        )

        # ── Form Category ───────────────────────────────────────────────────
        category, _ = FormCategory.objects.get_or_create(
            slug="human-resources",
            defaults={
                "name": "Human Resources",
                "description": "HR forms including payroll changes, onboarding, and leave requests.",
                "icon": "bi-people-fill",
                "order": 10,
            },
        )

        # ── Form Definition ─────────────────────────────────────────────────
        form, created = FormDefinition.objects.get_or_create(
            slug="payroll-change-notification",
            defaults={
                "name": "Payroll Change Notification (PCN)",
                "category": category,
                "description": (
                    "Submit a Payroll Change Notification to update an employee's "
                    "pay rate, title, department, or employment status."
                ),
                "instructions": (
                    "Complete all sections below. Both HR and Payroll must approve "
                    "before the change is processed. Attach any supporting documentation "
                    "(offer letter, promotion memo, etc.) in the final section."
                ),
                "is_active": True,
                "allow_withdrawal": True,
            },
        )
        if created:
            form.submit_groups.set([group_employees, group_hr, group_payroll])
            self.stdout.write(
                self.style.SUCCESS("Created form: Payroll Change Notification (PCN)")
            )
        else:
            self.stdout.write("Form already exists — skipping field creation check.")

        # ── Form Fields ─────────────────────────────────────────────────────
        if form.fields.count() == 0:
            FormField.objects.bulk_create(
                [
                    # Section: Employee Information
                    FormField(
                        form_definition=form,
                        field_name="section_employee",
                        field_label="Employee Information",
                        field_type="section",
                        order=1,
                    ),
                    FormField(
                        form_definition=form,
                        field_name="employee_name",
                        field_label="Employee Name",
                        field_type="text",
                        required=True,
                        order=2,
                        width="half",
                        placeholder="First Last",
                    ),
                    FormField(
                        form_definition=form,
                        field_name="employee_id",
                        field_label="Employee ID",
                        field_type="text",
                        required=True,
                        order=3,
                        width="half",
                        placeholder="e.g., EMP-00123",
                    ),
                    FormField(
                        form_definition=form,
                        field_name="job_title",
                        field_label="Current Job Title",
                        field_type="text",
                        required=True,
                        order=4,
                        width="half",
                    ),
                    FormField(
                        form_definition=form,
                        field_name="department",
                        field_label="Department",
                        field_type="text",
                        required=True,
                        order=5,
                        width="half",
                    ),
                    FormField(
                        form_definition=form,
                        field_name="manager_name",
                        field_label="Manager Name",
                        field_type="text",
                        required=True,
                        order=6,
                        width="half",
                    ),
                    FormField(
                        form_definition=form,
                        field_name="employment_type",
                        field_label="Employment Type",
                        field_type="radio",
                        required=True,
                        order=7,
                        width="half",
                        choices=[
                            {"value": "full_time", "label": "Full-Time"},
                            {"value": "part_time", "label": "Part-Time"},
                            {"value": "contract", "label": "Contract"},
                        ],
                    ),
                    # Section: Change Details
                    FormField(
                        form_definition=form,
                        field_name="section_change",
                        field_label="Change Details",
                        field_type="section",
                        order=8,
                    ),
                    FormField(
                        form_definition=form,
                        field_name="effective_date",
                        field_label="Effective Date",
                        field_type="date",
                        required=True,
                        order=9,
                        width="half",
                        help_text="Date the change takes effect in payroll.",
                    ),
                    FormField(
                        form_definition=form,
                        field_name="change_type",
                        field_label="Type of Change",
                        field_type="select",
                        required=True,
                        order=10,
                        width="half",
                        choices=[
                            {
                                "value": "salary_change",
                                "label": "Salary / Pay Rate Change",
                            },
                            {"value": "bonus", "label": "Bonus / One-Time Payment"},
                            {"value": "title_change", "label": "Title Change"},
                            {"value": "dept_transfer", "label": "Department Transfer"},
                            {"value": "promotion", "label": "Promotion"},
                            {"value": "leave", "label": "Leave of Absence"},
                            {"value": "return_leave", "label": "Return from Leave"},
                            {"value": "termination", "label": "Termination"},
                            {"value": "new_hire", "label": "New Hire"},
                            {"value": "other", "label": "Other"},
                        ],
                    ),
                    FormField(
                        form_definition=form,
                        field_name="current_pay_rate",
                        field_label="Current Pay Rate ($)",
                        field_type="decimal",
                        required=False,
                        order=11,
                        width="half",
                        placeholder="0.00",
                        help_text="Leave blank if this change does not affect pay.",
                    ),
                    FormField(
                        form_definition=form,
                        field_name="new_pay_rate",
                        field_label="New Pay Rate ($)",
                        field_type="decimal",
                        required=False,
                        order=12,
                        width="half",
                        placeholder="0.00",
                        help_text="Leave blank if this change does not affect pay.",
                    ),
                    FormField(
                        form_definition=form,
                        field_name="new_job_title",
                        field_label="New Job Title",
                        field_type="text",
                        required=False,
                        order=13,
                        width="half",
                        help_text="If title is changing, enter the new title.",
                    ),
                    FormField(
                        form_definition=form,
                        field_name="new_department",
                        field_label="New Department",
                        field_type="text",
                        required=False,
                        order=14,
                        width="half",
                        help_text="If transferring, enter the receiving department.",
                    ),
                    FormField(
                        form_definition=form,
                        field_name="change_reason",
                        field_label="Reason for Change",
                        field_type="textarea",
                        required=True,
                        order=15,
                        help_text="Provide a clear business justification for this change.",
                    ),
                    # Section: Financial / Budget
                    FormField(
                        form_definition=form,
                        field_name="section_financial",
                        field_label="Financial & Budget Information",
                        field_type="section",
                        order=16,
                    ),
                    FormField(
                        form_definition=form,
                        field_name="cost_center",
                        field_label="Cost Center / GL Code",
                        field_type="text",
                        required=False,
                        order=17,
                        width="half",
                        placeholder="e.g., CC-4210",
                    ),
                    FormField(
                        form_definition=form,
                        field_name="budget_approval_number",
                        field_label="Budget Approval Number",
                        field_type="text",
                        required=False,
                        order=18,
                        width="half",
                        placeholder="e.g., BUD-2026-0042",
                    ),
                    FormField(
                        form_definition=form,
                        field_name="annual_budget_impact",
                        field_label="Estimated Annual Budget Impact ($)",
                        field_type="decimal",
                        required=False,
                        order=19,
                        placeholder="0.00",
                        help_text="Net annual cost difference (positive = increase, negative = savings).",
                    ),
                    # Section: Supporting Documentation
                    FormField(
                        form_definition=form,
                        field_name="section_docs",
                        field_label="Supporting Documentation",
                        field_type="section",
                        order=20,
                    ),
                    FormField(
                        form_definition=form,
                        field_name="supporting_document",
                        field_label="Attach Document",
                        field_type="file",
                        required=False,
                        order=21,
                        help_text=(
                            "Upload offer letter, promotion memo, or other supporting document. "
                            "Accepted formats: PDF, DOC, DOCX (max 10 MB)."
                        ),
                    ),
                    FormField(
                        form_definition=form,
                        field_name="additional_comments",
                        field_label="Additional Comments",
                        field_type="textarea",
                        required=False,
                        order=22,
                        help_text="Any other information HR or Payroll should know.",
                    ),
                ]
            )
            self.stdout.write(
                self.style.SUCCESS(
                    "Added 22 fields to Payroll Change Notification (PCN)"
                )
            )

        # ── Workflow Definition ─────────────────────────────────────────────
        workflow, _ = WorkflowDefinition.objects.get_or_create(
            form_definition=form,
            defaults={
                "requires_approval": True,
                # approval_logic on the WorkflowDefinition is unused in staged mode,
                # but set it to "all" for clarity / legacy fallback.
                "approval_logic": "all",
                "approval_deadline_days": 5,
                "send_reminder_after_days": 2,
            },
        )
        workflow.requires_approval = True
        workflow.approval_deadline_days = 5
        workflow.send_reminder_after_days = 2
        workflow.save()
        self.stdout.write(self.style.SUCCESS("Configured WorkflowDefinition for PCN"))

        # ── Workflow Stage: HR & Payroll Review (parallel, all must approve) ─
        stage, stage_created = WorkflowStage.objects.get_or_create(
            workflow=workflow,
            order=1,
            defaults={
                "name": "HR & Payroll Review",
                "approval_logic": "all",
            },
        )
        stage.name = "HR & Payroll Review"
        stage.approval_logic = "all"
        stage.save()
        stage.approval_groups.set([group_hr, group_payroll])
        if stage_created:
            self.stdout.write(
                self.style.SUCCESS(
                    "Created WorkflowStage: 'HR & Payroll Review' (all must approve)"
                )
            )
        else:
            self.stdout.write("WorkflowStage already existed — updated groups.")

        # ── Summary ─────────────────────────────────────────────────────────
        self.stdout.write(self.style.SUCCESS("\n📋 PCN demo seed complete! 📋"))
        self.stdout.write("\nForm:")
        self.stdout.write("  • Payroll Change Notification (PCN)")
        self.stdout.write("    Category : Human Resources")
        self.stdout.write(
            "    Workflow : 1 stage — HR & Payroll Review (all must approve)"
        )
        self.stdout.write("\nLogin credentials (password: pcn123):")
        self.stdout.write("  • employee_demo  — submits PCN forms")
        self.stdout.write("  • hr_reviewer    — HR approver")
        self.stdout.write("  • payroll_reviewer — Payroll approver")
