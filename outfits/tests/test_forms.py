"""Editing an outfit keeps the compose rules for its name, with one garment enough and no tags;
a missing garment is replaced by one of the owner's other garments, same kind first."""

import pytest

from garments.models import GarmentType
from outfits.forms import OutfitEditForm, OutfitForm, ReplaceMissingGarmentForm
from tests.factories import make_garment, make_outfit

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures('temp_media_root')]


@pytest.fixture
def wardrobe(owner):
    return [
        make_garment(owner, type=GarmentType.SHIRT),
        make_garment(owner, type=GarmentType.SHOES),
    ]


def _edit(outfit, name, garments):
    return OutfitEditForm(
        {'name': name, 'garments': [g.pk for g in garments]},
        owner=outfit.owner,
        instance=outfit,
    )


def test_edit_accepts_a_single_garment(owner, wardrobe):
    outfit = make_outfit(owner, garments=wardrobe, name='Walk')

    form = _edit(outfit, 'Walk', wardrobe[:1])

    assert form.is_valid(), form.errors
    assert list(form.cleaned_data['garments']) == wardrobe[:1]


def test_edit_refuses_zero_garments(owner, wardrobe):
    outfit = make_outfit(owner, garments=wardrobe, name='Walk')

    form = _edit(outfit, 'Walk', [])

    assert not form.is_valid()
    assert form.errors['garments'] == ['Choose at least 1 garment.']


def test_edit_accepts_the_outfits_own_current_name(owner, wardrobe):
    outfit = make_outfit(owner, garments=wardrobe, name='Walk')

    form = _edit(outfit, 'walk', wardrobe)

    assert form.is_valid(), form.errors
    assert form.cleaned_data['name'] == 'walk'


@pytest.mark.parametrize('typed', ['Errand', 'ERRAND', 'errand'])
def test_edit_refuses_another_outfits_name_in_any_letter_case(owner, wardrobe, typed):
    make_outfit(owner, garments=wardrobe, name='Errand')
    outfit = make_outfit(owner, garments=wardrobe, name='Walk')

    form = _edit(outfit, typed, wardrobe)

    assert not form.is_valid()
    assert 'name' in form.errors


def test_an_empty_name_keeps_the_current_name(owner, wardrobe):
    make_outfit(owner, garments=wardrobe)
    outfit = make_outfit(owner, garments=wardrobe)
    assert outfit.name == 'outfit-2'

    form = _edit(outfit, '', wardrobe)

    assert form.is_valid(), form.errors
    assert form.cleaned_data['name'] == 'outfit-2'


def test_edit_offers_no_tag_input(owner, wardrobe):
    outfit = make_outfit(owner, garments=wardrobe, name='Walk')

    form = OutfitEditForm(
        {'name': 'Walk', 'garments': [g.pk for g in wardrobe], 'tag_names': 'letnie'},
        owner=owner,
        instance=outfit,
    )

    assert 'tag_names' not in form.fields
    assert form.is_valid(), form.errors
    assert 'tag_names' not in form.cleaned_data


def test_compose_still_needs_two_garments_and_offers_tags(owner, wardrobe):
    form = OutfitForm({'name': '', 'garments': [wardrobe[0].pk]}, owner=owner)

    assert not form.is_valid()
    assert form.errors['garments'] == ['Choose at least 2 garments.']
    assert 'tag_names' in form.fields


# --- replacing a missing garment ----------------------------------------------


@pytest.fixture
def gap(owner, wardrobe):
    """An outfit of the shirt that lost a pair of brown loafers."""
    lost = make_garment(owner, type=GarmentType.SHOES, description='brown loafers')
    outfit = make_outfit(owner, garments=[wardrobe[0], lost], name='Walk')
    lost.delete()
    return outfit, outfit.missing_garments.get()


def _candidates(form):
    """The garments offered, in the order the page lists them."""
    return [value.instance for value, _ in form.fields['garment'].choices]


def test_replace_lists_same_type_garments_first_and_leaves_out_the_outfits_own(
    owner, stranger, wardrobe, gap
):
    outfit, missing = gap
    older_sweater = make_garment(owner, type=GarmentType.SWEATER)
    boots = make_garment(owner, type=GarmentType.SHOES, description='boots')
    trousers = make_garment(owner, type=GarmentType.TROUSERS)
    make_garment(stranger, type=GarmentType.SHOES, description='their sneakers')

    form = ReplaceMissingGarmentForm(outfit=outfit, missing=missing)

    # wardrobe[0] is in the outfit; the rest by kind, then newest first.
    assert _candidates(form) == [boots, wardrobe[1], trousers, older_sweater]


def test_replace_of_an_other_type_matches_its_typed_kind_in_any_letter_case(owner, wardrobe):
    lost = make_garment(owner, type=GarmentType.OTHER, type_other='Scarf')
    outfit = make_outfit(owner, garments=[wardrobe[0], lost], name='Walk')
    lost.delete()
    hat = make_garment(owner, type=GarmentType.OTHER, type_other='hat')
    scarf = make_garment(owner, type=GarmentType.OTHER, type_other='SCARF')

    form = ReplaceMissingGarmentForm(outfit=outfit, missing=outfit.missing_garments.get())

    assert _candidates(form) == [scarf, hat, wardrobe[1]]


def test_replace_refuses_a_garment_outside_the_candidates(owner, stranger, wardrobe, gap):
    outfit, missing = gap
    theirs = make_garment(stranger, type=GarmentType.SHOES)

    for garment in (theirs, wardrobe[0]):
        form = ReplaceMissingGarmentForm({'garment': garment.pk}, outfit=outfit, missing=missing)
        assert not form.is_valid()
        assert 'garment' in form.errors

    form = ReplaceMissingGarmentForm({'garment': wardrobe[1].pk}, outfit=outfit, missing=missing)
    assert form.is_valid(), form.errors
    assert form.cleaned_data['garment'] == wardrobe[1]
