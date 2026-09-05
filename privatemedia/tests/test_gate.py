"""Every way the gate can fail, proven one case at a time."""

import io
import uuid

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from privatemedia.models import PrivateImage

pytestmark = pytest.mark.django_db


def _png_bytes():
    buffer = io.BytesIO()
    Image.new('RGB', (4, 4), 'red').save(buffer, format='PNG')
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


@pytest.fixture
def image(owner):
    return PrivateImage.objects.create(
        owner=owner,
        image=SimpleUploadedFile('holiday-photo.png', IMAGE_BYTES, content_type='image/png'),
    )


def gate_url(pk):
    return reverse('privatemedia:image', args=[pk])


def test_owner_receives_the_file_bytes(client, owner, image):
    client.force_login(owner)

    response = client.get(gate_url(image.pk))

    assert response.status_code == 200
    assert b''.join(response.streaming_content) == IMAGE_BYTES


def test_response_is_inline_and_privately_cached(client, owner, image):
    client.force_login(owner)

    response = client.get(gate_url(image.pk))

    assert response['Content-Disposition'].startswith('inline')
    assert 'private' in response['Cache-Control']


def test_second_user_gets_404(client, stranger, image):
    client.force_login(stranger)

    assert client.get(gate_url(image.pk)).status_code == 404


def test_anonymous_request_is_redirected_to_login(client, image):
    response = client.get(gate_url(image.pk))

    assert response.status_code == 302
    assert response.headers['Location'].startswith(settings.LOGIN_URL)


def test_nonexistent_uuid_gets_404(client, owner):
    client.force_login(owner)

    assert client.get(gate_url(uuid.uuid4())).status_code == 404


def test_the_two_404s_are_indistinguishable(client, stranger, image):
    """A probe must not be able to tell "not yours" from "never existed"."""
    client.force_login(stranger)

    not_yours = client.get(gate_url(image.pk))
    never_existed = client.get(gate_url(uuid.uuid4()))

    assert not_yours.status_code == never_existed.status_code == 404
    assert not_yours.content == never_existed.content
    # A validator header on the denial would confirm the row exists.
    for response in (not_yours, never_existed):
        assert 'ETag' not in response.headers
        assert 'Last-Modified' not in response.headers


def test_repeat_fetch_is_a_304(client, owner, image):
    """Conditional GET is wired explicitly — ConditionalGetMiddleware is absent."""
    client.force_login(owner)
    first = client.get(gate_url(image.pk))
    assert first['ETag']

    second = client.get(gate_url(image.pk), headers={'if-none-match': first['ETag']})

    assert second.status_code == 304
