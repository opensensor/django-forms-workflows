"""
Email notification handler for post-submission actions.

Sends email notifications with form data after submission or approval.
"""

import logging

from django.conf import settings
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.template.loader import render_to_string

from .base import BaseActionHandler

logger = logging.getLogger(__name__)


class EmailHandler(BaseActionHandler):
    """
    Handler for sending email notifications.

    Supports:
    - Static email addresses (email_to, email_cc)
    - Dynamic email addresses from form fields (email_to_field, email_cc_field)
    - Template-based subjects and bodies
    - Django template files for HTML emails
    - Placeholder substitution with form field values
    """

    def execute(self):
        """
        Execute the email notification action.

        Returns:
            dict: Result with 'success', 'message', and optional 'data'
        """
        try:
            # Build recipient list
            recipients = self._get_recipients()
            if not recipients:
                return {
                    "success": False,
                    "message": "No valid email recipients configured",
                }

            # Build CC list
            cc_list = self._get_cc_list()

            # Build subject and body
            subject = self._build_subject()
            body = self._build_body()
            html_body = self._build_html_body()

            # Get from email
            from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@example.com")

            # Send email
            result = self._send_email(
                subject=subject,
                body=body,
                html_body=html_body,
                from_email=from_email,
                to=recipients,
                cc=cc_list,
            )

            if result["success"]:
                self.log_success(result["message"])
            else:
                self.log_error(result["message"])

            return result

        except Exception as e:
            error_msg = f"Email notification failed: {str(e)}"
            self.log_error(error_msg, exc_info=True)
            return {"success": False, "message": error_msg}

    def _get_recipients(self) -> list:
        """
        Build list of recipient email addresses.

        Combines static addresses (email_to) with dynamic addresses
        from form fields (email_to_field).

        Returns:
            list: List of valid email addresses
        """
        recipients = []

        # Add static email addresses
        if self.action.email_to:
            static_emails = [
                e.strip() for e in self.action.email_to.split(",") if e.strip()
            ]
            recipients.extend(static_emails)

        # Add email from form field
        if self.action.email_to_field:
            field_email = self.get_form_field_value(self.action.email_to_field)
            if field_email and isinstance(field_email, str) and "@" in field_email:
                recipients.append(field_email.strip())

        # Remove duplicates while preserving order
        seen = set()
        unique_recipients = []
        for email in recipients:
            if email.lower() not in seen:
                seen.add(email.lower())
                unique_recipients.append(email)

        return unique_recipients

    def _get_cc_list(self) -> list:
        """
        Build list of CC email addresses.

        Returns:
            list: List of valid CC email addresses
        """
        cc_list = []

        # Add static CC addresses
        if self.action.email_cc:
            static_cc = [
                e.strip() for e in self.action.email_cc.split(",") if e.strip()
            ]
            cc_list.extend(static_cc)

        # Add CC from form field
        if self.action.email_cc_field:
            field_cc = self.get_form_field_value(self.action.email_cc_field)
            if field_cc and isinstance(field_cc, str) and "@" in field_cc:
                cc_list.append(field_cc.strip())

        # Remove duplicates
        seen = set()
        unique_cc = []
        for email in cc_list:
            if email.lower() not in seen:
                seen.add(email.lower())
                unique_cc.append(email)

        return unique_cc

    def _get_placeholders(self) -> dict:
        """
        Build dictionary of placeholders for template substitution.

        Returns:
            dict: Placeholder values from form data, user, and submission
        """
        placeholders = {}

        # Add all form field values
        for field_name, value in self.form_data.items():
            placeholders[field_name] = value if value is not None else ""

        # Add user information
        placeholders.update(
            {
                "username": self.user.username,
                "email": self.user.email,
                "first_name": self.user.first_name or "",
                "last_name": self.user.last_name or "",
                "full_name": f"{self.user.first_name} {self.user.last_name}".strip()
                or self.user.username,
                "user_id": self.user.id,
            }
        )

        # Add submission information
        placeholders.update(
            {
                "submission_id": self.submission.id,
                "form_name": self.submission.form_definition.name,
                "form_slug": self.submission.form_definition.slug,
                "status": self.submission.status,
                "status_display": self.submission.get_status_display(),
                "submitted_at": str(self.submission.submitted_at)
                if self.submission.submitted_at
                else "",
                "created_at": str(self.submission.created_at),
            }
        )

        return placeholders

    def _build_subject(self) -> str:
        """
        Build email subject from template.

        Returns:
            str: Rendered email subject
        """
        if not self.action.email_subject_template:
            # Default subject
            return f"Form Submission: {self.submission.form_definition.name}"

        placeholders = self._get_placeholders()
        template = self.action.email_subject_template

        try:
            return template.format(**placeholders)
        except KeyError as e:
            self.log_warning(f"Missing placeholder in subject template: {e}")
            return f"Form Submission: {self.submission.form_definition.name}"

    def _build_body(self) -> str:
        """
        Build plain text email body from template.

        Returns:
            str: Rendered email body
        """
        if not self.action.email_body_template:
            # Default body with form data
            return self._build_default_body()

        placeholders = self._get_placeholders()
        template = self.action.email_body_template

        try:
            return template.format(**placeholders)
        except KeyError as e:
            self.log_warning(f"Missing placeholder in body template: {e}")
            return self._build_default_body()

    def _build_default_body(self) -> str:
        """
        Build a default email body listing all form fields.

        Returns:
            str: Default formatted email body
        """
        lines = [
            f"Form: {self.submission.form_definition.name}",
            f"Submitted by: {self.user.email}",
            f"Status: {self.submission.get_status_display()}",
            "",
            "Form Data:",
            "-" * 40,
        ]

        for field_name, value in self.form_data.items():
            # Format the field name nicely
            display_name = field_name.replace("_", " ").title()
            lines.append(f"{display_name}: {value}")

        lines.extend(
            [
                "",
                "-" * 40,
                f"Submission ID: {self.submission.id}",
            ]
        )

        return "\n".join(lines)

    def _build_html_body(self) -> str | None:
        """
        Build HTML email body from Django template.

        Returns:
            str or None: Rendered HTML body, or None if no template configured
        """
        if not self.action.email_template_name:
            return None

        try:
            context = self._get_placeholders()
            # Add the full submission and form_data for complex templates
            context["submission"] = self.submission
            context["form_data"] = self.form_data
            context["user"] = self.user

            return render_to_string(self.action.email_template_name, context)
        except Exception as e:
            self.log_warning(f"Could not render HTML template: {e}")
            return None

    def _send_email(
        self,
        subject: str,
        body: str,
        html_body: str | None,
        from_email: str,
        to: list,
        cc: list,
    ) -> dict:
        """
        Send the email using Django's email backend.

        Args:
            subject: Email subject
            body: Plain text body
            html_body: Optional HTML body
            from_email: Sender email address
            to: List of recipient addresses
            cc: List of CC addresses

        Returns:
            dict: Result with success status and message
        """
        try:
            if html_body:
                # Send multipart email with HTML
                msg = EmailMultiAlternatives(
                    subject=subject,
                    body=body,
                    from_email=from_email,
                    to=to,
                    cc=cc if cc else None,
                )
                msg.attach_alternative(html_body, "text/html")
            else:
                # Send plain text email
                msg = EmailMessage(
                    subject=subject,
                    body=body,
                    from_email=from_email,
                    to=to,
                    cc=cc if cc else None,
                )

            # Send the email
            sent = msg.send(fail_silently=False)

            if sent:
                recipient_str = ", ".join(to)
                cc_str = f" (CC: {', '.join(cc)})" if cc else ""
                return {
                    "success": True,
                    "message": f"Email sent to {recipient_str}{cc_str}",
                    "data": {
                        "to": to,
                        "cc": cc,
                        "subject": subject,
                    },
                }
            else:
                return {
                    "success": False,
                    "message": "Email send returned 0 (no emails sent)",
                }

        except Exception as e:
            return {
                "success": False,
                "message": f"Email send error: {str(e)}",
            }
