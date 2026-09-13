"""The rule that keeps another user's garment out of an outfit, on every path.

Many-to-many writes (`.add()`, `.set()`, the admin form) never call
`Outfit.save()`, so `full_clean()` cannot see them. `m2m_changed` fires for all
of them, before the link rows are written.
"""

from django.core.exceptions import ValidationError
from django.db.models.signals import m2m_changed
from django.dispatch import receiver

from garments.models import Garment
from outfits.models import Outfit


@receiver(m2m_changed, sender=Outfit.garments.through)
def refuse_foreign_garments(sender, instance, action, reverse, pk_set, **kwargs):
    if action != 'pre_add' or not pk_set:
        return
    if reverse:
        # instance is a Garment, pk_set holds outfit ids.
        foreign = Outfit.objects.filter(pk__in=pk_set).exclude(owner_id=instance.owner_id)
    else:
        # instance is an Outfit, pk_set holds garment ids.
        foreign = Garment.objects.filter(pk__in=pk_set).exclude(owner_id=instance.owner_id)
    if foreign.exists():
        raise ValidationError('An outfit can only contain its owner’s garments.')
