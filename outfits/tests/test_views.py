"""Compose and detail never cross users, and a failed compose stores nothing.

Every assertion re-reads the database rather than trusting a status code.
"""

import io
import re
import uuid
from datetime import timedelta
from html import unescape
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from django.conf import settings
from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.templatetags.static import static
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from PIL import ExifTags, Image

from garments.models import Garment, GarmentType
from outfits.forms import OutfitEditForm, OutfitForm
from outfits.models import MissingGarment, Outfit, Tag
from privatemedia.models import PrivateImage
from privatemedia.processing import MAX_EDGE_PX
from privatemedia.validators import MAX_UPLOAD_BYTES
from tests.factories import make_garment, make_image, make_outfit

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures('temp_media_root')]

COMPOSE_URL = reverse('outfits:compose')
WARDROBE_URL = reverse('wardrobe')


def _detail_url(pk):
    return reverse('outfits:detail', args=[pk])


def _compose(client, garments, name=''):
    return client.post(COMPOSE_URL, {'name': name, 'garments': [g.pk for g in garments]})


def _checkbox(page, garment):
    return re.search(rf'<input[^>]*value="{garment.pk}"[^>]*>', page).group(0)


@pytest.fixture
def wardrobe(owner):
    return [
        make_garment(owner, type=GarmentType.SHIRT),
        make_garment(owner, type=GarmentType.SHOES),
    ]


# --- anonymous ---------------------------------------------------------------


@pytest.mark.parametrize('url', [COMPOSE_URL, _detail_url(uuid.uuid4())])
def test_anonymous_get_is_sent_to_login(client, url):
    response = client.get(url)

    assert response.status_code == 302
    assert response.headers['Location'].startswith(settings.LOGIN_URL)


def test_anonymous_post_is_sent_to_login_and_stores_nothing(client, owner, wardrobe):
    response = _compose(client, wardrobe)

    assert response.status_code == 302
    assert response.headers['Location'].startswith(settings.LOGIN_URL)
    assert not Outfit.objects.exists()


# --- the picker --------------------------------------------------------------


def test_picker_lists_own_garments_and_nothing_of_anyone_else(client, owner, stranger, wardrobe):
    foreign = make_garment(stranger, description='borrowed coat')
    client.force_login(owner)

    page = client.get(COMPOSE_URL).content.decode()

    for garment in wardrobe:
        assert garment.photo_url in page
        assert _checkbox(page, garment)
    assert foreign.photo_url not in page
    assert foreign.description not in page
    assert str(foreign.pk) not in page


def test_a_user_with_one_garment_is_sent_to_add_garments_instead(client, owner):
    make_garment(owner)
    client.force_login(owner)

    page = client.get(COMPOSE_URL).content.decode()

    assert 'Add at least 2 garments' in page
    assert reverse('garments:add') in page
    assert 'outfit-picker' not in page
    assert 'outfit-compose' not in page
    assert 'Save outfit' not in page


def test_picker_query_count_does_not_grow_with_garments(client, owner, wardrobe):
    client.force_login(owner)
    with CaptureQueriesContext(connection) as two:
        client.get(COMPOSE_URL)

    for _ in range(6):
        make_garment(owner)
    with CaptureQueriesContext(connection) as eight:
        client.get(COMPOSE_URL)

    assert len(eight.captured_queries) == len(two.captured_queries)


# --- composing ---------------------------------------------------------------


def test_valid_compose_stores_the_outfit_and_lands_on_its_page(client, owner, wardrobe):
    client.force_login(owner)

    response = _compose(client, wardrobe, name='Office')

    assert response.status_code == 302
    outfit = Outfit.objects.get()
    assert response.headers['Location'] == outfit.get_absolute_url()
    assert outfit.owner == owner
    assert outfit.name == 'Office'
    assert set(outfit.garments.all()) == set(wardrobe)
    followed = client.get(response.headers['Location']).content.decode()
    assert 'Outfit saved.' in followed
    assert 'No photo yet.' in followed


def test_blank_names_become_outfit_1_then_outfit_2(client, owner, wardrobe):
    client.force_login(owner)

    _compose(client, wardrobe)
    _compose(client, wardrobe)

    assert sorted(Outfit.objects.values_list('name', flat=True)) == ['outfit-1', 'outfit-2']


def test_a_case_variant_of_a_taken_name_is_a_field_error(client, owner, wardrobe):
    Outfit.objects.create(owner=owner, name='Summer wedding')
    client.force_login(owner)

    response = _compose(client, wardrobe, name='summer WEDDING')

    assert response.status_code == 200
    assert 'name' in response.context['form'].errors
    assert Outfit.objects.count() == 1


@pytest.mark.parametrize('count', [0, 1])
def test_fewer_than_two_garments_is_refused(client, owner, wardrobe, count):
    client.force_login(owner)

    response = _compose(client, wardrobe[:count])

    assert response.status_code == 200
    assert 'Choose at least 2 garments.' in ' '.join(response.context['form'].errors['garments'])
    assert not Outfit.objects.exists()


def test_another_users_garment_id_is_refused_and_stores_nothing(client, owner, stranger, wardrobe):
    foreign = make_garment(stranger)
    client.force_login(owner)

    response = _compose(client, [wardrobe[0], foreign])

    assert response.status_code == 200
    assert 'garments' in response.context['form'].errors
    assert not Outfit.objects.exists()
    assert foreign.outfits.count() == 0


def test_invalid_post_keeps_the_typed_name_and_the_ticked_garments(client, owner, wardrobe):
    third = make_garment(owner, type=GarmentType.TROUSERS)
    client.force_login(owner)

    page = _compose(client, [wardrobe[0], third], name='Office' * 20).content.decode()

    assert 'value="' + 'Office' * 20 + '"' in page
    assert 'checked' in _checkbox(page, wardrobe[0])
    assert 'checked' in _checkbox(page, third)
    assert 'checked' not in _checkbox(page, wardrobe[1])
    assert not Outfit.objects.exists()


def test_a_garment_can_be_in_two_outfits(client, owner, wardrobe):
    third = make_garment(owner, type=GarmentType.TROUSERS)
    client.force_login(owner)

    _compose(client, wardrobe, name='First')
    _compose(client, [wardrobe[0], third], name='Second')

    assert wardrobe[0].outfits.count() == 2
    assert Outfit.objects.count() == 2


def test_a_lost_default_name_race_is_retried_once(client, owner, wardrobe, monkeypatch):
    Outfit.objects.create(owner=owner, name='outfit-1')
    real = Outfit.default_name_for
    calls = []

    def taken_once(owner_id):
        calls.append(owner_id)
        return 'outfit-1' if len(calls) == 1 else real(owner_id)

    monkeypatch.setattr(Outfit, 'default_name_for', staticmethod(taken_once))
    client.force_login(owner)

    response = _compose(client, wardrobe)

    assert response.status_code == 302
    assert len(calls) == 2
    assert sorted(Outfit.objects.values_list('name', flat=True)) == ['outfit-1', 'outfit-2']


def test_a_typed_name_that_loses_the_race_is_reported_not_stored(
    client, owner, wardrobe, monkeypatch
):
    """The form's check ran before the other row existed; the model's check catches it."""
    Outfit.objects.create(owner=owner, name='Office')
    monkeypatch.setattr(OutfitForm, 'clean_name', lambda self: self.cleaned_data['name'])
    client.force_login(owner)

    response = _compose(client, wardrobe, name='office')

    assert response.status_code == 200
    assert 'name' in response.context['form'].errors
    assert Outfit.objects.count() == 1


# --- detail ------------------------------------------------------------------


def test_get_absolute_url_is_the_detail_route(owner):
    outfit = Outfit.objects.create(owner=owner)

    assert outfit.get_absolute_url() == f'/wardrobe/{outfit.pk}/'


def test_detail_shows_every_garment_to_its_owner_only(client, owner, stranger):
    outfit = Outfit.objects.create(owner=owner, name='Big night')
    garments = [make_garment(owner, type=type) for type in GarmentType if type != 'other']
    assert len(garments) > 4
    outfit.garments.set(garments)

    client.force_login(owner)
    response = client.get(outfit.get_absolute_url())
    page = response.content.decode()
    assert response.status_code == 200
    assert 'Big night' in page
    for garment in garments:
        assert garment.photo_url in page

    client.force_login(stranger)
    assert client.get(outfit.get_absolute_url()).status_code == 404
    assert client.get(_detail_url(uuid.uuid4())).status_code == 404


# --- the wardrobe grid -------------------------------------------------------


def _tile(page, outfit):
    """The <li> that links to this outfit, or None."""
    match = re.search(
        rf'<li>\s*<a href="{outfit.get_absolute_url()}".*?</li>', page, flags=re.DOTALL
    )
    return match.group(0) if match else None


