"""Garments are private through HTTP, and a failed add leaves nothing behind."""

import io
import re

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from PIL import Image

from garments.models import Garment, GarmentType
from privatemedia.models import PrivateImage
from privatemedia.processing import MAX_EDGE_PX
from privatemedia.validators import MAX_UPLOAD_BYTES

pytestmark = pytest.mark.django_db

LIST_URL = reverse('garments:list')
ADD_URL = reverse('garments:add')


def _image_upload(name='wardrobe-shirt.jpg', size=(2400, 1800), format='JPEG'):
    buffer = io.BytesIO()
    Image.new('RGB', size, 'teal').save(buffer, format=format)
    return SimpleUploadedFile(name, buffer.getvalue())


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


def _garment(user, description='', type=GarmentType.SHIRT):
    photo = PrivateImage.objects.create(
        owner=user, image=_image_upload(size=(8, 8)), original_filename='seed.jpg'
    )
    return Garment.objects.create(owner=user, photo=photo, type=type, description=description)


def _stored_files(media_root):
    return [path for path in media_root.rglob('*') if path.is_file()]


def _add(client, **overrides):
    data = {'type': GarmentType.SHIRT, 'type_other': '', 'description': '', **overrides}
    data.setdefault('photo', _image_upload())
    return client.post(ADD_URL, data)


@pytest.mark.parametrize('url', [LIST_URL, ADD_URL])
def test_anonymous_visitor_is_sent_to_login(client, url):
    response = client.get(url)

    assert response.status_code == 302
    assert response.headers['Location'].startswith(settings.LOGIN_URL)


def test_list_shows_own_garments_newest_first_and_nothing_of_anyone_else(client, owner, stranger):
    older = _garment(owner, description='blue oxford')
    newer = _garment(owner, description='grey hoodie')

    client.force_login(owner)
    page = client.get(LIST_URL).content.decode()
    assert page.index('grey hoodie') < page.index('blue oxford')

    client.force_login(stranger)
    page = client.get(LIST_URL).content.decode()
    for garment in (older, newer):
        assert garment.description not in page
        assert garment.photo_url not in page


def test_tile_photo_is_served_to_its_owner_only(client, owner, stranger):
    garment = _garment(owner)

    client.force_login(owner)
    page = client.get(LIST_URL).content.decode()
    src = re.search(r'<img src="([^"]+)"', page).group(1)
    assert client.get(src).status_code == 200

    client.force_login(stranger)
    assert client.get(garment.photo_url).status_code == 404


def test_valid_add_stores_a_normalized_photo_and_the_garment(client, owner):
    client.force_login(owner)

    response = _add(client, description='linen, summer')

    assert response.status_code == 302
    assert response.headers['Location'] == LIST_URL
    garment = Garment.objects.get()
    image = PrivateImage.objects.get()
    assert garment.owner == owner
    assert image.owner == owner
    assert garment.photo == image
    assert image.original_filename == 'wardrobe-shirt.jpg'
    assert image.image.name.endswith('.jpg')
    with Image.open(image.image.path) as stored:
        assert stored.format == 'JPEG'
        assert max(stored.size) <= MAX_EDGE_PX

    followed = client.get(response.headers['Location'])
    assert 'Garment added.' in followed.content.decode()


def test_heic_photo_can_be_added(client, owner):
    client.force_login(owner)

    response = _add(client, photo=_image_upload('IMG_0042.HEIC', size=(800, 600), format='HEIF'))

    assert response.status_code == 302
    assert PrivateImage.objects.get().original_filename == 'IMG_0042.HEIC'


def test_other_text_matching_a_listed_type_is_stored_as_that_type(client, owner):
    client.force_login(owner)

    _add(client, type=GarmentType.OTHER, type_other='Shirt')

    garment = Garment.objects.get()
    assert (garment.type, garment.type_other) == (GarmentType.SHIRT, '')


def test_invalid_form_stores_nothing(client, owner, temp_media_root):
    client.force_login(owner)

    response = _add(client, type=GarmentType.OTHER, type_other='')

    assert response.status_code == 200
    assert 'type_other' in response.context['form'].errors
    assert not Garment.objects.exists()
    assert not PrivateImage.objects.exists()
    assert _stored_files(temp_media_root) == []


def test_corrupt_photo_is_a_field_error_and_stores_nothing(client, owner, temp_media_root):
    client.force_login(owner)

    response = _add(client, photo=SimpleUploadedFile('broken.jpg', b'not an image' * 100))

    assert response.status_code == 200
    assert 'photo' in response.context['form'].errors
    assert not PrivateImage.objects.exists()
    assert _stored_files(temp_media_root) == []


def test_oversized_upload_is_a_field_error_and_stores_nothing(client, owner, temp_media_root):
    # An uncompressed BMP is a real image and passes ImageField's own check, so
    # it is the size ceiling that has to refuse it.
    upload = _image_upload('huge.bmp', size=(2000, 2000), format='BMP')
    assert upload.size > MAX_UPLOAD_BYTES
    client.force_login(owner)

    response = _add(client, photo=upload)

    assert response.status_code == 200
    assert 'too large' in ' '.join(response.context['form'].errors['photo'])
    assert not PrivateImage.objects.exists()
    assert _stored_files(temp_media_root) == []


def test_failure_after_the_photo_is_stored_removes_the_file(
    client, owner, temp_media_root, monkeypatch
):
    def fail(*args, **kwargs):
        raise RuntimeError('database went away')

    monkeypatch.setattr(Garment, 'save', fail)
    client.force_login(owner)
    client.raise_request_exception = True

    with pytest.raises(RuntimeError):
        _add(client)

    assert not PrivateImage.objects.exists()
    assert _stored_files(temp_media_root) == []


def test_list_query_count_does_not_grow_with_garments(client, owner):
    client.force_login(owner)
    _garment(owner)
    with CaptureQueriesContext(connection) as one:
        client.get(LIST_URL)

    for _ in range(4):
        _garment(owner)
    with CaptureQueriesContext(connection) as five:
        client.get(LIST_URL)

    assert len(five.captured_queries) == len(one.captured_queries)


def test_photo_input_offers_both_camera_and_library(client, owner):
    client.force_login(owner)

    page = client.get(ADD_URL).content.decode()

    photo_input = re.search(r'<input[^>]*name="photo"[^>]*>', page).group(0)
    assert 'accept="image/*"' in photo_input
    assert 'capture' not in photo_input
