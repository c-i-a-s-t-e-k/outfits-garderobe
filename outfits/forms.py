"""The compose form: a name plus a selection of the requester's own garments."""

from django import forms
from django.core.exceptions import ValidationError

from garments.models import Garment
from outfits.models import Outfit

MIN_GARMENTS = 2
MIN_GARMENTS_MESSAGE = f'Choose at least {MIN_GARMENTS} garments.'


class OutfitForm(forms.ModelForm):
    """Built for one owner: the picker lists their garments and nothing else.

    A posted id outside the owner's garments fails as an invalid choice before
    anything is stored. Name uniqueness is checked here as well as on the model,
    because ModelForm skips a constraint that references a field the form does
    not carry — `owner` — so the model's `(owner, lower(name))` rule would only
    surface at save time, as a non-field error the user cannot act on.
    """

    class Meta:
        model = Outfit
        fields = ['name', 'garments']
        labels = {'name': 'Name (optional)', 'garments': 'Garments'}
        help_texts = {'name': 'Leave it empty and the outfit is named outfit-N.'}
        widgets = {'garments': forms.CheckboxSelectMultiple}
        error_messages = {'garments': {'required': MIN_GARMENTS_MESSAGE}}

    def __init__(self, data=None, *, owner):
        super().__init__(data)
        # Set before validation: Outfit.clean() needs the owner to compute the
        # default name, and clean_name() needs it to scope the uniqueness check.
        self.instance.owner = owner
        self.fields['garments'].queryset = Garment.objects.filter(owner=owner)

    def clean_name(self):
        name = ' '.join(self.cleaned_data['name'].split())
        if name and Outfit.objects.filter(owner=self.instance.owner, name__iexact=name).exists():
            raise ValidationError(f'You already have an outfit named “{name}”.')
        return name

    def clean_garments(self):
        garments = self.cleaned_data['garments']
        if len(garments) < MIN_GARMENTS:
            raise ValidationError(MIN_GARMENTS_MESSAGE)
        return garments
