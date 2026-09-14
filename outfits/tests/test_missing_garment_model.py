"""Deleting a garment keeps every outfit that used it and records what went missing.

PRD Business Logic: an outfit survives the deletion of one of its garments and
is marked incomplete. The rule lives in a receiver, so it is checked here on
every deletion path: an instance, a queryset (the admin) and a whole account.
"""

import pytest
from django.db import connection

from garments.models import Garment, GarmentType
from outfits.models import MissingGarment, Outfit, Tag
from tests.factories import make_garment, make_outfit

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures('temp_media_root')]


@pytest.fixture
def wardrobe(owner):
    a = make_garment(owner, type=GarmentType.SHOES, description='brown loafers')
    b = make_garment(owner, type=GarmentType.SHIRT, description='navy oxford')
    c = make_garment(owner, type=GarmentType.TROUSERS, description='grey chinos')
    o1 = make_outfit(owner, garments=[a, b], name='autumn walk')
    o1.tags.add(Tag.objects.create(owner=owner, name='letnie'))
    o2 = make_outfit(owner, garments=[a, c], name='city errand')
    o3 = make_outfit(owner, garments=[b, c], name='office')
    return {'a': a, 'b': b, 'c': c, 'o1': o1, 'o2': o2, 'o3': o3}


@pytest.fixture
def strangers_outfit(stranger):
    shoes = make_garment(stranger, type=GarmentType.SHOES, description='black boots')
    shirt = make_garment(stranger)
    outfit = make_outfit(stranger, garments=[shoes, shirt], name='their outfit')
    return outfit


def _strangers_state(stranger):
    return {
        'outfits': list(Outfit.objects.filter(owner=stranger).order_by('pk').values()),
        'links': sorted(
            Outfit.garments.through.objects.filter(outfit__owner=stranger).values_list(
                'outfit_id', 'garment_id'
            )
        ),
        'missing': list(
            MissingGarment.objects.filter(outfit__owner=stranger).order_by('pk').values()
        ),
    }


def test_deleting_a_garment_keeps_each_outfit_with_the_rest_and_records_it(
    wardrobe, stranger, strangers_outfit
):
    before = _strangers_state(stranger)

    wardrobe['a'].delete()

    o1 = Outfit.objects.get(pk=wardrobe['o1'].pk)
    o2 = Outfit.objects.get(pk=wardrobe['o2'].pk)
    assert set(o1.garments.all()) == {wardrobe['b']}
    assert set(o2.garments.all()) == {wardrobe['c']}
    assert [tag.name for tag in o1.tags.all()] == ['letnie']
    for outfit in (o1, o2):
        [missing] = outfit.missing_garments.all()
        assert missing.type == GarmentType.SHOES
        assert missing.description == 'brown loafers'
        assert missing.display_type == 'Shoes'
        assert str(missing) == 'Shoes — brown loafers'
        assert outfit.is_incomplete
        assert outfit.missing_count == 1
    o3 = Outfit.objects.get(pk=wardrobe['o3'].pk)
    assert not o3.missing_garments.exists()
    assert not o3.is_incomplete
    assert _strangers_state(stranger) == before


def test_an_other_type_garment_is_recorded_with_its_own_type_name(owner):
    garment = make_garment(owner, type=GarmentType.OTHER, type_other='Kimono')
    outfit = make_outfit(owner, garments=[garment, make_garment(owner)])

    garment.delete()

    [missing] = outfit.missing_garments.all()
    assert (missing.type, missing.type_other, missing.description) == (
        GarmentType.OTHER,
        'Kimono',
        '',
    )
    assert missing.display_type == 'Kimono'
    assert str(missing) == 'Kimono'


def test_a_queryset_delete_records_every_garment_and_keeps_an_emptied_outfit(
    wardrobe, stranger, strangers_outfit
):
    before = _strangers_state(stranger)

    Garment.objects.filter(pk__in=[wardrobe['a'].pk, wardrobe['b'].pk]).delete()

    o1 = Outfit.objects.get(pk=wardrobe['o1'].pk)
    assert o1.missing_garments.count() == 2
    assert not o1.garments.exists()
    assert sorted(o1.missing_garments.values_list('description', flat=True)) == [
        'brown loafers',
        'navy oxford',
    ]
    assert Outfit.objects.get(pk=wardrobe['o2'].pk).missing_garments.count() == 1
    assert Outfit.objects.get(pk=wardrobe['o3'].pk).missing_garments.count() == 1
    assert _strangers_state(stranger) == before


def test_a_garment_in_no_outfit_deletes_without_a_record(owner):
    garment = make_garment(owner)

    garment.delete()

    assert not MissingGarment.objects.exists()


def test_deleting_the_account_leaves_no_outfit_garment_or_record_behind(
    wardrobe, owner, stranger, strangers_outfit
):
    # Each garment's pre_delete inserts records for outfits this same cascade
    # deletes; they must go with them. check_constraints() catches a record
    # left pointing at a deleted outfit, which PostgreSQL would refuse outright.
    before = _strangers_state(stranger)
    owner_pk = owner.pk

    owner.delete()

    assert not Outfit.objects.filter(owner_id=owner_pk).exists()
    assert not Garment.objects.filter(owner_id=owner_pk).exists()
    assert not MissingGarment.objects.filter(outfit__owner_id=owner_pk).exists()
    assert MissingGarment.objects.count() == 0
    connection.check_constraints()
    assert _strangers_state(stranger) == before


def test_deleting_an_outfit_deletes_its_records(wardrobe):
    wardrobe['a'].delete()
    o1 = wardrobe['o1']

    o1.delete()

    assert not MissingGarment.objects.filter(outfit_id=o1.pk).exists()
    assert MissingGarment.objects.filter(outfit=wardrobe['o2']).count() == 1


def test_prefetched_missing_count_makes_no_query(wardrobe, owner, django_assert_num_queries):
    wardrobe['a'].delete()
    outfits = list(Outfit.objects.filter(owner=owner).prefetch_related('missing_garments'))

    with django_assert_num_queries(0):
        flags = {outfit.name: (outfit.is_incomplete, outfit.missing_count) for outfit in outfits}

    assert flags == {
        'autumn walk': (True, 1),
        'city errand': (True, 1),
        'office': (False, 0),
    }
