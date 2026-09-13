"""Compose and detail never cross users, and a failed compose stores nothing.

Every assertion re-reads the database rather than trusting a status code.
"""

import re
import uuid
from datetime import timedelta
from html import unescape
from urllib.parse import parse_qs, urlsplit

import pytest
from django.conf import settings
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from garments.models import GarmentType
from outfits.forms import OutfitForm
from outfits.models import Outfit, Tag
from tests.factories import make_garment

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


def test_valid_compose_stores_the_outfit_and_lands_on_the_wardrobe(client, owner, wardrobe):
    client.force_login(owner)

    response = _compose(client, wardrobe, name='Office')

    assert response.status_code == 302
    assert response.headers['Location'] == WARDROBE_URL
    outfit = Outfit.objects.get()
    assert outfit.owner == owner
    assert outfit.name == 'Office'
    assert set(outfit.garments.all()) == set(wardrobe)
    followed = client.get(response.headers['Location'])
    assert 'Outfit saved.' in followed.content.decode()


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


# --- filtering the wardrobe by tag -------------------------------------------


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


def test_grid_query_count_does_not_grow_with_outfits_tags_or_selections(client, owner, wardrobe):
    first = _outfit_with(owner, wardrobe, 'First', tags=['x', 'y'])
    client.force_login(owner)

    def count(*tags):
        with CaptureQueriesContext(connection) as queries:
            client.get(WARDROBE_URL, {'tag': list(tags)} if tags else None)
        return len(queries.captured_queries)

    small = (count(), count('x', 'y'))

    first.tags.add(*Tag.resolve(owner, ['z0']))
    for n in range(1, 5):
        _outfit_with(owner, wardrobe, f'More {n}', tags=['x', 'y', f'z{n}'])
    large = (count(), count('x', 'y'))

    assert _shown(client.get(WARDROBE_URL).content.decode()) == {
        'First',
        *(f'More {n}' for n in range(1, 5)),
    }
    assert large == small
