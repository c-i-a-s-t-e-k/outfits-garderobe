"""A garment: one private photo, what kind of clothing it shows, and whose it is."""

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse

from privatemedia.models import PrivateImage


class GarmentType(models.TextChoices):
    TSHIRT = 'tshirt', 'T-shirt'
    SHIRT = 'shirt', 'Shirt'
    SWEATER = 'sweater', 'Sweater'
    OUTERWEAR = 'outerwear', 'Jacket / coat'
    TROUSERS = 'trousers', 'Trousers'
    SHORTS = 'shorts', 'Shorts'
    SKIRT = 'skirt', 'Skirt'
    DRESS = 'dress', 'Dress'
    SHOES = 'shoes', 'Shoes'
    ACCESSORY = 'accessory', 'Accessory'
    OTHER = 'other', 'Other'


class Garment(models.Model):
    """One piece of clothing in a user's wardrobe.

    S-03's outfits reference this model many-to-many: a garment belongs to any
    number of outfits. The photo lives in privatemedia, so the ownership check
    that guards it is the gate's, not restated here.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='garments',
    )
    # RESTRICT, not PROTECT: deleting a user cascades to both their garments and
    # their PrivateImage rows, and PROTECT would refuse that even though the
    # garment is going too. RESTRICT allows exactly that case while still
    # refusing to delete a photo a surviving garment shows.
    photo = models.OneToOneField(
        PrivateImage,
        on_delete=models.RESTRICT,
        related_name='garment',
    )
    type = models.CharField(max_length=20, choices=GarmentType.choices)
    # Free text only for GarmentType.OTHER — enforced by clean() and, against
    # bulk updates that skip it, by the check constraint below.
    type_other = models.CharField(max_length=40, blank=True)
    description = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['owner', '-created_at'])]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(type=GarmentType.OTHER) & ~models.Q(type_other='')
                    | ~models.Q(type=GarmentType.OTHER) & models.Q(type_other='')
                ),
                name='garment_type_other_matches_type',
                violation_error_message='Only the Other type carries custom text.',
            ),
        ]

    def __str__(self):
        if self.description:
            return f'{self.display_type} — {self.description}'
        return self.display_type

    def save(self, *args, **kwargs):
        # Same reasoning as PrivateImage.save(): Django validates only through
        # ModelForm, so the type rules and the owner check would not hold on a
        # plain objects.create() without this.
        self.full_clean()
        super().save(*args, **kwargs)

    def clean(self):
        self.type_other = ' '.join(self.type_other.split())
        self.description = self.description.strip()

        if self.type != GarmentType.OTHER:
            self.type_other = ''
        else:
            # "Shirt" typed under Other must not exist alongside the Shirt
            # choice, or a future filter by type would silently miss it.
            typed = self.type_other.casefold()
            for choice in GarmentType:
                if choice == GarmentType.OTHER:
                    continue
                if typed in (choice.value.casefold(), choice.label.casefold()):
                    self.type = choice.value
                    self.type_other = ''
                    break
            if self.type == GarmentType.OTHER and not self.type_other:
                raise ValidationError({'type_other': 'Name the type of garment.'})

        # A ModelForm runs clean() before the view has set owner and photo, so
        # the check can only apply once both are known.
        if self.owner_id and self.photo_id and self.photo.owner_id != self.owner_id:
            raise ValidationError('A garment can only use its owner’s photo.')

    @property
    def display_type(self):
        if self.type == GarmentType.OTHER:
            return self.type_other
        return self.get_type_display()

    @property
    def photo_url(self):
        """The gate URL for this garment's photo — built from photo_id, so no query."""
        return reverse('privatemedia:image', args=[self.photo_id])
