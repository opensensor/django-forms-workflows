"""
File workflow handlers for Django Forms Workflows.

Handles file operations triggered by workflow hooks:
- Rename files based on patterns
- Move files to different locations
- Copy files
- Delete files
- Call webhooks
- Execute custom handlers
"""

import hashlib
import logging
import os
import re
from importlib import import_module

import requests
from django.conf import settings
from django.core.files.storage import default_storage
from django.utils import timezone

logger = logging.getLogger(__name__)


class FilePatternResolver:
    """
    Resolves file naming patterns with token substitution.

    Supported tokens:
    - {user.id} - User ID
    - {user.username} - Username
    - {user.email} - User email
    - {user.employee_id} - Employee ID from profile
    - {field_name} - Form field name
    - {form_slug} - Form definition slug
    - {submission_id} - Submission ID
    - {status} - Current file status
    - {date} - Current date (YYYY-MM-DD)
    - {datetime} - Current datetime (YYYYMMDD_HHMMSS)
    - {original_name} - Original filename (without extension)
    - {ext} - File extension
    """

    def __init__(self, managed_file, submission=None):
        self.managed_file = managed_file
        self.submission = submission or managed_file.submission
        self.user = self.submission.submitter

    def resolve(self, pattern):
        """Resolve a pattern string with token substitution."""
        if not pattern:
            return ""

        now = timezone.now()
        original_name, ext = os.path.splitext(self.managed_file.original_filename)
        ext = ext.lstrip(".")  # Remove leading dot

        tokens = {
            "user.id": str(self.user.id),
            "user.username": self.user.username,
            "user.email": self.user.email,
            "user.employee_id": self._get_employee_id(),
            "field_name": self._get_field_name(),
            "form_slug": self.submission.form_definition.slug,
            "submission_id": str(self.submission.id),
            "status": self.managed_file.status,
            "date": now.strftime("%Y-%m-%d"),
            "datetime": now.strftime("%Y%m%d_%H%M%S"),
            "original_name": original_name,
            "ext": ext,
        }

        result = pattern
        for token, value in tokens.items():
            result = result.replace("{" + token + "}", str(value or ""))

        # Clean up any remaining empty tokens
        result = re.sub(r"\{[^}]+\}", "", result)
        # Clean up double slashes/underscores
        result = re.sub(r"//+", "/", result)
        result = re.sub(r"__+", "_", result)

        return result

    def _get_employee_id(self):
        """Get employee ID from user profile."""
        try:
            if hasattr(self.user, "forms_profile"):
                return self.user.forms_profile.employee_id or ""
            if hasattr(self.user, "profile"):
                return getattr(self.user.profile, "employee_id", "") or ""
        except Exception:
            pass
        return ""

    def _get_field_name(self):
        """Get the form field name."""
        if self.managed_file.form_field:
            return self.managed_file.form_field.field_name
        return "file"


