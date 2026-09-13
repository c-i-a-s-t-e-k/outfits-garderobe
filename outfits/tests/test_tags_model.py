"""Tag identity, the tag-ownership guard and the cleanup of tags nobody uses."""

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from outfits.models import Outfit, Tag
from outfits.tests.test_model import make_garment

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures('temp_media_root')]


def _links():
    return set(Outfit.tags.through.objects.values_list('outfit_id', 'tag_id'))


def _outfit(user, name=''):
    outfit = Outfit.objects.create(owner=user, name=name)
    outfit.garments.add(make_garment(user))
    return outfit


# --- identity ----------------------------------------------------------------


def test_name_whitespace_is_collapsed_and_the_key_is_case_folded(owner):
    tag = Tag.objects.create(owner=owner, name='  Letnie   wieczory ')

    tag.refresh_from_db()
    assert tag.name == 'Letnie wieczory'
    assert tag.normalized == 'letnie wieczory'


def test_a_case_variant_of_an_existing_tag_is_rejected_for_the_same_owner(owner):
    Tag.objects.create(owner=owner, name='Letnie wieczory')

    with pytest.raises(ValidationError):
        Tag.objects.create(owner=owner, name='LETNIE wieczory')

    assert Tag.objects.count() == 1


def test_the_same_name_saves_for_another_owner(owner, stranger):
    Tag.objects.create(owner=owner, name='Letnie wieczory')

    assert Tag.objects.create(owner=stranger, name='LETNIE wieczory').pk


def test_a_non_ascii_case_variant_is_the_same_tag(owner):
    """SQLite's LOWER() leaves `Ś` alone; the Python key must not."""
    Tag.objects.create(owner=owner, name='Ślub')

    with pytest.raises(ValidationError):
        Tag.objects.create(owner=owner, name='ślub')

    assert Tag.objects.count() == 1


def test_separators_are_not_folded(owner):
    Tag.objects.create(owner=owner, name='smart casual')
    Tag.objects.create(owner=owner, name='smart-casual')

    assert Tag.objects.count() == 2


@pytest.mark.parametrize('name', ['smart, casual', '   ', 'x' * 31])
def test_an_invalid_name_is_rejected(owner, name):
    with pytest.raises(ValidationError):
        Tag.objects.create(owner=owner, name=name)

    assert not Tag.objects.exists()


def test_database_refuses_a_duplicate_key_that_skips_clean(owner):
    """PostgreSQL must refuse what clean() would have caught, when clean() never runs."""
    Tag.objects.create(owner=owner, name='letnie')
    other = Tag.objects.create(owner=owner, name='zimowe')

    with pytest.raises(IntegrityError), transaction.atomic():
        Tag.objects.filter(pk=other.pk).update(normalized='letnie')


def test_database_refuses_an_empty_key_that_skips_clean(owner):
    tag = Tag.objects.create(owner=owner, name='letnie')

    with pytest.raises(IntegrityError), transaction.atomic():
        Tag.objects.filter(pk=tag.pk).update(normalized='')


def test_str_is_the_name(owner):
    assert str(Tag(owner=owner, name='Letnie')) == 'Letnie'


# --- resolve -----------------------------------------------------------------


def test_resolve_reuses_an_existing_tag_by_key_and_creates_the_missing_one(owner):
    existing = Tag.objects.create(owner=owner, name='Letnie')

    tags = Tag.resolve(owner, ['letnie', 'Nowy'])

    assert [t.name for t in tags] == ['Letnie', 'Nowy']
    assert tags[0].pk == existing.pk
    assert sorted(Tag.objects.filter(owner=owner).values_list('name', flat=True)) == [
        'Letnie',
        'Nowy',
    ]


def test_resolve_never_returns_or_changes_another_users_tag(owner, stranger):
    foreign = Tag.objects.create(owner=stranger, name='letnie')

    tags = Tag.resolve(owner, ['LETNIE'])

    assert tags[0].pk != foreign.pk
    assert tags[0].owner == owner
    foreign.refresh_from_db()
    assert (foreign.owner, foreign.name) == (stranger, 'letnie')
    assert Tag.objects.filter(owner=stranger).count() == 1


