"""A garment deleted without its page — the ORM, the admin, its account — obeys the same rule.

An instance delete and a queryset delete (what the admin runs) leave the same
missing slots as the page does. Deleting the whole account removes the owner's
outfits, garments and slots together and leaves no row pointing at a deleted
one, which PostgreSQL would refuse.
"""

import pytest
from django.contrib.auth import get_user_model
from django.db import connection

from garments.models import Garment
from outfits.models import MissingGarment, Outfit

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures('temp_media_root')]


def _slots_by_outfit(owner):
    return sorted(
        MissingGarment.objects.filter(outfit__owner=owner).values_list(
            'outfit__name', 'type', 'description'
        )
    )


@pytest.mark.parametrize('path', ['instance', 'queryset'])
def test_a_garment_deleted_outside_the_page_still_marks_its_outfits(
    owner, stranger, wardrobe, snapshot_of, path
):
    strangers_data = snapshot_of(stranger)

    if path == 'instance':
        wardrobe['a'].delete()
    else:
        Garment.objects.filter(pk=wardrobe['a'].pk).delete()

    assert _slots_by_outfit(owner) == [
        ('Autumn walk', 'shoes', 'brown loafers'),
        ('Office day', 'shoes', 'brown loafers'),
    ]
    assert Outfit.objects.filter(owner=owner).count() == 3
    assert snapshot_of(stranger) == strangers_data


def test_deleting_the_account_leaves_no_outfit_garment_or_slot_behind(
    owner, stranger, wardrobe, snapshot_of
):
    strangers_data = snapshot_of(stranger)
    owner_pk = owner.pk

    get_user_model().objects.filter(pk=owner_pk).delete()

    assert not Outfit.objects.filter(owner_id=owner_pk).exists()
    assert not Garment.objects.filter(owner_id=owner_pk).exists()
    assert not MissingGarment.objects.filter(outfit__owner_id=owner_pk).exists()
    assert not MissingGarment.objects.exclude(outfit__in=Outfit.objects.all()).exists()
    connection.check_constraints()
    assert snapshot_of(stranger) == strangers_data
