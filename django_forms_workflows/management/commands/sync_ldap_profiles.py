"""
Management command to sync LDAP attributes to UserProfile for all users.
"""

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from django_forms_workflows.models import UserProfile
from django_forms_workflows.signals import sync_ldap_attributes


class Command(BaseCommand):
    """Sync LDAP attributes to UserProfile for all users."""

    help = "Sync LDAP attributes to UserProfile for all users"

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            type=str,
            help="Sync only for specific username",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be synced without making changes",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Show detailed output",
        )

    def handle(self, *args, **options):
        username = options.get("username")
        dry_run = options.get("dry_run", False)
        verbose = options.get("verbose", False)

        # Get users to sync
        if username:
            users = User.objects.filter(username=username)
            if not users.exists():
                self.stdout.write(self.style.ERROR(f"User '{username}' not found"))
                return
        else:
            users = User.objects.all()

        total_users = users.count()
        self.stdout.write(f"Syncing LDAP attributes for {total_users} user(s)...")

        if dry_run:
            self.stdout.write(
                self.style.WARNING("DRY RUN MODE - No changes will be made")
            )

        synced_count = 0
        error_count = 0

        for user in users:
            try:
                if verbose:
                    self.stdout.write(f"Processing user: {user.username}")

                if not dry_run:
                    # Get or create profile
                    profile, created = UserProfile.objects.get_or_create(user=user)

                    # Sync LDAP attributes
                    sync_ldap_attributes(user, profile)

                    if created:
                        if verbose:
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f"  Created profile for {user.username}"
                                )
                            )
                    else:
                        if verbose:
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f"  Updated profile for {user.username}"
                                )
                            )

                    synced_count += 1
                else:
                    # Dry run - just check if user has LDAP attributes
                    ldap_user = getattr(user, "ldap_user", None)
                    if ldap_user:
                        if verbose:
                            self.stdout.write(
                                f"  Would sync LDAP attributes for {user.username}"
                            )
                        synced_count += 1
                    else:
                        if verbose:
                            self.stdout.write(
                                self.style.WARNING(
                                    f"  No LDAP attributes found for {user.username}"
                                )
                            )

            except Exception as e:
                error_count += 1
                self.stdout.write(
                    self.style.ERROR(f"Error syncing user {user.username}: {e}")
                )

        # Summary
        self.stdout.write("\n" + "=" * 50)
        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(f"DRY RUN: Would sync {synced_count} user(s)")
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Successfully synced {synced_count} user(s)")
            )

        if error_count > 0:
            self.stdout.write(self.style.ERROR(f"Errors: {error_count}"))

        self.stdout.write("=" * 50)