def _image_urls(fragment):
    return re.findall(r'<img src="([^"]+)"', fragment)


def test_grid_lists_own_outfits_newest_first_and_nothing_of_anyone_else(
    client, owner, stranger, wardrobe
):
    older = Outfit.objects.create(owner=owner, name='Older look')
    older.garments.set(wardrobe)
    newer = Outfit.objects.create(owner=owner, name='Newer look')
    newer.garments.set(wardrobe)
    # Two inserts can share a timestamp on a coarse clock; pin the order.
    Outfit.objects.filter(pk=older.pk).update(created_at=newer.created_at - timedelta(minutes=1))

    client.force_login(owner)
    page = client.get(WARDROBE_URL).content.decode()
    assert page.index('Newer look') < page.index('Older look')
    for outfit in (older, newer):
        assert _tile(page, outfit)

    client.force_login(stranger)
    page = client.get(WARDROBE_URL).content.decode()
    for outfit in (older, newer):
        assert outfit.name not in page
        assert outfit.get_absolute_url() not in page
    for garment in wardrobe:
        assert garment.photo_url not in page


def test_tile_shows_four_photos_in_type_order_and_counts_the_rest(client, owner):
    outfit = Outfit.objects.create(owner=owner, name='Everything')
    by_type = {
        type: make_garment(owner, type=type)
        for type in [
            GarmentType.SHOES,
            GarmentType.ACCESSORY,
            GarmentType.TROUSERS,
            GarmentType.TSHIRT,
            GarmentType.OUTERWEAR,
            GarmentType.SKIRT,
            GarmentType.SHIRT,
        ]
    }
    outfit.garments.set(by_type.values())
    client.force_login(owner)

    tile = _tile(client.get(WARDROBE_URL).content.decode(), outfit)

    assert _image_urls(tile) == [
        by_type[type].photo_url
        for type in [
            GarmentType.OUTERWEAR,
            GarmentType.SHIRT,
            GarmentType.TSHIRT,
            GarmentType.TROUSERS,
        ]
    ]
    assert '+3' in tile
    assert 'outfit-preview-4' in tile


def test_tile_of_two_garments_shows_both_and_no_badge(client, owner, wardrobe):
    outfit = Outfit.objects.create(owner=owner, name='Pair')
    outfit.garments.set(wardrobe)
    client.force_login(owner)

    tile = _tile(client.get(WARDROBE_URL).content.decode(), outfit)

    assert sorted(_image_urls(tile)) == sorted(g.photo_url for g in wardrobe)
    assert 'outfit-preview-more' not in tile
    assert 'outfit-preview-2' in tile


def test_tile_links_to_the_detail_page(client, owner, wardrobe):
    outfit = Outfit.objects.create(owner=owner, name='Pair')
    outfit.garments.set(wardrobe)
    client.force_login(owner)

    page = client.get(WARDROBE_URL).content.decode()

    assert f'<a href="{_detail_url(outfit.pk)}"' in page
    assert client.get(_detail_url(outfit.pk)).status_code == 200


def test_empty_wardrobe_with_two_garments_offers_compose(client, owner, wardrobe):
    client.force_login(owner)

    page = client.get(WARDROBE_URL).content.decode()

    assert 'No outfits yet' in page
    assert COMPOSE_URL in page
    assert 'outfit-grid' not in page


def test_empty_wardrobe_with_one_garment_sends_to_add_garments(client, owner):
    make_garment(owner)
    client.force_login(owner)

    page = client.get(WARDROBE_URL).content.decode()

    assert 'Add at least 2 garments' in page
    assert reverse('garments:add') in page
    assert COMPOSE_URL not in page


def test_grid_query_count_does_not_grow_with_outfits_or_garments(client, owner, wardrobe):
    outfit = Outfit.objects.create(owner=owner)
    outfit.garments.set(wardrobe)
    client.force_login(owner)
    with CaptureQueriesContext(connection) as one:
        client.get(WARDROBE_URL)

    extra = [make_garment(owner, type=type) for type in [GarmentType.TROUSERS] * 5]
    for _ in range(4):
        big = Outfit.objects.create(owner=owner)
        big.garments.set(wardrobe + extra)
    with CaptureQueriesContext(connection) as five:
        client.get(WARDROBE_URL)

    assert len(five.captured_queries) == len(one.captured_queries)


# --- tagging -----------------------------------------------------------------


def _tags_add_url(outfit):
    return reverse('outfits:tags_add', args=[outfit.pk])


def _tag_remove_url(outfit, tag):
    return reverse('outfits:tag_remove', args=[outfit.pk, tag.pk])


def _outfit_with(user, garments, name, tags=()):
    outfit = Outfit.objects.create(owner=user, name=name)
    outfit.garments.set(garments)
    outfit.tags.set(Tag.resolve(user, list(tags)))
    return outfit


def _tag_names(outfit):
    return sorted(Outfit.objects.get(pk=outfit.pk).tags.values_list('name', flat=True))


@pytest.fixture
def foreign_wardrobe(stranger):
    return [make_garment(stranger), make_garment(stranger, type=GarmentType.SHOES)]


def test_compose_stores_the_typed_tags_with_the_outfit(client, owner, wardrobe):
    client.force_login(owner)

    response = client.post(
        COMPOSE_URL,
        {'garments': [g.pk for g in wardrobe], 'tag_names': 'Letnie, , smart casual, letnie'},
    )

    assert response.status_code == 302
    outfit = Outfit.objects.get()
    assert _tag_names(outfit) == ['Letnie', 'smart casual']
    assert set(Tag.objects.values_list('owner', flat=True)) == {owner.pk}


def test_compose_reuses_an_existing_tag_and_keeps_its_spelling(client, owner, wardrobe):
    existing = _outfit_with(owner, wardrobe, 'Old', tags=['LETNIE']).tags.get()
    client.force_login(owner)

    client.post(COMPOSE_URL, {'garments': [g.pk for g in wardrobe], 'tag_names': 'letnie'})

    new = Outfit.objects.exclude(name='Old').get()
    assert list(new.tags.values_list('pk', 'name')) == [(existing.pk, 'LETNIE')]
    assert Tag.objects.count() == 1


def test_compose_never_attaches_another_users_same_named_tag(
    client, owner, stranger, wardrobe, foreign_wardrobe
):
    foreign_outfit = _outfit_with(stranger, foreign_wardrobe, 'Theirs', tags=['letnie'])
    foreign = foreign_outfit.tags.get()
    client.force_login(owner)

    client.post(COMPOSE_URL, {'garments': [g.pk for g in wardrobe], 'tag_names': 'letnie'})

    own = Outfit.objects.get(owner=owner).tags.get()
    assert own.pk != foreign.pk
    assert own.owner == owner
    assert list(foreign.outfits.all()) == [foreign_outfit]


def test_a_failed_compose_stores_no_outfit_and_no_tag_and_keeps_the_text(client, owner, wardrobe):
    client.force_login(owner)

    response = client.post(COMPOSE_URL, {'garments': [wardrobe[0].pk], 'tag_names': 'Nowy'})

    assert response.status_code == 200
    assert not Outfit.objects.exists()
    assert not Tag.objects.exists()
    assert 'value="Nowy"' in response.content.decode()


@pytest.mark.parametrize(
    'tag_names',
    [', '.join(f'tag{n}' for n in range(21)), 'x' * 31],
    ids=['21 tags', '31 characters'],
)
def test_compose_over_the_tag_limits_is_a_field_error(client, owner, wardrobe, tag_names):
    client.force_login(owner)

    response = client.post(
        COMPOSE_URL, {'garments': [g.pk for g in wardrobe], 'tag_names': tag_names}
    )

    assert response.status_code == 200
    assert 'tag_names' in response.context['form'].errors
    assert not Outfit.objects.exists()
    assert not Tag.objects.exists()


def test_detail_lists_tags_with_remove_forms_and_suggests_only_own_other_tags(
    client, owner, stranger, wardrobe, foreign_wardrobe
):
    outfit = _outfit_with(owner, wardrobe, 'Tagged', tags=['Letnie', 'smart casual'])
    other = _outfit_with(owner, wardrobe, 'Other', tags=['zimowe', 'letnie'])
    _outfit_with(stranger, foreign_wardrobe, 'Theirs', tags=['obce'])
    client.force_login(owner)

    page = client.get(outfit.get_absolute_url()).content.decode()

    for tag in outfit.tags.all():
        assert f'action="{_tag_remove_url(outfit, tag)}"' in page
        assert f'aria-label="Remove tag {tag.name}"' in page
    assert f'{WARDROBE_URL}?tag=smart%20casual' in page
    datalist = re.search(r'<datalist id="tag-suggestions">(.*?)</datalist>', page, re.DOTALL)
    assert re.findall(r'value="([^"]+)"', datalist.group(1)) == ['zimowe']
    assert 'obce' not in page
    assert other.tags.count() == 2


