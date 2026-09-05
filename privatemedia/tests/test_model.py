"""The model-level rules the gate rests on: opaque paths and a size ceiling."""

import io
import uuid

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.forms import modelform_factory

from privatemedia.models import PrivateImage, upload_to_uuid
from privatemedia.validators import MAX_UPLOAD_BYTES, validate_max_size


class _StubFile:
    def __init__(self, size):
        self.size = size


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
def test_original_filename_is_kept_as_metadata_only(settings, tmp_path, django_user_model):
    settings.MEDIA_ROOT = tmp_path / 'media'
    owner = django_user_model.objects.create_user(username='owner', password='pw-owner-12345')
    buffer = io.BytesIO()
    from PIL import Image

    Image.new('RGB', (4, 4), 'blue').save(buffer, format='PNG')

    image = PrivateImage.objects.create(
        owner=owner,
        image=SimpleUploadedFile('holiday-photo.png', buffer.getvalue(), content_type='image/png'),
    )

    assert image.original_filename == 'holiday-photo.png'
    assert 'holiday' not in image.image.name
