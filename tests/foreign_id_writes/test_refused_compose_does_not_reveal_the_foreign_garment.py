"""A compose refused for carrying someone else's garment re-renders nothing of theirs.

The error repeats the id the stranger posted — Django's invalid-choice message
does that — which reveals nothing they did not type. What matters is that the
refusal reads exactly like one for an id that never existed, and that the
garment's photo and description never appear.
"""

import re
import uuid

import pytest
from django.urls import reverse

from outfits.models import Outfit
from tests.factories import make_garment

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures('temp_media_root')]

CSRF_TOKEN = re.compile(r'name="csrfmiddlewaretoken" value="[^"]*"')


def _compose(client, garment_ids):
    return client.post(reverse('outfits:compose'), {'name': '', 'garments': garment_ids})


def _without(body, garment_id):
    """The page with the posted id and the per-render CSRF token blanked out."""
    return CSRF_TOKEN.sub('', body.replace(str(garment_id), '<posted id>'))


def test_refused_compose_reads_like_an_unknown_id_and_shows_nothing_of_the_owner(
    client, owner, stranger
):
    theirs = make_garment(owner, description='owner navy oxford')
    own = make_garment(stranger)
    make_garment(stranger)
    missing = uuid.uuid4()
    client.force_login(stranger)

    refused = _compose(client, [own.pk, theirs.pk])
    unknown = _compose(client, [own.pk, missing])

    assert refused.status_code == 200
    assert 'garments' in refused.context['form'].errors
    body = refused.content.decode()
    assert theirs.photo_url not in body
    assert theirs.description not in body
    assert _without(body, theirs.pk) == _without(unknown.content.decode(), missing)
    assert not Outfit.objects.exists()
