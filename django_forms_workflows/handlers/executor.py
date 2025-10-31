"""
Post-submission action executor.

Coordinates execution of post-submission actions based on triggers.
"""

import logging
from importlib import import_module

from .api_handler import APICallHandler
from .database_handler import DatabaseUpdateHandler
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
    """

    HANDLER_MAP = {
        "database": DatabaseUpdateHandler,
        "ldap": LDAPUpdateHandler,
        "api": APICallHandler,
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

            return result

        except Exception as e:
            result["message"] = f"Execution error: {str(e)}"
            logger.error(f"Error executing action '{action.name}': {e}", exc_info=True)
            return result

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

        try:
            # Parse module and function name
            module_path, function_name = action.custom_handler_path.rsplit(".", 1)

            # Import module
            module = import_module(module_path)

            # Get handler class or function
            handler = getattr(module, function_name)

            # Instantiate if it's a class
            if isinstance(handler, type):
                return handler(action, self.submission)

            # If it's a function, wrap it
            class FunctionHandler:
                def __init__(self, func, action, submission):
                    self.func = func
                    self.action = action
                    self.submission = submission

                def execute(self):
                    return self.func(self.action, self.submission)

            return FunctionHandler(handler, action, self.submission)

        except Exception as e:
            logger.error(
                f"Could not load custom handler '{action.custom_handler_path}': {e}",
                exc_info=True,
            )
            return None
