import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from django_forms_workflows.models import (
    ActionExecutionLog,
    APIToken,
    FormCategory,
    FormDefinition,
    FormField,
    FormSubmission,
    NotificationLog,
    NotificationRule,
    PostSubmissionAction,
    PrefillSource,
    StageApprovalGroup,
    SubWorkflowDefinition,
    WebhookDeliveryLog,
    WebhookEndpoint,
    WorkflowDefinition,
    WorkflowStage,
)
from django_forms_workflows.workflow_engine import (
    create_workflow_tasks,
    handle_approval,
    handle_rejection,
    handle_send_back,
)

DEMO_PASSWORD = "farm123"
DEMO_USER_AGENT = "seed_farm_demo"
SAMPLE_SIGNATURE = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
    "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


def _choice(value, label):
    return {"value": value, "label": label}


class Command(BaseCommand):
    help = (
        "Seed a comprehensive farm-themed showcase for the example project. "
        "Safe to run repeatedly."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        call_command("seed_prefill_sources", verbosity=0)

        groups = self._seed_groups()
        users = self._seed_users(groups)
        categories = self._seed_categories()
        prefill_sources = self._prefill_sources()

        showcase = {
            "equipment": self._seed_equipment_repair(
                groups, users, categories, prefill_sources
            ),
            "purchase": self._seed_capital_purchase(
                groups, users, categories, prefill_sources
            ),
            "irrigation": self._seed_irrigation_expansion(groups, categories),
            "incident": self._seed_safety_incident(groups, categories),
            "contact": self._seed_contact_update(groups, categories, prefill_sources),
            "harvest": self._seed_harvest_batch_log(groups, categories),
            "sensor": self._seed_sensor_upload(groups, categories),
        }

        token = self._seed_api_token(users["integration_ivy"])
        self._seed_sample_submissions(showcase, users)
        self._seed_demo_logs(showcase, users)
        self._print_summary(token)

    def _seed_groups(self):
        names = [
            "Farm Admins",
            "Barn Managers",
            "Field Crew",
            "Equipment Operators",
            "Farm Owners",
            "Finance Team",
            "Safety Team",
            "HR Team",
            "Agronomy Advisors",
            "Irrigation Specialists",
        ]
        groups = {name: Group.objects.get_or_create(name=name)[0] for name in names}
        self.stdout.write(self.style.SUCCESS(f"Ensured groups: {', '.join(names)}"))
        return groups

    def _seed_users(self, groups):
        user_model = get_user_model()
        specs = [
            {
                "username": "farmer_brown",
                "email": "farmer.brown@example.com",
                "first_name": "Farmer",
                "last_name": "Brown",
                "is_staff": True,
                "is_superuser": True,
                "groups": ["Farm Admins", "Barn Managers", "Farm Owners"],
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
            {
                "username": "finance_faith",
                "email": "faith.finance@example.com",
                "first_name": "Faith",
                "last_name": "Finance",
                "groups": ["Finance Team"],
            },
            {
                "username": "safety_sam",
                "email": "sam.safety@example.com",
                "first_name": "Safety",
                "last_name": "Sam",
                "groups": ["Safety Team"],
            },
            {
                "username": "hr_hannah",
                "email": "hannah.hr@example.com",
                "first_name": "HR",
                "last_name": "Hannah",
                "groups": ["HR Team"],
            },
            {
                "username": "advisor_amy",
                "email": "amy.advisor@example.com",
                "first_name": "Advisor",
                "last_name": "Amy",
                "groups": ["Agronomy Advisors"],
            },
            {
                "username": "irrigation_ivan",
                "email": "ivan.irrigation@example.com",
                "first_name": "Irrigation",
                "last_name": "Ivan",
                "groups": ["Irrigation Specialists"],
            },
            {
                "username": "integration_ivy",
                "email": "ivy.integration@example.com",
                "first_name": "Integration",
                "last_name": "Ivy",
                "groups": ["Farm Admins", "Finance Team"],
            },
        ]

        created = {}
        for spec in specs:
            user, was_created = user_model.objects.get_or_create(
                username=spec["username"],
                defaults={
                    "email": spec["email"],
                    "first_name": spec["first_name"],
                    "last_name": spec["last_name"],
                    "is_staff": spec.get("is_staff", False),
                    "is_superuser": spec.get("is_superuser", False),
                },
            )
            if was_created:
                user.set_password(DEMO_PASSWORD)
            for attr in (
                "email",
                "first_name",
                "last_name",
                "is_staff",
                "is_superuser",
            ):
                setattr(user, attr, spec.get(attr, getattr(user, attr)))
            user.save()
            user.groups.set([groups[name] for name in spec["groups"]])
            created[user.username] = user

        self.stdout.write(
            self.style.SUCCESS(
                f"Users ready: {', '.join(created)} (password: {DEMO_PASSWORD})"
            )
        )
        return created

    def _seed_categories(self):
        operations = self._ensure_category(
            slug="operations",
            name="Operations",
            description="Operational farm requests and logs.",
            icon="bi-gear-fill",
            order=10,
        )
        maintenance = self._ensure_category(
            slug="maintenance",
            name="Maintenance",
            description="Repairs, upkeep, and equipment issues.",
            icon="bi-tools",
            order=20,
            parent=operations,
        )
        finance = self._ensure_category(
            slug="finance",
            name="Finance",
            description="Purchases, approvals, and vendor spend.",
            icon="bi-cash-stack",
            order=30,
        )
        compliance = self._ensure_category(
            slug="compliance-safety",
            name="Compliance & Safety",
            description="Public incident intake and compliance forms.",
            icon="bi-shield-check",
            order=40,
        )
        people = self._ensure_category(
            slug="people-self-service",
            name="People & Self-Service",
            description="Employee self-service workflows and profile updates.",
            icon="bi-people-fill",
            order=50,
        )
        return {
            "operations": operations,
            "maintenance": maintenance,
            "finance": finance,
            "compliance": compliance,
            "people": people,
        }

    def _prefill_sources(self):
        keys = [
            "user.email",
            "user.first_name",
            "user.last_name",
            "user.full_name",
            "current_date",
        ]
        return {
            key: PrefillSource.objects.get(source_key=key)
            for key in keys
            if PrefillSource.objects.filter(source_key=key).exists()
        }

    def _seed_equipment_repair(self, groups, users, categories, sources):
        form = self._ensure_form(
            slug="equipment-repair",
            defaults={
                "category": categories["maintenance"],
                "name": "Equipment Repair Request",
                "description": "Showcases dynamic assignees, send-back, reassign, editable approvals, notifications, webhooks, and multifile uploads.",
                "instructions": "Use this demo form to experience a realistic maintenance workflow from supervisor triage through shop sign-off.",
                "enable_multi_step": True,
                "form_steps": [
                    {
                        "title": "Issue Intake",
                        "fields": [
                            "equipment_name",
                            "issue_type",
                            "issue_description",
                            "priority",
                        ],
                    },
                    {
                        "title": "Routing & Context",
                        "fields": [
                            "supervisor_email",
                            "cost_estimate",
                            "preferred_service_date",
                            "parts_needed",
                            "repair_photos",
                        ],
                    },
                ],
                "enable_auto_save": True,
                "pdf_generation": "anytime",
                "allow_resubmit": True,
            },
        )
        self._set_form_groups(
            form,
            submit_groups=[groups["Field Crew"], groups["Equipment Operators"]],
            view_groups=[
                groups["Field Crew"],
                groups["Equipment Operators"],
                groups["Barn Managers"],
            ],
            admin_groups=[groups["Farm Admins"]],
            reviewer_groups=[groups["Barn Managers"]],
        )

        self._sync_fields(
            form,
            [
                {
                    "field_name": "equipment_name",
                    "field_label": "Equipment",
                    "field_type": "text",
                    "required": True,
                    "order": 1,
                    "placeholder": "e.g. Tractor #12",
                },
                {
                    "field_name": "issue_type",
                    "field_label": "Issue Type",
                    "field_type": "radio",
                    "required": True,
                    "order": 2,
                    "choices": [
                        _choice("mechanical", "Mechanical"),
                        _choice("electrical", "Electrical"),
                        _choice("safety", "Safety"),
                        _choice("other", "Other"),
                    ],
                },
                {
                    "field_name": "issue_description",
                    "field_label": "Issue Description",
                    "field_type": "textarea",
                    "required": True,
                    "order": 3,
                },
                {
                    "field_name": "priority",
                    "field_label": "Priority",
                    "field_type": "select",
                    "required": True,
                    "order": 4,
                    "choices": [
                        _choice("low", "Low"),
                        _choice("medium", "Medium"),
                        _choice("high", "High"),
                        _choice("critical", "Critical"),
                    ],
                },
                {
                    "field_name": "supervisor_email",
                    "field_label": "Supervisor Email",
                    "field_type": "email",
                    "required": True,
                    "order": 5,
                    "help_text": "Dynamic assignee demo — use farmer.brown@example.com or mike.mechanic@example.com.",
                },
                {
                    "field_name": "cost_estimate",
                    "field_label": "Estimated Cost",
                    "field_type": "currency",
                    "required": False,
                    "order": 6,
                },
                {
                    "field_name": "preferred_service_date",
                    "field_label": "Preferred Service Date",
                    "field_type": "date",
                    "required": False,
                    "order": 7,
                },
                {
                    "field_name": "parts_needed",
                    "field_label": "Parts Needed",
                    "field_type": "multiselect_list",
                    "required": False,
                    "order": 8,
                    "choices": [
                        _choice("belt", "Replacement Belt"),
                        _choice("filters", "Filters"),
                        _choice("hydraulics", "Hydraulics"),
                        _choice("sensors", "Sensors"),
                    ],
                },
                {
                    "field_name": "repair_photos",
                    "field_label": "Repair Photos",
                    "field_type": "multifile",
                    "required": False,
                    "order": 9,
                },
            ],
        )

        workflow = self._ensure_workflow(
            form,
            "Repair Workflow",
            {
                "requires_approval": True,
                "approval_deadline_days": 4,
                "send_reminder_after_days": 2,
            },
        )
        triage = self._ensure_stage(
            workflow,
            "Supervisor Triage",
            1,
            {
                "approval_logic": "all",
                "assignee_form_field": "supervisor_email",
                "assignee_lookup_type": "email",
                "allow_send_back": True,
                "approve_label": "Triage Complete",
            },
        )
        self._set_stage_groups(triage, [groups["Barn Managers"]])
        signoff = self._ensure_stage(
            workflow,
            "Shop Sign-Off",
            2,
            {
                "approval_logic": "all",
                "allow_reassign": True,
                "allow_edit_form_data": True,
                "approve_label": "Close Repair",
            },
        )
        self._set_stage_groups(signoff, [groups["Equipment Operators"]])

        self._ensure_field(
            form,
            "repair_resolution",
            {
                "field_label": "Repair Resolution",
                "field_type": "textarea",
                "required": True,
                "order": 100,
                "workflow_stage": signoff,
                "help_text": "Approval-step field shown only during shop sign-off.",
            },
        )

        self._ensure_notification_rule(
            workflow,
            None,
            "submission_received",
            {
                "notify_submitter": True,
                "subject_template": "Repair #{submission_id} received for {form_name}",
            },
        )
        self._ensure_notification_rule(
            workflow,
            signoff,
            "approval_request",
            {
                "notify_stage_groups": True,
                "subject_template": "Repair #{submission_id} is waiting in the shop queue",
            },
        )
        endpoint = self._ensure_webhook(
            workflow,
            "Maintenance Board",
            {
                "url": "https://example.invalid/webhooks/maintenance",
                "events": [
                    "submission.created",
                    "task.created",
                    "submission.approved",
                    "submission.returned",
                ],
                "custom_headers": {"X-Demo-System": "maintenance-board"},
                "is_active": False,
                "retry_on_failure": False,
                "description": "Disabled by default so the sample project never posts externally unless you enable it.",
            },
        )
        return {
            "form": form,
            "workflow": workflow,
            "triage": triage,
            "signoff": signoff,
            "webhook": endpoint,
        }

    def _seed_capital_purchase(self, groups, users, categories, sources):
        form = self._ensure_form(
            slug="capital-purchase",
            defaults={
                "category": categories["finance"],
                "name": "Capital Purchase Request",
                "description": "Showcases multi-step forms, calculated fields, conditional fields, API exposure, bulk export, parallel approvals, approval-step fields, notifications, and webhooks.",
                "instructions": "This is the flagship finance workflow demo. Try a value above 5000 to trigger executive sign-off.",
                "enable_multi_step": True,
                "form_steps": [
                    {
                        "title": "Requester",
                        "fields": [
                            "request_date",
                            "requester_name",
                            "department",
                            "manager_username",
                        ],
                    },
                    {
                        "title": "Vendor & Spend",
                        "fields": [
                            "vendor_name",
                            "vendor_country",
                            "vendor_state",
                            "line_items",
                            "amount_requested",
                            "request_summary",
                        ],
                    },
                    {
                        "title": "Business Case",
                        "fields": ["business_case", "expedite"],
                    },
                ],
                "enable_auto_save": True,
                "api_enabled": True,
                "pdf_generation": "post_approval",
                "allow_resubmit": True,
            },
        )
        self._set_form_groups(
            form,
            submit_groups=[
                groups["Barn Managers"],
                groups["Finance Team"],
                groups["Farm Admins"],
            ],
            view_groups=[
                groups["Barn Managers"],
                groups["Finance Team"],
                groups["Farm Owners"],
                groups["Farm Admins"],
            ],
            admin_groups=[groups["Farm Admins"]],
            reviewer_groups=[groups["Finance Team"], groups["Farm Owners"]],
        )

        self._sync_fields(
            form,
            [
                {
                    "field_name": "request_date",
                    "field_label": "Request Date",
                    "field_type": "date",
                    "required": True,
                    "order": 1,
                    "prefill_source_config": sources.get("current_date"),
                },
                {
                    "field_name": "requester_name",
                    "field_label": "Requester Name",
                    "field_type": "text",
                    "required": True,
                    "order": 2,
                    "prefill_source_config": sources.get("user.full_name"),
                },
                {
                    "field_name": "department",
                    "field_label": "Department",
                    "field_type": "select",
                    "required": True,
                    "order": 3,
                    "choices": [
                        _choice("operations", "Operations"),
                        _choice("finance", "Finance"),
                        _choice("safety", "Safety"),
                        _choice("hr", "HR"),
                    ],
                },
                {
                    "field_name": "manager_username",
                    "field_label": "Manager Username",
                    "field_type": "text",
                    "required": True,
                    "order": 4,
                    "help_text": "Dynamic assignee demo — try farmer_brown.",
                },
                {
                    "field_name": "vendor_name",
                    "field_label": "Vendor Name",
                    "field_type": "text",
                    "required": True,
                    "order": 5,
                },
                {
                    "field_name": "vendor_country",
                    "field_label": "Vendor Country",
                    "field_type": "country",
                    "required": True,
                    "order": 6,
                },
                {
                    "field_name": "vendor_state",
                    "field_label": "Vendor State",
                    "field_type": "us_state",
                    "required": False,
                    "order": 7,
                    "conditional_rules": {
                        "operator": "AND",
                        "conditions": [
                            {
                                "field": "vendor_country",
                                "operator": "equals",
                                "value": "US",
                            }
                        ],
                        "action": "show",
                    },
                },
                {
                    "field_name": "line_items",
                    "field_label": "Requested Categories",
                    "field_type": "checkboxes",
                    "required": False,
                    "order": 8,
                    "choices": [
                        _choice("machinery", "Machinery"),
                        _choice("software", "Software"),
                        _choice("safety", "Safety Equipment"),
                        _choice("services", "Professional Services"),
                    ],
                },
                {
                    "field_name": "amount_requested",
                    "field_label": "Amount Requested",
                    "field_type": "currency",
                    "required": True,
                    "order": 9,
                },
                {
                    "field_name": "request_summary",
                    "field_label": "Calculated Summary",
                    "field_type": "calculated",
                    "required": False,
                    "order": 10,
                    "formula": "{department} purchase from {vendor_name}",
                    "help_text": "Calculated fields use token substitution from the current form data.",
                },
                {
                    "field_name": "business_case",
                    "field_label": "Business Case",
                    "field_type": "textarea",
                    "required": True,
                    "order": 11,
                },
                {
                    "field_name": "expedite",
                    "field_label": "Expedite Request",
                    "field_type": "checkbox",
                    "required": False,
                    "order": 12,
                },
            ],
        )

        workflow = self._ensure_workflow(
            form,
            "Capital Purchase Track",
            {
                "requires_approval": True,
                "approval_deadline_days": 5,
                "send_reminder_after_days": 2,
                "collapse_parallel_stages": True,
                "allow_bulk_export": True,
                "allow_bulk_pdf_export": True,
            },
        )
        ops_review = self._ensure_stage(
            workflow,
            "Operations Review",
            1,
            {
                "approval_logic": "all",
                "assignee_form_field": "manager_username",
                "assignee_lookup_type": "username",
                "validate_assignee_group": False,
                "allow_send_back": True,
            },
        )
        self._set_stage_groups(ops_review, [groups["Barn Managers"]])
        finance_review = self._ensure_stage(
            workflow,
            "Finance Review",
            1,
            {
                "approval_logic": "all",
                "allow_reassign": True,
            },
        )
        self._set_stage_groups(finance_review, [groups["Finance Team"]])
        owner_review = self._ensure_stage(
            workflow,
            "Owner Sign-Off",
            2,
            {
                "approval_logic": "any",
                "allow_edit_form_data": True,
                "approve_label": "Release Funds",
                "trigger_conditions": {
                    "operator": "AND",
                    "conditions": [
                        {
                            "field": "amount_requested",
                            "operator": "gte",
                            "value": 5000,
                        }
                    ],
                },
            },
        )
        self._set_stage_groups(owner_review, [groups["Farm Owners"]])

        self._ensure_field(
            form,
            "executive_budget_code",
            {
                "field_label": "Executive Budget Code",
                "field_type": "text",
                "required": True,
                "order": 100,
                "workflow_stage": owner_review,
                "help_text": "Approval-step field shown only to the final executive approver.",
            },
        )

        self._ensure_notification_rule(
            workflow,
            finance_review,
            "approval_request",
            {
                "notify_stage_groups": True,
                "subject_template": "Finance review opened for purchase #{submission_id}",
            },
        )
        self._ensure_notification_rule(
            workflow,
            None,
            "workflow_approved",
            {
                "notify_submitter": True,
                "static_emails": "finance-team@example.com",
                "subject_template": "Purchase #{submission_id} was approved",
            },
        )
        endpoint = self._ensure_webhook(
            workflow,
            "ERP Purchase Feed",
            {
                "url": "https://example.invalid/webhooks/purchases",
                "events": [
                    "submission.created",
                    "submission.approved",
                    "submission.rejected",
                ],
                "custom_headers": {"X-Demo-System": "erp"},
                "is_active": False,
                "retry_on_failure": True,
                "max_retries": 2,
                "description": "Ready-to-enable demo ERP webhook.",
            },
        )
        return {
            "form": form,
            "workflow": workflow,
            "ops_review": ops_review,
            "finance_review": finance_review,
            "owner_review": owner_review,
            "webhook": endpoint,
        }

    def _seed_irrigation_expansion(self, groups, categories):
        form = self._ensure_form(
            slug="irrigation-expansion",
            defaults={
                "category": categories["operations"],
                "name": "Irrigation Expansion Request",
                "description": "Showcases sub-workflows and sequential approvals.",
                "instructions": "Approve the parent request to spawn one zone checklist sub-workflow per requested zone.",
                "enable_multi_step": True,
                "form_steps": [
                    {
                        "title": "Project",
                        "fields": [
                            "project_name",
                            "zone_count",
                            "water_source",
                            "estimated_budget",
                        ],
                    },
                    {
                        "title": "Contact",
                        "fields": ["site_contact_name", "site_contact_email"],
                    },
                ],
            },
        )
        self._set_form_groups(
            form,
            submit_groups=[
                groups["Barn Managers"],
                groups["Irrigation Specialists"],
                groups["Farm Admins"],
            ],
            view_groups=[
                groups["Barn Managers"],
                groups["Irrigation Specialists"],
                groups["Farm Owners"],
                groups["Farm Admins"],
            ],
            admin_groups=[groups["Farm Admins"]],
            reviewer_groups=[groups["Irrigation Specialists"]],
        )
        self._sync_fields(
            form,
            [
                {
                    "field_name": "project_name",
                    "field_label": "Project Name",
                    "field_type": "text",
                    "required": True,
                    "order": 1,
                },
                {
                    "field_name": "zone_count",
                    "field_label": "Number of Zones",
                    "field_type": "number",
                    "required": True,
                    "order": 2,
                },
                {
                    "field_name": "water_source",
                    "field_label": "Primary Water Source",
                    "field_type": "select",
                    "required": True,
                    "order": 3,
                    "choices": [
                        _choice("well", "Well"),
                        _choice("pond", "Pond"),
                        _choice("municipal", "Municipal"),
                    ],
                },
                {
                    "field_name": "estimated_budget",
                    "field_label": "Estimated Budget",
                    "field_type": "currency",
                    "required": False,
                    "order": 4,
                },
                {
                    "field_name": "site_contact_name",
                    "field_label": "Site Contact Name",
                    "field_type": "text",
                    "required": True,
                    "order": 5,
                },
                {
                    "field_name": "site_contact_email",
                    "field_label": "Site Contact Email",
                    "field_type": "email",
                    "required": True,
                    "order": 6,
                },
            ],
        )

        workflow = self._ensure_workflow(
            form,
            "Irrigation Planning",
            {
                "requires_approval": True,
                "approval_deadline_days": 5,
            },
        )
        planning = self._ensure_stage(
            workflow,
            "Planning Review",
            1,
            {
                "approval_logic": "sequence",
                "allow_send_back": True,
            },
        )
        self._set_stage_groups(
            planning,
            [groups["Irrigation Specialists"], groups["Farm Owners"]],
            sequential=True,
        )

        sub_form = self._ensure_form(
            slug="irrigation-zone-checklist",
            defaults={
                "category": categories["operations"],
                "name": "Irrigation Zone Checklist",
                "description": "Child workflow used by the irrigation expansion demo.",
                "instructions": "This form is spawned automatically for each zone in the parent expansion request.",
            },
        )
        self._set_form_groups(
            sub_form,
            submit_groups=[groups["Irrigation Specialists"], groups["Farm Admins"]],
            view_groups=[
                groups["Irrigation Specialists"],
                groups["Farm Owners"],
                groups["Farm Admins"],
            ],
            admin_groups=[groups["Farm Admins"]],
            reviewer_groups=[groups["Irrigation Specialists"]],
        )
        self._sync_fields(
            sub_form,
            [
                {
                    "field_name": "zone_name",
                    "field_label": "Zone Name",
                    "field_type": "text",
                    "required": True,
                    "order": 1,
                },
                {
                    "field_name": "pipe_diameter",
                    "field_label": "Pipe Diameter",
                    "field_type": "decimal",
                    "required": False,
                    "order": 2,
                },
                {
                    "field_name": "requires_permit",
                    "field_label": "Requires Permit",
                    "field_type": "checkbox",
                    "required": False,
                    "order": 3,
                },
                {
                    "field_name": "zone_notes",
                    "field_label": "Zone Notes",
                    "field_type": "textarea",
                    "required": False,
                    "order": 4,
                },
            ],
        )
        sub_workflow = self._ensure_workflow(
            sub_form,
            "Zone Checklist Workflow",
            {
                "requires_approval": True,
                "approval_deadline_days": 3,
            },
        )
        zone_review = self._ensure_stage(
            sub_workflow,
            "Zone Review",
            1,
            {"approval_logic": "all"},
        )
        self._set_stage_groups(zone_review, [groups["Irrigation Specialists"]])
        config, _ = SubWorkflowDefinition.objects.update_or_create(
            parent_workflow=workflow,
            defaults={
                "sub_workflow": sub_workflow,
                "count_field": "zone_count",
                "label_template": "Zone {index}",
                "trigger": "on_approval",
                "detached": True,
            },
        )
        return {
            "form": form,
            "workflow": workflow,
            "planning": planning,
            "sub_form": sub_form,
            "sub_workflow": sub_workflow,
            "sub_stage": zone_review,
            "sub_config": config,
        }

    def _seed_safety_incident(self, groups, categories):
        form = self._ensure_form(
            slug="safety-incident-report",
            defaults={
                "category": categories["compliance"],
                "name": "Safety Incident Report",
                "description": "Public demo form showing anonymous submission, signature capture, conditional fields, multifile evidence, and PDF output.",
                "instructions": "This form is public — you can submit it without logging in.",
                "requires_login": False,
                "allow_save_draft": False,
                "allow_withdrawal": False,
                "allow_resubmit": True,
                "pdf_generation": "anytime",
            },
        )
        self._set_form_groups(
            form,
            submit_groups=[],
            view_groups=[groups["Safety Team"], groups["Farm Admins"]],
            admin_groups=[groups["Farm Admins"]],
            reviewer_groups=[groups["Safety Team"]],
        )
        self._sync_fields(
            form,
            [
                {
                    "field_name": "reporter_name",
                    "field_label": "Reporter Name",
                    "field_type": "text",
                    "required": False,
                    "order": 1,
                },
                {
                    "field_name": "reporter_email",
                    "field_label": "Reporter Email",
                    "field_type": "email",
                    "required": False,
                    "order": 2,
                },
                {
                    "field_name": "incident_date",
                    "field_label": "Incident Date",
                    "field_type": "date",
                    "required": True,
                    "order": 3,
                },
                {
                    "field_name": "incident_type",
                    "field_label": "Incident Type",
                    "field_type": "radio",
                    "required": True,
                    "order": 4,
                    "choices": [
                        _choice("equipment", "Equipment"),
                        _choice("animal", "Animal"),
                        _choice("injury", "Injury"),
                        _choice("spill", "Spill"),
                    ],
                },
                {
                    "field_name": "location",
                    "field_label": "Location",
                    "field_type": "text",
                    "required": True,
                    "order": 5,
                },
                {
                    "field_name": "description",
                    "field_label": "Description",
                    "field_type": "textarea",
                    "required": True,
                    "order": 6,
                },
                {
                    "field_name": "animal_tags",
                    "field_label": "Animal Tag Numbers",
                    "field_type": "textarea",
                    "required": False,
                    "order": 7,
                    "conditional_rules": {
                        "operator": "AND",
                        "conditions": [
                            {
                                "field": "incident_type",
                                "operator": "equals",
                                "value": "animal",
                            }
                        ],
                        "action": "show",
                    },
                },
                {
                    "field_name": "evidence_files",
                    "field_label": "Evidence Files",
                    "field_type": "multifile",
                    "required": False,
                    "order": 8,
                },
                {
                    "field_name": "signature",
                    "field_label": "Reporter Signature",
                    "field_type": "signature",
                    "required": True,
                    "order": 9,
                },
            ],
        )
        workflow = self._ensure_workflow(
            form,
            "Safety Intake Workflow",
            {
                "requires_approval": True,
                "hide_approval_history": True,
                "approval_deadline_days": 2,
            },
        )
        intake = self._ensure_stage(
            workflow,
            "Safety Intake",
            1,
            {"approval_logic": "all", "approve_label": "Acknowledge Incident"},
        )
        self._set_stage_groups(intake, [groups["Safety Team"]])
        self._ensure_notification_rule(
            workflow,
            None,
            "submission_received",
            {
                "static_emails": "safety@example.com",
                "subject_template": "New public safety incident #{submission_id}",
            },
        )
        return {"form": form, "workflow": workflow, "intake": intake}

    def _seed_contact_update(self, groups, categories, sources):
        form = self._ensure_form(
            slug="farmer-contact-update",
            defaults={
                "category": categories["people"],
                "name": "Farmer Contact Update",
                "description": "Showcases prefill sources and post-submission actions.",
                "instructions": "Most fields are prefilled from the current user record or system values.",
            },
        )
        self._set_form_groups(
            form,
            submit_groups=[
                groups["Field Crew"],
                groups["Barn Managers"],
                groups["Finance Team"],
                groups["Farm Admins"],
            ],
            view_groups=[groups["Farm Admins"], groups["HR Team"]],
            admin_groups=[groups["Farm Admins"]],
            reviewer_groups=[groups["HR Team"]],
        )
        self._sync_fields(
            form,
            [
                {
                    "field_name": "first_name",
                    "field_label": "First Name",
                    "field_type": "text",
                    "required": True,
                    "order": 1,
                    "prefill_source_config": sources.get("user.first_name"),
                    "width": "half",
                },
                {
                    "field_name": "last_name",
                    "field_label": "Last Name",
                    "field_type": "text",
                    "required": True,
                    "order": 2,
                    "prefill_source_config": sources.get("user.last_name"),
                    "width": "half",
                },
                {
                    "field_name": "email",
                    "field_label": "Email",
                    "field_type": "email",
                    "required": True,
                    "order": 3,
                    "prefill_source_config": sources.get("user.email"),
                },
                {
                    "field_name": "phone",
                    "field_label": "Phone",
                    "field_type": "phone",
                    "required": False,
                    "order": 4,
                },
                {
                    "field_name": "address",
                    "field_label": "Address",
                    "field_type": "textarea",
                    "required": False,
                    "order": 5,
                },
                {
                    "field_name": "update_date",
                    "field_label": "Update Date",
                    "field_type": "date",
                    "required": True,
                    "order": 6,
                    "prefill_source_config": sources.get("current_date"),
                },
            ],
        )
        api_action = self._ensure_post_action(
            form,
            "Log Contact Update to API",
            {
                "action_type": "api",
                "trigger": "on_submit",
                "description": "Demo API action for the sample site.",
                "is_active": False,
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
                        "email": "{email}",
                        "phone": "{phone}",
                        "updated_at": "{update_date}",
                    },
                    indent=2,
                ),
                "fail_silently": True,
                "retry_on_failure": False,
            },
        )
        db_action = self._ensure_post_action(
            form,
            "Update User Profile",
            {
                "action_type": "database",
                "trigger": "on_submit",
                "description": "Demo database update action.",
                "is_active": True,
                "order": 2,
                "db_alias": "default",
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
        return {"form": form, "api_action": api_action, "db_action": db_action}

    def _seed_harvest_batch_log(self, groups, categories):
        form = self._ensure_form(
            slug="harvest-batch-log",
            defaults={
                "category": categories["operations"],
                "name": "Harvest Batch Log",
                "description": "Showcases Excel template download and batch import.",
                "instructions": "Download the batch template, fill one row per harvest entry, and upload it back through the UI.",
                "allow_batch_import": True,
            },
        )
        self._set_form_groups(
            form,
            submit_groups=[groups["Field Crew"], groups["Farm Admins"]],
            view_groups=[
                groups["Field Crew"],
                groups["Barn Managers"],
                groups["Farm Admins"],
            ],
            admin_groups=[groups["Farm Admins"]],
            reviewer_groups=[groups["Barn Managers"]],
        )
        self._sync_fields(
            form,
            [
                {
                    "field_name": "harvest_date",
                    "field_label": "Harvest Date",
                    "field_type": "date",
                    "required": True,
                    "order": 1,
                },
                {
                    "field_name": "field_block",
                    "field_label": "Field Block",
                    "field_type": "text",
                    "required": True,
                    "order": 2,
                },
                {
                    "field_name": "crop",
                    "field_label": "Crop",
                    "field_type": "select",
                    "required": True,
                    "order": 3,
                    "choices": [
                        _choice("corn", "Corn"),
                        _choice("soy", "Soybeans"),
                        _choice("wheat", "Wheat"),
                    ],
                },
                {
                    "field_name": "weight_lbs",
                    "field_label": "Weight (lbs)",
                    "field_type": "number",
                    "required": True,
                    "order": 4,
                },
                {
                    "field_name": "moisture_percent",
                    "field_label": "Moisture %",
                    "field_type": "decimal",
                    "required": False,
                    "order": 5,
                },
            ],
        )
        return {"form": form}

    def _seed_sensor_upload(self, groups, categories):
        form = self._ensure_form(
            slug="sensor-data-upload",
            defaults={
                "category": categories["operations"],
                "name": "Sensor Data Upload",
                "description": "Showcases the spreadsheet file field for CSV/XLSX uploads.",
                "instructions": "Upload a spreadsheet export from a field sensor or IoT gateway.",
            },
        )
        self._set_form_groups(
            form,
            submit_groups=[groups["Agronomy Advisors"], groups["Farm Admins"]],
            view_groups=[groups["Agronomy Advisors"], groups["Farm Admins"]],
            admin_groups=[groups["Farm Admins"]],
            reviewer_groups=[groups["Agronomy Advisors"]],
        )
        self._sync_fields(
            form,
            [
                {
                    "field_name": "batch_name",
                    "field_label": "Batch Name",
                    "field_type": "text",
                    "required": True,
                    "order": 1,
                },
                {
                    "field_name": "captured_at",
                    "field_label": "Captured At",
                    "field_type": "datetime",
                    "required": False,
                    "order": 2,
                },
                {
                    "field_name": "sensor_file",
                    "field_label": "Sensor Spreadsheet",
                    "field_type": "spreadsheet",
                    "required": True,
                    "order": 3,
                },
                {
                    "field_name": "notes",
                    "field_label": "Notes",
                    "field_type": "textarea",
                    "required": False,
                    "order": 4,
                },
            ],
        )
        return {"form": form}

    def _seed_api_token(self, user):
        token, _ = APIToken.objects.get_or_create(
            user=user,
            name="Farm Demo API Token",
        )
        return token

    def _seed_sample_submissions(self, showcase, users):
        if FormSubmission.objects.filter(user_agent=DEMO_USER_AGENT).exists():
            self.stdout.write(
                self.style.WARNING(
                    "Sample submissions already present; skipping reseed."
                )
            )
            return

        repair_pending = self._make_submission(
            showcase["equipment"]["form"],
            users["farmer_jane"],
            {
                "equipment_name": "Tractor #12",
                "issue_type": "mechanical",
                "issue_description": "Hydraulic pressure drops after 20 minutes.",
                "priority": "high",
                "supervisor_email": users["farmer_brown"].email,
                "cost_estimate": "1800",
                "preferred_service_date": "2026-04-05",
                "parts_needed": ["hydraulics", "filters"],
                "repair_photos": [],
            },
            days_ago=2,
        )
        create_workflow_tasks(repair_pending)

        repair_returned = self._make_submission(
            showcase["equipment"]["form"],
            users["mechanic_mike"],
            {
                "equipment_name": "Harvester A7",
                "issue_type": "electrical",
                "issue_description": "Controller panel intermittently reboots.",
                "priority": "critical",
                "supervisor_email": users["farmer_brown"].email,
                "cost_estimate": "3200",
                "preferred_service_date": "2026-04-03",
                "parts_needed": ["sensors"],
                "repair_photos": [],
            },
            days_ago=5,
        )
        create_workflow_tasks(repair_returned)
        triage_task = repair_returned.approval_tasks.get(
            workflow_stage=showcase["equipment"]["triage"]
        )
        self._approve_task(triage_task, users["farmer_brown"])
        signoff_task = repair_returned.approval_tasks.get(
            workflow_stage=showcase["equipment"]["signoff"],
            status="pending",
        )
        signoff_task.status = "returned"
        signoff_task.completed_by = users["mechanic_mike"]
        signoff_task.completed_by = users["mechanic_mike"]
        signoff_task.comments = (
            "Need a clearer estimate before the shop can close this out."
        )
        signoff_task.save()
        handle_send_back(repair_returned, signoff_task, showcase["equipment"]["triage"])

        purchase_pending = self._make_submission(
            showcase["purchase"]["form"],
            users["finance_faith"],
            {
                "request_date": "2026-04-01",
                "requester_name": "Faith Finance",
                "department": "finance",
                "manager_username": "farmer_brown",
                "vendor_name": "HarvestTech",
                "vendor_country": "US",
                "vendor_state": "IA",
                "line_items": ["software", "services"],
                "amount_requested": "7200",
                "business_case": "Replace the aging procurement workstation and reporting stack.",
                "expedite": True,
            },
            days_ago=4,
        )
        create_workflow_tasks(purchase_pending)
        self._approve_task(
            purchase_pending.approval_tasks.get(
                workflow_stage=showcase["purchase"]["ops_review"]
            ),
            users["farmer_brown"],
        )
        self._approve_task(
            purchase_pending.approval_tasks.get(
                workflow_stage=showcase["purchase"]["finance_review"]
            ),
            users["finance_faith"],
        )

        purchase_approved = self._make_submission(
            showcase["purchase"]["form"],
            users["farmer_jane"],
            {
                "request_date": "2026-03-28",
                "requester_name": "Farmer Jane",
                "department": "operations",
                "manager_username": "farmer_brown",
                "vendor_name": "Field Supply Co",
                "vendor_country": "US",
                "vendor_state": "KS",
                "line_items": ["machinery"],
                "amount_requested": "1800",
                "business_case": "Purchase replacement sprayer nozzles before spring prep.",
                "expedite": False,
            },
            days_ago=9,
        )
        create_workflow_tasks(purchase_approved)
        self._approve_task(
            purchase_approved.approval_tasks.get(
                workflow_stage=showcase["purchase"]["ops_review"]
            ),
            users["farmer_brown"],
        )
        self._approve_task(
            purchase_approved.approval_tasks.get(
                workflow_stage=showcase["purchase"]["finance_review"]
            ),
            users["finance_faith"],
        )

        purchase_rejected = self._make_submission(
            showcase["purchase"]["form"],
            users["integration_ivy"],
            {
                "request_date": "2026-03-24",
                "requester_name": "Integration Ivy",
                "department": "finance",
                "manager_username": "farmer_brown",
                "vendor_name": "Future Farm Robotics",
                "vendor_country": "US",
                "vendor_state": "CA",
                "line_items": ["machinery", "software"],
                "amount_requested": "12500",
                "business_case": "Pilot autonomous irrigation routing hardware.",
                "expedite": False,
            },
            days_ago=12,
        )
        create_workflow_tasks(purchase_rejected)
        self._approve_task(
            purchase_rejected.approval_tasks.get(
                workflow_stage=showcase["purchase"]["ops_review"]
            ),
            users["farmer_brown"],
        )
        self._approve_task(
            purchase_rejected.approval_tasks.get(
                workflow_stage=showcase["purchase"]["finance_review"]
            ),
            users["finance_faith"],
        )
        owner_task = purchase_rejected.approval_tasks.get(
            workflow_stage=showcase["purchase"]["owner_review"],
            status="pending",
        )
        self._reject_task(owner_task, users["owner_olive"])

        irrigation = self._make_submission(
            showcase["irrigation"]["form"],
            users["advisor_amy"],
            {
                "project_name": "South Orchard Retrofit",
                "zone_count": 2,
                "water_source": "pond",
                "estimated_budget": "9600",
                "site_contact_name": "Amy Advisor",
                "site_contact_email": users["advisor_amy"].email,
            },
            days_ago=6,
        )
        create_workflow_tasks(irrigation)
        first_seq_task = irrigation.approval_tasks.get(status="pending")
        self._approve_task(first_seq_task, users["irrigation_ivan"])
        second_seq_task = irrigation.approval_tasks.get(status="pending")
        self._approve_task(second_seq_task, users["owner_olive"])

        incident = self._make_submission(
            showcase["incident"]["form"],
            None,
            {
                "reporter_name": "",
                "reporter_email": "",
                "incident_date": "2026-03-31",
                "incident_type": "animal",
                "location": "North pasture gate",
                "description": "Gate latch failed during morning rounds.",
                "animal_tags": "COW-117\nCOW-118",
                "evidence_files": [],
                "signature": SAMPLE_SIGNATURE,
            },
            days_ago=1,
        )
        create_workflow_tasks(incident)

        contact_update = self._make_submission(
            showcase["contact"]["form"],
            users["farmer_jane"],
            {
                "first_name": "Farmer",
                "last_name": "Jane",
                "email": users["farmer_jane"].email,
                "phone": "555-0123",
                "address": "123 Orchard Lane",
                "update_date": "2026-04-01",
            },
            days_ago=3,
            status="submitted",
        )

        self._make_submission(
            showcase["harvest"]["form"],
            users["farmer_jane"],
            {
                "harvest_date": "2026-03-30",
                "field_block": "North-14",
                "crop": "corn",
                "weight_lbs": 14250,
                "moisture_percent": "16.4",
            },
            days_ago=2,
            status="submitted",
        )
        self._make_submission(
            showcase["sensor"]["form"],
            users["advisor_amy"],
            {
                "batch_name": "Irrigation gateway export",
                "captured_at": "2026-04-01T08:15:00",
                "sensor_file": "demo-sensor-readings.xlsx",
                "notes": "Upload via the spreadsheet field demo form.",
            },
            days_ago=1,
            status="submitted",
        )
        withdrawn = self._make_submission(
            showcase["harvest"]["form"],
            users["farmer_jane"],
            {
                "harvest_date": "2026-03-20",
                "field_block": "West-03",
                "crop": "soy",
                "weight_lbs": 8450,
                "moisture_percent": "11.8",
            },
            days_ago=15,
            status="withdrawn",
        )
        withdrawn.completed_at = timezone.now() - timedelta(days=14)
        withdrawn.save(update_fields=["completed_at"])

        ActionExecutionLog.objects.get_or_create(
            action=showcase["contact"]["db_action"],
            submission=contact_update,
            trigger="on_submit",
            defaults={
                "success": True,
                "message": "Updated auth_user profile columns for the demo submitter.",
                "execution_data": {"rows_updated": 1},
            },
        )

    def _seed_demo_logs(self, showcase, users):
        purchase_submission = (
            FormSubmission.objects.filter(
                form_definition=showcase["purchase"]["form"],
                user_agent=DEMO_USER_AGENT,
            )
            .order_by("id")
            .first()
        )
        if purchase_submission is not None:
            NotificationLog.objects.get_or_create(
                notification_type="approval_request",
                submission=purchase_submission,
                recipient_email=users["finance_faith"].email,
                subject="Finance review opened for purchase demo",
                defaults={"status": "sent"},
            )
            WebhookDeliveryLog.objects.get_or_create(
                endpoint=showcase["purchase"]["webhook"],
                workflow=showcase["purchase"]["workflow"],
                submission=purchase_submission,
                event="submission.created",
                endpoint_name=showcase["purchase"]["webhook"].name,
                delivery_url=showcase["purchase"]["webhook"].url,
                attempt_number=1,
                defaults={
                    "success": False,
                    "status_code": 500,
                    "error_message": "Demo placeholder log — endpoint disabled by default.",
                    "request_headers": {"X-Demo-System": "erp"},
                    "payload": {"event": "submission.created", "demo": True},
                    "response_body": "Disabled in demo mode",
                },
            )

    def _make_submission(
        self, form, submitter, form_data, days_ago, status="submitted"
    ):
        submitted_at = timezone.now() - timedelta(days=days_ago)
        submission = FormSubmission.objects.create(
            form_definition=form,
            submitter=submitter,
            form_data=form_data,
            status=status,
            submitted_at=submitted_at,
            user_agent=DEMO_USER_AGENT,
        )
        FormSubmission.objects.filter(pk=submission.pk).update(
            created_at=submitted_at,
            submitted_at=submitted_at,
        )
        submission.refresh_from_db()
        return submission

    def _approve_task(self, task, approver):
        task.status = "approved"
        task.completed_by = approver
        task.completed_by = approver
        task.comments = "Seeded demo approval"
        task.save()
        handle_approval(task.submission, task, task.workflow_stage.workflow)

    def _reject_task(self, task, approver):
        task.status = "rejected"
        task.completed_by = approver
        task.completed_by = approver
        task.comments = "Seeded demo rejection"
        task.save()
        handle_rejection(task.submission, task, task.workflow_stage.workflow)

    def _ensure_category(self, slug, name, description, icon, order, parent=None):
        category, _ = FormCategory.objects.update_or_create(
            slug=slug,
            defaults={
                "name": name,
                "description": description,
                "icon": icon,
                "order": order,
                "parent": parent,
            },
        )
        return category

    def _ensure_form(self, slug, defaults):
        form, _ = FormDefinition.objects.update_or_create(slug=slug, defaults=defaults)
        return form

    def _ensure_field(self, form, field_name, defaults):
        field, _ = FormField.objects.update_or_create(
            form_definition=form,
            field_name=field_name,
            defaults=defaults,
        )
        return field

    def _sync_fields(self, form, field_defs):
        for field_def in field_defs:
            field_copy = dict(field_def)
            field_name = field_copy.pop("field_name")
            self._ensure_field(form, field_name, field_copy)

    def _ensure_workflow(self, form, name_label, defaults):
        workflow, _ = WorkflowDefinition.objects.update_or_create(
            form_definition=form,
            name_label=name_label,
            defaults=defaults,
        )
        return workflow

    def _ensure_stage(self, workflow, name, order, defaults):
        stage, _ = WorkflowStage.objects.update_or_create(
            workflow=workflow,
            name=name,
            order=order,
            defaults=defaults,
        )
        return stage

    def _set_form_groups(
        self,
        form,
        *,
        submit_groups,
        view_groups,
        admin_groups,
        reviewer_groups,
    ):
        form.submit_groups.set(submit_groups)
        form.view_groups.set(view_groups)
        form.admin_groups.set(admin_groups)
        form.reviewer_groups.set(reviewer_groups)

    def _set_stage_groups(self, stage, groups, sequential=False):
        stage.approval_groups.set(groups)
        if sequential:
            for position, group in enumerate(groups, start=1):
                StageApprovalGroup.objects.update_or_create(
                    stage=stage,
                    group=group,
                    role="approval",
                    defaults={"position": position},
                )

    def _ensure_notification_rule(self, workflow, stage, event, defaults):
        rule, _ = NotificationRule.objects.update_or_create(
            workflow=workflow,
            stage=stage,
            event=event,
            defaults=defaults,
        )
        return rule

    def _ensure_webhook(self, workflow, name, defaults):
        endpoint, _ = WebhookEndpoint.objects.update_or_create(
            workflow=workflow,
            name=name,
            defaults=defaults,
        )
        return endpoint

    def _ensure_post_action(self, form, name, defaults):
        action, _ = PostSubmissionAction.objects.update_or_create(
            form_definition=form,
            name=name,
            defaults=defaults,
        )
        return action

    def _print_summary(self, token):
        self.stdout.write(self.style.SUCCESS("\n🌾 Farm showcase seed complete! 🌾"))
        self.stdout.write("\nDemo forms:")
        self.stdout.write(
            "  • Equipment Repair Request — send-back, reassign, editable approvals, notifications, webhooks"
        )
        self.stdout.write(
            "  • Capital Purchase Request — API, bulk export, parallel approvals, conditional executive stage"
        )
        self.stdout.write(
            "  • Irrigation Expansion Request — sequential approvals + sub-workflows"
        )
        self.stdout.write(
            "  • Safety Incident Report — public form, signature, conditional fields, PDF"
        )
        self.stdout.write(
            "  • Farmer Contact Update — prefill + post-submission actions"
        )
        self.stdout.write("  • Harvest Batch Log — batch import template/upload")
        self.stdout.write("  • Sensor Data Upload — spreadsheet field")
        self.stdout.write(f"\nDemo login password: {DEMO_PASSWORD}")
        self.stdout.write("  • farmer_brown (admin)")
        self.stdout.write("  • farmer_jane")
        self.stdout.write("  • mechanic_mike")
        self.stdout.write("  • finance_faith")
        self.stdout.write("  • safety_sam")
        self.stdout.write("  • owner_olive")
        self.stdout.write("  • irrigation_ivan")
        self.stdout.write("\nAPI token user:")
        self.stdout.write(f"  • integration_ivy → Bearer {token.token}")
        self.stdout.write("\nUseful pages:")
        self.stdout.write("  • /forms/")
        self.stdout.write("  • /forms/approvals/")
        self.stdout.write("  • /forms/analytics/")
        self.stdout.write("  • /forms/forms-sync/export/")
        self.stdout.write("  • /api/docs/")
        self.stdout.write("  • /admin/")
