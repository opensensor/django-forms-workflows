"""Regression coverage for the security audit's authorization and input boundaries."""

import base64
import json
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory
from django.urls import reverse

from django_forms_workflows.models import (
    APIToken,
    DocumentTemplate,
    FormField,
    FormSubmission,
)
from django_forms_workflows.pdf import safe_pdf_url_fetcher
from django_forms_workflows.security import (
    grant_submission_receipt,
    render_success_message,
)
from django_forms_workflows.sso_backends import bound_sso_user, link_to_existing_user
from django_forms_workflows.utils import _get_client_ip, check_rate_limit

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def isolated_uploads(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    cache.clear()


@pytest.fixture
def auth_client(client, user):
    client.force_login(user)
    return client


def test_sso_does_not_link_email_prefix_or_full_email(superuser):
    backend = SimpleNamespace(name="google-oauth2")
    for email in [f"{superuser.username}@attacker.example", superuser.email]:
        assert link_to_existing_user(backend, {"email": email}, uid="unbound") == {}


def test_sso_binding_requires_matching_provider_and_subject(settings, user):
    settings.FORMS_WORKFLOWS_SSO = {
        "account_bindings": {"google-oauth2": {"subject-123": user.username}}
    }
    backend = SimpleNamespace(name="google-oauth2")
    assert link_to_existing_user(backend, {}, uid="subject-123")["user"] == user
    assert link_to_existing_user(backend, {}, uid="different") == {}
    assert bound_sso_user("different-provider", "subject-123") is None
    user.is_active = False
    user.save()
    with pytest.raises(PermissionDenied):
        link_to_existing_user(backend, {}, uid="subject-123")
    with pytest.raises(PermissionDenied):
        link_to_existing_user(backend, {}, user=user)


@pytest.mark.parametrize("bound", [False, True])
def test_saml_uses_issuer_subject_binding(monkeypatch, settings, user, bound):
    from django_forms_workflows.sso_views import SAMLACSView

    fake_auth = Mock()
    fake_auth.get_errors.return_value = []
    fake_auth.is_authenticated.return_value = True
    fake_auth.get_attributes.return_value = {"email": [user.email]}
    fake_auth.get_nameid.return_value = "stable-subject"
    monkeypatch.setitem(
        sys.modules,
        "onelogin.saml2.auth",
        SimpleNamespace(OneLogin_Saml2_Auth=Mock(return_value=fake_auth)),
    )
    settings.FORMS_WORKFLOWS_SSO = (
        {"account_bindings": {"saml:trusted-issuer": {"stable-subject": user.username}}}
        if bound
        else {}
    )
    request = RequestFactory().post("/sso/saml/acs/")
    with (
        patch("django_forms_workflows.sso_views.is_saml_available", return_value=True),
        patch(
            "django_forms_workflows.sso_views.get_saml_config",
            return_value={"idp": {"entityId": "trusted-issuer"}},
        ),
        patch("django_forms_workflows.sso_views.login") as login,
        patch("django_forms_workflows.sso_backends.sync_user_ldap_groups"),
        patch("django_forms_workflows.sso_backends.sync_user_ldap_attributes"),
    ):
        response = SAMLACSView.as_view()(request)
    assert response.status_code == (302 if bound else 400)
    assert login.called == bound
    if bound:
        assert login.call_args.args[1] == user


def test_success_receipt_rejects_anonymous_and_other_users(
    client, user, approver_user, form_definition
):
    form_definition.success_message = "Secret: {answer}"
    form_definition.save()
    sub = FormSubmission.objects.create(
        form_definition=form_definition, submitter=user, form_data={"answer": "private"}
    )
    url = reverse("forms_workflows:submission_success", args=[sub.pk])
    assert client.get(url).status_code == 404
    client.force_login(approver_user)
    assert client.get(url).status_code == 404
    client.force_login(user)
    assert b"private" in client.get(url).content


def test_public_receipt_is_session_bound_and_expires(client, form_definition):
    sub = FormSubmission.objects.create(form_definition=form_definition, form_data={})
    url = reverse("forms_workflows:submission_success", args=[sub.pk])
    request = SimpleNamespace(session=client.session)
    grant_submission_receipt(request, sub)
    request.session.save()
    assert client.get(url).status_code == 200
    from django.test import Client

    assert Client().get(url).status_code == 404
    session = client.session
    session["dfw_receipts"] = {str(sub.pk): 0}
    session.save()
    assert client.get(url).status_code == 404


def test_success_message_preserves_markup_but_escapes_answers():
    message = render_success_message(
        '<p>Hello {name}</p><a href="{link}">Continue</a>',
        {"name": '<img src=x onerror="alert(1)">', "link": "javascript:alert(1)"},
    )
    assert "<p>Hello &lt;img" in message
    assert "<img" not in message
    assert "javascript:" not in message


def test_anonymous_public_submission_gets_receipt(client, form_definition):
    form_definition.requires_login = False
    form_definition.success_message = "Thanks {name}"
    form_definition.save()
    FormField.objects.create(
        form_definition=form_definition,
        field_name="name",
        field_label="Name",
        field_type="text",
    )
    with patch("django_forms_workflows.views.create_approval_tasks"):
        response = client.post(
            reverse("forms_workflows:form_submit", args=[form_definition.slug]),
            {"name": "Public"},
        )
    assert response.status_code == 302
    assert b"Thanks Public" in client.get(response.url).content


@pytest.mark.parametrize("method", ["get", "post"])
def test_embed_requires_login(client, form_definition, method):
    form_definition.embed_enabled = True
    form_definition.requires_login = True
    form_definition.save()
    response = getattr(client, method)(
        reverse("forms_workflows:form_embed", args=[form_definition.slug])
    )
    assert response.status_code == 403
    assert not FormSubmission.objects.filter(form_definition=form_definition).exists()


def test_embed_enforces_one_per_user(auth_client, user, form_definition):
    form_definition.embed_enabled = True
    form_definition.one_per_user = True
    form_definition.save()
    FormSubmission.objects.create(
        form_definition=form_definition,
        submitter=user,
        form_data={},
        status="submitted",
    )
    response = auth_client.post(
        reverse("forms_workflows:form_embed", args=[form_definition.slug])
    )
    assert response.status_code == 403


@pytest.fixture
def upload_form(form_definition):
    FormField.objects.create(
        form_definition=form_definition,
        field_name="attachment",
        field_label="Attachment",
        field_type="file",
        required=True,
        allowed_extensions="pdf",
    )
    FormField.objects.create(
        form_definition=form_definition,
        field_name="name",
        field_label="Name",
        field_type="text",
        required=True,
    )
    return form_definition


def test_forged_upload_metadata_cannot_satisfy_required_field(auth_client, upload_form):
    data = {
        "name": "Attacker",
        "_stashed_files": json.dumps(
            {
                "attachment": {
                    "filename": "secret.pdf",
                    "path": "uploads/other-user/secret.pdf",
                }
            }
        ),
    }
    response = auth_client.post(
        reverse("forms_workflows:form_submit", args=[upload_form.slug]), data
    )
    assert response.status_code == 200
    assert response.context["form"].errors["attachment"]
    assert not FormSubmission.objects.filter(form_definition=upload_form).exists()


def test_valid_upload_recovers_from_session_only(
    auth_client, user, upload_form, settings
):
    url = reverse("forms_workflows:form_submit", args=[upload_form.slug])
    response = auth_client.post(
        url,
        {
            "attachment": SimpleUploadedFile(
                "ok.pdf", b"%PDF-local-test", content_type="application/pdf"
            )
        },
    )
    assert response.status_code == 200
    assert "name" in response.context["form"].errors
    assert "attachment" not in response.context["form"].errors
    with patch("django_forms_workflows.views.create_approval_tasks"):
        response = auth_client.post(url, {"name": "Recovered"})
    assert response.status_code == 302
    sub = FormSubmission.objects.get(form_definition=upload_form, submitter=user)
    assert sub.form_data["attachment"]["filename"] == "ok.pdf"
    assert (
        settings.MEDIA_ROOT / sub.form_data["attachment"]["path"]
    ).read_bytes() == b"%PDF-local-test"
    assert not auth_client.session.get("dfw_uploads")
    assert len(list(settings.MEDIA_ROOT.rglob("*.pdf"))) == 1


def test_upload_recovery_not_shared_between_browsers(auth_client, user, upload_form):
    from django.test import Client

    url = reverse("forms_workflows:form_submit", args=[upload_form.slug])
    auth_client.post(url, {"attachment": SimpleUploadedFile("ok.pdf", b"pdf")})
    other = Client()
    other.force_login(user)
    response = other.post(url, {"name": "No upload"})
    assert "attachment" in response.context["form"].errors


@pytest.mark.parametrize("draft", [False, True])
def test_invalid_upload_never_written(auth_client, upload_form, settings, draft):
    data = {"attachment": SimpleUploadedFile("bad.html", b"<script>alert(1)</script>")}
    if draft:
        data["save_draft"] = "1"
    response = auth_client.post(
        reverse("forms_workflows:form_submit", args=[upload_form.slug]), data
    )
    assert response.status_code == 400
    assert not list(settings.MEDIA_ROOT.rglob("*"))


@pytest.mark.parametrize("autosave", [False, True])
def test_drafts_cannot_store_client_file_paths(
    auth_client, upload_form, user, autosave
):
    fake = {"filename": "secret.pdf", "path": "uploads/victim/secret.pdf"}
    if autosave:
        response = auth_client.post(
            reverse("forms_workflows:form_auto_save", args=[upload_form.slug]),
            json.dumps({"attachment": fake, "name": fake, "unknown": fake}),
            content_type="application/json",
        )
        assert response.status_code == 200
    else:
        response = auth_client.post(
            reverse("forms_workflows:form_submit", args=[upload_form.slug]),
            {"save_draft": "1", "_stashed_files": json.dumps({"attachment": fake})},
        )
        assert response.status_code == 302
    sub = FormSubmission.objects.get(form_definition=upload_form, submitter=user)
    assert "path" not in json.dumps(sub.form_data)


def test_inactive_user_token_denied(client, user):
    token = APIToken.objects.create(user=user, name="Before deactivation")
    user.is_active = False
    user.save()
    assert (
        client.get(
            "/api/forms/", HTTP_AUTHORIZATION=f"Bearer {token.token}"
        ).status_code
        == 401
    )


@pytest.mark.parametrize("endpoint", ["analytics_dashboard", "analytics_export_csv"])
def test_analytics_scoped_to_visible_submissions(
    client, user, approver_user, form_definition, endpoint
):
    sub = FormSubmission.objects.create(
        form_definition=form_definition,
        submitter=user,
        form_data={},
        status="submitted",
    )
    client.force_login(approver_user)
    response = client.get(reverse(f"forms_workflows:{endpoint}"))
    assert response.status_code == 200
    assert form_definition.name.encode() not in response.content
    client.force_login(user)
    response = client.get(reverse(f"forms_workflows:{endpoint}"))
    assert response.status_code == 200
    assert form_definition.name.encode() in response.content
    assert sub.pk


@pytest.mark.parametrize(
    "endpoint,method,kwargs",
    [
        ("form_builder_api_save", "post", {}),
        ("form_builder_api_load", "get", {"form_id": 1}),
        ("form_builder_api_shared_list_save", "post", {}),
        ("form_builder_api_doc_template_save", "post", {"form_id": 1}),
        ("workflow_builder_save", "post", {}),
    ],
)
def test_staff_without_model_permissions_denied(
    client, staff_user, endpoint, method, kwargs
):
    client.force_login(staff_user)
    url = reverse(f"admin:{endpoint}", kwargs=kwargs)
    response = (
        getattr(client, method)(
            url,
            data=json.dumps({"name": "Injected", "slug": "injected", "fields": []}),
            content_type="application/json",
        )
        if method == "post"
        else client.get(url)
    )
    assert response.status_code == 403


def test_builder_with_explicit_model_permission_can_create(client, staff_user):
    staff_user.user_permissions.add(
        Permission.objects.get(
            content_type__app_label="django_forms_workflows",
            codename="add_formdefinition",
        )
    )
    client.force_login(staff_user)
    response = client.post(
        reverse("admin:form_builder_api_save"),
        json.dumps({"name": "Authorized", "slug": "authorized", "fields": []}),
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["success"]


def test_untrusted_forwarding_header_cannot_change_rate_identity(settings):
    settings.FORMS_WORKFLOWS_PUBLIC_RATE_LIMIT = "1/hour"
    factory = RequestFactory()
    for ip in ["198.51.100.1", "198.51.100.2"]:
        request = factory.post("/", REMOTE_ADDR="192.0.2.1", HTTP_X_FORWARDED_FOR=ip)
        assert _get_client_ip(request) == "192.0.2.1"
        assert check_rate_limit(request, "form") == (ip == "198.51.100.1")


def test_trusted_proxy_chain_walks_from_right(settings):
    settings.FORMS_WORKFLOWS_TRUSTED_PROXIES = ["10.0.0.0/8"]
    request = RequestFactory().get(
        "/", REMOTE_ADDR="10.0.0.1", HTTP_X_FORWARDED_FOR="1.2.3.4, 192.0.2.7, 10.0.0.2"
    )
    assert _get_client_ip(request) == "192.0.2.7"


def test_rate_limit_cache_failure_is_closed():
    with patch(
        "django.core.cache.backends.locmem.LocMemCache.add",
        side_effect=RuntimeError("unavailable"),
    ):
        assert not check_rate_limit(RequestFactory().post("/"), "form")


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/private",
        "https://example.com/image",
        "file:///etc/passwd",
        "data:image/svg+xml;base64,PHN2Zz4=",
        "ftp://example.com/file",
    ],
)
def test_pdf_disallows_external_and_active_resources(url):
    with pytest.raises(ValueError):
        safe_pdf_url_fetcher(url)