def test_detail_without_tags_says_so(client, owner, wardrobe):
    outfit = _outfit_with(owner, wardrobe, 'Bare')
    client.force_login(owner)

    page = client.get(outfit.get_absolute_url()).content.decode()

    assert 'No tags yet.' in page
    assert 'tag-list' not in page


def test_add_attaches_new_and_existing_tags_and_returns_to_the_outfit(client, owner, wardrobe):
    outfit = _outfit_with(owner, wardrobe, 'Target')
    existing = _outfit_with(owner, wardrobe, 'Other', tags=['letnie']).tags.get()
    client.force_login(owner)

    response = client.post(_tags_add_url(outfit), {'tag_names': 'Nowy, letnie'})

    assert response.status_code == 302
    assert response.headers['Location'] == outfit.get_absolute_url()
    assert _tag_names(outfit) == ['Nowy', 'letnie']
    assert Outfit.objects.get(pk=outfit.pk).tags.filter(pk=existing.pk).exists()
    assert Tag.objects.count() == 2
    assert 'Tags added.' in client.get(response.headers['Location']).content.decode()


def test_add_past_twenty_tags_is_refused_and_attaches_nothing(client, owner, wardrobe):
    outfit = _outfit_with(owner, wardrobe, 'Full', tags=[f'tag{n}' for n in range(19)])
    client.force_login(owner)

    response = client.post(_tags_add_url(outfit), {'tag_names': 'tag0, new1, new2'})

    assert response.status_code == 200
    assert 'at most 20 tags' in response.content.decode()
    assert len(_tag_names(outfit)) == 19
    assert not Tag.objects.filter(name__startswith='new').exists()


def test_add_to_another_users_outfit_is_404_and_changes_nothing(
    client, owner, stranger, foreign_wardrobe
):
    foreign = _outfit_with(stranger, foreign_wardrobe, 'Theirs', tags=['letnie'])
    client.force_login(owner)

    response = client.post(_tags_add_url(foreign), {'tag_names': 'Nowy'})

    assert response.status_code == 404
    assert _tag_names(foreign) == ['letnie']
    assert Tag.objects.count() == 1


def test_remove_detaches_the_tag_and_deletes_it_when_unused(client, owner, wardrobe):
    outfit = _outfit_with(owner, wardrobe, 'Target', tags=['letnie', 'zimowe'])
    tag = outfit.tags.get(name='letnie')
    client.force_login(owner)

    response = client.post(_tag_remove_url(outfit, tag))

    assert response.status_code == 302
    assert response.headers['Location'] == outfit.get_absolute_url()
    assert _tag_names(outfit) == ['zimowe']
    assert not Tag.objects.filter(pk=tag.pk).exists()
    assert 'Tag removed.' in client.get(response.headers['Location']).content.decode()


def test_remove_on_another_users_outfit_is_404(client, owner, stranger, foreign_wardrobe):
    foreign = _outfit_with(stranger, foreign_wardrobe, 'Theirs', tags=['letnie'])
    client.force_login(owner)

    response = client.post(_tag_remove_url(foreign, foreign.tags.get()))

    assert response.status_code == 404
    assert _tag_names(foreign) == ['letnie']


def test_remove_of_another_users_tag_from_an_own_outfit_is_404(
    client, owner, stranger, wardrobe, foreign_wardrobe
):
    outfit = _outfit_with(owner, wardrobe, 'Mine', tags=['letnie'])
    foreign = _outfit_with(stranger, foreign_wardrobe, 'Theirs', tags=['letnie'])
    client.force_login(owner)

    response = client.post(_tag_remove_url(outfit, foreign.tags.get()))

    assert response.status_code == 404
    assert _tag_names(foreign) == ['letnie']
    assert _tag_names(outfit) == ['letnie']


def test_remove_of_an_own_tag_the_outfit_does_not_carry_is_404(client, owner, wardrobe):
    outfit = _outfit_with(owner, wardrobe, 'Mine', tags=['letnie'])
    other = _outfit_with(owner, wardrobe, 'Other', tags=['zimowe'])
    client.force_login(owner)

    response = client.post(_tag_remove_url(outfit, other.tags.get()))

    assert response.status_code == 404
    assert _tag_names(outfit) == ['letnie']
    assert _tag_names(other) == ['zimowe']


@pytest.mark.parametrize('action', ['add', 'remove'])
def test_tag_actions_refuse_get_and_send_anonymous_posts_to_login(client, owner, wardrobe, action):
    outfit = _outfit_with(owner, wardrobe, 'Mine', tags=['letnie'])
    tag = outfit.tags.get()
    url = _tags_add_url(outfit) if action == 'add' else _tag_remove_url(outfit, tag)

    response = client.post(url, {'tag_names': 'Nowy'})
    assert response.status_code == 302
    assert response.headers['Location'].startswith(settings.LOGIN_URL)
    assert _tag_names(outfit) == ['letnie']

    client.force_login(owner)
    assert client.get(url).status_code == 405
    assert _tag_names(outfit) == ['letnie']


def test_detail_query_count_does_not_grow_with_tags(client, owner, wardrobe):
    one = _outfit_with(owner, wardrobe, 'One', tags=['a'])
    eight = _outfit_with(owner, wardrobe, 'Eight', tags=[f't{n}' for n in range(8)])
    client.force_login(owner)
    with CaptureQueriesContext(connection) as few:
        client.get(one.get_absolute_url())
    with CaptureQueriesContext(connection) as many:
        client.get(eight.get_absolute_url())

    assert len(many.captured_queries) == len(few.captured_queries)


# --- the outfit photo ----------------------------------------------------------


def _photo_upload_url(outfit):
    return reverse('outfits:photo_upload', args=[outfit.pk])


def _photo_remove_url(outfit):
    return reverse('outfits:photo_remove', args=[outfit.pk])


def _jpeg_upload(size=(1200, 1800), name='me-in-it.jpg', exif=None):
    buffer = io.BytesIO()
    extra = {'exif': exif} if exif is not None else {}
    Image.new('RGB', size, 'navy').save(buffer, format='JPEG', **extra)
    return SimpleUploadedFile(name, buffer.getvalue())


def _stored_files(media_root):
    return {path for path in Path(media_root).rglob('*') if path.is_file()}


def _file_of(image):
    return Path(image.image.path)


def _reread(outfit):
    return Outfit.objects.get(pk=outfit.pk)


@pytest.fixture
def photographed(owner, wardrobe):
    """The owner's outfit of both wardrobe garments, with a photo of the owner in it."""
    return make_outfit(owner, garments=wardrobe, photo=True, name='Photographed')


def _assert_garment_photos_intact(garments):
    for garment in garments:
        assert PrivateImage.objects.filter(pk=garment.photo_id).exists()
        assert _file_of(garment.photo).is_file()


def test_detail_without_a_photo_offers_an_upload_form(client, owner, wardrobe):
    outfit = make_outfit(owner, garments=wardrobe, name='Bare')
    client.force_login(owner)

    page = client.get(outfit.get_absolute_url()).content.decode()

    assert 'No photo yet.' in page
    form = re.search(
        rf'<form[^>]*action="{_photo_upload_url(outfit)}"[^>]*>.*?</form>', page, re.DOTALL
    ).group(0)
    assert 'enctype="multipart/form-data"' in form
    assert 'data-submit-once' in form
    assert 'Upload photo' in form
    assert 'data-shrink-status' in form
    photo_input = re.search(r'<input[^>]*name="photo"[^>]*>', form).group(0)
    assert 'data-shrink-photo' in photo_input
    assert 'accept="image/*"' in photo_input
    assert f'<script src="{static("js/photo-shrink.js")}" defer>' in page
    assert _photo_remove_url(outfit) not in page


def test_detail_with_a_photo_shows_it_with_replace_and_remove(client, owner, photographed):
    client.force_login(owner)

    page = client.get(photographed.get_absolute_url()).content.decode()

    assert f'<img src="{photographed.photo_url}"' in page
    assert 'Replace photo' in page
    assert f'href="{_photo_remove_url(photographed)}"' in page
    assert 'No photo yet.' not in page
    assert 'Upload photo' not in page


