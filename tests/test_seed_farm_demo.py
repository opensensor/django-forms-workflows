import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

from django_forms_workflows.models import (
    APIToken,
    FormDefinition,
    FormSubmission,
    PostSubmissionAction,
    SubWorkflowDefinition,
    WebhookEndpoint,
)


@pytest.mark.django_db
def test_seed_farm_demo_creates_comprehensive_showcase():
    call_command("seed_farm_demo", verbosity=0)

    assert FormDefinition.objects.filter(
        slug="equipment-repair", enable_multi_step=True
    ).exists()
    assert FormDefinition.objects.filter(
        slug="capital-purchase", api_enabled=True
    ).exists()
    assert FormDefinition.objects.filter(
        slug="harvest-batch-log", allow_batch_import=True
    ).exists()
    assert FormDefinition.objects.filter(
        slug="safety-incident-report", requires_login=False
    ).exists()
    assert FormDefinition.objects.filter(slug="sensor-data-upload").exists()

    purchase_form = FormDefinition.objects.get(slug="capital-purchase")
    assert purchase_form.workflows.filter(allow_bulk_export=True).exists()
    assert purchase_form.workflows.filter(allow_bulk_pdf_export=True).exists()
    assert WebhookEndpoint.objects.filter(
        workflow__form_definition=purchase_form
    ).exists()

    irrigation_form = FormDefinition.objects.get(slug="irrigation-expansion")
    assert SubWorkflowDefinition.objects.filter(
        parent_workflow__form_definition=irrigation_form,
        count_field="zone_count",
    ).exists()

    assert (
        PostSubmissionAction.objects.filter(
            form_definition__slug="farmer-contact-update"
        ).count()
        >= 2
    )
    assert APIToken.objects.filter(name="Farm Demo API Token").exists()
    assert FormSubmission.objects.filter(user_agent="seed_farm_demo").exists()

    user_model = get_user_model()
    assert user_model.objects.filter(
        username="farmer_brown", is_superuser=True
    ).exists()
    assert user_model.objects.filter(username="integration_ivy").exists()


@pytest.mark.django_db
def test_seed_farm_demo_is_idempotent():
    call_command("seed_farm_demo", verbosity=0)
    first_form_count = FormDefinition.objects.count()
    first_demo_submission_count = FormSubmission.objects.filter(
        user_agent="seed_farm_demo"
    ).count()
    first_token_count = APIToken.objects.filter(name="Farm Demo API Token").count()

    call_command("seed_farm_demo", verbosity=0)

    assert FormDefinition.objects.count() == first_form_count
    assert (
        FormSubmission.objects.filter(user_agent="seed_farm_demo").count()
        == first_demo_submission_count
    )
    assert (
        APIToken.objects.filter(name="Farm Demo API Token").count() == first_token_count
    )