class FileOperationHandler:
    """
    Handles file operations (rename, move, copy, delete).
    """

    def __init__(self, managed_file, hook=None):
        self.managed_file = managed_file
        self.hook = hook
        self.resolver = FilePatternResolver(managed_file)
        self.storage = default_storage

    def rename(self, target_pattern):
        """Rename file based on pattern."""
        try:
            new_filename = self.resolver.resolve(target_pattern)
            if not new_filename:
                return {"success": False, "message": "Empty target filename"}

            old_path = self.managed_file.file_path
            directory = os.path.dirname(old_path)
            new_path = os.path.join(directory, new_filename)

            if self.storage.exists(old_path):
                # Read content
                with self.storage.open(old_path, "rb") as f:
                    content = f.read()
                # Write to new location
                self.storage.save(new_path, content)
                # Delete old
                self.storage.delete(old_path)

                # Update managed file
                self.managed_file.stored_filename = new_filename
                self.managed_file.file_path = new_path
                self.managed_file.save(update_fields=["stored_filename", "file_path"])

                logger.info(f"Renamed file from {old_path} to {new_path}")
                return {"success": True, "message": f"Renamed to {new_filename}"}
            else:
                return {"success": False, "message": f"File not found: {old_path}"}

        except Exception as e:
            logger.error(f"Error renaming file: {e}", exc_info=True)
            return {"success": False, "message": str(e)}

    def move(self, target_pattern):
        """Move file to new location based on pattern."""
        try:
            new_path = self.resolver.resolve(target_pattern)
            if not new_path:
                return {"success": False, "message": "Empty target path"}

            old_path = self.managed_file.file_path

            if self.storage.exists(old_path):
                # Ensure directory exists
                directory = os.path.dirname(new_path)
                if directory and not self.storage.exists(directory):
                    os.makedirs(
                        os.path.join(settings.MEDIA_ROOT, directory), exist_ok=True
                    )

                # Read and write to new location
                with self.storage.open(old_path, "rb") as f:
                    content = f.read()
                self.storage.save(new_path, content)
                self.storage.delete(old_path)

                # Update managed file
                self.managed_file.file_path = new_path
                self.managed_file.stored_filename = os.path.basename(new_path)
                self.managed_file.save(update_fields=["file_path", "stored_filename"])

                logger.info(f"Moved file from {old_path} to {new_path}")
                return {"success": True, "message": f"Moved to {new_path}"}
            else:
                return {"success": False, "message": f"File not found: {old_path}"}

        except Exception as e:
            logger.error(f"Error moving file: {e}", exc_info=True)
            return {"success": False, "message": str(e)}

    def copy(self, target_pattern):
        """Copy file to new location based on pattern."""
        try:
            new_path = self.resolver.resolve(target_pattern)
            if not new_path:
                return {"success": False, "message": "Empty target path"}

            old_path = self.managed_file.file_path

            if self.storage.exists(old_path):
                # Ensure directory exists
                directory = os.path.dirname(new_path)
                if directory and not self.storage.exists(directory):
                    os.makedirs(
                        os.path.join(settings.MEDIA_ROOT, directory), exist_ok=True
                    )

                # Read and write to new location
                with self.storage.open(old_path, "rb") as f:
                    content = f.read()
                self.storage.save(new_path, content)

                logger.info(f"Copied file from {old_path} to {new_path}")
                return {"success": True, "message": f"Copied to {new_path}"}
            else:
                return {"success": False, "message": f"File not found: {old_path}"}

        except Exception as e:
            logger.error(f"Error copying file: {e}", exc_info=True)
            return {"success": False, "message": str(e)}

    def delete(self):
        """Delete the file."""
        try:
            file_path = self.managed_file.file_path

            if self.storage.exists(file_path):
                self.storage.delete(file_path)

                # Update managed file status
                self.managed_file.status = "deleted"
                self.managed_file.status_changed_at = timezone.now()
                self.managed_file.save(update_fields=["status", "status_changed_at"])

                logger.info(f"Deleted file: {file_path}")
                return {"success": True, "message": f"Deleted {file_path}"}
            else:
                return {"success": False, "message": f"File not found: {file_path}"}

        except Exception as e:
            logger.error(f"Error deleting file: {e}", exc_info=True)
            return {"success": False, "message": str(e)}


class WebhookHandler:
    """
    Handles webhook calls for file workflow hooks.
    """

    def __init__(self, managed_file, hook):
        self.managed_file = managed_file
        self.hook = hook
        self.resolver = FilePatternResolver(managed_file)

    def call(self):
        """Call the webhook with file information."""
        try:
            url = self.hook.webhook_url
            if not url:
                return {"success": False, "message": "No webhook URL configured"}

            method = (self.hook.webhook_method or "POST").upper()
            headers = self.hook.webhook_headers or {}

            # Build payload
            payload = self._build_payload()

            # Make request
            response = requests.request(
                method=method,
                url=url,
                json=payload,
                headers=headers,
                timeout=30,
            )

            if response.ok:
                logger.info(f"Webhook call successful: {url} ({response.status_code})")
                return {
                    "success": True,
                    "message": f"Webhook returned {response.status_code}",
                    "data": {"status_code": response.status_code},
                }
            else:
                logger.warning(f"Webhook call failed: {url} ({response.status_code})")
                return {
                    "success": False,
                    "message": f"Webhook returned {response.status_code}",
                    "data": {"status_code": response.status_code},
                }

        except requests.Timeout:
            logger.error(f"Webhook timeout: {self.hook.webhook_url}")
            return {"success": False, "message": "Webhook timeout"}
        except Exception as e:
            logger.error(f"Error calling webhook: {e}", exc_info=True)
            return {"success": False, "message": str(e)}

    def _build_payload(self):
        """Build webhook payload with file information."""
        submission = self.managed_file.submission

        # Default payload
        payload = {
            "event": self.hook.trigger,
            "timestamp": timezone.now().isoformat(),
            "file": {
                "id": self.managed_file.id,
                "original_filename": self.managed_file.original_filename,
                "stored_filename": self.managed_file.stored_filename,
                "file_path": self.managed_file.file_path,
                "file_size": self.managed_file.file_size,
                "mime_type": self.managed_file.mime_type,
                "status": self.managed_file.status,
                "version": self.managed_file.version,
            },
            "submission": {
                "id": submission.id,
                "form_slug": submission.form_definition.slug,
                "form_name": submission.form_definition.name,
                "status": submission.status,
            },
            "user": {
                "id": submission.submitter.id,
                "username": submission.submitter.username,
                "email": submission.submitter.email,
            },
        }

        # Apply custom payload template if provided
        if self.hook.webhook_payload_template:
            try:
                import json

                template = self.hook.webhook_payload_template
                resolved = self.resolver.resolve(template)
                payload = json.loads(resolved)
            except Exception as e:
                logger.warning(f"Failed to parse webhook payload template: {e}")

        return payload


