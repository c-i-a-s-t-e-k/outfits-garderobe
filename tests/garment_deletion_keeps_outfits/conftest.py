"""The wardrobe every garment-deletion scenario starts from.

The owner's loafers (a) are in two outfits: o1 with the shirt (b), tagged, and
o2 with the trousers (c), photographed. o3 is the shirt and trousers, without
the loafers. The stranger has an outfit of their own, with shoes of the same
kind, so a rule that crossed users would have something to touch.
"""

import pytest
from django.urls import reverse

from garments.models import GarmentType
from outfits.models import Tag
from tests.factories import make_garment, make_outfit
from tests.foreign_id_writes.conftest import snapshot_of  # noqa: F401 — a shared fixture


@pytest.fixture
def wardrobe(owner, stranger):
    a = make_garment(owner, type=GarmentType.SHOES, description='brown loafers')
    b = make_garment(owner, type=GarmentType.SHIRT, description='navy oxford')
    c = make_garment(owner, type=GarmentType.TROUSERS, description='grey chinos')
    o1 = make_outfit(owner, garments=[a, b], name='Autumn walk')
    o1.tags.set(Tag.resolve(owner, ['letnie']))
    o2 = make_outfit(owner, garments=[a, c], photo=True, name='Office day')
    o3 = make_outfit(owner, garments=[b, c], name='Errand')
    theirs = make_outfit(
        stranger,
        garments=[
            make_garment(stranger, type=GarmentType.SHOES, description='their loafers'),
            make_garment(stranger, type=GarmentType.SHIRT),
        ],
        name='Their walk',
    )
    return {'a': a, 'b': b, 'c': c, 'o1': o1, 'o2': o2, 'o3': o3, 'theirs': theirs}


@pytest.fixture
def delete_garment_through_its_page(client, owner):
    def delete(garment):
        client.force_login(owner)
        response = client.post(reverse('garments:delete', args=[garment.pk]))
        assert response.status_code == 302
        assert response.headers['Location'] == reverse('garments:list')

    return delete
