"""The two database checks every foreign-id write scenario ends with.

A status code says what the view answered; these say what it left behind.
"""

import pytest
from django.db.models import F, Q

from garments.models import Garment
from outfits.models import MissingGarment, Outfit, Tag
from privatemedia.models import PrivateImage

OutfitGarment = Outfit.garments.through
OutfitTag = Outfit.tags.through


@pytest.fixture
def snapshot_of():
    """A comparable picture of everything one user owns, links included.

    Links count if either end is the user's, so a foreign outfit gaining one of
    their garments or tags shows up as a change too.
    """

    def snapshot(user):
        return {
            'images': list(PrivateImage.objects.filter(owner=user).order_by('pk').values()),
            'garments': list(Garment.objects.filter(owner=user).order_by('pk').values()),
            'outfits': list(Outfit.objects.filter(owner=user).order_by('pk').values()),
            'tags': list(Tag.objects.filter(owner=user).order_by('pk').values()),
            # Owned through the outfit: a missing garment has no owner field.
            'missing': list(
                MissingGarment.objects.filter(outfit__owner=user).order_by('pk').values()
            ),
            'links': sorted(
                OutfitGarment.objects.filter(Q(outfit__owner=user) | Q(garment__owner=user))
                .values_list('outfit_id', 'garment_id')
                .distinct()
            ),
            'tag_links': sorted(
                OutfitTag.objects.filter(Q(outfit__owner=user) | Q(tag__owner=user))
                .values_list('outfit_id', 'tag_id')
                .distinct()
            ),
        }

    return snapshot


@pytest.fixture
def assert_no_cross_owner_links():
    """No row anywhere joins two users' objects, whatever path wrote it."""

    def check():
        mixed_photos = Garment.objects.exclude(photo__owner=F('owner'))
        assert not mixed_photos.exists(), f'garments on a foreign photo: {list(mixed_photos)}'

        mixed_outfit_photos = Outfit.objects.filter(photo__isnull=False).exclude(
            photo__owner=F('owner')
        )
        assert not mixed_outfit_photos.exists(), (
            f'outfits on a foreign photo: {list(mixed_outfit_photos)}'
        )

        # The through table, read directly: this is where an M2M write lands
        # without passing through either model's save().
        mixed_links = OutfitGarment.objects.exclude(outfit__owner=F('garment__owner'))
        assert not mixed_links.exists(), (
            f'outfit–garment links across owners: '
            f'{list(mixed_links.values_list("outfit_id", "garment_id"))}'
        )

        mixed_tag_links = OutfitTag.objects.exclude(outfit__owner=F('tag__owner'))
        assert not mixed_tag_links.exists(), (
            f'outfit–tag links across owners: '
            f'{list(mixed_tag_links.values_list("outfit_id", "tag_id"))}'
        )

    return check