class FileHookExecutor:
    """
    Executes file workflow hooks.
    """

    def __init__(self, managed_file, trigger):
        self.managed_file = managed_file
        self.trigger = trigger
        self.results = []

    def execute_all(self):
        """Execute all hooks for the given trigger."""
        from django_forms_workflows.models import FileWorkflowHook

        hooks = FileWorkflowHook.objects.filter(
            trigger=self.trigger,
            is_active=True,
        ).order_by("order", "name")

        executed = 0
        succeeded = 0
        failed = 0
        skipped = 0

        for hook in hooks:
            result = self._execute_hook(hook)
            self.results.append(result)

            if result.get("skipped"):
                skipped += 1
            elif result.get("success"):
                executed += 1
                succeeded += 1
            else:
                executed += 1
                failed += 1

        return {
            "executed": executed,
            "succeeded": succeeded,
            "failed": failed,
            "skipped": skipped,
            "results": self.results,
        }

    def _execute_hook(self, hook):
        """Execute a single hook."""
        result = {
            "hook_id": hook.id,
            "hook_name": hook.name,
            "action": hook.action,
            "success": False,
            "skipped": False,
            "message": "",
        }

        try:
            # Check if hook should execute
            if not hook.should_execute(self.managed_file):
                result["skipped"] = True
                result["message"] = "Condition not met"
                return result

            # Execute based on action type
            if hook.action == "rename":
                handler = FileOperationHandler(self.managed_file, hook)
                exec_result = handler.rename(hook.target_pattern)
            elif hook.action == "move":
                handler = FileOperationHandler(self.managed_file, hook)
                exec_result = handler.move(hook.target_pattern)
            elif hook.action == "copy":
                handler = FileOperationHandler(self.managed_file, hook)
                exec_result = handler.copy(hook.target_pattern)
            elif hook.action == "delete":
                handler = FileOperationHandler(self.managed_file, hook)
                exec_result = handler.delete()
            elif hook.action in ("webhook", "api"):
                handler = WebhookHandler(self.managed_file, hook)
                exec_result = handler.call()
            elif hook.action == "custom":
                exec_result = self._execute_custom(hook)
            else:
                exec_result = {
                    "success": False,
                    "message": f"Unknown action: {hook.action}",
                }

            result.update(exec_result)

        except Exception as e:
            result["message"] = f"Error: {str(e)}"
            logger.error(f"Error executing hook {hook.name}: {e}", exc_info=True)

        return result

    def _execute_custom(self, hook):
        """Execute a custom handler."""
        if not hook.custom_handler_path:
            return {"success": False, "message": "No custom handler configured"}

        try:
            module_path, function_name = hook.custom_handler_path.rsplit(".", 1)
            module = import_module(module_path)
            handler = getattr(module, function_name)

            # Call handler with file and config
            result = handler(
                self.managed_file,
                hook.custom_handler_config or {},
            )

            if isinstance(result, dict):
                return result
            return {"success": bool(result), "message": str(result)}

        except Exception as e:
            logger.error(f"Error in custom handler: {e}", exc_info=True)
            return {"success": False, "message": str(e)}


def calculate_file_hash(file_content):
    """Calculate SHA-256 hash of file content."""
    if isinstance(file_content, bytes):
        return hashlib.sha256(file_content).hexdigest()
    # If file-like object, read in chunks
    hasher = hashlib.sha256()
    for chunk in iter(lambda: file_content.read(8192), b""):
        hasher.update(chunk)
    file_content.seek(0)  # Reset file pointer
    return hasher.hexdigest()


def execute_file_hooks(managed_file, trigger):
    """
    Execute file workflow hooks for the given trigger.

    This is the main entry point called by the workflow engine.
    """
    try:
        executor = FileHookExecutor(managed_file, trigger)
        results = executor.execute_all()

        if results["failed"] > 0:
            logger.warning(
                f"Some file hooks failed for file {managed_file.id}: "
                f"{results['failed']} failed, {results['succeeded']} succeeded"
            )
        elif results["executed"] > 0:
            logger.info(
                f"File hooks completed for file {managed_file.id}: "
                f"{results['succeeded']} succeeded"
            )

        return results

    except Exception as e:
        logger.error(
            f"Error executing file hooks for file {managed_file.id}: {e}",
            exc_info=True,
        )
        return {"executed": 0, "succeeded": 0, "failed": 0, "skipped": 0, "results": []}
