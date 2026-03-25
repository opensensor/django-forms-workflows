"""
Management command to pre-provision Django User records from LDAP/Active Directory.

Queries AD for users in a configurable group or OU and creates Django User +
UserProfile records for any that don't already exist locally.  This ensures
that workflow approval tasks can be assigned to faculty/staff even before
they've logged in via SSO.

When a pre-provisioned user later authenticates via Google SSO (or any other
SSO), the social-auth pipeline's ``link_to_existing_user`` step matches them
by username, so the experience is seamless.
"""

import logging

import ldap
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from ldap.filter import escape_filter_chars

logger = logging.getLogger(__name__)
User = get_user_model()


class Command(BaseCommand):
    help = (
        "Pre-provision Django users from LDAP. Creates User + UserProfile "
        "records for AD users who have not yet logged in."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--group",
            type=str,
            help="LDAP group CN to sync (e.g. 'Faculty' or 'Staff'). "
            "Searches for members of this group.",
        )
        parser.add_argument(
            "--ou",
            type=str,
            help="Organisational Unit to search within (e.g. 'OU=Faculty,DC=sjcme,DC=edu'). "
            "If not provided, uses the default LDAP search base.",
        )
        parser.add_argument(
            "--filter",
            type=str,
            default="(&(objectClass=user)(objectCategory=person))",
            help="Raw LDAP filter. Default: all person/user objects.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be created without making changes.",
        )
        parser.add_argument(
            "--max-results",
            type=int,
            default=500,
            help="Maximum number of LDAP results to process (default 500).",
        )

    def handle(self, *args, **options):
        if not getattr(settings, "AUTH_LDAP_SERVER_URI", None):
            self.stderr.write(self.style.ERROR("LDAP is not configured."))
            return

        dry_run = options["dry_run"]
        group_cn = options.get("group")
        ou = options.get("ou") or getattr(settings, "AUTH_LDAP_USER_SEARCH", None)
        search_base = ou if isinstance(ou, str) else getattr(ou, "base_dn", "")
        max_results = options["max_results"]

        username_attr = getattr(
            settings, "FORMS_WORKFLOWS_LDAP_USERNAME_ATTR", "sAMAccountName"
        )

        # Build search filter
        base_filter = options["filter"]
        if group_cn:
            base_filter = (
                f"(&{base_filter}(memberOf=CN={escape_filter_chars(group_cn)},"
                f"{search_base}))"
            )

        self.stdout.write(f"Searching LDAP: base={search_base}")
        self.stdout.write(f"Filter: {base_filter}")

        try:
            from django_forms_workflows.ldap_backend import configure_ldap_connection

            conn = ldap.initialize(settings.AUTH_LDAP_SERVER_URI)
            configure_ldap_connection(conn)
            conn.simple_bind_s(
                settings.AUTH_LDAP_BIND_DN, settings.AUTH_LDAP_BIND_PASSWORD
            )
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"LDAP connection failed: {e}"))
            return

        try:
            conn.set_option(ldap.OPT_SIZELIMIT, max_results)
            results = conn.search_s(
                search_base,
                ldap.SCOPE_SUBTREE,
                base_filter,
                [username_attr, "givenName", "sn", "mail", "department", "title"],
            )
        except ldap.SIZELIMIT_EXCEEDED:
            self.stdout.write(
                self.style.WARNING(f"Hit LDAP size limit ({max_results})")
            )
            results = []
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"LDAP search failed: {e}"))
            conn.unbind_s()
            return

        created = 0
        skipped = 0
        errors = 0

        for dn, attrs in results:
            if not dn:
                continue
            username = self._attr(attrs, username_attr)
            if not username:
                continue

            if User.objects.filter(username__iexact=username).exists():
                skipped += 1
                continue

            email = self._attr(attrs, "mail")
            first = self._attr(attrs, "givenName")
            last = self._attr(attrs, "sn")
            dept = self._attr(attrs, "department")
            title = self._attr(attrs, "title")

            if dry_run:
                self.stdout.write(f"  Would create: {username} ({first} {last})")
                created += 1
                continue

            try:
                user = User.objects.create(
                    username=username,
                    email=email,
                    first_name=first,
                    last_name=last,
                    is_active=True,
                )
                try:
                    from django_forms_workflows.models import UserProfile

                    UserProfile.objects.get_or_create(
                        user=user,
                        defaults={"department": dept, "title": title},
                    )
                except Exception:
                    pass
                created += 1
            except Exception as e:
                errors += 1
                self.stderr.write(self.style.ERROR(f"  Error creating {username}: {e}"))

        conn.unbind_s()

        prefix = "DRY RUN: Would create" if dry_run else "Created"
        self.stdout.write(
            self.style.SUCCESS(
                f"\n{prefix} {created} user(s), skipped {skipped} existing, {errors} error(s)."
            )
        )

    @staticmethod
    def _attr(attrs, key):
        val = attrs.get(key, [b""])
        if isinstance(val, list):
            val = val[0] if val else b""
        return val.decode("utf-8") if isinstance(val, bytes) else str(val)
