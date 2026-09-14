"""The wardrobe grid, and composing, editing, deleting, tagging and photographing outfits."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import urlencode
from django.views.decorators.http import require_http_methods, require_POST

from garments.models import Garment
from outfits.forms import MIN_GARMENTS, AddTagsForm, OutfitEditForm, OutfitForm, OutfitPhotoForm
from outfits.models import Outfit, Tag
from privatemedia.models import discard_private_image, stored_private_image


class OutfitNameTaken(Exception):
    """A typed name that was free when the form validated is taken at save time."""


@login_required
def wardrobe(request):
    """The owner's outfits carrying every tag in `?tag=`, and a bar to change that.

    A constant number of queries however many outfits, garments, tags or
    selections there are: one to resolve the selected tags (none without a
    filter), the outfits, and one prefetch each of garments and tags. Preview
    order and the tag bar are computed in Python from the prefetched rows.
    """
    # Typed values keyed by identity, first spelling kept: `letnie` and
    # ` LETNIE ` in one query string are one selection.
    typed = {}
    for value in request.GET.getlist('tag'):
        key = Tag.normalize(value)
        if key:
            typed.setdefault(key, ' '.join(value.split()))

    resolved = {}
    if typed:
        # Resolved against the requester's tags only: another user's `letnie`
        # is never a match, so it can only yield an empty grid.
        resolved = {
            tag.normalized: tag
            for tag in Tag.objects.filter(owner=request.user, normalized__in=typed)
        }

    outfits = Outfit.objects.filter(owner=request.user)
    if len(resolved) < len(typed):
        # A tag the user does not have matches no outfit; still listed as
        # selected below so it can be dropped.
        outfits = outfits.none()
    for tag in resolved.values():
        # One filter per tag, so each gets its own join: AND, not OR.
        outfits = outfits.filter(tags=tag)
    outfits = list(outfits.prefetch_related('garments', 'tags'))

    selected_values = [resolved[key].name if key in resolved else typed[key] for key in typed]
    selected = [
        {
            'name': value,
            'url': _wardrobe_url(selected_values[:index] + selected_values[index + 1 :]),
        }
        for index, value in enumerate(selected_values)
    ]
    # Only tags on the outfits on screen: every one of them keeps at least one
    # outfit in view, so the bar never offers a dead end.
    on_screen = {tag.pk: tag for outfit in outfits for tag in outfit.tags.all()}
    available = [
        {'name': tag.name, 'url': _wardrobe_url([*selected_values, tag.name])}
        for tag in sorted(on_screen.values(), key=lambda tag: tag.normalized)
        if tag.normalized not in typed
    ]

    can_compose = Garment.objects.filter(owner=request.user).count() >= MIN_GARMENTS
    return render(
        request,
        'outfits/wardrobe.html',
        {
            'outfits': outfits,
            'can_compose': can_compose,
            'selected': selected,
            'available': available,
            'filtering': bool(typed),
        },
    )


def _wardrobe_url(tag_names):
    url = reverse('wardrobe')
    return f'{url}?{urlencode({"tag": tag_names}, doseq=True)}' if tag_names else url


@login_required
def outfit_compose(request):
    garment_count = Garment.objects.filter(owner=request.user).count()
    if garment_count < MIN_GARMENTS:
        return render(request, 'outfits/compose.html', {'form': None})

    if request.method == 'POST':
        form = OutfitForm(request.POST, owner=request.user)
        if form.is_valid():
            try:
                outfit = _store_outfit(form)
            except OutfitNameTaken:
                form.add_error('name', 'You already have an outfit with this name.')
            else:
                messages.success(request, 'Outfit saved.')
                # Its page, not the wardrobe: adding the photo is the next step.
                return redirect(outfit)
    else:
        form = OutfitForm(owner=request.user)
    return render(request, 'outfits/compose.html', {'form': form})


@login_required
@require_http_methods(['GET', 'POST'])
def outfit_edit(request, pk):
    """Change the outfit's name and garments; its tags, photo and missing slots stay."""
    # Ownership before the form: a stranger's garment ids are never validated.
    outfit = _owned_outfit(request, pk)
    form = OutfitEditForm(request.POST or None, owner=request.user, instance=outfit)
    if form.is_bound and form.is_valid():
        try:
            _store_outfit(form)
        except OutfitNameTaken:
            form.add_error('name', 'You already have an outfit with this name.')
        else:
            messages.success(request, 'Outfit updated.')
            return redirect(outfit)
    return render(request, 'outfits/edit.html', {'form': form, 'outfit': outfit})


@login_required
@require_http_methods(['GET', 'POST'])
def outfit_delete(request, pk):
    """Confirm, then delete the outfit and its photo; its garments stay."""
    outfit = _owned_outfit(request, pk)
    if request.method == 'POST':
        _delete_outfit(request.user, pk)
        messages.success(request, 'Outfit deleted.')
        return redirect('wardrobe')
    return render(request, 'outfits/delete.html', {'outfit': outfit})


@login_required
def outfit_detail(request, pk):
    outfit = _owned_outfit(request, pk)
    return _render_detail(request, outfit, AddTagsForm(outfit=outfit))


@login_required
@require_POST
def outfit_tags_add(request, pk):
    outfit = _owned_outfit(request, pk)
    form = AddTagsForm(request.POST, outfit=outfit)
    if not form.is_valid():
        return _render_detail(request, outfit, form)
    with transaction.atomic():
        outfit.tags.add(*Tag.resolve(request.user, form.cleaned_data['tag_names']))
    messages.success(request, 'Tags added.')
    return redirect(outfit)


