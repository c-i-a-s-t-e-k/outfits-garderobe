"""Editing a garment keeps the add rules, except that a new photo is optional."""

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from garments.forms import GarmentEditForm, GarmentForm
from garments.models import GarmentType
from tests.factories import make_garment

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures('temp_media_root')]


def _jpeg_upload():
    buffer = io.BytesIO()
    Image.new('RGB', (64, 48), 'teal').save(buffer, format='JPEG')
    return SimpleUploadedFile('new-shirt.jpg', buffer.getvalue())


def _data(**overrides):
    return {'type': GarmentType.SHIRT, 'type_other': '', 'description': '', **overrides}


def test_edit_without_a_photo_is_valid_and_keeps_none(owner):
    garment = make_garment(owner)

    form = GarmentEditForm(_data(description='washed once'), {}, instance=garment)

    assert form.is_valid(), form.errors
    assert form.cleaned_data['photo'] is None
    assert form.fields['photo'].label == 'Replace photo (optional)'


def test_edit_with_a_photo_normalizes_it_like_add(owner):
    garment = make_garment(owner)

    form = GarmentEditForm(_data(), {'photo': _jpeg_upload()}, instance=garment)

    assert form.is_valid(), form.errors
    assert form.cleaned_data['photo'].name.endswith('.jpg')
    assert form.original_filename == 'new-shirt.jpg'


def test_add_still_requires_a_photo():
    form = GarmentForm(_data(), {})

    assert not form.is_valid()
    assert 'photo' in form.errors
