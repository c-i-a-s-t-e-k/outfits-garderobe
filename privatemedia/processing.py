"""What a stored photo looks like: upright, small, and carrying nothing but pixels."""

import io

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from PIL import Image, ImageOps

# Long edge of every stored photo. Enough to recognise a garment on any screen,
# and small enough that a phone list of tiles stays fast.
MAX_EDGE_PX = 1600
JPEG_QUALITY = 85

# Pillow's own decompression-bomb ceiling (Image.MAX_IMAGE_PIXELS, ~89 MP, with
# a hard error at twice that, ~179 MP) is deliberately left at its default: it
# is what stops a small crafted file from exhausting a worker's memory on decode.


def normalize_photo(upload):
    """Turn an accepted upload into the one JPEG the private store keeps.

    The result is at most MAX_EDGE_PX on its long edge (never upscaled), rotated
    upright, flattened onto white if it had transparency, and stripped of EXIF,
    XMP and comments — GPS coordinates included. An RGB ICC profile survives,
    because iPhone photos are Display P3 and lose their colour without it.

    Raises ValidationError (`invalid_image` or `image_too_many_pixels`) for
    anything that cannot be fully decoded, so a form can show it as a field error.
    The upload's read position is reset afterwards.
    """
    upload.seek(0)
    try:
        with Image.open(upload) as source:
            icc_profile = source.info.get('icc_profile')
            # draft() only works before pixel data is loaded, and exif_transpose()
            # loads it — so this order is the difference between libjpeg decoding
            # a 12 MP photo at 1/4 scale and decoding all of it.
            source.draft('RGB', (MAX_EDGE_PX, MAX_EDGE_PX))
            image = ImageOps.exif_transpose(source)
            image = _flatten_to_rgb(image)
    except Image.DecompressionBombError as exc:
        raise ValidationError(
            'This image has too many pixels to process.',
            code='image_too_many_pixels',
        ) from exc
    except (OSError, SyntaxError, ValueError) as exc:
        # UnidentifiedImageError and "image file is truncated" are both OSError;
        # Pillow's format plugins raise SyntaxError/ValueError on malformed headers.
        raise ValidationError(
            'Upload a valid image. The file is either not an image or is corrupted.',
            code='invalid_image',
        ) from exc
    finally:
        upload.seek(0)

    image.thumbnail((MAX_EDGE_PX, MAX_EDGE_PX), Image.Resampling.LANCZOS)
    # Pillow's JPEG writer falls back to image.info for some metadata (the
    # comment marker, at least), so clear it rather than trust that only the
    # keyword arguments below get written.
    image.info = {}

    output = io.BytesIO()
    image.save(
        output,
        format='JPEG',
        quality=JPEG_QUALITY,
        optimize=True,
        progressive=True,
        icc_profile=_rgb_icc_profile(icc_profile),
    )
    # The .jpg name is what upload_to_uuid keeps as the extension, and the
    # extension is what decides the Content-Type the gate serves.
    return ContentFile(output.getvalue(), name='photo.jpg')


def _flatten_to_rgb(image):
    if image.has_transparency_data:
        rgba = image.convert('RGBA')
        flattened = Image.new('RGB', rgba.size, 'white')
        flattened.paste(rgba, mask=rgba.getchannel('A'))
        return flattened
    if image.mode != 'RGB':
        return image.convert('RGB')
    return image


def _rgb_icc_profile(profile):
    """Keep a profile only if it describes RGB data, which the output always is.

    A CMYK or greyscale profile attached to an RGB JPEG would be wrong, not just
    useless. Bytes 16-20 of an ICC header are its data colour space signature.
    """
    if profile and profile[16:20] == b'RGB ':
        return profile
    return None
