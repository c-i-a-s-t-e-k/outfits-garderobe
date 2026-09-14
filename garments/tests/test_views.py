"""Garments are private through HTTP, and a failed add leaves nothing behind."""

import io
import re
from datetime import timedelta
from pathlib import Path

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.templatetags.static import static
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from PIL import Image

from garments.models import Garment, GarmentType
from privatemedia import uploadhandlers
from privatemedia.models import PrivateImage
from privatemedia.processing import MAX_EDGE_PX
from privatemedia.validators import MAX_UPLOAD_BYTES
from tests.factories import make_garment, make_outfit

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures('temp_media_root')]

LIST_URL = reverse('garments:list')
ADD_URL = reverse('garments:add')


def _image_upload(name='wardrobe-shirt.jpg', size=(2400, 1800), format='JPEG'):
    buffer = io.BytesIO()
    Image.new('RGB', size, 'teal').save(buffer, format=format)
    return SimpleUploadedFile(name, buffer.getvalue())


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
    older = make_garment(owner, description='blue oxford')
    newer = make_garment(owner, description='grey hoodie')
    # Two inserts can share a timestamp on a coarse clock; pin the order the list
    # must show instead of relying on the gap between them.
    Garment.objects.filter(pk=older.pk).update(created_at=newer.created_at - timedelta(minutes=1))

    client.force_login(owner)
    page = client.get(LIST_URL).content.decode()
    assert page.index('grey hoodie') < page.index('blue oxford')

    client.force_login(stranger)
    page = client.get(LIST_URL).content.decode()
    for garment in (older, newer):
        assert garment.description not in page
        assert garment.photo_url not in page


def test_tile_photo_is_served_to_its_owner_only(client, owner, stranger):
    garment = make_garment(owner)

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


def test_photo_with_too_many_pixels_says_so(client, owner, temp_media_root, monkeypatch):
    # Pillow raises (rather than warns) above twice MAX_IMAGE_PIXELS.
    monkeypatch.setattr(Image, 'MAX_IMAGE_PIXELS', 100)
    client.force_login(owner)

    response = _add(client, photo=_image_upload(size=(40, 40)))

    assert response.status_code == 200
    assert 'too many pixels' in ' '.join(response.context['form'].errors['photo'])
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


def test_request_over_the_size_ceiling_is_refused_before_it_is_parsed(
    client, owner, temp_media_root, monkeypatch
):
    monkeypatch.setattr(uploadhandlers, 'MAX_REQUEST_BYTES', 1024)
    client.force_login(owner)

    response = _add(client, photo=_image_upload())

    assert response.status_code == 400
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
    make_garment(owner)
    with CaptureQueriesContext(connection) as one:
        client.get(LIST_URL)

    for _ in range(4):
        make_garment(owner)
    with CaptureQueriesContext(connection) as five:
        client.get(LIST_URL)

    assert len(five.captured_queries) == len(one.captured_queries)


def test_photo_input_offers_both_camera_and_library(client, owner):
    client.force_login(owner)

    page = client.get(ADD_URL).content.decode()

    photo_input = re.search(r'<input[^>]*name="photo"[^>]*>', page).group(0)
    assert 'accept="image/*"' in photo_input
    assert 'capture' not in photo_input


def test_add_page_wires_up_the_photo_shrink_script(client, owner):
    client.force_login(owner)

    page = client.get(ADD_URL).content.decode()

    photo_input = re.search(r'<input[^>]*name="photo"[^>]*>', page).group(0)
    assert 'data-shrink-photo' in photo_input
    assert f'<script src="{static("js/photo-shrink.js")}" defer>' in page
    assert 'data-shrink-status' in page


# --- edit ----------------------------------------------------------------------


def _edit_url(garment):
    return reverse('garments:edit', args=[garment.pk])


def _edit(client, garment, **overrides):
    data = {'type': garment.type, 'type_other': garment.type_other, 'description': ''}
    return client.post(_edit_url(garment), {**data, **overrides})


def _file_of(image):
    return Path(image.image.path)