def test_upload_stores_a_normalized_photo_for_the_outfit_and_its_owner(
    client, owner, wardrobe, temp_media_root
):
    outfit = make_outfit(owner, garments=wardrobe, name='Bare')
    client.force_login(owner)

    response = client.post(_photo_upload_url(outfit), {'photo': _jpeg_upload()})

    assert response.status_code == 302
    assert response.headers['Location'] == outfit.get_absolute_url()
    photo = _reread(outfit).photo
    assert photo is not None
    assert photo.owner == owner
    assert photo.original_filename == 'me-in-it.jpg'
    with Image.open(_file_of(photo)) as stored:
        assert stored.format == 'JPEG'
        assert max(stored.size) <= MAX_EDGE_PX
        assert stored.height > stored.width
    assert _stored_files(temp_media_root) - {_file_of(g.photo) for g in wardrobe} == {
        _file_of(photo)
    }
    assert 'Photo added.' in client.get(response.headers['Location']).content.decode()


def test_upload_stores_an_exif_rotated_photo_upright(client, owner, wardrobe):
    outfit = make_outfit(owner, garments=wardrobe, name='Bare')
    exif = Image.Exif()
    exif[ExifTags.Base.Orientation] = 6  # "rotate 90° clockwise to display"
    client.force_login(owner)

    client.post(_photo_upload_url(outfit), {'photo': _jpeg_upload(size=(400, 200), exif=exif)})

    with Image.open(_file_of(_reread(outfit).photo)) as stored:
        assert stored.size == (200, 400)
        assert ExifTags.Base.Orientation not in stored.getexif()


def test_replace_links_the_new_photo_and_deletes_the_old_one_after_commit(
    client, owner, wardrobe, photographed, django_capture_on_commit_callbacks
):
    old = photographed.photo
    old_file = _file_of(old)
    assert old_file.is_file()
    client.force_login(owner)

    with django_capture_on_commit_callbacks() as callbacks:
        response = client.post(_photo_upload_url(photographed), {'photo': _jpeg_upload()})
        # Until the change commits, the old bytes are still needed.
        assert old_file.is_file()
    for callback in callbacks:
        callback()

    assert response.status_code == 302
    new = _reread(photographed).photo
    assert new.pk != old.pk
    assert new.owner == owner
    assert _file_of(new).is_file()
    assert not PrivateImage.objects.filter(pk=old.pk).exists()
    assert not old_file.exists()
    assert PrivateImage.objects.filter(outfit__pk=photographed.pk).count() == 1
    assert PrivateImage.objects.count() == len(wardrobe) + 1
    _assert_garment_photos_intact(wardrobe)
    assert 'Photo replaced.' in client.get(response.headers['Location']).content.decode()


def _corrupt_upload():
    return SimpleUploadedFile('broken.jpg', b'not an image' * 100)


def _oversized_upload():
    # An uncompressed BMP of ~11 MB: a real image, over the upload ceiling but
    # under the request limit, so it is the field's size check that refuses it.
    buffer = io.BytesIO()
    Image.new('RGB', (2000, 2000), 'navy').save(buffer, format='BMP')
    upload = SimpleUploadedFile('huge.bmp', buffer.getvalue())
    assert upload.size > MAX_UPLOAD_BYTES
    return upload


@pytest.mark.parametrize(
    ('make_upload', 'message'),
    [(_corrupt_upload, 'Upload a valid image'), (_oversized_upload, 'too large')],
    ids=['corrupt', '11 MB'],
)
def test_a_refused_upload_is_a_field_error_and_stores_nothing(
    client, owner, photographed, temp_media_root, make_upload, message
):
    upload = make_upload()
    files_before = _stored_files(temp_media_root)
    images_before = PrivateImage.objects.count()
    client.force_login(owner)

    response = client.post(_photo_upload_url(photographed), {'photo': upload})

    assert response.status_code == 200
    assert message in ' '.join(response.context['photo_form'].errors['photo'])
    assert message in response.content.decode()
    assert _reread(photographed).photo_id == photographed.photo_id
    assert PrivateImage.objects.count() == images_before
    assert _stored_files(temp_media_root) == files_before


def test_a_replace_that_fails_keeps_the_old_photo_and_stores_no_new_file(
    client, owner, photographed, temp_media_root, monkeypatch, django_capture_on_commit_callbacks
):
    old_file = _file_of(photographed.photo)
    files_before = _stored_files(temp_media_root)
    images_before = PrivateImage.objects.count()

    def fail(*args, **kwargs):
        raise RuntimeError('database went away')

    monkeypatch.setattr(Outfit, 'save', fail)
    client.force_login(owner)
    client.raise_request_exception = True

    with django_capture_on_commit_callbacks(execute=True), pytest.raises(RuntimeError):
        client.post(_photo_upload_url(photographed), {'photo': _jpeg_upload()})

    assert _reread(photographed).photo_id == photographed.photo_id
    assert old_file.is_file()
    assert PrivateImage.objects.count() == images_before
    assert _stored_files(temp_media_root) == files_before


def test_upload_to_another_users_outfit_is_404_and_stores_nothing(
    client, owner, stranger, photographed, temp_media_root
):
    make_garment(stranger)
    files_before = _stored_files(temp_media_root)
    images_before = PrivateImage.objects.count()
    client.force_login(stranger)

    response = client.post(_photo_upload_url(photographed), {'photo': _jpeg_upload()})

    assert response.status_code == 404
    assert _reread(photographed).photo_id == photographed.photo_id
    assert PrivateImage.objects.count() == images_before
    assert _stored_files(temp_media_root) == files_before


def test_upload_refuses_get(client, owner, photographed):
    client.force_login(owner)

    assert client.get(_photo_upload_url(photographed)).status_code == 405


def test_remove_page_shows_the_photo_and_a_confirm_form(client, owner, photographed):
    client.force_login(owner)

    response = client.get(_photo_remove_url(photographed))
    page = response.content.decode()

    assert response.status_code == 200
    assert f'<img src="{photographed.photo_url}"' in page
    assert 'The photo is deleted permanently. The outfit and its garments stay.' in page
    assert re.search(r'<form method="post">.*?Remove photo</button>', page, re.DOTALL)
    assert f'<a href="{photographed.get_absolute_url()}">Cancel</a>' in page
    assert _reread(photographed).photo_id == photographed.photo_id


def test_confirming_remove_unlinks_the_photo_and_deletes_it_after_commit(
    client, owner, wardrobe, photographed, django_capture_on_commit_callbacks
):
    photo = photographed.photo
    photo_file = _file_of(photo)
    client.force_login(owner)

    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(_photo_remove_url(photographed))

    assert response.status_code == 302
    assert response.headers['Location'] == photographed.get_absolute_url()
    assert _reread(photographed).photo_id is None
    assert set(_reread(photographed).garments.all()) == set(wardrobe)
    assert not PrivateImage.objects.filter(pk=photo.pk).exists()
    assert not photo_file.exists()
    _assert_garment_photos_intact(wardrobe)
    followed = client.get(response.headers['Location']).content.decode()
    assert 'Photo removed.' in followed
    assert 'No photo yet.' in followed


@pytest.mark.parametrize('method', ['get', 'post'])
def test_remove_on_an_outfit_without_a_photo_goes_back_to_it(client, owner, wardrobe, method):
    outfit = make_outfit(owner, garments=wardrobe, name='Bare')
    images_before = PrivateImage.objects.count()
    client.force_login(owner)

    response = getattr(client, method)(_photo_remove_url(outfit))

    assert response.status_code == 302
    assert response.headers['Location'] == outfit.get_absolute_url()
    assert _reread(outfit).photo_id is None
    assert PrivateImage.objects.count() == images_before
    assert 'Photo removed.' not in client.get(response.headers['Location']).content.decode()


@pytest.mark.parametrize('method', ['get', 'post'])
def test_remove_on_another_users_outfit_photo_is_404_and_changes_nothing(
    client, owner, stranger, photographed, method, django_capture_on_commit_callbacks
):
    photo_file = _file_of(photographed.photo)
    client.force_login(stranger)

    with django_capture_on_commit_callbacks(execute=True):
        response = getattr(client, method)(_photo_remove_url(photographed))

    assert response.status_code == 404
    assert _reread(photographed).photo_id == photographed.photo_id
    assert PrivateImage.objects.filter(pk=photographed.photo_id).exists()
    assert photo_file.is_file()


def test_detail_query_count_is_the_same_with_and_without_a_photo(
    client, owner, wardrobe, photographed
):
    bare = make_outfit(owner, garments=wardrobe, name='Bare')
    client.force_login(owner)
    with CaptureQueriesContext(connection) as without_photo:
        client.get(bare.get_absolute_url())
    with CaptureQueriesContext(connection) as with_photo:
        client.get(photographed.get_absolute_url())

    assert len(with_photo.captured_queries) == len(without_photo.captured_queries)


