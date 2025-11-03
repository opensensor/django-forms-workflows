"""
Management command to create default form templates.

Usage:
    python manage.py create_default_templates
"""

from django.core.management.base import BaseCommand

from django_forms_workflows.models import FormTemplate


class Command(BaseCommand):
    help = "Create default form templates for common use cases"

    def handle(self, *args, **options):
        templates = [
            {
                "name": "Contact Form",
                "slug": "contact-form",
                "description": "Simple contact form with name, email, subject, and message fields",
                "category": "general",
                "is_system": True,
                "template_data": {
                    "name": "Contact Form",
                    "slug": "contact-form",
                    "description": "Get in touch with us",
                    "instructions": "Please fill out the form below and we will get back to you as soon as possible.",
                    "is_active": True,
                    "requires_login": False,
                    "allow_save_draft": False,
                    "allow_withdrawal": False,
                    "fields": [
                        {
                            "order": 1,
                            "field_name": "full_name",
                            "field_label": "Full Name",
                            "field_type": "text",
                            "required": True,
                            "help_text": "",
                            "placeholder": "John Doe",
                            "width": "full",
                            "css_class": "",
                            "choices": "",
                            "default_value": "",
                            "prefill_source_id": None,
                            "validation": {
                                "min_value": None,
                                "max_value": None,
                                "min_length": None,
                                "max_length": 100,
                                "regex_validation": "",
                                "regex_error_message": "",
                            },
                            "conditional": {"show_if_field": "", "show_if_value": ""},
                        },
                        {
                            "order": 2,
                            "field_name": "email",
                            "field_label": "Email Address",
                            "field_type": "email",
                            "required": True,
                            "help_text": "We will respond to this email address",
                            "placeholder": "john@example.com",
                            "width": "full",
                            "css_class": "",
                            "choices": "",
                            "default_value": "",
                            "prefill_source_id": None,
                            "validation": {
                                "min_value": None,
                                "max_value": None,
                                "min_length": None,
                                "max_length": None,
                                "regex_validation": "",
                                "regex_error_message": "",
                            },
                            "conditional": {"show_if_field": "", "show_if_value": ""},
                        },
                        {
                            "order": 3,
                            "field_name": "subject",
                            "field_label": "Subject",
                            "field_type": "text",
                            "required": True,
                            "help_text": "",
                            "placeholder": "What is this regarding?",
                            "width": "full",
                            "css_class": "",
                            "choices": "",
                            "default_value": "",
                            "prefill_source_id": None,
                            "validation": {
                                "min_value": None,
                                "max_value": None,
                                "min_length": None,
                                "max_length": 200,
                                "regex_validation": "",
                                "regex_error_message": "",
                            },
                            "conditional": {"show_if_field": "", "show_if_value": ""},
                        },
                        {
                            "order": 4,
                            "field_name": "message",
                            "field_label": "Message",
                            "field_type": "textarea",
                            "required": True,
                            "help_text": "Please provide as much detail as possible",
                            "placeholder": "Your message here...",
                            "width": "full",
                            "css_class": "",
                            "choices": "",
                            "default_value": "",
                            "prefill_source_id": None,
                            "validation": {
                                "min_value": None,
                                "max_value": None,
                                "min_length": 10,
                                "max_length": 2000,
                                "regex_validation": "",
                                "regex_error_message": "",
                            },
                            "conditional": {"show_if_field": "", "show_if_value": ""},
                        },
                    ],
                },
            },
            {
                "name": "Equipment Request",
                "slug": "equipment-request",
                "description": "Request new equipment or supplies for your department",
                "category": "request",
                "is_system": True,
                "template_data": {
                    "name": "Equipment Request",
                    "slug": "equipment-request",
                    "description": "Request new equipment or supplies",
                    "instructions": "Please provide detailed information about the equipment you need.",
                    "is_active": True,
                    "requires_login": True,
                    "allow_save_draft": True,
                    "allow_withdrawal": True,
                    "fields": [
                        {
                            "order": 1,
                            "field_name": "equipment_type",
                            "field_label": "Equipment Type",
                            "field_type": "select",
                            "required": True,
                            "help_text": "",
                            "placeholder": "",
                            "width": "full",
                            "css_class": "",
                            "choices": "Computer,Monitor,Keyboard,Mouse,Printer,Phone,Desk,Chair,Other",
                            "default_value": "",
                            "prefill_source_id": None,
                            "validation": {},
                            "conditional": {},
                        },
                        {
                            "order": 2,
                            "field_name": "quantity",
                            "field_label": "Quantity",
                            "field_type": "number",
                            "required": True,
                            "help_text": "How many do you need?",
                            "placeholder": "1",
                            "width": "half",
                            "css_class": "",
                            "choices": "",
                            "default_value": "1",
                            "prefill_source_id": None,
                            "validation": {
                                "min_value": 1,
                                "max_value": 100,
                                "min_length": None,
                                "max_length": None,
                                "regex_validation": "",
                                "regex_error_message": "",
                            },
                            "conditional": {},
                        },
                        {
                            "order": 3,
                            "field_name": "justification",
                            "field_label": "Business Justification",
                            "field_type": "textarea",
                            "required": True,
                            "help_text": "Explain why this equipment is needed",
                            "placeholder": "",
                            "width": "full",
                            "css_class": "",
                            "choices": "",
                            "default_value": "",
                            "prefill_source_id": None,
                            "validation": {"min_length": 20, "max_length": 1000},
                            "conditional": {},
                        },
                        {
                            "order": 4,
                            "field_name": "urgency",
                            "field_label": "Urgency",
                            "field_type": "radio",
                            "required": True,
                            "help_text": "",
                            "placeholder": "",
                            "width": "full",
                            "css_class": "",
                            "choices": "Low,Medium,High,Critical",
                            "default_value": "Medium",
                            "prefill_source_id": None,
                            "validation": {},
                            "conditional": {},
                        },
                    ],
                },
            },
            {
                "name": "Feedback Survey",
                "slug": "feedback-survey",
                "description": "Collect feedback from users or customers",
                "category": "survey",
                "is_system": True,
                "template_data": {
                    "name": "Feedback Survey",
                    "slug": "feedback-survey",
                    "description": "We value your feedback",
                    "instructions": "Please take a moment to share your thoughts with us.",
                    "is_active": True,
                    "requires_login": False,
                    "allow_save_draft": True,
                    "allow_withdrawal": False,
                    "fields": [
                        {
                            "order": 1,
                            "field_name": "overall_satisfaction",
                            "field_label": "Overall Satisfaction",
                            "field_type": "radio",
                            "required": True,
                            "help_text": "How satisfied are you overall?",
                            "placeholder": "",
                            "width": "full",
                            "css_class": "",
                            "choices": "Very Dissatisfied,Dissatisfied,Neutral,Satisfied,Very Satisfied",
                            "default_value": "",
                            "prefill_source_id": None,
                            "validation": {},
                            "conditional": {},
                        },
                        {
                            "order": 2,
                            "field_name": "comments",
                            "field_label": "Additional Comments",
                            "field_type": "textarea",
                            "required": False,
                            "help_text": "Please share any additional feedback",
                            "placeholder": "",
                            "width": "full",
                            "css_class": "",
                            "choices": "",
                            "default_value": "",
                            "prefill_source_id": None,
                            "validation": {},
                            "conditional": {},
                        },
                    ],
                },
            },
        ]

        created_count = 0
        updated_count = 0

        for template_data in templates:
            template, created = FormTemplate.objects.update_or_create(
                slug=template_data["slug"], defaults=template_data
            )

            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f"Created template: {template.name}")
                )
            else:
                updated_count += 1
                self.stdout.write(
                    self.style.WARNING(f"Updated template: {template.name}")
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"\nCompleted! Created {created_count} templates, updated {updated_count} templates."
            )
        )