def test_pdf_allows_bounded_inline_png(settings):
    data = b"\x89PNG\r\n\x1a\nlocal-test"
    url = "data:image/png;base64," + base64.b64encode(data).decode()
    assert safe_pdf_url_fetcher(url)["string"] == data
    settings.FORMS_WORKFLOWS_PDF_MAX_RESOURCE_BYTES = 8
    with pytest.raises(ValueError):
        safe_pdf_url_fetcher(url)


def test_document_template_escapes_answer_markup(form_definition, user):
    template = DocumentTemplate(
        form_definition=form_definition, name="PDF", html_content="<p>{answer}</p>"
    )
    sub = FormSubmission(
        form_definition=form_definition,
        submitter=user,
        form_data={"answer": '<img src="http://127.0.0.1/private">'},
    )
    assert "<img" not in template.render(sub)
    assert "&lt;img" in template.render(sub)


def test_pdf_render_does_not_fetch_network(client, form_definition, user):
    pytest.importorskip("weasyprint")
    form_definition.pdf_generation = "anytime"
    form_definition.save()
    DocumentTemplate.objects.create(
        form_definition=form_definition,
        name="PDF",
        is_default=True,
        html_content='<p>{answer}</p><img src="http://127.0.0.1/static.png">',
    )
    sub = FormSubmission.objects.create(
        form_definition=form_definition,
        submitter=user,
        status="submitted",
        form_data={"answer": '<img src="http://127.0.0.1/private">'},
    )
    client.force_login(user)
    with patch(
        "urllib.request.OpenerDirector.open",
        side_effect=AssertionError("No network permitted"),
    ) as fetch:
        response = client.get(reverse("forms_workflows:submission_pdf", args=[sub.pk]))
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    fetch.assert_not_called()


