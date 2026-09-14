"""Every guarded project route, and how to put it under the privacy contracts.

This file is the only thing a new owner-scoped view has to edit to be covered.
The net (`cross_user_visibility/test_new_guarded_route_cannot_skip_the_contract.py`)
fails until the route is registered here; once it is, every scenario file that
parametrizes over `ROUTES` exercises it with no per-route test code.

A declaration says:

- `kind`: `read` (the view only shows the owner's data) or `write` (it stores something);
- `seed(user)`: builds that user's data and returns the `reverse` kwargs plus the
  markers — names, descriptions, photo URLs, pks — that must never reach anyone else;
- `shows_photos`: whether the owner's page renders their photos as `<img src>`;
- `post_only`: the view answers POST alone (a GET is 405), so there is no page to
  inspect and scenarios probe it with a POST instead;
- `foreign_payload(seeded, requester)` (writes only): a POST body pointing at the
  seeded user's objects. `requester` is the user posting it, or `None` for an
  anonymous visitor, who has nothing of their own to mix in.

Builders write real files, so callers need the `temp_media_root` fixture.
"""

import io
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import URLPattern, get_resolver
from PIL import Image

from garments.models import GarmentType
from outfits.models import Tag
from tests.factories import make_garment, make_outfit


@dataclass(frozen=True)
class Seeded:
    kwargs: dict
    markers: list[str]
    garments: list = field(default_factory=list)
    outfits: list = field(default_factory=list)


@dataclass(frozen=True)
class OwnerScopedRoute:
    kind: Literal['read', 'write']
    seed: Callable[..., Seeded]
    shows_photos: bool
    foreign_payload: Callable[[Seeded, object], dict] | None = None
    post_only: bool = False


@dataclass(frozen=True)
class ProjectRoute:
    name: str | None
    route: str
    callback: Callable


# --- seeders -----------------------------------------------------------------


def _seed_wardrobe(user, kwargs_for=lambda garments, outfit: {}):
    """Three garments and two outfits — enough for every page to render data.

    The first outfit is tagged, carries a photo of its owner, and lost a garment,
    so it has a missing slot; the second has none of these, so the wardrobe
    renders both kinds of tile. The third garment is in no outfit, a spare to
    replace the missing one with. Every text marker carries the username, so two
    users seeded the same way never share a marker by accident.
    """
    garments = [
        make_garment(user, type=GarmentType.SHIRT, description=f'{user.username} navy oxford'),
        make_garment(user, type=GarmentType.SHOES, description=f'{user.username} brown loafers'),
    ]
    outfit = make_outfit(user, garments=garments, photo=True, name=f'{user.username} autumn walk')
    tag = Tag.objects.create(owner=user, name=f'{user.username} letnie')
    outfit.tags.add(tag)
    bare = make_outfit(user, garments=garments, name=f'{user.username} city errand')
    missing = _lose_garment(
        outfit,
        make_garment(user, type=GarmentType.ACCESSORY, description=f'{user.username} red belt'),
    )
    garments.append(
        make_garment(user, type=GarmentType.SHOES, description=f'{user.username} grey sneakers')
    )
    markers = [
        *(garment.description for garment in garments),
        *(garment.photo_url for garment in garments),
        *(str(garment.pk) for garment in garments),
        outfit.name,
        str(outfit.pk),
        outfit.get_absolute_url(),
        outfit.photo_url,
        str(outfit.photo_id),
        bare.name,
        str(bare.pk),
        tag.name,
        str(tag.pk),
        missing.description,
        str(missing.pk),
    ]
    return Seeded(
        kwargs=kwargs_for(garments, outfit),
        markers=markers,
        garments=garments,
        outfits=[outfit, bare],
    )


def _lose_garment(outfit, garment):
    """Delete a garment of the outfit through the ORM, so the rule records the slot.

    The garment's photo goes with it, file included: the seeder leaves no orphan.
    """
    outfit.garments.add(garment)
    photo = garment.photo
    garment.delete()
    photo.image.delete(save=False)
    photo.delete()
    return outfit.missing_garments.get()


