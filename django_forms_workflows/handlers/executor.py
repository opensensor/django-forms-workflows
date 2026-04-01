"""
Post-submission action executor.

Coordinates execution of post-submission actions based on triggers.
"""

import logging
from importlib import import_module

from .api_handler import APICallHandler
from .database_handler import DatabaseUpdateHandler
from .email_handler import EmailHandler
from .ldap_handler import LDAPUpdateHandler

logger = logging.getLogger(__name__)


class PostSubmissionActionExecutor:
    """
    Executes post-submission actions for a form submission.

    Handles:
    - Action filtering by trigger type
    - Conditional execution
    - Error handling and retries
    - Custom handler loading
    - Action execution logging (for is_locked functionality)
    """

    HANDLER_MAP = {
        "database": DatabaseUpdateHandler,
        "ldap": LDAPUpdateHandler,
        "api": APICallHandler,
        "email": EmailHandler,
    }

    def __init__(self, submission, trigger):
        """
        Initialize the executor.

        Args:
            submission: FormSubmission instance
            trigger: Trigger type ('on_submit', 'on_approve', 'on_reject', 'on_complete')
        """
        self.submission = submission
        self.trigger = trigger
        self.results = []

    def execute_all(self):
        """
        Execute all post-submission actions for the given trigger.

        Returns:
            dict: Summary of execution results
        """
        # Get actions for this form and trigger
        actions = self._get_actions()

        if not actions:
            logger.debug(
                f"No post-submission actions for trigger '{self.trigger}' "
                f"on form {self.submission.form_definition.name}"
            )
            return {
                "executed": 0,
                "succeeded": 0,
                "failed": 0,
                "skipped": 0,
                "results": [],
            }

        logger.info(
            f"Executing {len(actions)} post-submission action(s) "
            f"for trigger '{self.trigger}' on submission {self.submission.id}"
        )

        # Execute each action
        executed = 0
        succeeded = 0
        failed = 0
        skipped = 0

        for action in actions:
            result = self._execute_action(action)
            self.results.append(result)

            if result["skipped"]:
                skipped += 1
            elif result["success"]:
                executed += 1
                succeeded += 1
            else:
                executed += 1
                failed += 1

        summary = {
            "executed": executed,
            "succeeded": succeeded,
            "failed": failed,
            "skipped": skipped,
            "results": self.results,
        }

        logger.info(
            f"Post-submission actions complete: "
            f"{succeeded} succeeded, {failed} failed, {skipped} skipped"
        )

        return summary

    def _get_actions(self):
        """
        Get post-submission actions for this form and trigger.

        Returns:
            QuerySet: PostSubmissionAction instances
        """
        from django_forms_workflows.models import PostSubmissionAction

        return PostSubmissionAction.objects.filter(
            form_definition=self.submission.form_definition,
            trigger=self.trigger,
            is_active=True,
        ).order_by("order", "name")

    def _execute_action(self, action):
        """
        Execute a single post-submission action.

        Args:
            action: PostSubmissionAction instance

        Returns:
            dict: Execution result
        """
        result = {
            "action_id": action.id,
            "action_name": action.name,
            "action_type": action.action_type,
            "success": False,
            "skipped": False,
            "message": "",
            "attempts": 0,
        }

        try:
            # Check if action should execute (conditional logic)
            if not action.should_execute(self.submission):
                result["skipped"] = True
                result["message"] = "Condition not met"
                logger.debug(f"Skipping action '{action.name}': condition not met")
                return result

            # Get handler for action type
            handler = self._get_handler(action)
            if not handler:
                result["message"] = f"No handler for action type: {action.action_type}"
                logger.error(result["message"])
                return result

            # Execute with retries
            max_attempts = action.max_retries + 1 if action.retry_on_failure else 1

            for attempt in range(max_attempts):
                result["attempts"] = attempt + 1

                try:
                    exec_result = handler.execute()
                    result["success"] = exec_result["success"]
                    result["message"] = exec_result["message"]
                    result["data"] = exec_result.get("data")

                    if result["success"]:
                        break  # Success, no need to retry

                    if not action.retry_on_failure:
                        break  # Don't retry

                    if attempt < max_attempts - 1:
                        logger.warning(
                            f"Action '{action.name}' failed (attempt {attempt + 1}/{max_attempts}), "
                            f"retrying..."
                        )

                except Exception as e:
                    result["message"] = f"Handler exception: {str(e)}"
                    logger.error(
                        f"Action '{action.name}' handler exception: {e}", exc_info=True
                    )

                    if not action.retry_on_failure or attempt >= max_attempts - 1:
                        break

            # Handle failure
            if not result["success"] and not action.fail_silently:
                logger.error(
                    f"Action '{action.name}' failed after {result['attempts']} attempt(s): "
                    f"{result['message']}"
                )

            # Log the execution for is_locked functionality
            self._log_execution(action, result)

            return result

        except Exception as e:
            result["message"] = f"Execution error: {str(e)}"
            logger.error(f"Error executing action '{action.name}': {e}", exc_info=True)
            # Log failed execution
            self._log_execution(action, result)
            return result

    def _log_execution(self, action, result):
        """
        Log action execution for is_locked functionality.

        Args:
            action: PostSubmissionAction instance
            result: Execution result dict
        """
        try:
            from django_forms_workflows.models import ActionExecutionLog

            ActionExecutionLog.objects.create(
                action=action,
                submission=self.submission,
                trigger=self.trigger,
                success=result.get("success", False),
                message=result.get("message", ""),
                execution_data={
                    "attempts": result.get("attempts", 0),
                    "data": result.get("data"),
                },
            )
        except Exception as e:
            logger.warning(f"Could not log action execution: {e}")

    def _get_handler(self, action):
        """
        Get handler instance for the action.

        Args:
            action: PostSubmissionAction instance

        Returns:
            BaseActionHandler instance or None
        """
        if action.action_type == "custom":
            return self._get_custom_handler(action)

        handler_class = self.HANDLER_MAP.get(action.action_type)
        if not handler_class:
            return None

        return handler_class(action, self.submission)

    def _get_custom_handler(self, action):
        """
        Load and instantiate a custom handler.

        Resolution order:
        1. Look up ``custom_handler_path`` in the callback registry (short name).
        2. Fall back to direct dotted-path import (backward compatible).

        Args:
            action: PostSubmissionAction instance

        Returns:
            Handler instance or None
        """
        if not action.custom_handler_path:
            logger.error(
                f"Custom handler path not configured for action '{action.name}'"
            )
            return None

        handler_ref = action.custom_handler_path

        # 1. Try the callback registry first (allows short names like "id_photo_copy")
        from django_forms_workflows.callback_registry import get_handler as registry_get

        handler = registry_get(handler_ref)

        # 2. Fall back to direct dotted-path import
        if handler is None and "." in handler_ref:
            try:
                module_path, function_name = handler_ref.rsplit(".", 1)
                module = import_module(module_path)
                handler = getattr(module, function_name)
            except Exception as e:
                logger.error(
                    f"Could not load custom handler '{handler_ref}': {e}",
                    exc_info=True,
                )
                return None

        if handler is None:
            logger.error(
                f"Custom handler '{handler_ref}' not found in registry "
                f"and could not be imported for action '{action.name}'"
            )
            return None

        # Instantiate if it's a class
        if isinstance(handler, type):
            return handler(action, self.submission)

        # If it's a function, wrap it
        class _FunctionHandler:
            def __init__(self, func, _action, _submission):
                self.func = func
                self.action = _action
                self.submission = _submission

            def execute(self):
                return self.func(self.action, self.submission)

        return _FunctionHandler(handler, action, self.submission)
