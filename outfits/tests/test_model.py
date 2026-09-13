"""The naming rules, the ownership guard and the preview order of an outfit."""

import io
from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from PIL import Image

from garments.models import Garment, GarmentType
from outfits.models import Outfit
from privatemedia.models import PrivateImage

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures('temp_media_root')]


def _png_bytes():
    buffer = io.BytesIO()
    Image.new('RGB', (4, 4), 'green').save(buffer, format='PNG')
    return buffer.getvalue()


IMAGE_BYTES = _png_bytes()


def make_garment(user, type=GarmentType.SHIRT, **fields):
    photo = PrivateImage.objects.create(
        owner=user,
        image=SimpleUploadedFile('garment.png', IMAGE_BYTES, content_type='image/png'),
    )
    return Garment.objects.create(owner=user, photo=photo, type=type, **fields)


def _links():
    return set(Outfit.garments.through.objects.values_list('outfit_id', 'garment_id'))


# --- default names -----------------------------------------------------------


def test_blank_name_on_the_first_outfit_becomes_outfit_1(owner):
    outfit = Outfit.objects.create(owner=owner, name='')

    assert outfit.name == 'outfit-1'


def test_default_name_fills_the_lowest_gap(owner):
    Outfit.objects.create(owner=owner, name='outfit-1')
    Outfit.objects.create(owner=owner, name='outfit-3')

    assert Outfit.objects.create(owner=owner).name == 'outfit-2'


def test_default_name_counts_taken_numbers_regardless_of_case(owner):
    Outfit.objects.create(owner=owner, name='outfit-1')
    Outfit.objects.create(owner=owner, name='OUTFIT-2')

    assert Outfit.objects.create(owner=owner).name == 'outfit-3'


def test_another_users_default_name_does_not_count(owner, stranger):
    Outfit.objects.create(owner=stranger, name='outfit-1')

    assert Outfit.objects.create(owner=owner).name == 'outfit-1'


def test_a_zero_padded_name_does_not_occupy_its_number(owner):
    Outfit.objects.create(owner=owner, name='outfit-02')

    assert Outfit.objects.create(owner=owner).name == 'outfit-1'
    assert Outfit.objects.create(owner=owner).name == 'outfit-2'


def test_whitespace_only_name_gets_the_default(owner):
    assert Outfit.objects.create(owner=owner, name='   ').name == 'outfit-1'


def test_name_whitespace_is_collapsed_and_stripped(owner):
    outfit = Outfit.objects.create(owner=owner, name='  Summer   wedding ')

    outfit.refresh_from_db()
    assert outfit.name == 'Summer wedding'


# --- uniqueness --------------------------------------------------------------


def test_a_case_variant_of_an_existing_name_is_rejected_for_the_same_owner(owner):
    Outfit.objects.create(owner=owner, name='Summer wedding')

    with pytest.raises(ValidationError):
        Outfit.objects.create(owner=owner, name='summer wedding')


def test_the_same_name_saves_for_another_owner(owner, stranger):
    Outfit.objects.create(owner=owner, name='Summer wedding')

    assert Outfit.objects.create(owner=stranger, name='summer wedding').pk


def test_database_refuses_a_case_variant_duplicate_that_skips_clean(owner):
    """PostgreSQL must refuse what clean() would have caught, when clean() never runs."""
    Outfit.objects.create(owner=owner, name='Summer wedding')
    other = Outfit.objects.create(owner=owner, name='Office')

    with pytest.raises(IntegrityError), transaction.atomic():
        Outfit.objects.filter(pk=other.pk).update(name='SUMMER WEDDING')


def test_database_refuses_an_empty_name_that_skips_clean(owner):
    outfit = Outfit.objects.create(owner=owner, name='Office')

    with pytest.raises(IntegrityError), transaction.atomic():
        Outfit.objects.filter(pk=outfit.pk).update(name='')


# --- garment ownership -------------------------------------------------------


def test_another_users_garment_cannot_be_added_to_an_outfit(owner, stranger):
    outfit = Outfit.objects.create(owner=owner)
    own = make_garment(owner)
    foreign = make_garment(stranger)

    # The guard raises inside add()'s own atomic block, which joins the
    # surrounding transaction; the savepoint keeps the test's usable afterwards.
    with pytest.raises(ValidationError), transaction.atomic():
        outfit.garments.add(own, foreign)

    assert _links() == set()


