"""An outfit that lost a garment looks incomplete wherever it is browsed, and can be repaired.

After the loafers are deleted, the grid marks both outfits that held them, on a
collage tile and a photo tile alike, filtered or not; a notice counts them and
narrows the grid to them. Each outfit's page offers Replace, Keep without it and
Delete outfit, and each repair makes the outfit look complete again. An outfit
with nothing left cannot be kept as it is.
"""

import re

import pytest
from django.urls import reverse

from garments.models import GarmentType
from outfits.models import Outfit
from tests.factories import make_garment

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures('temp_media_root')]

WARDROBE_URL = reverse('wardrobe')


def _tile(page, outfit):
    match = re.search(rf'<li>\s*<a href="{outfit.get_absolute_url()}".*?</li>', page, re.DOTALL)
    return match.group(0) if match else None


def _is_marked(page, outfit):
    tile = _tile(page, outfit)
    assert tile, f'{outfit.name} has no tile on this page'
    return 'Incomplete · 1 missing' in tile


def _shown(page):
    return set(re.findall(r'<span class="outfit-name">([^<]+)</span>', page))


def _slot(outfit):
    return Outfit.objects.get(pk=outfit.pk).missing_garments.get()


@pytest.fixture
def after_deletion(client, wardrobe, delete_garment_through_its_page):
    delete_garment_through_its_page(wardrobe['a'])
    return wardrobe


def test_the_grid_marks_both_outfits_and_leads_to_them(client, after_deletion):
    o1, o2, o3 = after_deletion['o1'], after_deletion['o2'], after_deletion['o3']

    page = client.get(WARDROBE_URL).content.decode()

    assert _is_marked(page, o1)
    assert _is_marked(page, o2)
    assert 'outfit-preview-photo' in _tile(page, o2)
    assert not _is_marked(page, o3)
    assert _is_marked(client.get(WARDROBE_URL, {'tag': 'letnie'}).content.decode(), o1)
    assert '2 outfits need attention.' in ' '.join(page.split())
    assert _shown(client.get(WARDROBE_URL, {'incomplete': '1'}).content.decode()) == {
        o1.name,
        o2.name,
    }


def test_the_outfit_page_offers_replace_keep_and_delete(client, after_deletion):
    o1 = after_deletion['o1']
    slot = _slot(o1)

    page = client.get(o1.get_absolute_url()).content.decode()

    assert f'href="{reverse("outfits:missing_replace", args=[o1.pk, slot.pk])}"' in page
    assert f'action="{reverse("outfits:missing_dismiss", args=[o1.pk, slot.pk])}"' in page
    assert f'href="{reverse("outfits:delete", args=[o1.pk])}"' in page


def test_replacing_and_keeping_each_make_an_outfit_complete_again(client, owner, after_deletion):
    o1, o2 = after_deletion['o1'], after_deletion['o2']
    boots = make_garment(owner, type=GarmentType.SHOES, description='boots')

    client.post(
        reverse('outfits:missing_replace', args=[o1.pk, _slot(o1).pk]), {'garment': boots.pk}
    )
    client.post(reverse('outfits:missing_dismiss', args=[o2.pk, _slot(o2).pk]))

    page = client.get(WARDROBE_URL).content.decode()
    assert not _is_marked(page, o1)
    assert not _is_marked(page, o2)
    assert 'need attention' not in page
    assert set(Outfit.objects.get(pk=o1.pk).garments.all()) == {after_deletion['b'], boots}
    assert set(Outfit.objects.get(pk=o2.pk).garments.all()) == {after_deletion['c']}


def test_an_outfit_with_no_garments_left_cannot_be_kept_as_it_is(
    client, after_deletion, delete_garment_through_its_page
):
    o2 = after_deletion['o2']
    delete_garment_through_its_page(after_deletion['c'])
    slots = list(Outfit.objects.get(pk=o2.pk).missing_garments.values_list('pk', flat=True))
    assert len(slots) == 2

    page = client.get(o2.get_absolute_url()).content.decode()
    assert 'Keep without it' not in page
    assert 'Replace' in page

    client.post(reverse('outfits:missing_dismiss', args=[o2.pk, slots[0]]))

    outfit = Outfit.objects.get(pk=o2.pk)
    assert list(outfit.missing_garments.values_list('pk', flat=True)) == slots
    assert not outfit.garments.exists()
