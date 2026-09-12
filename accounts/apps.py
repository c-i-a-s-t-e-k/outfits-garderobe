from django.apps import AppConfig


class AccountsConfig(AppConfig):
    # The app holds no models; this matches privatemedia/apps.py:7 so the
    # project has one answer rather than two if a model is ever added here.
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'accounts'
