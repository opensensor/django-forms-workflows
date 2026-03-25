"""
Tests for django_forms_workflows REST API (api_views.py / api_urls.py).

Covers:
 - Bearer token authentication (missing / invalid / inactive / valid)
 - Two-level opt-in gate (api_enabled=False → 404)
 - Permission checks (view_groups / submit_groups)
 - GET /api/forms/ list
 - GET /api/forms/<slug>/ field schema
 - POST /api/forms/<slug>/submit/ — JSON, validation errors, happy path, draft, ?draft=1
 - POST /api/forms/<slug>/submit/ — multipart/form-data
 - GET /api/submissions/<id>/ status
 - GET /api/schema/ (staff required)
 - GET /api/docs/ (staff required)
"""

import json

import pytest
from django.contrib.auth.models import Group, User
from django.test import Client

from django_forms_workflows.models import (
    APIToken,
    FormField,
    FormSubmission,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def api_client():
    return Client()


@pytest.fixture
def api_form(form_definition):
    """A FormDefinition with api_enabled=True and a required text field."""
    form_definition.api_enabled = True
    form_definition.save()
    FormField.objects.filter(form_definition=form_definition).delete()
    FormField.objects.create(
        form_definition=form_definition,
        field_name="full_name",
        field_label="Full Name",
        field_type="text",
        required=True,
        order=1,
    )
    FormField.objects.create(
        form_definition=form_definition,
        field_name="notes",
        field_label="Notes",
        field_type="textarea",
        required=False,
        order=2,
    )
    return form_definition


@pytest.fixture
def token(user):
    return APIToken.objects.create(user=user, name="Test Token")


@pytest.fixture
def auth_headers(token):
    return {"HTTP_AUTHORIZATION": f"Bearer {token.token}"}


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _post_json(client, url, data, headers=None):
    headers = headers or {}
    return client.post(
        url,
        data=json.dumps(data),
        content_type="application/json",
        **headers,
    )


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


class TestBearerAuth:
    def test_missing_token_returns_401(self, api_client, api_form):
        r = _post_json(
            api_client, f"/api/forms/{api_form.slug}/submit/", {"full_name": "Alice"}
        )
        assert r.status_code == 401

    def test_invalid_token_returns_401(self, api_client, api_form):
        r = _post_json(
            api_client,
            f"/api/forms/{api_form.slug}/submit/",
            {"full_name": "Alice"},
            {"HTTP_AUTHORIZATION": "Bearer not-a-uuid"},
        )
        assert r.status_code == 401

    def test_inactive_token_returns_401(self, api_client, api_form, user):
        dead = APIToken.objects.create(user=user, name="Dead", is_active=False)
        r = _post_json(
            api_client,
            f"/api/forms/{api_form.slug}/submit/",
            {"full_name": "Alice"},
            {"HTTP_AUTHORIZATION": f"Bearer {dead.token}"},
        )
        assert r.status_code == 401

    def test_valid_token_accepted(self, api_client, api_form, auth_headers):
        r = _post_json(
            api_client,
            f"/api/forms/{api_form.slug}/submit/",
            {"full_name": "Alice"},
            auth_headers,
        )
        assert r.status_code == 201

    def test_last_used_at_updated(self, api_client, api_form, token, auth_headers):
        assert token.last_used_at is None
        _post_json(
            api_client,
            f"/api/forms/{api_form.slug}/submit/",
            {"full_name": "Alice"},
            auth_headers,
        )
        token.refresh_from_db()
        assert token.last_used_at is not None


# ---------------------------------------------------------------------------
# Two-level opt-in gate
# ---------------------------------------------------------------------------


class TestApiEnabledGate:
    def test_api_disabled_form_returns_404(
        self, api_client, form_definition, auth_headers
    ):
        form_definition.api_enabled = False
        form_definition.save()
        FormField.objects.create(
            form_definition=form_definition,
            field_name="x",
            field_label="X",
            field_type="text",
            required=False,
            order=1,
        )
        r = _post_json(
            api_client,
            f"/api/forms/{form_definition.slug}/submit/",
            {"x": "y"},
            auth_headers,
        )
        assert r.status_code == 404

    def test_api_enabled_form_accessible(self, api_client, api_form, auth_headers):
        r = _post_json(
            api_client,
            f"/api/forms/{api_form.slug}/submit/",
            {"full_name": "Bob"},
            auth_headers,
        )
        assert r.status_code == 201

    def test_api_disabled_form_excluded_from_list(
        self, api_client, form_definition, auth_headers
    ):
        form_definition.api_enabled = False
        form_definition.save()
        r = api_client.get("/api/forms/", **auth_headers)
        data = r.json()
        slugs = [f["slug"] for f in data["forms"]]
        assert form_definition.slug not in slugs


# ---------------------------------------------------------------------------
# Permission checks
# ---------------------------------------------------------------------------


class TestApiPermissions:
    def test_submit_groups_blocks_non_member(
        self, api_client, api_form, user, auth_headers
    ):
        g = Group.objects.create(name="Submit Only API")
        api_form.submit_groups.add(g)
        r = _post_json(
            api_client,
            f"/api/forms/{api_form.slug}/submit/",
            {"full_name": "Eve"},
            auth_headers,
        )
        assert r.status_code == 403

    def test_submit_groups_allows_member(
        self, api_client, api_form, user, auth_headers
    ):
        g = Group.objects.create(name="Submit Allowed API")
        api_form.submit_groups.add(g)
        user.groups.add(g)
        r = _post_json(
            api_client,
            f"/api/forms/{api_form.slug}/submit/",
            {"full_name": "Eve"},
            auth_headers,
        )
        assert r.status_code == 201


# ---------------------------------------------------------------------------
# Form list and detail
# ---------------------------------------------------------------------------


class TestFormList:
    def test_returns_api_enabled_forms(self, api_client, api_form, auth_headers):
        r = api_client.get("/api/forms/", **auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["count"] >= 1
        slugs = [f["slug"] for f in data["forms"]]
        assert api_form.slug in slugs

    def test_requires_auth(self, api_client, api_form):
        r = api_client.get("/api/forms/")
        assert r.status_code == 401


class TestFormDetail:
    def test_returns_field_schema(self, api_client, api_form, auth_headers):
        r = api_client.get(f"/api/forms/{api_form.slug}/", **auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["slug"] == api_form.slug
        field_names = [f["name"] for f in data["fields"]]
        assert "full_name" in field_names

    def test_api_disabled_returns_404(self, api_client, form_definition, auth_headers):
        form_definition.api_enabled = False
        form_definition.save()
        r = api_client.get(f"/api/forms/{form_definition.slug}/", **auth_headers)
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Submission — JSON
# ---------------------------------------------------------------------------


class TestApiSubmitJson:
    def test_valid_submission_returns_201(self, api_client, api_form, auth_headers):
        r = _post_json(
            api_client,
            f"/api/forms/{api_form.slug}/submit/",
            {"full_name": "Alice"},
            auth_headers,
        )
        assert r.status_code == 201
        data = r.json()
        # No approval steps on test form → workflow may auto-approve immediately
        assert data["status"] in ("submitted", "approved", "pending_approval")
        assert "id" in data and "status_url" in data

    def test_submission_saved_to_db(self, api_client, api_form, user, auth_headers):
        _post_json(
            api_client,
            f"/api/forms/{api_form.slug}/submit/",
            {"full_name": "Alice"},
            auth_headers,
        )
        sub = FormSubmission.objects.filter(
            form_definition=api_form, submitter=user
        ).first()
        assert sub is not None
        assert sub.status in ("submitted", "approved", "pending_approval")
        assert sub.form_data["full_name"] == "Alice"

    def test_validation_error_returns_400(self, api_client, api_form, auth_headers):
        r = _post_json(
            api_client,
            f"/api/forms/{api_form.slug}/submit/",
            {"notes": "hi"},
            auth_headers,
        )
        assert r.status_code == 400
        assert "full_name" in r.json()["errors"]

    def test_invalid_json_body_returns_400(self, api_client, api_form, auth_headers):
        r = api_client.post(
            f"/api/forms/{api_form.slug}/submit/",
            data=b"not json }{",
            content_type="application/json",
            **auth_headers,
        )
        assert r.status_code == 400

    def test_user_agent_recorded(self, api_client, api_form, user, auth_headers):
        api_client.defaults["HTTP_USER_AGENT"] = "TestAgent/1.0"
        _post_json(
            api_client,
            f"/api/forms/{api_form.slug}/submit/",
            {"full_name": "Bob"},
            auth_headers,
        )
        sub = FormSubmission.objects.filter(
            form_definition=api_form, submitter=user
        ).last()
        assert sub.user_agent == "TestAgent/1.0"


# ---------------------------------------------------------------------------
# Draft support
# ---------------------------------------------------------------------------


class TestApiDraft:
    def test_draft_flag_saves_as_draft(self, api_client, api_form, user, auth_headers):
        r = _post_json(
            api_client,
            f"/api/forms/{api_form.slug}/submit/?draft=1",
            {"full_name": "Draft User"},
            auth_headers,
        )
        assert r.status_code == 201
        assert r.json()["status"] == "draft"
        assert FormSubmission.objects.get(id=r.json()["id"]).status == "draft"

    def test_draft_reused_on_second_call(
        self, api_client, api_form, user, auth_headers
    ):
        _post_json(
            api_client,
            f"/api/forms/{api_form.slug}/submit/?draft=1",
            {"full_name": "First"},
            auth_headers,
        )
        _post_json(
            api_client,
            f"/api/forms/{api_form.slug}/submit/?draft=1",
            {"full_name": "Second"},
            auth_headers,
        )
        assert (
            FormSubmission.objects.filter(
                form_definition=api_form, submitter=user, status="draft"
            ).count()
            == 1
        )

    def test_draft_promoted_on_full_submit(
        self, api_client, api_form, user, auth_headers
    ):
        r1 = _post_json(
            api_client,
            f"/api/forms/{api_form.slug}/submit/?draft=1",
            {"full_name": "Draft"},
            auth_headers,
        )
        draft_id = r1.json()["id"]
        _post_json(
            api_client,
            f"/api/forms/{api_form.slug}/submit/",
            {"full_name": "Final"},
            auth_headers,
        )
        # No approval steps on test form → workflow may auto-approve immediately
        assert FormSubmission.objects.get(id=draft_id).status in (
            "submitted",
            "approved",
        )

    def test_draft_disabled_form_returns_400(self, api_client, api_form, auth_headers):
        api_form.allow_save_draft = False
        api_form.save()
        r = _post_json(
            api_client,
            f"/api/forms/{api_form.slug}/submit/?draft=1",
            {"full_name": "Alice"},
            auth_headers,
        )
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# Multipart submission
# ---------------------------------------------------------------------------


class TestApiSubmitMultipart:
    def test_multipart_submission_accepted(
        self, api_client, api_form, user, auth_headers
    ):
        r = api_client.post(
            f"/api/forms/{api_form.slug}/submit/",
            data={"full_name": "Multipart User"},
            **auth_headers,
        )
        assert r.status_code == 201
        sub = FormSubmission.objects.filter(
            form_definition=api_form, submitter=user
        ).first()
        assert sub.form_data["full_name"] == "Multipart User"

    def test_multipart_validation_error_returns_400(
        self, api_client, api_form, auth_headers
    ):
        r = api_client.post(
            f"/api/forms/{api_form.slug}/submit/",
            data={"notes": "no name supplied"},
            **auth_headers,
        )
        assert r.status_code == 400
        assert "full_name" in r.json()["errors"]


# ---------------------------------------------------------------------------
# Submission status
# ---------------------------------------------------------------------------


class TestApiSubmissionStatus:
    def test_status_returns_correct_shape(self, api_client, api_form, auth_headers):
        r = _post_json(
            api_client,
            f"/api/forms/{api_form.slug}/submit/",
            {"full_name": "Alice"},
            auth_headers,
        )
        sub_id = r.json()["id"]
        r2 = api_client.get(f"/api/submissions/{sub_id}/", **auth_headers)
        assert r2.status_code == 200
        data = r2.json()
        assert data["id"] == sub_id
        assert data["form"] == api_form.slug
        assert "approval_tasks" in data

    def test_other_user_cannot_see_submission(self, api_client, api_form, auth_headers):
        r = _post_json(
            api_client,
            f"/api/forms/{api_form.slug}/submit/",
            {"full_name": "Alice"},
            auth_headers,
        )
        sub_id = r.json()["id"]
        other = User.objects.create_user("other_api_user", password="pass")
        other_token = APIToken.objects.create(user=other, name="Other Token")
        r2 = api_client.get(
            f"/api/submissions/{sub_id}/",
            HTTP_AUTHORIZATION=f"Bearer {other_token.token}",
        )
        assert r2.status_code == 404


# ---------------------------------------------------------------------------
# Schema and docs (staff-only)
# ---------------------------------------------------------------------------


class TestApiSchema:
    def test_schema_requires_staff(self, api_client, user):
        api_client.force_login(user)
        r = api_client.get("/api/schema/")
        assert r.status_code in (302, 403)

    def test_schema_accessible_to_staff(self, api_client, api_form, superuser):
        api_client.force_login(superuser)
        r = api_client.get("/api/schema/")
        assert r.status_code == 200
        spec = r.json()
        assert spec["openapi"] == "3.0.3"
        assert any(api_form.slug in path for path in spec["paths"])

    def test_schema_excludes_api_disabled_forms(
        self, api_client, form_definition, superuser
    ):
        form_definition.api_enabled = False
        form_definition.save()
        api_client.force_login(superuser)
        r = api_client.get("/api/schema/")
        spec = r.json()
        assert not any(form_definition.slug in path for path in spec["paths"])


class TestApiDocs:
    def test_docs_requires_staff(self, api_client, user):
        api_client.force_login(user)
        r = api_client.get("/api/docs/")
        assert r.status_code in (302, 403)

    def test_docs_accessible_to_staff(self, api_client, superuser):
        api_client.force_login(superuser)
        r = api_client.get("/api/docs/")
        assert r.status_code == 200
        assert b"swagger-ui" in r.content.lower()
        assert b"unpkg.com" not in r.content
        assert b"cdn." not in r.content
        assert b"swagger-ui-bundle.js" in r.content
