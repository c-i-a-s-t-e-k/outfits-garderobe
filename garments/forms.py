"""The add- and edit-garment forms: a photo plus the garment's own fields."""

from django import forms

from garments.models import Garment, GarmentType
from privatemedia.forms import NormalizedPhotoMixin


class GarmentForm(NormalizedPhotoMixin, forms.ModelForm):
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


class GarmentEditForm(GarmentForm):
    """Editing a garment: the add rules, but no upload keeps the current photo."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['photo'].required = False
        self.fields['photo'].label = 'Replace photo (optional)'

    def clean_photo(self):
        # The mixin sizes and decodes unconditionally, so an empty upload has to
        # stop here before it is handed a None.
        if not self.cleaned_data['photo']:
            return None
        return super().clean_photo()
