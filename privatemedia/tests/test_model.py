"""The model-level rules the gate rests on: opaque paths and a size ceiling."""

import io
import uuid

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.forms import modelform_factory
from PIL import Image

from privatemedia.models import PrivateImage, upload_to_uuid
from privatemedia.validators import MAX_UPLOAD_BYTES, validate_max_size


class _StubFile:
    def __init__(self, size):
        self.size = size


def _png_bytes():
    buffer = io.BytesIO()
    Image.new('RGB', (4, 4), 'blue').save(buffer, format='PNG')
    return buffer.getvalue()


def test_upload_to_never_leaks_the_original_name():
    path = upload_to_uuid(None, 'My Holiday Photo.JPEG')

    assert path.startswith('private/')
    assert 'holiday' not in path.lower()
    assert path.endswith('.jpeg')
    uuid.UUID(hex=path.removeprefix('private/').removesuffix('.jpeg'))


def test_upload_to_tolerates_a_missing_extension():
    path = upload_to_uuid(None, 'scan')

    uuid.UUID(hex=path.removeprefix('private/'))


def test_validator_rejects_a_file_above_the_ceiling():
    with pytest.raises(ValidationError):
        validate_max_size(_StubFile(MAX_UPLOAD_BYTES + 1))


def test_validator_accepts_a_file_at_the_ceiling():
    validate_max_size(_StubFile(MAX_UPLOAD_BYTES))


@pytest.mark.django_db
def test_non_image_is_rejected_despite_extension(settings, tmp_path, django_user_model):
    """Content, not the extension, decides — checked at the form layer the admin uses."""
    settings.MEDIA_ROOT = tmp_path / 'media'
    owner = django_user_model.objects.create_user(username='owner', password='pw-owner-12345')
    form_class = modelform_factory(PrivateImage, fields=['owner', 'image'])

    form = form_class(
        data={'owner': owner.pk},
        files={
            'image': SimpleUploadedFile(
                'not-really.png', b'this is not a png', content_type='image/png'
            )
        },
    )

    assert not form.is_valid()
    assert 'image' in form.errors


@pytest.mark.django_db
def test_objects_create_still_enforces_the_size_ceiling(settings, tmp_path, django_user_model):
    """The ceiling must hold on the plain ORM path, not only through a form.

    S-02 and S-04 upload without going near the admin, so a rule that only
    ModelForm._post_clean() applies would not actually be inherited.
    """
    settings.MEDIA_ROOT = tmp_path / 'media'
    owner = django_user_model.objects.create_user(username='owner', password='pw-owner-12345')
    oversized = SimpleUploadedFile(
        'huge.png', b'x' * (MAX_UPLOAD_BYTES + 1), content_type='image/png'
    )

    with pytest.raises(ValidationError):
        PrivateImage.objects.create(owner=owner, image=oversized)


@pytest.mark.django_db
def test_objects_create_rejects_a_dangerous_extension(settings, tmp_path, django_user_model):
    """upload_to preserves the extension, so the extension is what gets served.

    A stored `.html` would come back through the gate as text/html — same origin,
    owner's session. `validate_image_file_extension` is a model-level validator,
    so `full_clean()` in save() applies it to the plain ORM path too.
    """
    settings.MEDIA_ROOT = tmp_path / 'media'
    owner = django_user_model.objects.create_user(username='owner', password='pw-owner-12345')
    disguised = SimpleUploadedFile('evil.html', _png_bytes(), content_type='image/png')

    with pytest.raises(ValidationError):
        PrivateImage.objects.create(owner=owner, image=disguised)


@pytest.mark.django_db
def test_original_filename_is_kept_as_metadata_only(settings, tmp_path, django_user_model):
    settings.MEDIA_ROOT = tmp_path / 'media'
    owner = django_user_model.objects.create_user(username='owner', password='pw-owner-12345')

    image = PrivateImage.objects.create(
        owner=owner,
        image=SimpleUploadedFile('holiday-photo.png', _png_bytes(), content_type='image/png'),
    )

    assert image.original_filename == 'holiday-photo.png'
    assert 'holiday' not in image.image.name
