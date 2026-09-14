"""Deleting a garment through its page keeps every outfit that used it, each with the rest.

Both outfits that held the garment survive with their other garments, their tag
and their photo, and each records exactly what went missing. An outfit without
the garment, and every outfit of another user, stay as they were.
"""

import pytest

from outfits.models import Outfit

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures('temp_media_root')]


def _slots(outfit):
    return [
        (slot.display_type, slot.description)
        for slot in Outfit.objects.get(pk=outfit.pk).missing_garments.all()
    ]


def test_deleting_a_garment_keeps_every_outfit_that_used_it(
    wardrobe, stranger, snapshot_of, delete_garment_through_its_page
):
    o1, o2, o3 = wardrobe['o1'], wardrobe['o2'], wardrobe['o3']
    strangers_data = snapshot_of(stranger)

    delete_garment_through_its_page(wardrobe['a'])

    kept_o1 = Outfit.objects.get(pk=o1.pk)
    kept_o2 = Outfit.objects.get(pk=o2.pk)
    assert set(kept_o1.garments.all()) == {wardrobe['b']}
    assert set(kept_o2.garments.all()) == {wardrobe['c']}
    assert [tag.name for tag in kept_o1.tags.all()] == ['letnie']
    assert kept_o2.photo_id == o2.photo_id
    assert _slots(o1) == [('Shoes', 'brown loafers')]
    assert _slots(o2) == [('Shoes', 'brown loafers')]

    assert set(Outfit.objects.get(pk=o3.pk).garments.all()) == {wardrobe['b'], wardrobe['c']}
    assert _slots(o3) == []
    assert snapshot_of(stranger) == strangers_data
