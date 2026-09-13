"""The add-garment form: a photo plus the garment's own fields."""

from django import forms

from garments.models import Garment, GarmentType
from privatemedia.processing import normalize_photo
from privatemedia.validators import validate_max_size


class GarmentForm(forms.ModelForm):
    # Not a model field: the view turns the normalized file into a PrivateImage
    # and links it, so owner and photo never come from the request.
    # No `capture` attribute — with it, phones offer only the camera and hide
    # the photo library. data-shrink-photo hands the input to
    # static/js/photo-shrink.js, which only ever swaps in a smaller file.
    # A FileField, not an ImageField: ImageField opens the upload itself and
    # reports every failure — too many pixels included — as "not an image", so
    # recognising the image is left to normalize_photo, which says what went wrong.
    photo = forms.FileField(
        widget=forms.FileInput(attrs={'accept': 'image/*', 'data-shrink-photo': True})
    )

    field_order = ['photo', 'type', 'type_other', 'description']

    class Meta:
        model = Garment
        fields = ['type', 'type_other', 'description']
        labels = {
            'type': 'Type',
            'type_other': 'Type name',
            'description': 'Description (optional)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['type'].choices = [('', 'Choose a type'), *GarmentType.choices]
        # Set by clean_photo(): normalization renames the file to photo.jpg, so
        # the name the user picked has to be carried to the view separately.
        self.original_filename = ''

    def clean_photo(self):
        upload = self.cleaned_data['photo']
        # Before decoding, so a 20 MB file is refused without being processed.
        validate_max_size(upload)
        normalized = normalize_photo(upload)
        self.original_filename = upload.name[:255]
        return normalized