def test_readonly_workflow_builder_does_not_create_workflow(
    client, staff_user, form_definition
):
    from django_forms_workflows.models import WorkflowDefinition

    staff_user.user_permissions.add(
        *Permission.objects.filter(
            content_type__app_label="django_forms_workflows",
            codename__in=["view_formdefinition", "view_workflowdefinition"],
        )
    )
    client.force_login(staff_user)
    for name in ["workflow_builder", "workflow_builder_load"]:
        response = client.get(reverse(f"admin:{name}", args=[form_definition.pk]))
        assert response.status_code == 200
    assert not WorkflowDefinition.objects.filter(
        form_definition=form_definition
    ).exists()


def test_workflow_save_without_id_requires_change_permission(
    client, staff_user, workflow, form_definition
):
    staff_user.user_permissions.add(
        *Permission.objects.filter(
            content_type__app_label="django_forms_workflows",
            codename__in=["change_formdefinition", "add_workflowdefinition"],
        )
    )
    client.force_login(staff_user)
    response = client.post(
        reverse("admin:workflow_builder_save"),
        json.dumps(
            {
                "form_id": form_definition.pk,
                "workflow": {"nodes": [], "connections": []},
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 403
    workflow.refresh_from_db()
    assert workflow.requires_approval


def test_rate_limit_concurrent_requests_do_not_lose_increments(settings):
    from concurrent.futures import ThreadPoolExecutor

    settings.FORMS_WORKFLOWS_PUBLIC_RATE_LIMIT = "5/hour"
    request = RequestFactory().post("/", REMOTE_ADDR="192.0.2.1")
    with ThreadPoolExecutor(max_workers=10) as pool:
        accepted = list(
            pool.map(lambda _: check_rate_limit(request, "concurrent"), range(30))
        )
    assert sum(accepted) == 5


def test_analytics_chart_escapes_script_end_tag(client, user, form_definition):
    payload = "</script><script>window.injected=1</script>"
    form_definition.name = payload
    form_definition.save()
    FormSubmission.objects.create(
        form_definition=form_definition,
        submitter=user,
        form_data={},
        status="submitted",
    )
    client.force_login(user)
    response = client.get(reverse("forms_workflows:analytics_dashboard"))
    assert payload.encode() not in response.content
    assert b"\\u003C/script\\u003E" in response.content


def test_analytics_csv_neutralizes_formula(client, user, form_definition):
    form_definition.name = '=HYPERLINK("https://example.com")'
    form_definition.save()
    FormSubmission.objects.create(
        form_definition=form_definition,
        submitter=user,
        form_data={},
        status="submitted",
    )
    client.force_login(user)
    response = client.get(reverse("forms_workflows:analytics_export_csv"))
    import csv
    import io

    rows = list(csv.reader(io.StringIO(response.content.decode())))
    assert rows[1][1].startswith("'=HYPERLINK")


def test_autosave_preserves_previously_validated_files(auth_client, user, upload_form):
    url = reverse("forms_workflows:form_submit", args=[upload_form.slug])
    response = auth_client.post(
        url, {"save_draft": "1", "attachment": SimpleUploadedFile("keep.pdf", b"pdf")}
    )
    assert response.status_code == 302
    sub = FormSubmission.objects.get(form_definition=upload_form, submitter=user)
    original = sub.form_data["attachment"]
    response = auth_client.post(
        reverse("forms_workflows:form_auto_save", args=[upload_form.slug]),
        json.dumps(
            {
                "name": "updated",
                "attachment": {"filename": "forged", "path": "other/file"},
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 200
    sub.refresh_from_db()
    assert sub.form_data["attachment"] == original
    with patch("django_forms_workflows.views.create_approval_tasks"):
        response = auth_client.post(url, {"name": "Ready"})
    assert response.status_code == 302
    sub.refresh_from_db()
    assert sub.form_data["attachment"] == original
    assert sub.status == "submitted"


def test_upload_recovery_expires(auth_client, user, upload_form):
    url = reverse("forms_workflows:form_submit", args=[upload_form.slug])
    auth_client.post(url, {"attachment": SimpleUploadedFile("ok.pdf", b"pdf")})
    session = auth_client.session
    entries = session["dfw_uploads"]
    for entry in entries.values():
        entry["expires"] = 0
    session["dfw_uploads"] = entries
    session.save()
    response = auth_client.post(url, {"name": "Expired"})
    assert "attachment" in response.context["form"].errors
