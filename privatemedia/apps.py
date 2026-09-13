from django.apps import AppConfig


class PrivatemediaConfig(AppConfig):
    # PrivateImage uses an explicit UUID primary key, but this is the project's
    # first domain app and sets the default the next model here inherits.
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'privatemedia'

    def ready(self):
        # Photos from Apple devices arrive as HEIC, which Pillow cannot read on
        # its own. normalize_photo decodes through this registration, and the
        # model's validate_image_file_extension asks Pillow's registry at call
        # time which formats exist, so registering here — before any request —
        # is what lets them accept HEIC at all.
        from pillow_heif import register_heif_opener

        register_heif_opener()
