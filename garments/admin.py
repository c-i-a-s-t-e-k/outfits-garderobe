"""Staff-only surface for inspecting garments, matching privatemedia's admin."""

from django.contrib import admin

from garments.models import Garment


@admin.register(Garment)
class GarmentAdmin(admin.ModelAdmin):
    list_display = ('type', 'description', 'owner', 'created_at')
    list_filter = ('owner', 'type')
    list_select_related = ('owner',)
    # An id box instead of a select of every user's photos by filename.
    raw_id_fields = ('photo',)
    readonly_fields = ('created_at',)
