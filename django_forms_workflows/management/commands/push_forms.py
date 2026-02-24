"""
Management command: push_forms

Push local form + workflow + config definitions to a remote django-forms-workflows
instance.

Usage
-----
    python manage.py push_forms \\
        --dest-url https://prod.example.com \\
        --token SECRET \\
        [--slugs time-off,onboarding] \\
        [--conflict update|skip|new_slug]
"""

import sys

import requests
from django.core.management.base import BaseCommand, CommandError

from django_forms_workflows.models import FormDefinition
from django_forms_workflows.sync_api import build_export_payload


class Command(BaseCommand):
    help = "Push local form definitions to a remote instance."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dest-url",
            required=True,
            help="Base URL of the destination instance (e.g. https://prod.example.com).",
        )
        parser.add_argument(
            "--token",
            required=True,
            help="Bearer token matching FORMS_SYNC_API_TOKEN on the destination instance.",
        )
        parser.add_argument(
            "--slugs",
            default="",
            help="Comma-separated list of form slugs to push. Omit to push all forms.",
        )
        parser.add_argument(
            "--conflict",
            default="update",
            choices=["update", "skip", "new_slug"],
            help=(
                "How to handle conflicts on the destination when a form already exists. "
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
            help="Build the payload and display forms without sending to the destination.",
        )

    def handle(self, *args, **options):
        dest_url = options["dest_url"].rstrip("/")
        token = options["token"]
        conflict = options["conflict"]
        timeout = options["timeout"]
        dry_run = options["dry_run"]
        slugs = options["slugs"].strip()

        if slugs:
            slug_list = [s.strip() for s in slugs.split(",") if s.strip()]
            qs = FormDefinition.objects.filter(slug__in=slug_list)
            missing = set(slug_list) - set(qs.values_list("slug", flat=True))
            if missing:
                raise CommandError(
                    f"The following slugs were not found locally: {', '.join(sorted(missing))}"
                )
        else:
            qs = FormDefinition.objects.all()

        payload = build_export_payload(qs)
        form_count = payload["form_count"]

        self.stdout.write(f"Prepared {form_count} form(s) for push.")

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run — not sending to destination."))
            for form_data in payload.get("forms", []):
                slug = form_data.get("form", {}).get("slug", "?")
                name = form_data.get("form", {}).get("name", "?")
                self.stdout.write(f"  • {slug}: {name}")
            return

        import_url = f"{dest_url}/forms-sync/import/?conflict={conflict}"
        self.stdout.write(f"Pushing to {import_url} …")

        try:
            response = requests.post(
                import_url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                timeout=timeout,
            )
        except requests.exceptions.ConnectionError as exc:
            raise CommandError(f"Could not connect to {dest_url}: {exc}") from exc
        except requests.exceptions.Timeout:
            raise CommandError(f"Request timed out after {timeout}s.")

        if response.status_code == 401:
            raise CommandError("Authentication failed — check your --token value.")
        if response.status_code == 403:
            raise CommandError("Sync API is disabled on the destination instance.")
        if not response.ok:
            raise CommandError(
                f"Destination returned HTTP {response.status_code}: {response.text[:200]}"
            )

        try:
            result = response.json()
        except ValueError as exc:
            raise CommandError(f"Destination returned invalid JSON: {exc}") from exc

        counts = result.get("counts", {})
        for form_summary in result.get("forms", []):
            action = form_summary.get("action", "?")
            slug = form_summary.get("slug", "?")
            style = self.style.SUCCESS if action == "created" else (
                self.style.WARNING if action == "updated" else self.style.NOTICE
            )
            self.stdout.write(style(f"  [{action}] {slug}"))

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone! Created: {counts.get('created', 0)}, "
                f"Updated: {counts.get('updated', 0)}, Skipped: {counts.get('skipped', 0)}"
            )
        )