def test_list_tile_links_to_its_garments_edit_page(client, owner):
    garment = make_garment(owner, description='blue oxford')
    client.force_login(owner)

    page = client.get(LIST_URL).content.decode()

    assert f'<a href="{_edit_url(garment)}"' in page


def test_editing_the_description_alone_keeps_the_photo(client, owner):
    garment = make_garment(owner, description='blue oxford')
    photo_file = _file_of(garment.photo)
    client.force_login(owner)

    response = _edit(client, garment, description='blue oxford, ironed')

    assert response.status_code == 302
    assert response.headers['Location'] == LIST_URL
    garment.refresh_from_db()
    assert garment.description == 'blue oxford, ironed'
    assert PrivateImage.objects.get().pk == garment.photo_id
    assert photo_file.is_file()
    assert 'Garment updated.' in client.get(LIST_URL).content.decode()


def test_replacing_the_photo_links_a_new_one_and_deletes_the_old_after_commit(
    client, owner, django_capture_on_commit_callbacks
):
    garment = make_garment(owner, type=GarmentType.SHOES)
    other = make_garment(owner)
    outfit = make_outfit(owner, garments=[garment, other])
    old = garment.photo
    old_file = _file_of(old)
    client.force_login(owner)

    with django_capture_on_commit_callbacks(execute=True):
        response = _edit(client, garment, photo=_image_upload())

    assert response.status_code == 302
    garment.refresh_from_db()
    assert garment.photo_id != old.pk
    assert garment.photo.owner == owner
    assert _file_of(garment.photo).is_file()
    assert not PrivateImage.objects.filter(pk=old.pk).exists()
    assert not old_file.exists()
    assert set(outfit.garments.all()) == {garment, other}
    assert _file_of(other.photo).is_file()


def test_a_replace_that_fails_keeps_the_old_photo_and_stores_no_new_file(
    client, owner, temp_media_root, monkeypatch, django_capture_on_commit_callbacks
):
    garment = make_garment(owner)
    old_file = _file_of(garment.photo)
    files_before = _stored_files(temp_media_root)

    def fail(*args, **kwargs):
        raise RuntimeError('database went away')

    monkeypatch.setattr(Garment, 'save', fail)
    client.force_login(owner)
    client.raise_request_exception = True

    with django_capture_on_commit_callbacks(execute=True), pytest.raises(RuntimeError):
        _edit(client, garment, photo=_image_upload())

    assert Garment.objects.get().photo_id == garment.photo_id
    assert PrivateImage.objects.get().pk == garment.photo_id
    assert old_file.is_file()
    assert _stored_files(temp_media_root) == files_before


@pytest.mark.parametrize(
    'make_upload',
    [
        lambda: SimpleUploadedFile('broken.jpg', b'not an image' * 100),
        lambda: _image_upload('huge.bmp', size=(2000, 2000), format='BMP'),
    ],
    ids=['corrupt', '11 MB'],
)
def test_a_refused_photo_on_edit_is_a_field_error_and_changes_nothing(
    client, owner, temp_media_root, make_upload
):
    garment = make_garment(owner, description='blue oxford')
    files_before = _stored_files(temp_media_root)
    client.force_login(owner)

    response = _edit(client, garment, description='changed', photo=make_upload())

    assert response.status_code == 200
    assert 'photo' in response.context['form'].errors
    assert Garment.objects.get().description == 'blue oxford'
    assert PrivateImage.objects.get().pk == garment.photo_id
    assert _stored_files(temp_media_root) == files_before


def test_other_text_matching_a_listed_type_is_folded_on_edit(client, owner):
    garment = make_garment(owner, type=GarmentType.SHOES)
    client.force_login(owner)

    _edit(client, garment, type=GarmentType.OTHER, type_other='shirt')

    garment.refresh_from_db()
    assert (garment.type, garment.type_other) == (GarmentType.SHIRT, '')


# --- delete --------------------------------------------------------------------


def _delete_url(garment):
    return reverse('garments:delete', args=[garment.pk])


def test_edit_page_links_to_the_delete_confirmation(client, owner):
    garment = make_garment(owner)
    client.force_login(owner)

    page = client.get(_edit_url(garment)).content.decode()

    assert f'href="{_delete_url(garment)}"' in page