@pytest.fixture
def photo_and_collage(owner, wardrobe):
    """A: the owner's photo over both wardrobe garments; B: three garments, no photo."""
    return {
        'A': make_outfit(owner, garments=wardrobe, photo=True, name='Outfit A'),
        'B': make_outfit(
            owner,
            garments=[*wardrobe, make_garment(owner, type=GarmentType.TROUSERS)],
            name='Outfit B',
        ),
    }


def test_a_photo_tile_shows_the_photo_and_a_bare_tile_its_collage(
    client, owner, stranger, photo_and_collage, foreign_wardrobe
):
    a, b = photo_and_collage['A'], photo_and_collage['B']
    theirs = make_outfit(stranger, garments=foreign_wardrobe, photo=True, name='Theirs')
    client.force_login(owner)

    page = client.get(WARDROBE_URL).content.decode()

    a_tile, b_tile = _tile(page, a), _tile(page, b)
    assert _image_urls(a_tile) == [a.photo_url]
    assert 'outfit-preview-photo' in a_tile
    assert '<span class="outfit-name">Outfit A</span>' in a_tile
    assert sorted(_image_urls(b_tile)) == sorted(g.photo_url for g in b.garments.all())
    assert 'outfit-preview-3' in b_tile
    assert 'outfit-preview-photo' not in b_tile
    assert _shown(page) == {'Outfit A', 'Outfit B'}
    assert theirs.photo_url not in page
    assert theirs.get_absolute_url() not in page


def test_removing_the_photo_turns_the_tile_back_into_its_collage(
    client, owner, wardrobe, photo_and_collage, django_capture_on_commit_callbacks
):
    a = photo_and_collage['A']
    photo_url = a.photo_url
    client.force_login(owner)

    with django_capture_on_commit_callbacks(execute=True):
        assert client.post(_photo_remove_url(a)).status_code == 302

    tile = _tile(client.get(WARDROBE_URL).content.decode(), a)
    assert photo_url not in tile
    assert sorted(_image_urls(tile)) == sorted(g.photo_url for g in wardrobe)
    assert 'outfit-preview-2' in tile


def test_a_tag_filter_leaves_out_the_photo_of_an_outfit_it_hides(client, owner, photo_and_collage):
    a, b = photo_and_collage['A'], photo_and_collage['B']
    a.tags.set(Tag.resolve(owner, ['letnie']))
    b.tags.set(Tag.resolve(owner, ['zimowe']))
    client.force_login(owner)

    page = _filtered(client, 'zimowe')

    assert _shown(page) == {'Outfit B'}
    assert a.photo_url not in page
    assert _filtered(client, 'letnie').count(a.photo_url) == 1


def _shown(page):
    """Names of the outfits whose tiles are on the page."""
    return set(re.findall(r'<span class="outfit-name">([^<]+)</span>', page))


def _bar(page):
    """The tag bar's chips as (name, tags in the chip's link, selected), in order."""
    nav = re.search(r'<nav class="tag-bar".*?</nav>', page, flags=re.DOTALL)
    if nav is None:
        return []
    chips = re.findall(
        r'<a href="([^"]+)" class="tag-chip( tag-chip-selected)?"[^>]*>([^<]+?)\s*(?:<span|</a>)',
        nav.group(0),
    )
    return [
        (name, parse_qs(urlsplit(unescape(href)).query).get('tag', []), bool(chosen))
        for href, chosen, name in chips
        if name != 'All'
    ]


def _available(page):
    return [name for name, _, chosen in _bar(page) if not chosen]


def _selected(page):
    return [name for name, _, chosen in _bar(page) if chosen]


def _link_of(page, name):
    return next(tags for chip, tags, _ in _bar(page) if chip == name)


def _filtered(client, *tags):
    return client.get(WARDROBE_URL, {'tag': list(tags)}).content.decode()


@pytest.fixture
def tagged(owner, stranger, wardrobe, foreign_wardrobe):
    """A {letnie}, B {Letnie, smart casual}, C {smart casual, zimowe}, D {}; S is the stranger's.

    B's `Letnie` resolves to A's `letnie`: one tag, spelled as first typed.
    """
    return {
        'A': _outfit_with(owner, wardrobe, 'Outfit A', tags=['letnie']),
        'B': _outfit_with(owner, wardrobe, 'Outfit B', tags=['Letnie', 'smart casual']),
        'C': _outfit_with(owner, wardrobe, 'Outfit C', tags=['smart casual', 'zimowe']),
        'D': _outfit_with(owner, wardrobe, 'Outfit D'),
        'S': _outfit_with(stranger, foreign_wardrobe, 'Theirs', tags=['letnie', 'obce']),
    }


def test_each_tile_shows_its_own_tags_and_nothing_of_anyone_else(client, owner, tagged):
    client.force_login(owner)

    page = client.get(WARDROBE_URL).content.decode()

    assert '<span class="outfit-tags">letnie</span>' in _tile(page, tagged['A'])
    assert '<span class="outfit-tags">letnie · smart casual</span>' in _tile(page, tagged['B'])
    assert '<span class="outfit-tags">smart casual · zimowe</span>' in _tile(page, tagged['C'])
    assert 'outfit-tags' not in _tile(page, tagged['D'])
    assert _shown(page) == {'Outfit A', 'Outfit B', 'Outfit C', 'Outfit D'}
    for filtered in (page, _filtered(client, 'letnie'), _filtered(client, 'obce')):
        assert 'Theirs' not in filtered
        assert 'obce' not in _available(filtered)
        assert tagged['S'].get_absolute_url() not in filtered


@pytest.mark.parametrize('value', ['letnie', 'LETNIE', ' letnie '])
def test_one_tag_shows_exactly_the_outfits_carrying_it(client, owner, tagged, value):
    client.force_login(owner)

    assert _shown(_filtered(client, value)) == {'Outfit A', 'Outfit B'}


def test_a_raw_encoded_value_is_normalized_too(client, owner, tagged):
    client.force_login(owner)

    page = client.get(f'{WARDROBE_URL}?tag=%20letnie%20').content.decode()

    assert _shown(page) == {'Outfit A', 'Outfit B'}


def test_two_tags_show_only_outfits_carrying_both(client, owner, tagged):
    client.force_login(owner)

    assert _shown(_filtered(client, 'letnie', 'smart casual')) == {'Outfit B'}


def test_two_spellings_of_one_tag_are_one_selection(client, owner, tagged):
    client.force_login(owner)

    page = _filtered(client, 'letnie', 'Letnie')

    assert _shown(page) == {'Outfit A', 'Outfit B'}
    assert _selected(page) == ['letnie']


def test_a_separator_variant_is_a_different_tag_and_matches_nothing(client, owner, tagged):
    client.force_login(owner)

    page = _filtered(client, 'smart-casual')

    assert _shown(page) == set()
    assert 'No outfits have all these tags.' in page
    assert 'Show all outfits' in page
    assert 'outfit-grid' not in page


def test_an_unknown_tag_empties_the_grid_and_can_be_dropped(client, owner, tagged):
    client.force_login(owner)

    page = _filtered(client, 'letnie', 'nonexistent')

    assert _shown(page) == set()
    assert _selected(page) == ['letnie', 'nonexistent']
    assert _link_of(page, 'nonexistent') == ['letnie']
    assert _link_of(page, 'letnie') == ['nonexistent']
    assert _available(page) == []


def test_another_users_same_named_tag_filters_only_their_own_outfits(client, stranger, tagged):
    client.force_login(stranger)

    page = _filtered(client, 'letnie')

    assert _shown(page) == {'Theirs'}
    for name in ('Outfit A', 'Outfit B', 'Outfit C', 'Outfit D', 'smart casual', 'zimowe'):
        assert name not in page
    assert _available(client.get(WARDROBE_URL).content.decode()) == ['letnie', 'obce']


def test_unfiltered_bar_lists_each_own_tag_in_use_once_by_key(client, owner, tagged):
    client.force_login(owner)

    page = client.get(WARDROBE_URL).content.decode()

    assert _available(page) == ['letnie', 'smart casual', 'zimowe']
    assert _selected(page) == []
    assert re.search(r'<a href="/wardrobe/" class="tag-chip" aria-current="page">All</a>', page)


def test_with_a_tag_selected_the_bar_offers_only_tags_that_narrow(client, owner, tagged):
    client.force_login(owner)

    page = _filtered(client, 'letnie')

    assert _selected(page) == ['letnie']
    assert _available(page) == ['smart casual']
    assert 'aria-current' not in re.search(r'<nav class="tag-bar".*?</nav>', page, re.S).group(0)
    assert 'aria-label="Remove filter letnie"' in page


