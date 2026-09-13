"""A write carrying another user's ids leaves that user's data exactly as it was.

Parametrized over every `write` route in the registry, with two payload shapes:
the stranger's own objects mixed with the owner's, and the owner's alone. The
outcome is read back from the database, never inferred from the status code: a
refused write stores nothing, and an accepted one may only store rows that
belong to the stranger.
"""

from urllib.parse import urlsplit

import pytest
from django.conf import settings
from django.urls import reverse

from garments.models import Garment
from outfits.models import Outfit, Tag
from privatemedia.models import PrivateImage
from tests.factories import make_garment
from tests.owner_scoped_routes import ROUTES

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures('temp_media_root')]

WRITE_ROUTES = [name for name, declaration in ROUTES.items() if declaration.kind == 'write']
OWNED_MODELS = (PrivateImage, Garment, Outfit, Tag)


def _pks():
    return {model: set(model.objects.values_list('pk', flat=True)) for model in OWNED_MODELS}


def _new_rows(before):
    return [row for model in OWNED_MODELS for row in model.objects.exclude(pk__in=before[model])]


def _is_success_redirect(response):
    return (
        response.status_code == 302
        and urlsplit(response.headers['Location']).path != settings.LOGIN_URL
    )


@pytest.mark.parametrize('mix_in_own', [True, False], ids=['mixed-with-own', 'only-theirs'])
@pytest.mark.parametrize('name', WRITE_ROUTES)
def test_foreign_write_leaves_the_owners_data_untouched(
    client, owner, stranger, snapshot_of, assert_no_cross_owner_links, name, mix_in_own
):
    declaration = ROUTES[name]
    seeded = declaration.seed(owner)
    # Enough of their own that a view gated on having garments processes the form.
    make_garment(stranger)
    make_garment(stranger)
    owners_data = snapshot_of(owner)
    before = _pks()
    client.force_login(stranger)

    payload = declaration.foreign_payload(seeded, stranger if mix_in_own else None)
    response = client.post(reverse(name, kwargs=seeded.kwargs), payload)

    new_rows = _new_rows(before)
    if _is_success_redirect(response):
        assert all(row.owner_id == stranger.pk for row in new_rows), (
            f'{name} accepted the write and stored rows for someone else: {new_rows}'
        )
    else:
        assert not new_rows, f'{name} refused the write but stored {new_rows}'
    assert snapshot_of(owner) == owners_data
    assert_no_cross_owner_links()