def _seed_outfit_detail(user):
    return _seed_wardrobe(user, kwargs_for=lambda garments, outfit: {'pk': outfit.pk})


def _seed_outfit_tag(user):
    return _seed_wardrobe(
        user,
        kwargs_for=lambda garments, outfit: {'pk': outfit.pk, 'tag_pk': outfit.tags.get().pk},
    )


def _seed_missing_slot(user):
    return _seed_wardrobe(
        user,
        kwargs_for=lambda garments, outfit: {
            'pk': outfit.pk,
            'missing_pk': outfit.missing_garments.get().pk,
        },
    )


def _seed_garment(user):
    return _seed_wardrobe(user, kwargs_for=lambda garments, outfit: {'pk': garments[0].pk})


def _seed_photo(user):
    return _seed_wardrobe(user, kwargs_for=lambda garments, outfit: {'pk': garments[0].photo_id})


# --- hostile payloads ----------------------------------------------------------


def _photo_upload():
    buffer = io.BytesIO()
    Image.new('RGB', (64, 48), 'teal').save(buffer, format='JPEG')
    return SimpleUploadedFile('hostile-shirt.jpg', buffer.getvalue())


def _garment_add_payload(seeded, requester):
    """A valid upload that also claims the seeded user's owner, photo and garment id."""
    garment = seeded.garments[0]
    return {
        # Multipart carries both under one name: the upload in FILES, the seeded
        # user's photo pk in POST — where a model-bound `photo` field would read it.
        'photo': [_photo_upload(), str(garment.photo_id)],
        'type': GarmentType.SHIRT,
        'type_other': '',
        'description': 'posted over someone else',
        'owner': garment.owner_id,
        'id': garment.pk,
    }


def _garment_edit_payload(seeded, requester):
    """The add payload, aimed by the URL at the seeded garment: upload, owner, id and photo pk."""
    return _garment_add_payload(seeded, requester)


def _garment_delete_payload(seeded, requester):
    """The seeded user's garment is in the URL; confirming carries nothing."""
    return {}


def _compose_payload(seeded, requester):
    """The seeded user's garments, plus one of the requester's own when they have any."""
    garment_ids = [garment.pk for garment in seeded.garments]
    if requester is not None:
        own = requester.garments.first()
        if own is not None:
            garment_ids = [own.pk, garment_ids[0]]
    return {'name': 'hostile compose', 'garments': garment_ids}


def _outfit_edit_payload(seeded, requester):
    """The compose payload, aimed by the URL at the seeded user's outfit."""
    return _compose_payload(seeded, requester)


def _outfit_delete_payload(seeded, requester):
    """The seeded user's outfit is in the URL; confirming carries nothing."""
    return {}


def _missing_replace_payload(seeded, requester):
    """A replacement for the seeded user's slot: the requester's own garment, else their spare."""
    garment = seeded.garments[2]
    if requester is not None:
        garment = requester.garments.first() or garment
    return {'garment': garment.pk}


def _missing_dismiss_payload(seeded, requester):
    """The seeded user's outfit and slot are in the URL; the body carries nothing."""
    return {}


def _tags_add_payload(seeded, requester):
    """Tag names, including the seeded user's own tag spelled exactly as they typed it."""
    names = [seeded.outfits[0].tags.get().name]
    if requester is not None:
        names.insert(0, f'{requester.username} letnie')
    return {'tag_names': ', '.join(names)}


def _tag_remove_payload(seeded, requester):
    """The seeded user's outfit and tag are in the URL; the body carries nothing."""
    return {}


def _photo_upload_payload(seeded, requester):
    """A valid photo, aimed by the URL at the seeded user's outfit."""
    return {'photo': _photo_upload()}


def _photo_remove_payload(seeded, requester):
    """The seeded user's outfit is in the URL; confirming carries nothing."""
    return {}