def test_chip_links_add_to_or_drop_from_the_current_selection(client, owner, tagged):
    client.force_login(owner)

    one = _filtered(client, 'letnie')
    assert _link_of(one, 'smart casual') == ['letnie', 'smart casual']
    assert _link_of(one, 'letnie') == []
    assert f'<a href="{WARDROBE_URL}" class="tag-chip tag-chip-selected"' in one

    two = _filtered(client, *_link_of(one, 'smart casual'))
    assert _shown(two) == {'Outfit B'}
    assert _link_of(two, 'letnie') == ['smart casual']
    assert _link_of(two, 'smart casual') == ['letnie']
    assert _shown(_filtered(client, *_link_of(two, 'letnie'))) == {'Outfit B', 'Outfit C'}


def test_a_tag_removed_from_its_last_outfit_leaves_the_filter_and_the_bar(client, owner, tagged):
    tag = tagged['A'].tags.get()
    client.force_login(owner)

    for key in ('A', 'B'):
        assert client.post(_tag_remove_url(tagged[key], tag)).status_code == 302

    assert _shown(_filtered(client, 'letnie')) == set()
    assert _available(client.get(WARDROBE_URL).content.decode()) == ['smart casual', 'zimowe']


def test_grid_query_count_does_not_grow_with_outfits_tags_selections_photos_or_missing_slots(
    client, owner, wardrobe
):
    first = _outfit_with(owner, wardrobe, 'First', tags=['x', 'y'])
    client.force_login(owner)

    def count(*tags, incomplete=False):
        params = {'tag': list(tags)} if tags else {}
        if incomplete:
            params['incomplete'] = '1'
        with CaptureQueriesContext(connection) as queries:
            client.get(WARDROBE_URL, params)
        return len(queries.captured_queries)

    small = [count(), count('x', 'y')]
    # The incomplete filter needs one match to render a tile at all.
    _lose_a_garment(first)
    small += [count(incomplete=True), count('x', 'y', incomplete=True)]

    first.tags.add(*Tag.resolve(owner, ['z0']))
    first.photo = make_image(owner)
    first.save()
    for n in range(1, 5):
        more = _outfit_with(owner, wardrobe, f'More {n}', tags=['x', 'y', f'z{n}'])
        more.photo = make_image(owner)
        more.save()
        for _ in range(n):
            _lose_a_garment(more)
    large = [count(), count('x', 'y'), count(incomplete=True), count('x', 'y', incomplete=True)]

    page = client.get(WARDROBE_URL).content.decode()
    assert _shown(page) == {'First', *(f'More {n}' for n in range(1, 5))}
    assert page.count('outfit-preview-photo') == 5
    assert page.count('class="outfit-incomplete"') == 5
    assert large == small


# --- editing an outfit -----------------------------------------------------------


def _edit_url(outfit):
    return reverse('outfits:edit', args=[outfit.pk])


def _missing(outfit):
    return list(MissingGarment.objects.filter(outfit=outfit).values_list('pk', 'description'))


@pytest.fixture
def lived_in(owner, wardrobe):
    """A tagged outfit with a photo that lost a garment: all a rename must leave alone."""
    lost = make_garment(owner, type=GarmentType.ACCESSORY, description='red belt')
    outfit = make_outfit(owner, garments=[*wardrobe, lost], photo=True, name='Walk')
    outfit.tags.set(Tag.resolve(owner, ['letnie']))
    lost.delete()
    return outfit


@pytest.mark.parametrize('tag_names', [None, 'zimowe, smart casual'])
def test_edit_renames_and_swaps_garments_and_keeps_tags_photo_and_missing_slots(
    client, owner, wardrobe, lived_in, tag_names
):
    added = make_garment(owner, type=GarmentType.SWEATER)
    slots = _missing(lived_in)
    client.force_login(owner)
    data = {'name': 'Long walk', 'garments': [wardrobe[0].pk, added.pk]}
    if tag_names is not None:
        data['tag_names'] = tag_names

    response = client.post(_edit_url(lived_in), data)

    assert response.status_code == 302
    assert response.headers['Location'] == lived_in.get_absolute_url()
    outfit = _reread(lived_in)
    assert outfit.name == 'Long walk'
    assert set(outfit.garments.all()) == {wardrobe[0], added}
    assert _tag_names(outfit) == ['letnie']
    assert outfit.photo_id == lived_in.photo_id
    # Unticking a garment is not losing it: only a deleted garment leaves a slot.
    assert _missing(outfit) == slots
    assert 'Outfit updated.' in client.get(response.headers['Location']).content.decode()


def test_edit_page_ticks_the_current_garments_and_notes_the_missing_slot(
    client, owner, wardrobe, lived_in
):
    spare = make_garment(owner, type=GarmentType.SWEATER)
    client.force_login(owner)

    page = client.get(_edit_url(lived_in)).content.decode()

    assert 'checked' in _checkbox(page, wardrobe[0])
    assert 'checked' in _checkbox(page, wardrobe[1])
    assert 'checked' not in _checkbox(page, spare)
    assert 'name="tag_names"' not in page
    note = re.search(r'<p class="notice">.*?</p>', page, re.DOTALL).group(0)
    assert 'This outfit has 1 missing garment.' in note
    assert 'Adding garments here does not close them' in note
    assert f'href="{lived_in.get_absolute_url()}"' in note


def test_adding_a_garment_through_edit_leaves_the_missing_slot_open(
    client, owner, wardrobe, lived_in
):
    added = make_garment(owner, type=GarmentType.ACCESSORY, description='brown belt')
    slots = _missing(lived_in)
    client.force_login(owner)

    client.post(
        _edit_url(lived_in), {'name': 'Walk', 'garments': [g.pk for g in (*wardrobe, added)]}
    )

    assert set(_reread(lived_in).garments.all()) == {*wardrobe, added}
    assert _missing(lived_in) == slots


def test_edit_page_of_a_complete_outfit_has_no_missing_note(client, owner, wardrobe):
    outfit = make_outfit(owner, garments=wardrobe, name='Complete')
    client.force_login(owner)

    page = client.get(_edit_url(outfit)).content.decode()

    assert 'class="notice"' not in page
    assert 'missing garment' not in page


def test_an_invalid_edit_is_shown_again_and_changes_nothing(client, owner, wardrobe, lived_in):
    client.force_login(owner)

    response = client.post(_edit_url(lived_in), {'name': 'Renamed', 'garments': []})

    assert response.status_code == 200
    assert 'Choose at least 1 garment.' in response.content.decode()
    assert _reread(lived_in).name == 'Walk'
    assert set(_reread(lived_in).garments.all()) == set(wardrobe)


@pytest.mark.parametrize('method', ['get', 'post'])
def test_edit_of_another_users_outfit_is_404_and_changes_nothing(
    client, owner, stranger, wardrobe, lived_in, method
):
    own = make_garment(stranger)
    client.force_login(stranger)

    response = getattr(client, method)(
        _edit_url(lived_in), {'name': 'hostile', 'garments': [own.pk, wardrobe[0].pk]}
    )

    assert response.status_code == 404
    outfit = _reread(lived_in)
    assert outfit.name == 'Walk'
    assert set(outfit.garments.all()) == set(wardrobe)
    assert _tag_names(outfit) == ['letnie']


def _meanwhile(monkeypatch, change):
    """Run `change` after the edit form validates and before the view stores it: another tab."""
    is_valid = OutfitEditForm.is_valid

    def validate_then_change(form):
        valid = is_valid(form)
        change()
        return valid

    monkeypatch.setattr(OutfitEditForm, 'is_valid', validate_then_change)


def test_an_edit_does_not_bring_back_an_outfit_deleted_meanwhile(
    client, owner, wardrobe, lived_in, monkeypatch
):
    client.force_login(owner)
    _meanwhile(monkeypatch, lambda: Outfit.objects.filter(pk=lived_in.pk).delete())

    response = client.post(_edit_url(lived_in), {'name': 'Renamed', 'garments': [wardrobe[0].pk]})

    assert response.status_code == 404
    assert not Outfit.objects.filter(pk=lived_in.pk).exists()


def test_an_edit_keeps_a_photo_replaced_meanwhile(client, owner, wardrobe, lived_in, monkeypatch):
    replacement = make_image(owner)

    def replace_photo():
        Outfit.objects.filter(pk=lived_in.pk).update(photo=replacement)
        PrivateImage.objects.filter(pk=lived_in.photo_id).delete()

    client.force_login(owner)
    _meanwhile(monkeypatch, replace_photo)

    response = client.post(_edit_url(lived_in), {'name': 'Renamed', 'garments': [wardrobe[0].pk]})

    assert response.status_code == 302
    outfit = _reread(lived_in)
    assert outfit.name == 'Renamed'
    assert set(outfit.garments.all()) == {wardrobe[0]}
    assert outfit.photo_id == replacement.pk


