"""The wardrobe grid, composing, reading and tagging an outfit — for its owner only."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from garments.models import Garment
from outfits.forms import MIN_GARMENTS, AddTagsForm, OutfitForm
from outfits.models import Outfit, Tag


class OutfitNameTaken(Exception):
    """A typed name that was free when the form validated is taken at save time."""


@login_required
def wardrobe(request):
    # Two queries however many outfits and garments there are: the outfits and
    # one prefetch of their garments. Preview order is computed in Python, and
    # each tile's images are photo_url, which needs no photo row.
    outfits = Outfit.objects.filter(owner=request.user).prefetch_related('garments')
    can_compose = Garment.objects.filter(owner=request.user).count() >= MIN_GARMENTS
    return render(
        request, 'outfits/wardrobe.html', {'outfits': outfits, 'can_compose': can_compose}
    )


@login_required
def outfit_compose(request):
    garment_count = Garment.objects.filter(owner=request.user).count()
    if garment_count < MIN_GARMENTS:
        return render(request, 'outfits/compose.html', {'form': None})

    if request.method == 'POST':
        form = OutfitForm(request.POST, owner=request.user)
        if form.is_valid():
            try:
                _store_outfit(form)
            except OutfitNameTaken:
                form.add_error('name', 'You already have an outfit with this name.')
            else:
                messages.success(request, 'Outfit saved.')
                return redirect('wardrobe')
    else:
        form = OutfitForm(owner=request.user)
    return render(request, 'outfits/compose.html', {'form': form})


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


def _owned_outfit(request, pk):
    # One 404 for "no such outfit" and "not your outfit": the URL space must not
    # reveal which ids exist.
    return get_object_or_404(
        Outfit.objects.prefetch_related('garments', 'tags'), pk=pk, owner=request.user
    )


def _render_detail(request, outfit, form):
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
        {'outfit': outfit, 'tag_form': form, 'suggested_tags': suggested_tags},
    )


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
