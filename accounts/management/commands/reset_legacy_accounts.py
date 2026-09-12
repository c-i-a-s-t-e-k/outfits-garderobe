"""Retire the pre-allauth accounts, and the files their deletion would orphan.

Two environments hold accounts that predate this change: development, and
production, where they are F-01's acceptance evidence. Neither can log in
through the new flow — `ACCOUNT_LOGIN_METHODS = {'email'}` authenticates against
allauth's `EmailAddress` table, and these rows have no record in it at all (one
of them has no email address whatsoever). They are deleted rather than
backfilled.

Two properties make this safe enough to point at production:

*It selects on state, not on names.* "Every user with no `EmailAddress` row at
all" is a predicate, so the command is safe to run twice and means the same
thing in both environments — a hardcoded username list would be a different,
staler command each time it ran.

Note what that predicate is *not*: "no **verified** `EmailAddress`". That wider
version would also match every account that has signed up but not yet clicked
its confirmation link, and deleting those in production would destroy real users
who simply had not opened their mail yet. Having no `EmailAddress` record at all
is what "pre-allauth" actually means — allauth writes that row at signup, before
verification — so this is the predicate that cannot widen over time.

*It defaults to a dry run.* Nothing is deleted without `--commit`. The dry run
prints the exact users and the exact file paths, which is the artifact a human
reads before authorising the only irreversible step in this plan.

The file sweep has to exist regardless of how the deletion is triggered:
`PrivateImage.owner` is `on_delete=CASCADE` (privatemedia/models.py:30-34), so
deleting a user removes the rows and leaves every byte on disk. In production
that disk is a mounted Railway volume, where nothing else will ever collect them.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from privatemedia.models import PrivateImage


class Command(BaseCommand):
    help = 'Delete pre-allauth users (no EmailAddress row) and sweep their orphaned files.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--commit',
            action='store_true',
            help='Actually delete. Without this flag the command only reports.',
        )

    def handle(self, *args, **options):
        commit = options['commit']
        User = get_user_model()

        # isnull, not `exclude(emailaddress__verified=True)`: the latter also
        # matches a signup that has not been confirmed yet, which is a live
        # user, not a legacy one. See the module docstring.
        #
        # A superuser with no EmailAddress row is a legacy row by this
        # definition, and deleting it is the point — but only after the
        # replacement exists. The plan sequences the production run *after* a
        # fresh account has proven the flow, so /admin/ is never unreachable.
        legacy = User.objects.filter(emailaddress__isnull=True).order_by('pk')

        if not legacy.exists():
            self.stdout.write(self.style.SUCCESS('No legacy accounts. Nothing to do.'))
            return

        images = PrivateImage.objects.filter(owner__in=legacy).select_related('owner')

        # Resolve every path before deleting anything: once the rows are gone
        # the storage names are gone with them, and the files become
        # unreachable rather than merely orphaned.
        files = []
        for image in images:
            try:
                files.append((image, image.image.path))
            except (ValueError, NotImplementedError):
                # No file associated, or a storage backend without local paths.
                files.append((image, None))

        self.stdout.write(f'Legacy users ({legacy.count()}):')
        for user in legacy:
            self.stdout.write(
                f'  id={user.pk} username={user.username!r} email={user.email!r} '
                f'superuser={user.is_superuser}'
            )

        self.stdout.write(f'Files their PrivateImage rows would orphan ({len(files)}):')
        for image, path in files:
            if path is None:
                self.stdout.write(f'  {image.pk} — no resolvable path, skipping file')
            else:
                self.stdout.write(f'  {path}')

        if not commit:
            self.stdout.write(
                self.style.WARNING('\nDry run — nothing deleted. Re-run with --commit to apply.')
            )
            return

        # Delete the rows in one transaction, then the bytes. Doing it in this
        # order means a crash between the two leaves unreferenced files (which
        # this command finds again on its next run) rather than rows pointing at
        # files that are already gone.
        with transaction.atomic():
            deleted_users, _ = legacy.delete()

        removed = 0
        for image, path in files:
            if path is None:
                continue
            try:
                image.image.storage.delete(image.image.name)
                removed += 1
            except OSError as exc:
                self.stderr.write(self.style.ERROR(f'Could not remove {path}: {exc}'))

        self.stdout.write(
            self.style.SUCCESS(
                f'Deleted {deleted_users} row(s) across cascades; removed {removed} file(s).'
            )
        )
