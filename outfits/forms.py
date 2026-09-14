"""Compose, edit and replacement forms, the outfit photo form, and the tag input for typed tags."""

from django import forms
from django.core.exceptions import ValidationError
from django.forms.models import ModelChoiceIteratorValue

from garments.models import Garment
from outfits.models import Outfit, Tag
from privatemedia.forms import NormalizedPhotoMixin

MIN_GARMENTS = 2
TAG_TOO_LONG_MESSAGE = f'Tags are at most {Tag.MAX_LENGTH} characters.'
TOO_MANY_TAGS_MESSAGE = f'An outfit can have at most {Tag.MAX_PER_OUTFIT} tags.'


class TagNamesField(forms.CharField):
    """Comma-separated text in, a list of cleaned tag names out.

    Each piece has its whitespace collapsed; empty pieces are dropped, and a
    name whose `Tag.normalize` key repeats an earlier one is dropped too, so
    `Letnie, letnie` is one name, spelled as typed first.
    """

    def __init__(self, *, required=False, max_length=700, **kwargs):
        kwargs.setdefault('help_text', 'Separate tags with commas.')
        super().__init__(required=required, max_length=max_length, **kwargs)

    def clean(self, value):
        # CharField's own clean validates the raw text (required, max_length);
        # the list is built afterwards, so no validator ever sees a list.
        text = super().clean(value)
        names = {}
        for piece in text.split(','):
            name = ' '.join(piece.split())
            if name:
                names.setdefault(Tag.normalize(name), name)
        names = list(names.values())
        if self.required and not names:
            raise ValidationError(self.error_messages['required'], code='required')
        if any(len(name) > Tag.MAX_LENGTH for name in names):
            raise ValidationError(TAG_TOO_LONG_MESSAGE, code='tag_too_long')
        if len(names) > Tag.MAX_PER_OUTFIT:
            raise ValidationError(TOO_MANY_TAGS_MESSAGE, code='too_many_tags')
        return names


class OutfitForm(forms.ModelForm):
    """Built for one owner: the picker lists their garments and nothing else.

    A posted id outside the owner's garments fails as an invalid choice before
    anything is stored. Name uniqueness is checked here as well as on the model,
    because ModelForm skips a constraint that references a field the form does
    not carry — `owner` — so the model's `(owner, lower(name))` rule would only
    surface at save time, as a non-field error the user cannot act on.
    """

    # Deliberately not named `tags` and not in Meta.fields: the view resolves
    # these names to the owner's Tag rows. A form field sharing the relation's
    # name would be one Meta.fields edit away from save_m2m() writing it raw.
    tag_names = TagNamesField(label='Tags (optional)')

    class Meta:
        model = Outfit
        fields = ['name', 'garments']
        labels = {'name': 'Name (optional)', 'garments': 'Garments'}
        help_texts = {'name': 'Leave it empty and the outfit is named outfit-N.'}
        widgets = {'garments': forms.CheckboxSelectMultiple}

    min_garments = MIN_GARMENTS

    def __init__(self, data=None, *, owner, instance=None):
        super().__init__(data, instance=instance)
        # Set before validation: Outfit.clean() needs the owner to compute the
        # default name, and clean_name() needs it to scope the uniqueness check.
        self.instance.owner = owner
        self.fields['garments'].queryset = Garment.objects.filter(owner=owner)
        self.fields['garments'].error_messages['required'] = self.min_garments_message

    @property
    def min_garments_message(self):
        noun = 'garment' if self.min_garments == 1 else 'garments'
        return f'Choose at least {self.min_garments} {noun}.'

    def clean_name(self):
        name = ' '.join(self.cleaned_data['name'].split())
        taken = Outfit.objects.filter(owner=self.instance.owner, name__iexact=name)
        if name and taken.exclude(pk=self.instance.pk).exists():
            raise ValidationError(f'You already have an outfit named “{name}”.')
        return name

    def clean_garments(self):
        garments = self.cleaned_data['garments']
        if len(garments) < self.min_garments:
            raise ValidationError(self.min_garments_message)
        return garments


class OutfitEditForm(OutfitForm):
    """An existing outfit's name and garments; its tags are changed on its own page.

    One garment is enough, unlike compose: *Keep without it* can already leave
    an outfit with one, and that outfit must stay editable. Zero is refused, so
    a saved outfit never looks complete while empty.
    """

    # Removes the inherited field: the view then leaves the outfit's tags alone.
    tag_names = None
    min_garments = 1

    class Meta(OutfitForm.Meta):
        labels = {**OutfitForm.Meta.labels, 'name': 'Name'}
        help_texts = {}

    def clean_name(self):
        # Empty keeps the name. Left empty, the model would rename the outfit to
        # the lowest free outfit-N. clean_name() runs before the form copies its
        # values onto the instance, so instance.name is still the stored one.
        return super().clean_name() or self.instance.name


class ReplaceMissingGarmentForm(forms.Form):
    """One of the owner's garments to fill a missing slot, garments of the same kind first.

    Garments already in the outfit are not offered. A posted id outside the
    offered garments fails as an invalid choice.
    """

    garment = forms.ModelChoiceField(
        queryset=Garment.objects.none(),
        widget=forms.RadioSelect,
        label='Replacement',
        error_messages={'required': 'Choose a garment.'},
    )

    def __init__(self, data=None, *, outfit, missing):
        super().__init__(data)
        field = self.fields['garment']
        field.queryset = Garment.objects.filter(owner=outfit.owner_id).exclude(
            pk__in=[garment.pk for garment in outfit.garments.all()]
        )
        # Ordered in Python: a stable sort keeps the default order within each group.
        candidates = sorted(field.queryset, key=lambda garment: not _same_kind(garment, missing))
        field.choices = [
            (ModelChoiceIteratorValue(garment.pk, garment), field.label_from_instance(garment))
            for garment in candidates
        ]


def _same_kind(garment, missing):
    if garment.type != missing.type:
        return False
    return garment.type_other.casefold() == missing.type_other.casefold()


class OutfitPhotoForm(NormalizedPhotoMixin, forms.Form):
    """The owner's photo of themselves in the outfit, under the garment photo's rules."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['photo'].label = 'Photo of you in this outfit'


class AddTagsForm(forms.Form):
    """Tags typed on an outfit's page, checked against what it already carries."""

    tag_names = TagNamesField(required=True, label='Add tags')

    def __init__(self, data=None, *, outfit):
        super().__init__(data)
        self.outfit = outfit
        self.fields['tag_names'].widget.attrs['list'] = 'tag-suggestions'

    def clean_tag_names(self):
        names = self.cleaned_data['tag_names']
        carried = {tag.normalized for tag in self.outfit.tags.all()}
        new = {Tag.normalize(name) for name in names} - carried
        if len(carried) + len(new) > Tag.MAX_PER_OUTFIT:
            raise ValidationError(TOO_MANY_TAGS_MESSAGE, code='too_many_tags')
        return names
