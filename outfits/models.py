"""An outfit: a named set of one user's garments, kept as a durable reference."""

import re
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
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


class Tag(models.Model):
    """One user's label for outfits.

    `Letnie` and ` letnie ` are the same tag: identity is the `normalized` key,
    and the tag keeps the spelling it was first typed with. The key is computed
    in Python and compared exactly, never with `iexact` or `Lower()` — SQLite
    folds only ASCII case, so `Ślub` and `ślub` would be two tags in dev and
    tests but one on PostgreSQL.
    """

    MAX_LENGTH = 30
    MAX_PER_OUTFIT = 20

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='tags',
    )
    name = models.CharField(max_length=MAX_LENGTH)
    # blank=True only because clean_fields() runs before clean() fills it in;
    # the check constraint below keeps an empty key out of the table.
    # casefold() can expand a character to up to three (`ß` → `ss`), so the key
    # gets room for a name that is at its limit.
    normalized = models.CharField(max_length=MAX_LENGTH * 3, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['normalized']
        constraints = [
            models.UniqueConstraint(
                fields=['owner', 'normalized'],
                name='tag_unique_per_owner',
                violation_error_message='You already have this tag.',
            ),
            models.CheckConstraint(
                condition=~models.Q(normalized=''),
                name='tag_name_not_empty',
                violation_error_message='A tag needs a name.',
            ),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Same reasoning as Outfit.save(): Django validates only through
        # ModelForm, so the key and the uniqueness check would not hold on a
        # plain objects.create() without this.
        self.full_clean()
        super().save(*args, **kwargs)

    def clean(self):
        self.name = ' '.join(self.name.split())
        self.normalized = self.normalize(self.name)
        if not self.normalized:
            raise ValidationError({'name': 'A tag needs a name.'})
        if ',' in self.name:
            # Commas separate tags in every input, so a tag cannot contain one.
            raise ValidationError({'name': 'A tag cannot contain a comma.'})

    @staticmethod
    def normalize(text):
        """The identity key: whitespace collapsed and stripped, case folded."""
        return ' '.join(text.split()).casefold()

    @classmethod
    def resolve(cls, owner, names):
        """The owner's tags for these cleaned names, in input order.

        Existing tags are reused by key and keep their spelling; missing ones
        are created. A name whose key repeats an earlier one is skipped.
        """
        keyed = {}
        for name in names:
            keyed.setdefault(cls.normalize(name), name)
        found = cls._existing_by_key(owner, keyed)
        tags = []
        for key, name in keyed.items():
            tag = found.get(key)
            if tag is None:
                tag = found[key] = cls._create_or_fetch(owner, name, key)
            tags.append(tag)
        return tags

    @classmethod
    def _existing_by_key(cls, owner, keys):
        return {tag.normalized: tag for tag in cls.objects.filter(owner=owner, normalized__in=keys)}

    @classmethod
    def _create_or_fetch(cls, owner, name, key):
        # Another request may create the same tag between the read and this
        # insert. If it committed first, full_clean() sees it (ValidationError);
        # if not, the constraint does (IntegrityError). Either way the row that
        # won is the tag — first spelling wins. The savepoint keeps a failed
        # insert from breaking the caller's transaction.
        try:
            with transaction.atomic():
                return cls.objects.create(owner=owner, name=name)
        except (IntegrityError, ValidationError):
            existing = cls.objects.filter(owner=owner, normalized=key).first()
            if existing is None:
                raise
            return existing


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
    tags = models.ManyToManyField(Tag, related_name='outfits', blank=True)
    # The owner's photo of themselves wearing the outfit. RESTRICT for the same
    # reason as Garment.photo: deleting a user cascades to both their outfits and
    # their PrivateImage rows, which PROTECT would refuse, while a photo a
    # surviving outfit shows still cannot be deleted from under it.
    photo = models.OneToOneField(
        'privatemedia.PrivateImage',
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name='outfit',
    )
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
        if self.owner_id and self.photo_id and self.photo.owner_id != self.owner_id:
            raise ValidationError('An outfit can only use its owner’s photo.')

    @property
    def photo_url(self):
        """The gate URL for this outfit's photo, or None — built from photo_id, so no query."""
        if self.photo_id is None:
            return None
        return reverse('privatemedia:image', args=[self.photo_id])

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

    # Like the garment properties above, these read missing_garments.all(), so
    # a prefetch_related('missing_garments') covers them.

    @property
    def missing_count(self):
        return len(self.missing_garments.all())

    @property
    def is_incomplete(self):
        return self.missing_count > 0


class MissingGarment(models.Model):
    """A garment an outfit lost because the garment was deleted.

    It copies what the garment was, so the outfit can say what is missing and a
    replacement of the same kind can be suggested. Written by the `Garment`
    `pre_delete` receiver in `outfits/signals.py`; incompleteness cannot be
    worked out afterwards, because Django removes the link rows with the garment.

    Ownership is the outfit's: there is no `owner` field to keep consistent, so
    every lookup goes through `outfit__owner`.

    Keep this model free of signal receivers and of relations that point at it.
    Deleting an account fires each garment's `pre_delete`, which inserts rows
    for outfits the same cascade is about to delete. Without receivers Django
    removes these rows with a fast delete, a query evaluated after the inserts;
    a receiver would make it collect the rows before them, and PostgreSQL would
    then refuse the outfit delete. `test_missing_garment_model.py` pins this.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    outfit = models.ForeignKey(
        Outfit,
        on_delete=models.CASCADE,
        related_name='missing_garments',
    )
    type = models.CharField(max_length=20, choices=GarmentType.choices)
    type_other = models.CharField(max_length=40, blank=True)
    description = models.CharField(max_length=200, blank=True)
    removed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['removed_at']

    def __str__(self):
        if self.description:
            return f'{self.display_type} — {self.description}'
        return self.display_type

    @property
    def display_type(self):
        if self.type == GarmentType.OTHER:
            return self.type_other
        return self.get_type_display()
