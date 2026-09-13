"""A user's garment list and the flow that adds one."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render

from garments.forms import GarmentForm
from garments.models import Garment
from privatemedia.models import PrivateImage


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


def _store_garment(owner, form):
    """Store the photo and the garment together, or leave nothing behind.

    The file is written to the volume during the PrivateImage insert, before the
    garment exists. A rollback removes rows but never bytes, so any failure
    after the write deletes the file explicitly before re-raising.
    """
    image = PrivateImage(
        owner=owner,
        image=form.cleaned_data['photo'],
        original_filename=form.original_filename,
    )
    try:
        with transaction.atomic():
            image.save()
            garment = form.save(commit=False)
            garment.owner = owner
            garment.photo = image
            garment.save()
    except BaseException:
        # _committed turns True once storage has written the file, which also
        # covers an insert that failed after the write.
        if image.image._committed:
            image.image.delete(save=False)
        raise
    return garment
