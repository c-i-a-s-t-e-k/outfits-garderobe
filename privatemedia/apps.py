from django.apps import AppConfig


class PrivatemediaConfig(AppConfig):
    # PrivateImage uses an explicit UUID primary key, but this is the project's
    # first domain app and sets the default the next model here inherits.
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'privatemedia'
