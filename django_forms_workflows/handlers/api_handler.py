"""
API call handler for post-submission actions.

Makes HTTP API calls with form data after submission or approval.
"""

import json
import logging

import requests

from .base import BaseActionHandler

logger = logging.getLogger(__name__)


class APICallHandler(BaseActionHandler):
    """
    Handler for making API calls with form data.

    Supports:
    - Configurable HTTP methods (GET, POST, PUT, PATCH)
    - Custom headers
    - Template-based request bodies
    - Response validation
    """

    def execute(self):
        """
        Execute the API call.

        Returns:
            dict: Result with 'success', 'message', and optional 'data'
        """
        try:
            # Validate configuration
            if not self.action.api_endpoint:
                return {"success": False, "message": "API endpoint not configured"}

            # Build request
            method = (self.action.api_method or "POST").upper()
            url = self.action.api_endpoint
            headers = self._build_headers()
            body = self._build_body()

            # Execute API call
            result = self._call_api(method, url, headers, body)

            if result["success"]:
                self.log_success(result["message"])
            else:
                self.log_error(result["message"])

            return result

        except Exception as e:
            error_msg = f"API call failed: {str(e)}"
            self.log_error(error_msg, exc_info=True)
            return {"success": False, "message": error_msg}

    def _build_headers(self):
        """
        Build HTTP headers from configuration.

        Returns:
            dict: HTTP headers
        """
        headers = {}

        if self.action.api_headers:
            # api_headers is a JSON field
            if isinstance(self.action.api_headers, dict):
                headers = self.action.api_headers.copy()
            else:
                try:
                    headers = json.loads(self.action.api_headers)
                except json.JSONDecodeError:
                    self.log_warning("Could not parse api_headers as JSON")

        # Set default Content-Type if not specified
        if "Content-Type" not in headers:
            headers["Content-Type"] = "application/json"

        return headers

    def _build_body(self):
        """
        Build request body from template.

        Template can use {field_name} placeholders for form fields.

        Returns:
            str or dict: Request body
        """
        if not self.action.api_body_template:
            # No template, send all form data
            return self.form_data

        template = self.action.api_body_template

        # Build placeholders from form data
        placeholders = {}
        for field_name, value in self.form_data.items():
            placeholders[field_name] = value

        # Add user information
        placeholders.update(
            {
                "username": self.user.username,
                "email": self.user.email,
                "first_name": self.user.first_name,
                "last_name": self.user.last_name,
                "user_id": self.user.id,
            }
        )

        # Add submission information
        placeholders.update(
            {
                "submission_id": self.submission.id,
                "form_name": self.submission.form_definition.name,
                "status": self.submission.status,
            }
        )

        # Replace placeholders in template
        try:
            body_str = template.format(**placeholders)

            # Try to parse as JSON
            try:
                return json.loads(body_str)
            except json.JSONDecodeError:
                # Return as string if not valid JSON
                return body_str

        except KeyError as e:
            self.log_warning(f"Missing placeholder in body template: {e}")
            return self.form_data

    def _call_api(self, method, url, headers, body):
        """
        Execute the HTTP API call.

        Args:
            method: HTTP method (GET, POST, PUT, PATCH)
            url: API endpoint URL
            headers: HTTP headers dict
            body: Request body (dict or str)

        Returns:
            dict: Result with success status and message
        """
        try:
            # Prepare request kwargs
            kwargs = {
                "headers": headers,
                "timeout": 30,  # 30 second timeout
            }

            # Add body for methods that support it
            if method in ["POST", "PUT", "PATCH"]:
                if isinstance(body, dict):
                    kwargs["json"] = body
                else:
                    kwargs["data"] = body

            # Make request
            response = requests.request(method, url, **kwargs)

            # Check response status
            if response.status_code >= 200 and response.status_code < 300:
                return {
                    "success": True,
                    "message": f"API call successful: {method} {url} -> {response.status_code}",
                    "data": {
                        "status_code": response.status_code,
                        "response": response.text[:500],  # First 500 chars
                    },
                }
            else:
                return {
                    "success": False,
                    "message": f"API call failed: {method} {url} -> {response.status_code}",
                    "data": {
                        "status_code": response.status_code,
                        "response": response.text[:500],
                    },
                }

        except requests.exceptions.Timeout:
            return {"success": False, "message": f"API call timed out: {method} {url}"}
        except requests.exceptions.ConnectionError:
            return {
                "success": False,
                "message": f"API call connection error: {method} {url}",
            }
        except Exception as e:
            return {"success": False, "message": f"API call exception: {str(e)}"}
