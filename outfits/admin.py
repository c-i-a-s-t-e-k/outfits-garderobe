"""Staff-only surface for inspecting outfits and tags, matching garments' admin."""

from django.contrib import admin

from outfits.models import Outfit, Tag


@admin.register(Outfit)
class OutfitAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'created_at')
    list_filter = ('owner',)
    list_select_related = ('owner',)
    # Id boxes instead of selects of every user's garments and tags.
    raw_id_fields = ('garments', 'tags')
    readonly_fields = ('created_at',)


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'created_at')
    list_filter = ('owner',)
    list_select_related = ('owner',)
    readonly_fields = ('created_at',)
