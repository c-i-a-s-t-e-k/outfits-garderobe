"""Adding a garment takes its owner and photo from the server, whatever the request says.

The protection is structural — `owner` and `photo` are not form fields — so it
is one `fields = '__all__'` away from gone. This pins the outcome.
"""

import pytest
from django.urls import reverse

from garments.models import Garment
from privatemedia.models import PrivateImage
from tests.owner_scoped_routes import ROUTES

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures('temp_media_root')]


def test_posted_owner_photo_and_id_do_not_reach_the_stored_garment(client, owner, stranger):
    declaration = ROUTES['garments:add']
    seeded = declaration.seed(owner)
    theirs = seeded.garments[0]
    owners_garments = set(Garment.objects.filter(owner=owner).values_list('pk', flat=True))
    garments_before = set(Garment.objects.values_list('pk', flat=True))
    client.force_login(stranger)

    # A valid upload that also posts owner=<owner>, photo=<their photo>, id=<their garment>.
    payload = declaration.foreign_payload(seeded, stranger)
    assert (payload['owner'], payload['photo'][1], payload['id']) == (
        owner.pk,
        str(theirs.photo_id),
        theirs.pk,
    )
    response = client.post(reverse('garments:add'), payload)

    assert response.status_code == 302
    created = Garment.objects.exclude(pk__in=garments_before)
    assert created.count() == 1
    garment = created.get()
    assert garment.owner == stranger
    assert garment.pk != theirs.pk
    assert garment.photo_id != theirs.photo_id
    assert PrivateImage.objects.get(pk=garment.photo_id).owner == stranger

    assert set(Garment.objects.filter(owner=owner).values_list('pk', flat=True)) == owners_garments
    theirs.refresh_from_db()
    assert theirs.owner == owner
    assert PrivateImage.objects.get(pk=theirs.photo_id).garment == theirs
