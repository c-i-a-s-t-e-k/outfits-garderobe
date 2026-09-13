"""Compose and detail never cross users, and a failed compose stores nothing.

Every assertion re-reads the database rather than trusting a status code.
"""

import re
import uuid

import pytest
from django.conf import settings
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from garments.models import GarmentType
from outfits.forms import OutfitForm
from outfits.models import Outfit
from outfits.tests.test_model import make_garment

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