# --- deleting an outfit ----------------------------------------------------------


def _delete_url(outfit):
    return reverse('outfits:delete', args=[outfit.pk])


def test_delete_page_of_a_tagged_outfit_with_a_photo_warns_about_both(
    client, owner, wardrobe, lived_in
):
    lived_in.tags.add(*Tag.resolve(owner, ['smart-casual']))
    client.force_login(owner)

    response = client.get(_delete_url(lived_in))
    page = response.content.decode()

    assert response.status_code == 200
    assert '<h1>Delete outfit</h1>' in page
    assert 'Walk' in page
    assert 'Its garments stay in your wardrobe.' in page
    assert 'This outfit is tagged: letnie · smart-casual.' in page
    assert 'Tags no other outfit uses disappear from your wardrobe filter.' in page
    assert 'Its photo is deleted permanently.' in page
    assert '<img' not in page
    assert re.search(r'<form method="post"[^>]*>.*?Delete outfit</button>', page, re.DOTALL)
    assert f'<a href="{lived_in.get_absolute_url()}">Cancel</a>' in page
    assert Outfit.objects.filter(pk=lived_in.pk).exists()


def test_delete_page_of_a_bare_outfit_mentions_no_tags_and_no_photo(client, owner, wardrobe):
    outfit = make_outfit(owner, garments=wardrobe, name='Bare')
    client.force_login(owner)

    page = client.get(_delete_url(outfit)).content.decode()

    assert 'Its garments stay in your wardrobe.' in page
    assert 'This outfit is tagged' not in page
    main = page.lower().split('<main', 1)[-1].split('</main>', 1)[0]
    assert 'photo' not in main


def test_delete_confirmation_is_sent_only_once(client, owner, wardrobe):
    outfit = make_outfit(owner, garments=wardrobe, name='Bare')
    client.force_login(owner)

    page = client.get(_delete_url(outfit)).content.decode()

    form = re.search(r'<form[^>]*>(?:(?!</form>).)*?Delete outfit</button>', page, re.DOTALL)
    assert 'data-submit-once' in form.group(0).split('>', 1)[0]
    assert f'<script src="{static("js/photo-shrink.js")}" defer>' in page


def test_confirming_delete_removes_the_outfit_its_slots_unused_tags_and_photo_after_commit(
    client, owner, wardrobe, lived_in, django_capture_on_commit_callbacks
):
    lived_in.tags.add(*Tag.resolve(owner, ['shared']))
    other = _outfit_with(owner, wardrobe, 'Other', tags=['shared'])
    photo = lived_in.photo
    photo_file = _file_of(photo)
    assert _missing(lived_in)
    client.force_login(owner)

    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(_delete_url(lived_in))

    assert response.status_code == 302
    assert response.headers['Location'] == WARDROBE_URL
    assert not Outfit.objects.filter(pk=lived_in.pk).exists()
    assert not MissingGarment.objects.exists()
    assert sorted(Tag.objects.values_list('name', flat=True)) == ['shared']
    assert _tag_names(other) == ['shared']
    assert not PrivateImage.objects.filter(pk=photo.pk).exists()
    assert not photo_file.exists()
    assert set(Garment.objects.all()) == set(wardrobe)
    _assert_garment_photos_intact(wardrobe)
    followed = client.get(response.headers['Location']).content.decode()
    assert 'Outfit deleted.' in followed


def test_confirming_delete_of_an_outfit_without_a_photo_keeps_every_image(
    client, owner, wardrobe, django_capture_on_commit_callbacks
):
    outfit = make_outfit(owner, garments=wardrobe, name='Bare')
    images_before = PrivateImage.objects.count()
    client.force_login(owner)

    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(_delete_url(outfit))

    assert response.status_code == 302
    assert not Outfit.objects.filter(pk=outfit.pk).exists()
    assert PrivateImage.objects.count() == images_before
    _assert_garment_photos_intact(wardrobe)


@pytest.mark.parametrize('method', ['get', 'post'])
def test_delete_of_another_users_outfit_is_404_and_changes_nothing(
    client, owner, stranger, wardrobe, lived_in, method, django_capture_on_commit_callbacks
):
    photo_file = _file_of(lived_in.photo)
    slots = _missing(lived_in)
    client.force_login(stranger)

    with django_capture_on_commit_callbacks(execute=True):
        response = getattr(client, method)(_delete_url(lived_in))

    assert response.status_code == 404
    outfit = _reread(lived_in)
    assert outfit.photo_id == lived_in.photo_id
    assert photo_file.is_file()
    assert _tag_names(outfit) == ['letnie']
    assert _missing(outfit) == slots


def test_detail_links_to_edit_and_delete_right_under_the_heading(client, owner, wardrobe):
    outfit = make_outfit(owner, garments=wardrobe, name='Walk')
    client.force_login(owner)

    page = client.get(outfit.get_absolute_url()).content.decode()

    actions = re.search(
        r'</h1>\s*(<[^>]*class="outfit-actions".*?</[a-z]+>)\s*<p>Composed', page, re.DOTALL
    )
    assert actions, 'the actions row sits directly under the heading'
    assert f'<a href="{_edit_url(outfit)}">Edit outfit</a>' in actions.group(1)
    assert f'<a href="{_delete_url(outfit)}">Delete outfit</a>' in actions.group(1)


# --- repairing a missing garment -------------------------------------------------


def _replace_url(outfit, missing_pk):
    return reverse('outfits:missing_replace', args=[outfit.pk, missing_pk])


def _dismiss_url(outfit, missing_pk):
    return reverse('outfits:missing_dismiss', args=[outfit.pk, missing_pk])


@pytest.fixture
def gap(owner, wardrobe):
    """The shirt's outfit, which lost a pair of brown loafers, and that missing slot."""
    lost = make_garment(owner, type=GarmentType.SHOES, description='brown loafers')
    outfit = make_outfit(owner, garments=[wardrobe[0], lost], name='Walk')
    lost.delete()
    return outfit, outfit.missing_garments.get()


def _radio_values(page):
    return re.findall(r'<input type="radio" name="garment" value="([^"]+)"', page)


def test_replace_page_names_the_missing_garment_and_offers_same_type_garments_first(
    client, owner, wardrobe, gap
):
    outfit, missing = gap
    boots = make_garment(owner, type=GarmentType.SHOES, description='boots')
    client.force_login(owner)

    page = client.get(_replace_url(outfit, missing.pk)).content.decode()

    assert 'Replace a missing garment' in page
    assert 'Missing: Shoes — brown loafers' in page
    assert _radio_values(page) == [str(boots.pk), str(wardrobe[1].pk)]
    assert boots.photo_url in page
    assert 'Add to outfit' in page


def test_replacing_adds_the_garment_and_closes_the_slot(client, owner, wardrobe, gap):
    outfit, missing = gap
    client.force_login(owner)

    response = client.post(_replace_url(outfit, missing.pk), {'garment': wardrobe[1].pk})

    assert response.status_code == 302
    assert response.headers['Location'] == outfit.get_absolute_url()
    assert set(_reread(outfit).garments.all()) == set(wardrobe)
    assert _missing(outfit) == []
    assert 'Garment added to the outfit.' in client.get(outfit.get_absolute_url()).content.decode()


def test_an_invalid_replace_is_shown_again_and_changes_nothing(
    client, owner, stranger, wardrobe, gap
):
    outfit, missing = gap
    theirs = make_garment(stranger, type=GarmentType.SHOES)
    client.force_login(owner)

    response = client.post(_replace_url(outfit, missing.pk), {'garment': theirs.pk})

    assert response.status_code == 200
    assert response.context['form'].errors['garment']
    assert list(_reread(outfit).garments.all()) == [wardrobe[0]]
    assert _missing(outfit) == [(missing.pk, 'brown loafers')]


def test_replace_page_without_candidates_links_to_adding_a_garment(client, owner, wardrobe, gap):
    outfit, missing = gap
    outfit.garments.add(wardrobe[1])
    client.force_login(owner)

    page = client.get(_replace_url(outfit, missing.pk)).content.decode()

    assert 'You have no other garments to use.' in page
    assert reverse('garments:add') in page
    assert _radio_values(page) == []


def test_keeping_without_it_closes_the_slot_and_keeps_the_garments(client, owner, wardrobe, gap):
    outfit, missing = gap
    client.force_login(owner)

    response = client.post(_dismiss_url(outfit, missing.pk))

    assert response.status_code == 302
    assert response.headers['Location'] == outfit.get_absolute_url()
    assert list(_reread(outfit).garments.all()) == [wardrobe[0]]
    assert _missing(outfit) == []
    assert 'Outfit kept without it.' in client.get(outfit.get_absolute_url()).content.decode()