ROUTES = {
    'wardrobe': OwnerScopedRoute(kind='read', seed=_seed_wardrobe, shows_photos=True),
    'outfits:detail': OwnerScopedRoute(kind='read', seed=_seed_outfit_detail, shows_photos=True),
    # The gate answers with the photo's bytes, not a page that embeds it.
    'privatemedia:image': OwnerScopedRoute(kind='read', seed=_seed_photo, shows_photos=False),
    'garments:list': OwnerScopedRoute(kind='read', seed=_seed_wardrobe, shows_photos=True),
    'garments:add': OwnerScopedRoute(
        kind='write',
        seed=_seed_wardrobe,
        shows_photos=False,
        foreign_payload=_garment_add_payload,
    ),
    # Both pages show the garment's photo.
    'garments:edit': OwnerScopedRoute(
        kind='write',
        seed=_seed_garment,
        shows_photos=True,
        foreign_payload=_garment_edit_payload,
    ),
    'garments:delete': OwnerScopedRoute(
        kind='write',
        seed=_seed_garment,
        shows_photos=True,
        foreign_payload=_garment_delete_payload,
    ),
    'outfits:compose': OwnerScopedRoute(
        kind='write',
        seed=_seed_wardrobe,
        shows_photos=True,
        foreign_payload=_compose_payload,
    ),
    # The picker shows the owner's garment photos.
    'outfits:edit': OwnerScopedRoute(
        kind='write',
        seed=_seed_outfit_detail,
        shows_photos=True,
        foreign_payload=_outfit_edit_payload,
    ),
    'outfits:delete': OwnerScopedRoute(
        kind='write',
        seed=_seed_outfit_detail,
        shows_photos=False,
        foreign_payload=_outfit_delete_payload,
    ),
    'outfits:tags_add': OwnerScopedRoute(
        kind='write',
        seed=_seed_outfit_detail,
        shows_photos=False,
        foreign_payload=_tags_add_payload,
        post_only=True,
    ),
    'outfits:tag_remove': OwnerScopedRoute(
        kind='write',
        seed=_seed_outfit_tag,
        shows_photos=False,
        foreign_payload=_tag_remove_payload,
        post_only=True,
    ),
    'outfits:photo_upload': OwnerScopedRoute(
        kind='write',
        seed=_seed_outfit_detail,
        shows_photos=False,
        foreign_payload=_photo_upload_payload,
        post_only=True,
    ),
    # The confirmation page shows the photo that is about to be removed.
    'outfits:photo_remove': OwnerScopedRoute(
        kind='write',
        seed=_seed_outfit_detail,
        shows_photos=True,
        foreign_payload=_photo_remove_payload,
    ),
    # The picker shows the owner's garment photos.
    'outfits:missing_replace': OwnerScopedRoute(
        kind='write',
        seed=_seed_missing_slot,
        shows_photos=True,
        foreign_payload=_missing_replace_payload,
    ),
    'outfits:missing_dismiss': OwnerScopedRoute(
        kind='write',
        seed=_seed_missing_slot,
        shows_photos=False,
        foreign_payload=_missing_dismiss_payload,
        post_only=True,
    ),
}


# --- the resolver ----------------------------------------------------------------


def _is_project_code(callback):
    path = Path(sys.modules[callback.__module__].__file__).resolve()
    return path.is_relative_to(settings.BASE_DIR) and 'site-packages' not in path.parts


def _walk(patterns, namespaces=(), prefix=''):
    for entry in patterns:
        route = prefix + str(entry.pattern)
        if isinstance(entry, URLPattern):
            name = ':'.join([*namespaces, entry.name]) if entry.name else None
            yield ProjectRoute(name=name, route=route, callback=entry.callback)
        else:
            inner = (*namespaces, entry.namespace) if entry.namespace else namespaces
            yield from _walk(entry.url_patterns, inner, route)


def project_routes() -> Iterator[ProjectRoute]:
    """Every route whose view lives in this repository, named as `reverse` expects.

    Third-party views (admin, allauth) are left out: their access rules are theirs
    to test (test-plan §7).
    """
    for route in _walk(get_resolver().url_patterns):
        if _is_project_code(route.callback):
            yield route


def is_guarded(callback):
    """Closed to anonymous visitors: `LoginRequiredMiddleware` reads exactly this."""
    return getattr(callback, 'login_required', True) is not False
