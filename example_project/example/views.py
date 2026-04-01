from django.contrib.auth import get_user_model
from django.db.utils import OperationalError, ProgrammingError
from django.shortcuts import render
from django.urls import reverse

from django_forms_workflows.models import APIToken, FormDefinition, FormSubmission

DEMO_USERNAMES = [
    "farmer_brown",
    "farmer_jane",
    "mechanic_mike",
    "finance_faith",
    "safety_sam",
    "owner_olive",
    "irrigation_ivan",
    "integration_ivy",
]

SHOWCASE_FORMS = {
    "equipment-repair": [
        "dynamic assignees",
        "send back",
        "reassign",
        "editable approval data",
        "multifile uploads",
        "notifications",
        "webhooks",
    ],
    "capital-purchase": [
        "multi-step form",
        "conditional fields",
        "calculated fields",
        "API-enabled form",
        "parallel approvals",
        "bulk export / PDF",
        "approval-step fields",
    ],
    "irrigation-expansion": [
        "sequential approvals",
        "sub-workflows",
        "analytics sample data",
    ],
    "safety-incident-report": [
        "public submission",
        "signature field",
        "conditional logic",
        "PDF anytime",
    ],
    "farmer-contact-update": [
        "prefill sources",
        "database action",
        "API action",
    ],
    "harvest-batch-log": ["batch import", "Excel template"],
    "sensor-data-upload": ["spreadsheet field"],
}


def home(request):
    try:
        forms = {
            form.slug: form
            for form in FormDefinition.objects.filter(slug__in=SHOWCASE_FORMS)
            .select_related("category")
            .prefetch_related(
                "workflows__stages", "workflows__webhook_endpoints", "post_actions"
            )
        }
        showcase_cards = []
        for slug, features in SHOWCASE_FORMS.items():
            form = forms.get(slug)
            if not form:
                continue
            workflow_count = form.workflows.count()
            stage_count = sum(
                workflow.stages.count() for workflow in form.workflows.all()
            )
            webhook_count = sum(
                workflow.webhook_endpoints.count() for workflow in form.workflows.all()
            )
            showcase_cards.append(
                {
                    "form": form,
                    "features": features,
                    "workflow_count": workflow_count,
                    "stage_count": stage_count,
                    "webhook_count": webhook_count,
                    "submit_url": reverse(
                        "forms_workflows:form_submit", kwargs={"slug": form.slug}
                    ),
                    "admin_url": reverse(
                        "admin:django_forms_workflows_formdefinition_change",
                        args=[form.id],
                    ),
                    "builder_url": reverse("admin:form_builder_edit", args=[form.id]),
                    "workflow_builder_url": reverse(
                        "admin:workflow_builder",
                        args=[form.id],
                    ),
                }
            )

        user_model = get_user_model()
        demo_users = []
        user_lookup = {
            user.username: user
            for user in user_model.objects.filter(
                username__in=DEMO_USERNAMES
            ).prefetch_related("groups")
        }
        for username in DEMO_USERNAMES:
            user = user_lookup.get(username)
            if user is not None:
                demo_users.append(user)

        api_token = None
        if request.user.is_authenticated and request.user.is_staff:
            api_token = APIToken.objects.filter(name="Farm Demo API Token").first()

        context = {
            "demo_ready": bool(showcase_cards),
            "showcase_cards": showcase_cards,
            "demo_users": demo_users,
            "api_token": api_token,
            "stats": {
                "forms": FormDefinition.objects.count(),
                "submissions": FormSubmission.objects.count(),
                "workflow_forms": FormDefinition.objects.filter(workflows__isnull=False)
                .distinct()
                .count(),
            },
        }
    except (OperationalError, ProgrammingError):
        context = {
            "demo_ready": False,
            "showcase_cards": [],
            "demo_users": [],
            "api_token": None,
            "stats": {"forms": 0, "submissions": 0, "workflow_forms": 0},
        }
    return render(request, "index.html", context)
