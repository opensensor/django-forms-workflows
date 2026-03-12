"""
Shared fixtures for django-forms-workflows test suite.
"""

import pytest
from django.contrib.auth.models import Group, User

from django_forms_workflows.models import (
    FormCategory,
    FormDefinition,
    FormField,
    FormSubmission,
    PostSubmissionAction,
    PrefillSource,
    WorkflowDefinition,
    WorkflowStage,
)


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username="testuser",
        email="test@example.com",
        password="testpass123",
        first_name="Test",
        last_name="User",
    )


@pytest.fixture
def staff_user(db):
    return User.objects.create_user(
        username="staffuser",
        email="staff@example.com",
        password="testpass123",
        is_staff=True,
    )


@pytest.fixture
def superuser(db):
    return User.objects.create_superuser(
        username="admin",
        email="admin@example.com",
        password="testpass123",
    )


@pytest.fixture
def approver_user(db):
    return User.objects.create_user(
        username="approver",
        email="approver@example.com",
        password="testpass123",
    )


@pytest.fixture
def approval_group(db):
    return Group.objects.create(name="Approvers")


@pytest.fixture
def second_approval_group(db):
    return Group.objects.create(name="Finance Approvers")


@pytest.fixture
def category(db):
    return FormCategory.objects.create(
        name="HR Forms",
        slug="hr-forms",
        description="Human Resources forms",
        order=1,
    )


@pytest.fixture
def form_definition(db, category):
    return FormDefinition.objects.create(
        name="Test Form",
        slug="test-form",
        description="A test form",
        instructions="Fill out this test form",
        category=category,
        is_active=True,
        allow_save_draft=True,
        allow_withdrawal=True,
    )


@pytest.fixture
def form_with_fields(form_definition):
    FormField.objects.create(
        form_definition=form_definition,
        field_name="full_name",
        field_label="Full Name",
        field_type="text",
        order=1,
        required=True,
    )
    FormField.objects.create(
        form_definition=form_definition,
        field_name="email",
        field_label="Email",
        field_type="email",
        order=2,
        required=True,
    )
    FormField.objects.create(
        form_definition=form_definition,
        field_name="department",
        field_label="Department",
        field_type="select",
        order=3,
        choices=[
            {"value": "hr", "label": "Human Resources"},
            {"value": "it", "label": "IT"},
            {"value": "finance", "label": "Finance"},
        ],
    )
    FormField.objects.create(
        form_definition=form_definition,
        field_name="amount",
        field_label="Amount",
        field_type="decimal",
        order=4,
        min_value=0,
        max_value=10000,
    )
    FormField.objects.create(
        form_definition=form_definition,
        field_name="notes",
        field_label="Notes",
        field_type="textarea",
        order=5,
    )
    return form_definition


@pytest.fixture
def workflow(form_definition, approval_group):
    wf = WorkflowDefinition.objects.create(
        form_definition=form_definition,
        requires_approval=True,
        approval_logic="any",
    )
    wf.approval_groups.add(approval_group)
    return wf


@pytest.fixture
def staged_workflow(form_definition, approval_group, second_approval_group):
    wf = WorkflowDefinition.objects.create(
        form_definition=form_definition,
        requires_approval=True,
        approval_logic="sequence",
    )
    stage1 = WorkflowStage.objects.create(
        workflow=wf, name="Manager Review", order=1, approval_logic="all"
    )
    stage1.approval_groups.add(approval_group)
    stage2 = WorkflowStage.objects.create(
        workflow=wf, name="Finance Review", order=2, approval_logic="all"
    )
    stage2.approval_groups.add(second_approval_group)
    return wf


@pytest.fixture
def submission(form_with_fields, user):
    return FormSubmission.objects.create(
        form_definition=form_with_fields,
        submitter=user,
        form_data={
            "full_name": "Test User",
            "email": "test@example.com",
            "department": "it",
            "amount": "500.00",
            "notes": "Test submission",
        },
        status="submitted",
    )


@pytest.fixture
def prefill_source(db):
    return PrefillSource.objects.create(
        name="User Email",
        source_type="user",
        source_key="user.email",
        description="Current user email",
    )


@pytest.fixture
def db_prefill_source(db):
    return PrefillSource.objects.create(
        name="Employee Name",
        source_type="database",
        source_key="dbo.EMPLOYEES.FULL_NAME",
        db_schema="dbo",
        db_table="EMPLOYEES",
        db_column="FULL_NAME",
        db_lookup_field="ID_NUMBER",
        db_user_field="employee_id",
    )


@pytest.fixture
def post_action_email(form_definition):
    return PostSubmissionAction.objects.create(
        form_definition=form_definition,
        name="Send Notification",
        action_type="email",
        trigger="on_approve",
        email_to="admin@example.com",
        email_subject_template="Form {form_name} approved",
        email_body_template="Submission by {submitter} has been approved.",
    )
