"""
Management command: pull_forms

Pull form + workflow + config definitions from a remote django-forms-workflows
instance and import them into the local database.

Usage
-----
    python manage.py pull_forms \\
        --source-url https://test.example.com \\
        --token SECRET \\
        [--slugs time-off,onboarding] \\
        [--conflict update|skip|new_slug]
"""

import requests
from django.core.management.base import BaseCommand, CommandError

from django_forms_workflows.sync_api import import_payload


class Command(BaseCommand):
    help = "Pull form definitions from a remote instance and import them locally."

    def add_arguments(self, parser):
        parser.add_argument(
            "--source-url",
            required=True,
            help="Base URL of the source instance (e.g. https://test.example.com).",
        )
        parser.add_argument(
            "--token",
            required=True,
            help="Bearer token matching FORMS_SYNC_API_TOKEN on the source instance.",
        )
        parser.add_argument(
            "--slugs",
            default="",
            help="Comma-separated list of form slugs to pull. Omit to pull all forms.",
        )
        parser.add_argument(
            "--conflict",
            default="update",
            choices=["update", "skip", "new_slug"],
            help=(
                "How to handle conflicts when a form with the same slug already exists. "
                "update (default): overwrite. skip: leave existing. new_slug: create with _imported suffix."
            ),
        )
        parser.add_argument(
            "--timeout",
            type=int,
            default=30,
            help="HTTP request timeout in seconds (default: 30).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Fetch and display forms without writing to the database.",
        )

    def handle(self, *args, **options):
        source_url = options["source_url"].rstrip("/")
        token = options["token"]
        conflict = options["conflict"]
        timeout = options["timeout"]
        dry_run = options["dry_run"]
        slugs = options["slugs"].strip()

        export_url = f"{source_url}/forms-sync/export/"
        params = {}
        if slugs:
            params["slugs"] = slugs

        self.stdout.write(f"Fetching forms from {export_url} …")
        try:
            response = requests.get(
                export_url,
                params=params,
                headers={"Authorization": f"Bearer {token}"},
                timeout=timeout,
            )
        except requests.exceptions.ConnectionError as exc:
            raise CommandError(f"Could not connect to {source_url}: {exc}") from exc
        except requests.exceptions.Timeout:
            raise CommandError(f"Request timed out after {timeout}s.") from None

        if response.status_code == 401:
            raise CommandError("Authentication failed — check your --token value.")
        if response.status_code == 403:
            raise CommandError("Sync API is disabled on the source instance.")
        if not response.ok:
            raise CommandError(
                f"Source returned HTTP {response.status_code}: {response.text[:200]}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise CommandError(f"Source returned invalid JSON: {exc}") from exc

        form_count = payload.get("form_count", len(payload.get("forms", [])))
        self.stdout.write(f"Received {form_count} form(s).")

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run — not writing to database."))
            for form_data in payload.get("forms", []):
                slug = form_data.get("form", {}).get("slug", "?")
                name = form_data.get("form", {}).get("name", "?")
                self.stdout.write(f"  • {slug}: {name}")
            return

        results = import_payload(payload, conflict=conflict)
        counts = {"created": 0, "updated": 0, "skipped": 0}
        for form_obj, action in results:
            counts[action] = counts.get(action, 0) + 1
            style = (
                self.style.SUCCESS
                if action == "created"
                else (self.style.WARNING if action == "updated" else self.style.NOTICE)
            )
            self.stdout.write(style(f"  [{action}] {form_obj.slug}: {form_obj.name}"))

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone! Created: {counts['created']}, "
                f"Updated: {counts['updated']}, Skipped: {counts['skipped']}"
            )
        )