def test_a_garment_cannot_be_added_to_another_users_outfit_from_the_garment_side(owner, stranger):
    outfit = Outfit.objects.create(owner=stranger)
    garment = make_garment(owner)

    with pytest.raises(ValidationError), transaction.atomic():
        garment.outfits.add(outfit)

    assert _links() == set()


def test_one_garment_belongs_to_two_outfits(owner):
    garment = make_garment(owner)
    first = Outfit.objects.create(owner=owner)
    second = Outfit.objects.create(owner=owner)

    first.garments.add(garment)
    second.garments.add(garment)

    assert set(garment.outfits.all()) == {first, second}


def test_two_outfits_with_the_same_garments_both_save(owner):
    garments = [make_garment(owner), make_garment(owner, type=GarmentType.TROUSERS)]

    first = Outfit.objects.create(owner=owner)
    first.garments.set(garments)
    second = Outfit.objects.create(owner=owner)
    second.garments.set(garments)

    assert set(first.garments.all()) == set(second.garments.all()) == set(garments)


# --- preview -----------------------------------------------------------------


def test_preview_shows_four_garments_in_type_order_and_counts_the_rest(owner):
    outfit = Outfit.objects.create(owner=owner)
    by_type = {}
    for type in [
        GarmentType.SHOES,
        GarmentType.ACCESSORY,
        GarmentType.TROUSERS,
        GarmentType.TSHIRT,
        GarmentType.OUTERWEAR,
        GarmentType.OTHER,
        GarmentType.SHIRT,
    ]:
        fields = {'type_other': 'Scarf'} if type == GarmentType.OTHER else {}
        by_type[type] = make_garment(owner, type=type, **fields)
    outfit.garments.set(by_type.values())

    outfit = Outfit.objects.prefetch_related('garments').get(pk=outfit.pk)

    assert outfit.preview_garments == [
        by_type[GarmentType.OUTERWEAR],
        by_type[GarmentType.SHIRT],
        by_type[GarmentType.TSHIRT],
        by_type[GarmentType.TROUSERS],
    ]
    assert outfit.hidden_garment_count == 3
    assert outfit.ordered_garments[4:] == [
        by_type[GarmentType.SHOES],
        by_type[GarmentType.ACCESSORY],
        by_type[GarmentType.OTHER],
    ]


def test_preview_of_two_garments_shows_both_and_hides_none(owner):
    outfit = Outfit.objects.create(owner=owner)
    shoes = make_garment(owner, type=GarmentType.SHOES)
    dress = make_garment(owner, type=GarmentType.DRESS)
    outfit.garments.set([shoes, dress])

    assert outfit.preview_garments == [dress, shoes]
    assert outfit.hidden_garment_count == 0


def test_garments_of_one_type_keep_the_order_they_were_added(owner):
    outfit = Outfit.objects.create(owner=owner)
    first = make_garment(owner, description='blue')
    second = make_garment(owner, description='white')
    # Two inserts can share a timestamp on a coarse clock; pin the order.
    Garment.objects.filter(pk=first.pk).update(created_at=second.created_at - timedelta(minutes=1))
    outfit.garments.set([second, first])

    assert [g.description for g in outfit.preview_garments] == ['blue', 'white']


def test_preview_makes_no_query_after_a_prefetch(owner, django_assert_num_queries):
    outfit = Outfit.objects.create(owner=owner)
    outfit.garments.set([make_garment(owner), make_garment(owner, type=GarmentType.SHOES)])
    outfit = Outfit.objects.prefetch_related('garments').get(pk=outfit.pk)

    with django_assert_num_queries(0):
        assert len(outfit.preview_garments) == 2
        assert outfit.hidden_garment_count == 0
        assert len(outfit.ordered_garments) == 2


# --- lifecycle ---------------------------------------------------------------


def test_deleting_the_owner_removes_their_outfits(owner):
    outfit = Outfit.objects.create(owner=owner)
    outfit.garments.add(make_garment(owner))

    owner.delete()

    assert not Outfit.objects.exists()
    assert _links() == set()


def test_str_is_the_name(owner):
    assert str(Outfit(owner=owner, name='Office')) == 'Office'
