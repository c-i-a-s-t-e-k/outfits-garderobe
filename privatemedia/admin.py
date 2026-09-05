"""Staff-only surface for exercising the gate before S-02 ships an upload UI."""

from django.contrib import admin

from privatemedia.models import PrivateImage


@admin.register(PrivateImage)
class PrivateImageAdmin(admin.ModelAdmin):
    list_display = ('id', 'owner', 'original_filename', 'uploaded_at')
    list_filter = ('owner',)
    readonly_fields = ('original_filename', 'uploaded_at')