def test_resolve_returns_the_row_a_concurrent_request_created(owner, monkeypatch):
    winner = Tag.objects.create(owner=owner, name='Letnie')
    # The read happened before the other request committed: it saw nothing.
    monkeypatch.setattr(Tag, '_existing_by_key', classmethod(lambda cls, owner, keys: {}))

    tags = Tag.resolve(owner, ['letnie'])

    assert [t.pk for t in tags] == [winner.pk]
    assert Tag.objects.get(pk=winner.pk).name == 'Letnie'
    assert Tag.objects.count() == 1


# --- ownership ---------------------------------------------------------------


def test_another_users_tag_cannot_be_added_to_an_outfit(owner, stranger):
    outfit = _outfit(owner)
    own = Tag.objects.create(owner=owner, name='letnie')
    foreign = Tag.objects.create(owner=stranger, name='zimowe')

    # The guard raises inside add()'s own atomic block, which joins the
    # surrounding transaction; the savepoint keeps the test's usable afterwards.
    with pytest.raises(ValidationError), transaction.atomic():
        outfit.tags.add(own, foreign)

    assert _links() == set()


def test_a_tag_cannot_be_added_to_another_users_outfit_from_the_tag_side(owner, stranger):
    outfit = _outfit(stranger)
    tag = Tag.objects.create(owner=owner, name='letnie')

    with pytest.raises(ValidationError), transaction.atomic():
        tag.outfits.add(outfit)

    assert _links() == set()


# --- cleanup -----------------------------------------------------------------


def test_a_tag_survives_removal_from_one_outfit_and_goes_with_the_last(owner):
    first, second = _outfit(owner), _outfit(owner)
    tag = Tag.objects.create(owner=owner, name='letnie')
    first.tags.add(tag)
    second.tags.add(tag)

    first.tags.remove(tag)
    assert Tag.objects.filter(pk=tag.pk).exists()

    second.tags.remove(tag)
    assert not Tag.objects.filter(pk=tag.pk).exists()


def test_clear_deletes_unshared_tags_and_keeps_shared_ones(owner):
    outfit, other = _outfit(owner), _outfit(owner)
    only_here = Tag.objects.create(owner=owner, name='letnie')
    shared = Tag.objects.create(owner=owner, name='smart casual')
    outfit.tags.add(only_here, shared)
    other.tags.add(shared)

    outfit.tags.clear()

    assert set(Tag.objects.all()) == {shared}
    assert _links() == {(other.pk, shared.pk)}


def test_deleting_an_outfit_deletes_only_the_tags_it_alone_carried(owner, stranger):
    outfit, other = _outfit(owner), _outfit(owner)
    only_here = Tag.objects.create(owner=owner, name='letnie')
    shared = Tag.objects.create(owner=owner, name='smart casual')
    outfit.tags.add(only_here, shared)
    other.tags.add(shared)
    foreign_outfit = _outfit(stranger)
    foreign = Tag.objects.create(owner=stranger, name='letnie')
    foreign_outfit.tags.add(foreign)

    outfit.delete()

    assert not Tag.objects.filter(pk=only_here.pk).exists()
    assert set(Tag.objects.all()) == {shared, foreign}
    assert _links() == {(other.pk, shared.pk), (foreign_outfit.pk, foreign.pk)}


def test_deleting_the_owner_removes_their_tags(owner, stranger):
    _outfit(owner).tags.add(Tag.objects.create(owner=owner, name='letnie'))
    Tag.objects.create(owner=owner, name='unused')
    foreign = Tag.objects.create(owner=stranger, name='letnie')
    _outfit(stranger).tags.add(foreign)

    owner.delete()

    assert set(Tag.objects.all()) == {foreign}
    assert len(_links()) == 1
