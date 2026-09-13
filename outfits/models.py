"""An outfit: a named set of one user's garments, kept as a durable reference."""

import re
import uuid

from django.conf import settings
from django.db import models
from django.db.models.functions import Lower
from django.urls import reverse

from garments.models import GarmentType

# The order garments appear in a preview tile and on the detail page: the
# pieces that make an outfit recognisable at a glance come first.
GARMENT_TYPE_ORDER = [
    GarmentType.OUTERWEAR,
    GarmentType.DRESS,
    GarmentType.SWEATER,
    GarmentType.SHIRT,
    GarmentType.TSHIRT,
    GarmentType.TROUSERS,
    GarmentType.SKIRT,
    GarmentType.SHORTS,
    GarmentType.SHOES,
    GarmentType.ACCESSORY,
    GarmentType.OTHER,
]
_TYPE_RANK = {value: rank for rank, value in enumerate(GARMENT_TYPE_ORDER)}

PREVIEW_SIZE = 4


def _garment_sort_key(garment):
    return (_TYPE_RANK.get(garment.type, len(_TYPE_RANK)), garment.created_at, garment.pk)


class Outfit(models.Model):
    """A set of garments composed by their owner.

    A garment belongs to any number of outfits, which is the whole point of the
    product: clothes stay sorted by kind, outfits remember the combinations.
    Names are never empty and unique per owner regardless of case; a blank name
    becomes the lowest free `outfit-N`.
    """

    DEFAULT_NAME_PREFIX = 'outfit-'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='outfits',
    )
    # blank=True only so that clean() gets a chance to fill in the default; the
    # check constraint below is what keeps an empty name out of the table.
    name = models.CharField(max_length=60, blank=True)
    garments = models.ManyToManyField('garments.Garment', related_name='outfits')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['owner', '-created_at'])]
        constraints = [
            models.UniqueConstraint(
                Lower('name'),
                'owner',
                name='outfit_name_unique_per_owner',
                violation_error_message='You already have an outfit with this name.',
            ),
            models.CheckConstraint(
                condition=~models.Q(name=''),
                name='outfit_name_not_empty',
                violation_error_message='An outfit needs a name.',
            ),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Same reasoning as Garment.save(): Django validates only through
        # ModelForm, so the default name and the uniqueness check would not
        # hold on a plain objects.create() without this.
        self.full_clean()
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('outfits:detail', args=[self.pk])

    def clean(self):
        self.name = ' '.join(self.name.split())
        # A ModelForm runs clean() before the view has set owner, in which case
        # the default has to wait for the next full_clean() — the one in save().
        if not self.name and self.owner_id:
            self.name = self.default_name_for(self.owner_id)

    @classmethod
    def default_name_for(cls, owner):
        """The lowest free `outfit-N` for this owner, ignoring case.

        Only exact `outfit-<digits>` names occupy a number: `outfit-02` does not
        take `outfit-2`. Numbers freed by a deletion are reused — "lowest free"
        is meant literally.
        """
        pattern = re.compile(rf'^{re.escape(cls.DEFAULT_NAME_PREFIX)}(\d+)$', re.IGNORECASE)
        names = cls.objects.filter(
            owner=owner, name__istartswith=cls.DEFAULT_NAME_PREFIX
        ).values_list('name', flat=True)
        taken = set()
        for name in names:
            match = pattern.match(name)
            if match and not (len(match[1]) > 1 and match[1].startswith('0')):
                taken.add(int(match[1]))
        number = 1
        while number in taken:
            number += 1
        return f'{cls.DEFAULT_NAME_PREFIX}{number}'

    # The three properties below read garments.all() once and sort in Python,
    # so a prefetch_related('garments') covers them without a query per outfit.

    @property
    def ordered_garments(self):
        return sorted(self.garments.all(), key=_garment_sort_key)

    @property
    def preview_garments(self):
        return self.ordered_garments[:PREVIEW_SIZE]

    @property
    def hidden_garment_count(self):
        return max(len(self.garments.all()) - PREVIEW_SIZE, 0)
