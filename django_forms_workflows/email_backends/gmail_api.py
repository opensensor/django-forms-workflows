"""
Gmail API Email Backend for Django

This backend sends emails using Google's Gmail API with a service account.
It supports domain-wide delegation to send emails as any user in the domain.

Configuration in settings.py:
    EMAIL_BACKEND = 'django_forms_workflows.email_backends.GmailAPIBackend'

    GMAIL_API = {
        'service_account_json': '/path/to/service-account.json',
        # OR
        'service_account_base64': 'base64-encoded-json-credentials',

        'delegated_user': 'noreply@yourdomain.com',  # User to impersonate
        'scopes': ['https://www.googleapis.com/auth/gmail.send'],
    }

Requirements:
    pip install google-auth google-api-python-client
"""

import base64
import json
import logging
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)


def get_gmail_service(config):
    """
    Create and return an authenticated Gmail API service.

    Args:
        config: Dictionary with Gmail API configuration

    Returns:
        Gmail API service object
    """
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError as err:
        raise ImportError(
            "Gmail API backend requires google-auth and google-api-python-client. "
            "Install with: pip install google-auth google-api-python-client"
        ) from err

    scopes = config.get("scopes", ["https://www.googleapis.com/auth/gmail.send"])
    delegated_user = config.get("delegated_user")

    # Load credentials from JSON file or base64-encoded string
    if "service_account_json" in config:
        credentials = service_account.Credentials.from_service_account_file(
            config["service_account_json"], scopes=scopes
        )
    elif "service_account_base64" in config:
        # Decode base64 credentials
        json_str = base64.b64decode(config["service_account_base64"]).decode("utf-8")
        service_info = json.loads(json_str)
        credentials = service_account.Credentials.from_service_account_info(
            service_info, scopes=scopes
        )
    else:
        raise ValueError(
            "Gmail API config must include either 'service_account_json' "
            "or 'service_account_base64'"
        )

    # Delegate to the specified user (required for sending as that user)
    if delegated_user:
        credentials = credentials.with_subject(delegated_user)

    # Build the Gmail service
    service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
    return service


class GmailAPIBackend(BaseEmailBackend):
    """
    Django email backend that sends emails via Gmail API.

    This is more reliable than SMTP for Google Workspace environments
    and supports domain-wide delegation with service accounts.
    """

    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.config = getattr(settings, "GMAIL_API", {})
        self._service = None

    @property
    def service(self):
        """Lazy-load the Gmail service."""
        if self._service is None:
            self._service = get_gmail_service(self.config)
        return self._service

    def send_messages(self, email_messages):
        """
        Send one or more EmailMessage objects and return the number sent.
        """
        if not email_messages:
            return 0

        sent_count = 0
        for message in email_messages:
            try:
                self._send(message)
                sent_count += 1
            except Exception as e:
                logger.error(f"Failed to send email via Gmail API: {e}")
                if not self.fail_silently:
                    raise

        return sent_count

    def _send(self, email_message):
        """Send a single EmailMessage via Gmail API."""
        # Convert Django EmailMessage to MIME message
        mime_message = self._build_mime_message(email_message)

        # Encode the message
        raw_message = base64.urlsafe_b64encode(mime_message.as_bytes()).decode("utf-8")

        # Send via Gmail API
        self.service.users().messages().send(
            userId="me", body={"raw": raw_message}
        ).execute()

        logger.info(
            f"Email sent via Gmail API to {', '.join(email_message.to)}: "
            f"{email_message.subject}"
        )

    def _build_mime_message(self, email_message):
        """
        Convert a Django EmailMessage to a MIME message.

        Handles plain text, HTML, and multipart messages with attachments.
        """
        # Check if this is an HTML email or has alternatives
        has_html = hasattr(email_message, "alternatives") and email_message.alternatives
        has_attachments = email_message.attachments

        if has_html or has_attachments:
            # Multipart message
            if has_attachments:
                msg = MIMEMultipart("mixed")
                msg_body = MIMEMultipart("alternative")
            else:
                msg = MIMEMultipart("alternative")
                msg_body = msg

            # Add plain text body
            msg_body.attach(MIMEText(email_message.body, "plain", "utf-8"))

            # Add HTML alternatives
            if has_html:
                for content, mimetype in email_message.alternatives:
                    if mimetype == "text/html":
                        msg_body.attach(MIMEText(content, "html", "utf-8"))

            # If we have attachments, add the body part and attachments
            if has_attachments:
                msg.attach(msg_body)
                for attachment in email_message.attachments:
                    self._add_attachment(msg, attachment)
        else:
            # Simple plain text message
            msg = MIMEText(email_message.body, "plain", "utf-8")

        # Set headers
        msg["Subject"] = email_message.subject
        msg["From"] = email_message.from_email
        msg["To"] = ", ".join(email_message.to)

        if email_message.cc:
            msg["Cc"] = ", ".join(email_message.cc)
        if email_message.bcc:
            msg["Bcc"] = ", ".join(email_message.bcc)
        if email_message.reply_to:
            msg["Reply-To"] = ", ".join(email_message.reply_to)

        return msg

    def _add_attachment(self, msg, attachment):
        """Add an attachment to the MIME message."""
        if isinstance(attachment, tuple):
            filename, content, mimetype = attachment
        else:
            # MIMEBase attachment
            msg.attach(attachment)
            return

        if mimetype is None:
            mimetype = "application/octet-stream"

        maintype, subtype = mimetype.split("/", 1)

        if maintype == "text":
            part = MIMEText(content, _subtype=subtype)
        else:
            part = MIMEBase(maintype, subtype)
            if isinstance(content, str):
                content = content.encode("utf-8")
            part.set_payload(content)
            from email import encoders

            encoders.encode_base64(part)

        part.add_header("Content-Disposition", "attachment", filename=filename)
        msg.attach(part)
