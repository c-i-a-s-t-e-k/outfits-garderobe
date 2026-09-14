"""Staff-only surface for inspecting outfits and tags, matching garments' admin."""

from django.contrib import admin

from outfits.models import MissingGarment, Outfit, Tag


class MissingGarmentInline(admin.TabularInline):
    """What the outfit lost to deleted garments — a record, so nothing is editable."""

    model = MissingGarment
    fields = readonly_fields = ('type', 'type_other', 'description', 'removed_at')
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Outfit)
class OutfitAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'created_at')
    list_filter = ('owner',)
    list_select_related = ('owner',)
    # Id boxes instead of selects of every user's garments, tags and photos.
    raw_id_fields = ('garments', 'tags', 'photo')
    readonly_fields = ('created_at',)
    inlines = (MissingGarmentInline,)


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'created_at')
    list_filter = ('owner',)
    list_select_related = ('owner',)
    readonly_fields = ('created_at',)
