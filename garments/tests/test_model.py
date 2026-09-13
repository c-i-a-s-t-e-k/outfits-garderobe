"""The rules that keep type data filterable and a garment's photo tied to its owner."""

import io

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.db.models import RestrictedError
from django.urls import reverse
from PIL import Image

from garments.models import Garment, GarmentType
from privatemedia.models import PrivateImage

pytestmark = pytest.mark.django_db


def _png_bytes():
    buffer = io.BytesIO()
    Image.new('RGB', (4, 4), 'green').save(buffer, format='PNG')
    return buffer.getvalue()


IMAGE_BYTES = _png_bytes()


@pytest.fixture(autouse=True)
def temp_media_root(settings, tmp_path):
    """Keep every test's uploads out of the real MEDIA_ROOT."""
    settings.MEDIA_ROOT = tmp_path / 'media'
    return settings.MEDIA_ROOT


@pytest.fixture
def owner(django_user_model):
    return django_user_model.objects.create_user(username='owner', password='pw-owner-12345')


@pytest.fixture
def stranger(django_user_model):
    return django_user_model.objects.create_user(username='stranger', password='pw-other-12345')


def _photo(user):
    return PrivateImage.objects.create(
        owner=user,
        image=SimpleUploadedFile('garment.png', IMAGE_BYTES, content_type='image/png'),
    )


@pytest.fixture
def photo(owner):
    return _photo(owner)


@pytest.mark.parametrize(
    ('typed', 'expected'),
    [
        ('shirt ', GarmentType.SHIRT),
        ('SHIRT', GarmentType.SHIRT),
        ('tshirt', GarmentType.TSHIRT),
        ('  jacket   /  coat ', GarmentType.OUTERWEAR),
    ],
)
def test_other_text_matching_a_choice_is_folded_into_it(owner, photo, typed, expected):
    garment = Garment.objects.create(
        owner=owner, photo=photo, type=GarmentType.OTHER, type_other=typed
    )

    garment.refresh_from_db()
    assert garment.type == expected
    assert garment.type_other == ''


def test_other_text_is_tidied_and_kept(owner, photo):
    garment = Garment.objects.create(
        owner=owner, photo=photo, type=GarmentType.OTHER, type_other='Wool   scarf '
    )

    garment.refresh_from_db()
    assert garment.type == GarmentType.OTHER
    assert garment.type_other == 'Wool scarf'


@pytest.mark.parametrize('typed', ['', '   '])
def test_other_without_text_is_rejected(owner, photo, typed):
    with pytest.raises(ValidationError) as excinfo:
        Garment.objects.create(owner=owner, photo=photo, type=GarmentType.OTHER, type_other=typed)

    assert 'type_other' in excinfo.value.message_dict


def test_leftover_text_on_a_listed_type_is_cleared(owner, photo):
    garment = Garment.objects.create(
        owner=owner, photo=photo, type=GarmentType.SHOES, type_other='sneakers'
    )

    garment.refresh_from_db()
    assert garment.type_other == ''


def test_database_enforces_the_other_rule_against_bulk_updates(owner, photo):
    """PostgreSQL must refuse what clean() would have caught, when clean() never runs."""
    garment = Garment.objects.create(owner=owner, photo=photo, type=GarmentType.SHIRT)

    with pytest.raises(IntegrityError), transaction.atomic():
        Garment.objects.filter(pk=garment.pk).update(type=GarmentType.OTHER)


def test_photo_of_another_user_is_rejected(owner, stranger):
    with pytest.raises(ValidationError):
        Garment.objects.create(owner=owner, photo=_photo(stranger), type=GarmentType.SHIRT)


def test_clean_skips_the_owner_check_until_owner_and_photo_are_set():
    """A ModelForm validates the instance before the view assigns owner and photo."""
    Garment(type=GarmentType.SHIRT).full_clean(exclude=['owner', 'photo'])


def test_one_photo_cannot_back_two_garments(owner, photo):
    Garment.objects.create(owner=owner, photo=photo, type=GarmentType.SHIRT)

    with pytest.raises(ValidationError):
        Garment.objects.create(owner=owner, photo=photo, type=GarmentType.SHOES)


def test_deleting_the_user_removes_garments_and_their_photos(owner, photo):
    """The RESTRICT case: the photo goes because its garment is going in the same delete."""
    Garment.objects.create(owner=owner, photo=photo, type=GarmentType.SHIRT)

    owner.delete()

    assert not Garment.objects.exists()
    assert not PrivateImage.objects.exists()


def test_a_photo_in_use_cannot_be_deleted_on_its_own(owner, photo):
    Garment.objects.create(owner=owner, photo=photo, type=GarmentType.SHIRT)

    with pytest.raises(RestrictedError):
        photo.delete()


def test_description_longer_than_200_characters_is_rejected(owner, photo):
    with pytest.raises(ValidationError) as excinfo:
        Garment.objects.create(
            owner=owner, photo=photo, type=GarmentType.SHIRT, description='x' * 201
        )

    assert 'description' in excinfo.value.message_dict


def test_display_type_and_photo_url(owner, photo, django_assert_num_queries):
    listed = Garment.objects.create(owner=owner, photo=photo, type=GarmentType.OUTERWEAR)
    custom = Garment.objects.create(
        owner=owner, photo=_photo(owner), type=GarmentType.OTHER, type_other='Wool scarf'
    )
    listed = Garment.objects.get(pk=listed.pk)

    with django_assert_num_queries(0):
        assert listed.display_type == 'Jacket / coat'
        assert listed.photo_url == reverse('privatemedia:image', args=[photo.pk])
    assert custom.display_type == 'Wool scarf'
