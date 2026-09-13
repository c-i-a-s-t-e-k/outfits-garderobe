"""Staff-only surface for inspecting outfits, matching garments' admin."""

from django.contrib import admin

from outfits.models import Outfit


@admin.register(Outfit)
class OutfitAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'created_at')
    list_filter = ('owner',)
    list_select_related = ('owner',)
    # An id box instead of a select of every user's garments.
    raw_id_fields = ('garments',)
    readonly_fields = ('created_at',)
