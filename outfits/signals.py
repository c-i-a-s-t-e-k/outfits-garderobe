"""The rules that hold on an outfit's garments and tags, on every path.

Many-to-many writes (`.add()`, `.set()`, `.remove()`, `.clear()`, the admin
form) never call `Outfit.save()`, so `full_clean()` cannot see them.
`m2m_changed` fires for all of them:

- `pre_add`, before the link rows are written, refuses another user's garment
  or tag, from either side of the relation.
- `post_remove` and `post_clear` delete the owner's tags that no outfit carries
  any more, so a user's tag list is exactly the tags in use.

Deleting an outfit removes its tag links without `m2m_changed`, so an `Outfit`
`post_delete` receiver runs the same cleanup; by then the links are gone.
"""

from django.core.exceptions import ValidationError
from django.db.models.signals import m2m_changed, post_delete
from django.dispatch import receiver

from garments.models import Garment
from outfits.models import Outfit, Tag


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


@receiver(m2m_changed, sender=Outfit.tags.through)
def refuse_foreign_tags(sender, instance, action, reverse, pk_set, **kwargs):
    if action != 'pre_add' or not pk_set:
        return
    if reverse:
        # instance is a Tag, pk_set holds outfit ids.
        foreign = Outfit.objects.filter(pk__in=pk_set).exclude(owner_id=instance.owner_id)
    else:
        # instance is an Outfit, pk_set holds tag ids.
        foreign = Tag.objects.filter(pk__in=pk_set).exclude(owner_id=instance.owner_id)
    if foreign.exists():
        raise ValidationError('An outfit can only carry its owner’s tags.')


def _delete_unused_tags(owner_id):
    Tag.objects.filter(owner_id=owner_id, outfits__isnull=True).delete()


@receiver(m2m_changed, sender=Outfit.tags.through)
def delete_tags_left_unused_by_unlinking(sender, instance, action, **kwargs):
    if action in ('post_remove', 'post_clear'):
        # Tags and outfits share one owner (see refuse_foreign_tags), so the
        # instance's owner is the owner on either side.
        _delete_unused_tags(instance.owner_id)


@receiver(post_delete, sender=Outfit)
def delete_tags_left_unused_by_outfit_delete(sender, instance, **kwargs):
    _delete_unused_tags(instance.owner_id)
