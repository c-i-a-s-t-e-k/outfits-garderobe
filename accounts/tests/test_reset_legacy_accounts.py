"""What `reset_legacy_accounts` must and must not delete.

This command is the only irreversible step in S-01, and in Phase 4 it runs
against production. The cases below are the ones where getting it wrong destroys
real data rather than merely failing.
"""

import io
from pathlib import Path

import pytest
from allauth.account.models import EmailAddress
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from PIL import Image

from privatemedia.models import PrivateImage

pytestmark = pytest.mark.django_db


def _png_bytes():
    buffer = io.BytesIO()
    Image.new('RGB', (4, 4), 'blue').save(buffer, format='PNG')
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def temp_media_root(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / 'media'
    return settings.MEDIA_ROOT


@pytest.fixture
def legacy_user(django_user_model):
    """A pre-allauth row: no EmailAddress record at all."""
    return django_user_model.objects.create_user(username='ciastek', password='pw-legacy-123')


@pytest.fixture
def pending_user(django_user_model):
    """Signed up through allauth, has not clicked the confirmation link yet."""
    account = django_user_model.objects.create_user(
        username='pending@example.com', email='pending@example.com', password='pw-pending-123'
    )
    EmailAddress.objects.create(user=account, email=account.email, verified=False, primary=True)
    return account


@pytest.fixture
def confirmed_user(django_user_model):
    account = django_user_model.objects.create_user(
        username='ada@example.com', email='ada@example.com', password='pw-ada-1234'
    )
    EmailAddress.objects.create(user=account, email=account.email, verified=True, primary=True)
    return account


def run(*args):
    out = io.StringIO()
    call_command('reset_legacy_accounts', *args, stdout=out, stderr=out)
    return out.getvalue()


def test_dry_run_is_the_default_and_deletes_nothing(django_user_model, legacy_user):
    output = run()

    assert 'Dry run' in output
    assert django_user_model.objects.filter(pk=legacy_user.pk).exists()


def test_dry_run_names_the_rows_and_the_files(legacy_user):
    image = PrivateImage.objects.create(
        owner=legacy_user,
        image=SimpleUploadedFile('x.png', _png_bytes(), content_type='image/png'),
    )

    output = run()

    assert 'ciastek' in output
    assert image.image.path in output


def test_commit_deletes_the_legacy_user_and_its_files(django_user_model, legacy_user):
    image = PrivateImage.objects.create(
        owner=legacy_user,
        image=SimpleUploadedFile('x.png', _png_bytes(), content_type='image/png'),
    )
    path = image.image.path

    run('--commit')

    assert not django_user_model.objects.filter(pk=legacy_user.pk).exists()
    assert PrivateImage.objects.count() == 0
    # CASCADE removes the row and never the bytes — the sweep is what does this.
    assert not Path(path).exists()


def test_a_pending_signup_is_never_touched(django_user_model, pending_user):
    """The regression this test exists for.

    An earlier predicate — "no *verified* EmailAddress" — also matched accounts
    that had signed up but not yet confirmed. Run against production that
    deletes live users whose only fault is not having opened their mail yet.
    """
    output = run()

    assert 'No legacy accounts' in output

    run('--commit')

    assert django_user_model.objects.filter(pk=pending_user.pk).exists()


def test_a_confirmed_account_is_never_touched(django_user_model, confirmed_user):
    run('--commit')

    assert django_user_model.objects.filter(pk=confirmed_user.pk).exists()


def test_only_the_legacy_row_goes_when_all_three_coexist(
    django_user_model, legacy_user, pending_user, confirmed_user
):
    run('--commit')

    remaining = set(django_user_model.objects.values_list('username', flat=True))
    assert remaining == {'pending@example.com', 'ada@example.com'}


def test_running_twice_is_safe(django_user_model, legacy_user):
    run('--commit')

    output = run('--commit')

    assert 'No legacy accounts' in output
    assert django_user_model.objects.count() == 0