def test_keeping_an_outfit_with_no_garments_is_refused(client, owner, wardrobe, gap):
    outfit, missing = gap
    outfit.garments.clear()
    client.force_login(owner)

    response = client.post(_dismiss_url(outfit, missing.pk), follow=True)

    assert 'An outfit with no garments needs a replacement or deletion.' in (
        response.content.decode()
    )
    assert _missing(outfit) == [(missing.pk, 'brown loafers')]


@pytest.mark.parametrize(
    ('action', 'method'), [('replace', 'get'), ('replace', 'post'), ('dismiss', 'post')]
)
def test_a_slot_already_closed_goes_back_to_the_outfit_and_changes_nothing(
    client, owner, wardrobe, gap, action, method
):
    outfit, missing = gap
    url = (_replace_url if action == 'replace' else _dismiss_url)(outfit, missing.pk)
    missing.delete()
    client.force_login(owner)

    response = getattr(client, method)(url, {'garment': wardrobe[1].pk})

    assert response.status_code == 302
    assert response.headers['Location'] == outfit.get_absolute_url()
    assert list(_reread(outfit).garments.all()) == [wardrobe[0]]
    assert not list(get_messages(response.wsgi_request))


def test_dismiss_refuses_get(client, owner, gap):
    outfit, missing = gap
    client.force_login(owner)

    assert client.get(_dismiss_url(outfit, missing.pk)).status_code == 405
    assert _missing(outfit) == [(missing.pk, 'brown loafers')]


def _missing_section(page):
    match = re.search(r'<section aria-labelledby="missing-heading">.*?</section>', page, re.DOTALL)
    return match.group(0) if match else None


def test_detail_leads_with_the_missing_garments_and_their_repairs(client, owner, wardrobe, gap):
    outfit, missing = gap
    client.force_login(owner)

    page = client.get(outfit.get_absolute_url()).content.decode()

    section = _missing_section(page)
    assert section, 'an incomplete outfit shows its missing garments'
    # Directly under the actions row, before tags.
    assert page.index('class="outfit-actions"') < page.index(section) < page.index('tags-heading')
    assert '<h2 id="missing-heading">Missing garments</h2>' in section
    assert 'Shoes' in section
    assert 'brown loafers' in section
    assert f'href="{_replace_url(outfit, missing.pk)}"' in section
    assert f'action="{_dismiss_url(outfit, missing.pk)}"' in section
    assert f'href="{_delete_url(outfit)}"' in section


def test_detail_of_an_outfit_with_no_garments_left_offers_no_keep_without_it(client, owner, gap):
    outfit, missing = gap
    outfit.garments.clear()
    client.force_login(owner)

    section = _missing_section(client.get(outfit.get_absolute_url()).content.decode())

    assert f'href="{_replace_url(outfit, missing.pk)}"' in section
    assert _dismiss_url(outfit, missing.pk) not in section
    assert f'href="{_delete_url(outfit)}"' in section


def test_detail_of_a_complete_outfit_has_no_missing_section(client, owner, wardrobe):
    outfit = make_outfit(owner, garments=wardrobe, name='Walk')
    client.force_login(owner)

    assert _missing_section(client.get(outfit.get_absolute_url()).content.decode()) is None


def test_detail_query_count_is_the_same_with_and_without_missing_slots(client, owner, wardrobe):
    complete = make_outfit(owner, garments=wardrobe, name='Complete')
    lost = [make_garment(owner, type=GarmentType.ACCESSORY) for _ in range(3)]
    broken = make_outfit(owner, garments=[*wardrobe, *lost], name='Broken')
    for garment in lost:
        garment.delete()
    client.force_login(owner)
    with CaptureQueriesContext(connection) as none_missing:
        client.get(complete.get_absolute_url())
    with CaptureQueriesContext(connection) as three_missing:
        page = client.get(broken.get_absolute_url()).content.decode()

    assert page.count('Keep without it') == 3
    assert len(three_missing.captured_queries) == len(none_missing.captured_queries)


# --- incomplete outfits in the grid ------------------------------------------------


def _lose_a_garment(outfit, description='red belt'):
    lost = make_garment(outfit.owner, type=GarmentType.ACCESSORY, description=description)
    outfit.garments.add(lost)
    lost.delete()


@pytest.fixture
def incomplete(owner, stranger, wardrobe, foreign_wardrobe):
    """A: tagged, photo, lost one garment; B: collage, lost two; C: tagged, complete; S: theirs."""
    a = _outfit_with(owner, wardrobe, 'Outfit A', tags=['letnie'])
    a.photo = make_image(owner)
    a.save()
    _lose_a_garment(a)
    b = _outfit_with(owner, wardrobe, 'Outfit B')
    _lose_a_garment(b)
    _lose_a_garment(b, description='grey scarf')
    c = _outfit_with(owner, wardrobe, 'Outfit C', tags=['letnie'])
    s = _outfit_with(stranger, foreign_wardrobe, 'Theirs')
    _lose_a_garment(s)
    return {'A': a, 'B': b, 'C': c, 'S': s}


def _badge_in_preview(tile):
    preview = re.search(r'<div class="outfit-preview[^"]*">(.*?)</div>', tile, re.DOTALL)
    badge = re.search(r'<span class="outfit-incomplete">([^<]+)</span>', preview.group(1))
    return badge.group(1) if badge else None


def _notice(page):
    match = re.search(r'<p class="notice">(.*?)</p>', page, re.DOTALL)
    return match.group(1) if match else None


def _query_of(href):
    return parse_qs(urlsplit(unescape(href)).query)


def test_incomplete_tiles_carry_a_badge_on_photo_and_collage_alike(client, owner, incomplete):
    client.force_login(owner)

    page = client.get(WARDROBE_URL).content.decode()

    a, b, c = (_tile(page, incomplete[key]) for key in 'ABC')
    assert 'outfit-preview-photo' in a
    assert _badge_in_preview(a) == 'Incomplete · 1 missing'
    assert _badge_in_preview(b) == 'Incomplete · 2 missing'
    assert _badge_in_preview(c) is None
    assert 'aria-label="Outfit A, incomplete"' in a
    assert 'aria-label="Outfit C"' in c
    assert _badge_in_preview(_tile(_filtered(client, 'letnie'), incomplete['A']))


def test_banner_counts_own_incomplete_outfits_and_links_to_them_keeping_the_tags(
    client, owner, incomplete
):
    client.force_login(owner)

    for page, tags in (
        (client.get(WARDROBE_URL).content.decode(), []),
        (_filtered(client, 'letnie'), ['letnie']),
    ):
        notice = _notice(page)
        # The count ignores the filters: it is about the whole wardrobe.
        assert '2 outfits need attention.' in ' '.join(notice.split())
        href = re.search(r'<a href="([^"]+)">Show them</a>', notice).group(1)
        assert _query_of(href) == {'incomplete': ['1'], **({'tag': tags} if tags else {})}


def test_no_banner_without_incomplete_outfits(client, owner, wardrobe):
    _outfit_with(owner, wardrobe, 'Complete')
    client.force_login(owner)

    assert _notice(client.get(WARDROBE_URL).content.decode()) is None


def test_incomplete_filter_shows_only_incomplete_outfits_and_combines_with_tags(
    client, owner, incomplete
):
    client.force_login(owner)

    only = client.get(WARDROBE_URL, {'incomplete': '1'}).content.decode()
    both = client.get(WARDROBE_URL, {'incomplete': '1', 'tag': 'letnie'}).content.decode()

    assert _shown(only) == {'Outfit A', 'Outfit B'}
    assert _shown(both) == {'Outfit A'}
    assert _notice(only) is None
    # Selected chip "Incomplete ×" drops the filter and keeps the tag.
    assert ('Incomplete', ['letnie'], True) in _bar(both)
    incomplete_chip = re.search(r'<a href="([^"]+)"[^>]*>Incomplete ', both).group(1)
    assert _query_of(incomplete_chip) == {'tag': ['letnie']}
    # A tag chip keeps the incomplete filter.
    letnie_chip = re.search(r'<a href="([^"]+)"[^>]*>letnie ', both).group(1)
    assert _query_of(letnie_chip) == {'incomplete': ['1']}


def test_incomplete_filter_with_no_match_says_so_and_links_to_all(client, owner, wardrobe):
    _outfit_with(owner, wardrobe, 'Complete')
    client.force_login(owner)

    page = client.get(WARDROBE_URL, {'incomplete': '1'}).content.decode()

    assert _shown(page) == set()
    assert 'No incomplete outfits match.' in page
    assert f'<a href="{WARDROBE_URL}">Show all outfits</a>' in page
