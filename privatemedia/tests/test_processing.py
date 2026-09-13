"""The properties of a stored photo that no browser would ever show are wrong."""

import io

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.validators import get_available_image_extensions
from PIL import ExifTags, Image, ImageCms

from privatemedia.models import PrivateImage
from privatemedia.processing import MAX_EDGE_PX, normalize_photo

ORIENTATION = ExifTags.Base.Orientation

pytestmark = pytest.mark.usefixtures('temp_media_root')


def _upload(image, format='JPEG', name=None, **save_kwargs):
    buffer = io.BytesIO()
    image.save(buffer, format=format, **save_kwargs)
    extension = {'JPEG': 'jpg', 'PNG': 'png', 'HEIF': 'heic'}[format]
    return SimpleUploadedFile(name or f'photo.{extension}', buffer.getvalue())


def _open(content_file):
    content_file.seek(0)
    return Image.open(io.BytesIO(content_file.read()))


@pytest.mark.parametrize(
    ('size', 'expected'),
    [
        ((2400, 1800), (1600, 1200)),
        ((1200, 3000), (640, 1600)),
    ],
    ids=['landscape', 'portrait'],
)
def test_large_input_is_shrunk_to_the_long_edge_limit(size, expected):
    result = _open(normalize_photo(_upload(Image.new('RGB', size, 'navy'))))

    assert result.format == 'JPEG'
    assert result.size == expected
    assert max(result.size) == MAX_EDGE_PX


def test_small_input_is_not_upscaled():
    result = _open(normalize_photo(_upload(Image.new('RGB', (800, 600), 'navy'))))

    assert result.size == (800, 600)


def test_exif_orientation_is_applied_and_then_dropped():
    exif = Image.Exif()
    exif[ORIENTATION] = 6  # "rotate 90° clockwise to display"

    result = _open(normalize_photo(_upload(Image.new('RGB', (400, 200)), exif=exif)))

    assert result.size == (200, 400)
    assert ORIENTATION not in result.getexif()


def test_gps_coordinates_do_not_survive():
    exif = Image.Exif()
    gps = exif.get_ifd(ExifTags.IFD.GPSInfo)
    gps[ExifTags.GPS.GPSLatitudeRef] = 'N'
    gps[ExifTags.GPS.GPSLatitude] = (52.0, 13.0, 30.0)
    upload = _upload(Image.new('RGB', (400, 300)), exif=exif)
    assert _open(upload).getexif().get_ifd(ExifTags.IFD.GPSInfo), 'fixture must carry GPS'

    result = _open(normalize_photo(upload))

    assert 'exif' not in result.info
    assert len(result.getexif()) == 0


def test_rgb_icc_profile_is_preserved():
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()

    result = _open(normalize_photo(_upload(Image.new('RGB', (400, 300)), icc_profile=profile)))

    assert result.info.get('icc_profile') == profile


def test_transparent_png_becomes_an_rgb_jpeg_on_white():
    image = Image.new('RGBA', (40, 40), (0, 0, 0, 0))

    result = _open(normalize_photo(_upload(image, format='PNG')))

    assert result.format == 'JPEG'
    assert result.mode == 'RGB'
    assert all(channel > 250 for channel in result.getpixel((20, 20)))


def test_heic_input_comes_out_as_jpeg():
    result = _open(normalize_photo(_upload(Image.new('RGB', (400, 300), 'navy'), format='HEIF')))

    assert result.format == 'JPEG'
    assert result.size == (400, 300)


def test_oriented_heic_is_upright_and_not_rotated_twice():
    """libheif applies the container rotation on decode; exif_transpose must not repeat it."""
    exif = Image.Exif()
    exif[ORIENTATION] = 6
    # Raw bytes, not the Exif object: only from bytes does pillow-heif turn the
    # tag into the container's rotation, the way a camera writes a HEIC. Given
    # the object, it writes an unrotated file whose tag it then ignores on read.
    upload = _upload(Image.new('RGB', (400, 200)), format='HEIF', exif=exif.tobytes())

    result = _open(normalize_photo(upload))

    assert result.size == (200, 400)
    assert ORIENTATION not in result.getexif()


def test_random_bytes_are_an_invalid_image():
    with pytest.raises(ValidationError) as excinfo:
        normalize_photo(SimpleUploadedFile('photo.jpg', b'definitely not an image' * 50))

    assert excinfo.value.code == 'invalid_image'


def test_truncated_jpeg_is_an_invalid_image():
    buffer = io.BytesIO()
    Image.effect_noise((800, 600), 64).convert('RGB').save(buffer, format='JPEG')
    truncated = buffer.getvalue()[: len(buffer.getvalue()) // 2]

    with pytest.raises(ValidationError) as excinfo:
        normalize_photo(SimpleUploadedFile('photo.jpg', truncated))

    assert excinfo.value.code == 'invalid_image'


def test_corrupt_heic_is_an_invalid_image():
    """libheif reports a broken bitstream as EOFError, not the OSError Pillow uses."""
    buffer = io.BytesIO()
    Image.new('RGB', (400, 300), 'navy').save(buffer, format='HEIF')
    data = bytearray(buffer.getvalue())
    # The first mdat payload bytes are an HEVC NAL unit length; flipping them
    # makes the decoder read past the end of the data.
    data[data.find(b'mdat') + 4] ^= 0xFF

    with pytest.raises(ValidationError) as excinfo:
        normalize_photo(SimpleUploadedFile('photo.heic', bytes(data)))

    assert excinfo.value.code == 'invalid_image'


@pytest.mark.parametrize('format', ['EPS', 'TIFF'])
def test_formats_outside_the_allowlist_are_an_invalid_image(format):
    buffer = io.BytesIO()
    Image.new('RGB', (40, 40), 'navy').save(buffer, format=format)

    with pytest.raises(ValidationError) as excinfo:
        normalize_photo(SimpleUploadedFile(f'photo.{format.lower()}', buffer.getvalue()))

    assert excinfo.value.code == 'invalid_image'


def test_image_above_the_pixel_ceiling_is_refused(monkeypatch):
    upload = _upload(Image.new('RGB', (40, 40)))
    # Pillow raises (rather than warns) above twice MAX_IMAGE_PIXELS.
    monkeypatch.setattr(Image, 'MAX_IMAGE_PIXELS', 100)

    with pytest.raises(ValidationError) as excinfo:
        normalize_photo(upload)

    assert excinfo.value.code == 'image_too_many_pixels'


def test_input_read_position_is_reset():
    upload = _upload(Image.new('RGB', (400, 300)))

    normalize_photo(upload)

    assert upload.tell() == 0


@pytest.mark.django_db
def test_output_is_accepted_by_private_image(django_user_model):
    owner = django_user_model.objects.create_user(username='owner', password='pw-owner-12345')
    upload = _upload(Image.new('RGB', (2400, 1800)), format='HEIF', name='IMG_0001.HEIC')

    image = PrivateImage.objects.create(
        owner=owner,
        image=normalize_photo(upload),
        original_filename=upload.name,
    )

    assert image.image.name.endswith('.jpg')
    assert image.original_filename == 'IMG_0001.HEIC'
    with Image.open(image.image.path) as stored:
        assert stored.format == 'JPEG'
        assert max(stored.size) == MAX_EDGE_PX


def test_heic_is_a_recognised_image_extension():
    assert 'heic' in get_available_image_extensions()