@login_required
@require_POST
def outfit_tag_remove(request, pk, tag_pk):
    outfit = get_object_or_404(Outfit, pk=pk, owner=request.user)
    # Looked up through this outfit's tags: another user's tag and an own tag
    # this outfit does not carry are the same 404 as another user's outfit.
    tag = get_object_or_404(outfit.tags, pk=tag_pk)
    outfit.tags.remove(tag)
    messages.success(request, 'Tag removed.')
    return redirect(outfit)


@login_required
@require_POST
def outfit_photo_upload(request, pk):
    """Add the outfit's photo, or replace the one it has."""
    # Ownership before the form: a stranger's upload is refused without the
    # server ever decoding it.
    outfit = _owned_outfit(request, pk)
    form = OutfitPhotoForm(request.POST, request.FILES)
    if not form.is_valid():
        return _render_detail(request, outfit, AddTagsForm(outfit=outfit), photo_form=form)
    replaced = _store_outfit_photo(request.user, pk, form)
    messages.success(request, 'Photo replaced.' if replaced else 'Photo added.')
    return redirect(outfit)


@login_required
@require_http_methods(['GET', 'POST'])
def outfit_photo_remove(request, pk):
    """Confirm, then remove the outfit's photo; the outfit and its garments stay."""
    outfit = get_object_or_404(Outfit, pk=pk, owner=request.user)
    # Nothing to remove — a stale tab or a second tap on confirm — is not an error.
    if outfit.photo_id is None:
        return redirect(outfit)
    if request.method == 'POST':
        if _remove_outfit_photo(request.user, pk):
            messages.success(request, 'Photo removed.')
        return redirect(outfit)
    return render(request, 'outfits/photo_remove.html', {'outfit': outfit})


def _owned_outfit(request, pk):
    # One 404 for "no such outfit" and "not your outfit": the URL space must not
    # reveal which ids exist.
    return get_object_or_404(
        Outfit.objects.prefetch_related('garments', 'tags'), pk=pk, owner=request.user
    )


def _render_detail(request, outfit, form, photo_form=None):
    # Suggestions for the tag input: the owner's tags in use elsewhere. The
    # outfit's own tags come from the prefetch, so this is one query.
    suggested_tags = (
        Tag.objects.filter(owner=request.user, outfits__isnull=False)
        .exclude(pk__in=[tag.pk for tag in outfit.tags.all()])
        .distinct()
    )
    return render(
        request,
        'outfits/detail.html',
        {
            'outfit': outfit,
            'tag_form': form,
            'photo_form': photo_form or OutfitPhotoForm(),
            'suggested_tags': suggested_tags,
        },
    )


def _locked_outfit(owner, pk):
    # The row lock (real on PostgreSQL, a no-op on SQLite) makes two concurrent
    # uploads or removes take turns, so each one retires exactly the photo it
    # replaced. Re-checks ownership: this is the row that gets written.
    return get_object_or_404(Outfit.objects.select_for_update(), pk=pk, owner=owner)


@transaction.atomic
def _store_outfit_photo(owner, pk, form):
    """Link a newly stored photo to the outfit and retire the previous one.

    Returns whether a photo was replaced. If anything fails, the new file is
    removed and the rollback restores the old row; the old file is only
    deleted once this commits.
    """
    outfit = _locked_outfit(owner, pk)
    previous = outfit.photo
    photo = form.cleaned_data['photo']
    with stored_private_image(owner, photo, form.original_filename) as image:
        outfit.photo = image
        outfit.save()
        if previous is not None:
            discard_private_image(previous)
    return previous is not None


@transaction.atomic
def _remove_outfit_photo(owner, pk):
    """Unlink and retire the outfit's photo; returns whether there was one."""
    outfit = _locked_outfit(owner, pk)
    previous = outfit.photo
    if previous is None:
        return False
    # Unlinked first: Outfit.photo is RESTRICT, so the image row cannot go while
    # the outfit still points at it.
    outfit.photo = None
    outfit.save()
    discard_private_image(previous)
    return True


@transaction.atomic
def _delete_outfit(owner, pk):
    """Delete the outfit, then retire its photo.

    Its missing slots cascade with it, and the post_delete receiver in
    outfits.signals deletes the tags no other outfit carries. The photo goes
    last: Outfit.photo is RESTRICT, so the image row cannot go while the outfit
    still points at it.
    """
    outfit = _locked_outfit(owner, pk)
    photo = outfit.photo
    outfit.delete()
    if photo is not None:
        discard_private_image(photo)


@transaction.atomic
def _store_outfit(form):
    """Store the outfit with its garments and tags together, or leave nothing behind.

    Composing and editing share it. The edit form carries no tags, so an edit
    leaves the outfit's tags as they are.

    Two unnamed saves in parallel can both compute the same `outfit-N`. The
    row insert runs in its own savepoint; if the name is refused — by the
    database constraint, or by full_clean() when the other row committed first
    — and the name was auto-assigned, it is recomputed once. A typed name that
    lost the same race is reported back to the form instead.
    """
    outfit = form.save(commit=False)
    auto_named = form.cleaned_data['name'] == ''
    try:
        with transaction.atomic():
            outfit.save()
    except (IntegrityError, ValidationError):
        if not auto_named:
            raise OutfitNameTaken from None
        outfit.name = ''
        outfit.save()
    form.save_m2m()
    if 'tag_names' in form.cleaned_data:
        outfit.tags.set(Tag.resolve(outfit.owner, form.cleaned_data['tag_names']))
    return outfit
