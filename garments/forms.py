"""The add-garment form: a photo plus the garment's own fields."""

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
