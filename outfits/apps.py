from django.apps import AppConfig


class OutfitsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'outfits'

    def ready(self):
        # Importing the module is what connects the receivers that keep another
        # user's garments and tags out of an outfit on every ORM path, delete
        # tags no outfit carries any more, and record the garments an outfit
        # loses when they are deleted.
        from outfits import signals  # noqa: F401
