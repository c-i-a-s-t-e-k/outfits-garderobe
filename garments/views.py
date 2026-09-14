"""A user's garment list, and adding, editing and deleting a garment — for its owner only."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from garments.forms import GarmentEditForm, GarmentForm
from garments.models import Garment
from privatemedia.models import discard_private_image, stored_private_image


@login_required
def garment_list(request):
    # One query however many garments there are: tiles read photo_url, which is
    # built from photo_id without fetching the PrivateImage row.
    garments = Garment.objects.filter(owner=request.user)
    return render(request, 'garments/list.html', {'garments': garments})


@login_required
def garment_add(request):
    if request.method == 'POST':
        form = GarmentForm(request.POST, request.FILES)
        if form.is_valid():
            _store_garment(request.user, form)
            messages.success(request, 'Garment added.')
            return redirect('garments:list')
    else:
        form = GarmentForm()
    return render(request, 'garments/add.html', {'form': form})


@login_required
@require_http_methods(['GET', 'POST'])
def garment_edit(request, pk):
    """Change the garment's fields, and replace its photo when a new one is picked."""
    # Ownership before the form: a stranger's upload is refused without the
    # server ever decoding it.
    garment = _owned_garment(request, pk)
    if request.method == 'POST':
        form = GarmentEditForm(request.POST, request.FILES, instance=garment)
        if form.is_valid():
            if form.cleaned_data['photo'] is None:
                form.save()
            else:
                _replace_garment_photo(request.user, form)
            messages.success(request, 'Garment updated.')
            return redirect('garments:list')
    else:
        form = GarmentEditForm(instance=garment)
    return render(request, 'garments/edit.html', {'form': form, 'garment': garment})


@login_required
@require_http_methods(['GET', 'POST'])
def garment_delete(request, pk):
    """Confirm, then delete the garment and its photo; its outfits stay, marked incomplete."""
    garment = _owned_garment(request, pk)
    if request.method == 'POST':
        affected = _delete_garment(request.user, pk)
        message = 'Garment deleted.'
        if affected == 1:
            message += ' 1 outfit is now incomplete.'
        elif affected:
            message += f' {affected} outfits are now incomplete.'
        messages.success(request, message)
        return redirect('garments:list')
    affected_outfits = list(garment.outfits.values_list('name', flat=True))
    return render(
        request,
        'garments/delete.html',
        {'garment': garment, 'affected_outfits': affected_outfits},
    )


def _owned_garment(request, pk):
    # One 404 for "no such garment" and "not your garment": the URL space must
    # not reveal which ids exist.
    return get_object_or_404(Garment.objects.select_related('photo'), pk=pk, owner=request.user)


def _locked_garment(owner, pk):
    # The row lock (real on PostgreSQL, a no-op on SQLite) makes two concurrent
    # replaces or deletes take turns, so each one retires exactly the photo it
    # replaced. Re-checks ownership: this is the row that gets written.
    return get_object_or_404(
        Garment.objects.select_for_update().select_related('photo'), pk=pk, owner=owner
    )


def _store_garment(owner, form):
    """Store the photo and the garment together, or leave nothing behind."""
    photo = form.cleaned_data['photo']
    with stored_private_image(owner, photo, form.original_filename) as image:
        garment = form.save(commit=False)
        garment.owner = owner
        garment.photo = image
        garment.save()
    return garment


@transaction.atomic
def _replace_garment_photo(owner, form):
    """Link a newly stored photo to the garment and retire the previous one.

    If anything fails, the new file is removed and the rollback restores the old
    row; the old file is only deleted once this commits.
    """
    previous = _locked_garment(owner, form.instance.pk).photo
    photo = form.cleaned_data['photo']
    with stored_private_image(owner, photo, form.original_filename) as image:
        garment = form.save(commit=False)
        # Repointed before the discard: Garment.photo is RESTRICT, so the old
        # image row cannot go while the garment still points at it.
        garment.photo = image
        garment.save()
        discard_private_image(previous)
    return garment


@transaction.atomic
def _delete_garment(owner, pk):
    """Delete the garment, then retire its photo; returns how many outfits it left incomplete.

    The pre_delete receiver in outfits.signals records the loss on each outfit
    before Django removes the link rows. The photo goes last for the same
    RESTRICT reason as in _replace_garment_photo().
    """
    garment = _locked_garment(owner, pk)
    photo = garment.photo
    affected = garment.outfits.count()
    garment.delete()
    discard_private_image(photo)
    return affected