def test_delete_page_names_every_outfit_the_garment_will_leave_incomplete(client, owner):
    garment = make_garment(owner, type=GarmentType.SHOES)
    make_outfit(owner, garments=[garment, make_garment(owner)], name='autumn walk')
    make_outfit(owner, garments=[garment, make_garment(owner)], name='city errand')
    make_outfit(owner, garments=[make_garment(owner), make_garment(owner)], name='gym day')
    client.force_login(owner)

    response = client.get(_delete_url(garment))

    page = response.content.decode()
    assert response.status_code == 200
    assert 'autumn walk' in page
    assert 'city errand' in page
    assert 'gym day' not in page
    assert 'marked incomplete' in page
    # The confirmation changes nothing by itself.
    assert Garment.objects.filter(pk=garment.pk).exists()


def test_delete_page_of_a_garment_in_no_outfit_says_so(client, owner):
    garment = make_garment(owner)
    client.force_login(owner)

    page = client.get(_delete_url(garment)).content.decode()

    assert 'This garment is not in any outfit.' in page


def test_confirmed_delete_removes_the_garment_and_its_photo_and_keeps_its_outfits(
    client, owner, django_capture_on_commit_callbacks
):
    garment = make_garment(owner, type=GarmentType.SHOES, description='brown loafers')
    shirt, trousers = make_garment(owner), make_garment(owner, type=GarmentType.TROUSERS)
    walk = make_outfit(owner, garments=[garment, shirt])
    errand = make_outfit(owner, garments=[garment, trousers])
    photo_pk, photo_file = garment.photo_id, _file_of(garment.photo)
    client.force_login(owner)

    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(_delete_url(garment))

    assert response.status_code == 302
    assert response.headers['Location'] == LIST_URL
    assert not Garment.objects.filter(pk=garment.pk).exists()
    assert not PrivateImage.objects.filter(pk=photo_pk).exists()
    assert not photo_file.exists()
    assert set(walk.garments.all()) == {shirt}
    assert set(errand.garments.all()) == {trousers}
    for outfit in (walk, errand):
        missing = outfit.missing_garments.get()
        assert (missing.type, missing.description) == (GarmentType.SHOES, 'brown loafers')
    page = client.get(LIST_URL).content.decode()
    assert 'Garment deleted.' in page
    assert '2 outfits are now incomplete.' in page


def test_deleting_a_garment_in_no_outfit_says_nothing_about_outfits(
    client, owner, django_capture_on_commit_callbacks
):
    garment = make_garment(owner)
    client.force_login(owner)

    with django_capture_on_commit_callbacks(execute=True):
        client.post(_delete_url(garment))

    page = client.get(LIST_URL).content.decode()
    assert 'Garment deleted.' in page
    assert 'incomplete' not in page


# --- strangers -------------------------------------------------------------------


@pytest.mark.parametrize('method', ['get', 'post'])
@pytest.mark.parametrize('url_for', [_edit_url, _delete_url], ids=['edit', 'delete'])
def test_another_users_garment_is_404_to_edit_or_delete_and_changes_nothing(
    client, owner, stranger, temp_media_root, django_capture_on_commit_callbacks, method, url_for
):
    garment = make_garment(owner, description='blue oxford')
    make_outfit(owner, garments=[garment, make_garment(owner)])
    make_garment(stranger)
    files_before = _stored_files(temp_media_root)
    client.force_login(stranger)

    with django_capture_on_commit_callbacks(execute=True):
        if method == 'get':
            response = client.get(url_for(garment))
        else:
            response = client.post(
                url_for(garment),
                {'type': GarmentType.SHOES, 'description': 'stolen', 'photo': _image_upload()},
            )

    assert response.status_code == 404
    reread = Garment.objects.get(pk=garment.pk)
    assert (reread.description, reread.photo_id) == ('blue oxford', garment.photo_id)
    assert PrivateImage.objects.filter(owner=owner).count() == 2
    assert not garment.outfits.get().missing_garments.exists()
    assert _stored_files(temp_media_root) == files_before
