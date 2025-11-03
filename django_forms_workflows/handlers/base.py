"""
Base handler for post-submission actions.
"""

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class BaseActionHandler(ABC):
    """
    Base class for post-submission action handlers.
    """

    def __init__(self, action, submission):
        """
        Initialize the handler.

        Args:
            action: PostSubmissionAction instance
            submission: FormSubmission instance
        """
        self.action = action
        self.submission = submission
        self.user = submission.submitter
        self.form_data = submission.form_data

    @abstractmethod
    def execute(self):
        """
        Execute the action.

        Returns:
            dict: Result with 'success' (bool), 'message' (str), and optional 'data'
        """
        pass

    def get_form_field_value(self, field_name):
        """
        Get a form field value from the submission.

        Args:
            field_name: Name of the form field

        Returns:
            The field value or None if not found
        """
        return self.form_data.get(field_name)

    def get_user_profile_value(self, field_name):
        """
        Get a value from the user's profile or user model.

        Args:
            field_name: Name of the UserProfile field or User model field

        Returns:
            The field value or None if not found
        """
        try:
            # First try to get from user model directly (e.g., id, username, email)
            if hasattr(self.user, field_name):
                return getattr(self.user, field_name, None)

            # Then try to get from user profile if it exists
            if hasattr(self.user, "profile"):
                profile = self.user.profile
                return getattr(profile, field_name, None)

            return None
        except Exception as e:
            logger.warning(f"Could not get user profile field {field_name}: {e}")
            return None

    def log_success(self, message, **kwargs):
        """Log successful action execution."""
        logger.info(
            f"PostSubmissionAction success: {self.action.name} "
            f"(submission {self.submission.id}): {message}",
            extra=kwargs,
        )

    def log_error(self, message, **kwargs):
        """Log action execution error."""
        logger.error(
            f"PostSubmissionAction error: {self.action.name} "
            f"(submission {self.submission.id}): {message}",
            extra=kwargs,
        )

    def log_warning(self, message, **kwargs):
        """Log action execution warning."""
        logger.warning(
            f"PostSubmissionAction warning: {self.action.name} "
            f"(submission {self.submission.id}): {message}",
            extra=kwargs,
        )
