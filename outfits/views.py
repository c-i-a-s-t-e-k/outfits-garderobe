"""The wardrobe grid, composing an outfit and reading one back — for its owner only."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render

from garments.models import Garment
from outfits.forms import MIN_GARMENTS, OutfitForm
from outfits.models import Outfit


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
    # One 404 for "no such outfit" and "not your outfit": the URL space must not
    # reveal which ids exist.
    outfit = get_object_or_404(
        Outfit.objects.prefetch_related('garments'), pk=pk, owner=request.user
    )
    return render(request, 'outfits/detail.html', {'outfit': outfit})


@transaction.atomic
def _store_outfit(form):
    """Store the outfit and its garments together, or leave nothing behind.

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
    return outfit
