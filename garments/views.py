"""A user's garment list and the flow that adds one."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from garments.forms import GarmentForm
from garments.models import Garment
from privatemedia.models import stored_private_image


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
    """Store the photo and the garment together, or leave nothing behind."""
    photo = form.cleaned_data['photo']
    with stored_private_image(owner, photo, form.original_filename) as image:
        garment = form.save(commit=False)
        garment.owner = owner
        garment.photo = image
        garment.save()
    return garment
