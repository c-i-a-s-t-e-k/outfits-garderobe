from django.apps import AppConfig


class OutfitsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'outfits'

    def ready(self):
        # Importing the module is what connects the m2m_changed receiver that
        # keeps another user's garment out of an outfit on every ORM path.
        from outfits import signals  # noqa: F401
