"""Builders for owner-scoped objects, shared by every test that needs one.

Each builder writes a real (tiny) file through `PrivateImage`, so the calling
module must keep uploads out of the real MEDIA_ROOT with
`pytest.mark.usefixtures('temp_media_root')`.
"""

import io

from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from garments.models import Garment, GarmentType
from outfits.models import Outfit
from privatemedia.models import PrivateImage


def _png_bytes():
    buffer = io.BytesIO()
    Image.new('RGB', (4, 4), 'green').save(buffer, format='PNG')
    return buffer.getvalue()


IMAGE_BYTES = _png_bytes()


def make_image(user):
    return PrivateImage.objects.create(
        owner=user,
        image=SimpleUploadedFile('garment.png', IMAGE_BYTES, content_type='image/png'),
    )


def make_garment(user, type=GarmentType.SHIRT, **fields):
    return Garment.objects.create(owner=user, photo=make_image(user), type=type, **fields)


def make_outfit(user, garments=(), **fields):
    outfit = Outfit.objects.create(owner=user, **fields)
    if garments:
        outfit.garments.set(garments)
    return outfit
