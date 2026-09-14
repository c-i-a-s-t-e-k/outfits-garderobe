"""The wardrobe grid; composing, editing, deleting, tagging, photographing and repairing outfits."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import urlencode
from django.views.decorators.http import require_http_methods, require_POST

from garments.models import Garment
from outfits.forms import (
    MIN_GARMENTS,
    AddTagsForm,
    OutfitEditForm,
    OutfitForm,
    OutfitPhotoForm,
    ReplaceMissingGarmentForm,
)
from outfits.models import Outfit, Tag
from privatemedia.models import discard_private_image, stored_private_image


class OutfitNameTaken(Exception):
    """A typed name that was free when the form validated is taken at save time."""


@login_required
def wardrobe(request):
    """The owner's outfits carrying every tag in `?tag=`, and a bar to change that.

    `?incomplete=1` narrows them further to outfits with a missing garment. Above
    the bar, a notice counts every incomplete outfit, whatever the filters.

    A constant number of queries however many outfits, garments, tags, missing
    slots or selections there are: one to resolve the selected tags (none
    without a filter), the outfits, one prefetch each of garments, tags and
    missing slots, and the incomplete count (none while that filter is on).
    Preview order, badges and the tag bar come from the prefetched rows.
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

    only_incomplete = request.GET.get('incomplete') == '1'

    outfits = Outfit.objects.filter(owner=request.user)
    if len(resolved) < len(typed):
        # A tag the user does not have matches no outfit; still listed as
        # selected below so it can be dropped.
        outfits = outfits.none()
    for tag in resolved.values():
        # One filter per tag, so each gets its own join: AND, not OR.
        outfits = outfits.filter(tags=tag)
    if only_incomplete:
        outfits = outfits.filter(missing_garments__isnull=False).distinct()
    outfits = list(outfits.prefetch_related('garments', 'tags', 'missing_garments'))

    selected_values = [resolved[key].name if key in resolved else typed[key] for key in typed]
    selected = [
        {
            'name': value,
            'url': _wardrobe_url(
                selected_values[:index] + selected_values[index + 1 :], only_incomplete
            ),
        }
        for index, value in enumerate(selected_values)
    ]
    # Only tags on the outfits on screen: every one of them keeps at least one
    # outfit in view, so the bar never offers a dead end.
    on_screen = {tag.pk: tag for outfit in outfits for tag in outfit.tags.all()}
    available = [
        {'name': tag.name, 'url': _wardrobe_url([*selected_values, tag.name], only_incomplete)}
        for tag in sorted(on_screen.values(), key=lambda tag: tag.normalized)
        if tag.normalized not in typed
    ]

    incomplete_count = 0
    if not only_incomplete:
        # The notice is hidden while the filter is on, so the count is skipped.
        incomplete_count = (
            Outfit.objects.filter(owner=request.user, missing_garments__isnull=False)
            .distinct()
            .count()
        )

    can_compose = Garment.objects.filter(owner=request.user).count() >= MIN_GARMENTS
    return render(
        request,
        'outfits/wardrobe.html',
        {
            'outfits': outfits,
            'can_compose': can_compose,
            'selected': selected,
            'available': available,
            'only_incomplete': only_incomplete,
            'incomplete_count': incomplete_count,
            'show_incomplete_url': _wardrobe_url(selected_values, incomplete=True),
            'drop_incomplete_url': _wardrobe_url(selected_values),
            'filtering': bool(typed) or only_incomplete,
        },
    )


def _wardrobe_url(tag_names, incomplete=False):
    params = {'tag': tag_names} if tag_names else {}
    if incomplete:
        params['incomplete'] = 1
    url = reverse('wardrobe')
    return f'{url}?{urlencode(params, doseq=True)}' if params else url


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
    if request.method == 'POST':
        form = OutfitEditForm(request.POST, owner=request.user, instance=outfit)
        if form.is_valid():
            try:
                _update_outfit(request.user, pk, form)
            except OutfitNameTaken:
                form.add_error('name', 'You already have an outfit with this name.')
            else:
                messages.success(request, 'Outfit updated.')
                return redirect(outfit)
    else:
        form = OutfitEditForm(owner=request.user, instance=outfit)
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


@login_required
@require_http_methods(['GET', 'POST'])
def outfit_missing_replace(request, pk, missing_pk):
    """Fill one missing slot with another of the owner's garments."""
    # Ownership first: a stranger gets the same 404 whether or not the slot exists.
    outfit = _owned_outfit(request, pk)
    missing = next((slot for slot in outfit.missing_garments.all() if slot.pk == missing_pk), None)
    # Already closed — a second tab or a double tap — is not an error.
    if missing is None:
        return redirect(outfit)
    if request.method == 'POST':
        form = ReplaceMissingGarmentForm(request.POST, outfit=outfit, missing=missing)
        if form.is_valid():
            with transaction.atomic():
                slot = _locked_slot(outfit, missing_pk)
                if slot is None:
                    return redirect(outfit)
                outfit.garments.add(form.cleaned_data['garment'])
                slot.delete()
            messages.success(request, 'Garment added to the outfit.')
            return redirect(outfit)
    else:
        form = ReplaceMissingGarmentForm(outfit=outfit, missing=missing)
    return render(
        request,
        'outfits/missing_replace.html',
        {'outfit': outfit, 'missing': missing, 'form': form},
    )


@login_required
@require_POST
def outfit_missing_dismiss(request, pk, missing_pk):
    """Close one missing slot without adding anything, unless nothing would be left."""
    outfit = _owned_outfit(request, pk)
    with transaction.atomic():
        slot = _locked_slot(outfit, missing_pk)
        if slot is None:
            return redirect(outfit)
        if not outfit.garments.exists():
            messages.error(request, 'An outfit with no garments needs a replacement or deletion.')
            return redirect(outfit)
        slot.delete()
    messages.success(request, 'Outfit kept without it.')
    return redirect(outfit)


def _locked_slot(outfit, missing_pk):
    # Looked up through the outfit, so only its own slots match; the lock makes
    # a replace and a dismiss of the same slot take turns, and the loser finds
    # it gone.
    return outfit.missing_garments.select_for_update().filter(pk=missing_pk).first()


def _owned_outfit(request, pk):
    # One 404 for "no such outfit" and "not your outfit": the URL space must not
    # reveal which ids exist.
    return get_object_or_404(
        Outfit.objects.prefetch_related('garments', 'tags', 'missing_garments'),
        pk=pk,
        owner=request.user,
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
    outfit.tags.set(Tag.resolve(outfit.owner, form.cleaned_data['tag_names']))
    return outfit


@transaction.atomic
def _update_outfit(owner, pk, form):
    """Write an edit's name and garments onto the outfit as it is now.

    The form's instance was read before validation, and saving it would write
    back every column as it was then: a photo another tab has since replaced,
    or, when the outfit was deleted meanwhile, the whole outfit again. So the
    row is re-read under the lock (404 when it is gone) and only the edited
    fields are copied onto it.
    """
    outfit = _locked_outfit(owner, pk)
    outfit.name = form.cleaned_data['name']
    try:
        with transaction.atomic():
            outfit.save()
    except (IntegrityError, ValidationError):
        # A fresh row keeps its own photo and a non-empty name, so only a name
        # taken since the form validated can be refused here.
        raise OutfitNameTaken from None
    outfit.garments.set(form.cleaned_data['garments'])
    return outfit
