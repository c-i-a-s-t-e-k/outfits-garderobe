"""Authentication is default-deny: a view is closed to anonymous visitors unless it opts out.

This is the layer the route net relies on. A forgotten `@login_required` is harmless
only while `LoginRequiredMiddleware` runs, and a public view is a deliberate,
visible `@login_not_required`.
"""

import sys
from pathlib import Path

from django.conf import settings
from django.urls import get_resolver

LOGIN_REQUIRED_MIDDLEWARE = 'django.contrib.auth.middleware.LoginRequiredMiddleware'
AUTHENTICATION_MIDDLEWARE = 'django.contrib.auth.middleware.AuthenticationMiddleware'

# Every project view anonymous visitors may reach, and why. Adding one is a
# deliberate edit here, with its reason.
PUBLIC_PROJECT_VIEWS = {
    # Railway's healthcheck probes it anonymously.
    'outfits_garderobe.urls.health',
    # `/` sends anonymous visitors to login and signed-in ones to the wardrobe.
    'accounts.views.home',
}


def _callbacks(patterns):
    for entry in patterns:
        if hasattr(entry, 'url_patterns'):
            yield from _callbacks(entry.url_patterns)
        else:
            yield entry.callback


def _is_project_code(callback):
    path = Path(sys.modules[callback.__module__].__file__).resolve()
    return path.is_relative_to(settings.BASE_DIR) and 'site-packages' not in path.parts


def test_login_required_middleware_runs_after_authentication():
    middleware = list(settings.MIDDLEWARE)

    assert LOGIN_REQUIRED_MIDDLEWARE in middleware
    assert middleware.index(AUTHENTICATION_MIDDLEWARE) < middleware.index(LOGIN_REQUIRED_MIDDLEWARE)


def test_only_the_known_public_project_views_opt_out_of_login():
    opted_out = {
        f'{callback.__module__}.{callback.__qualname__}'
        for callback in _callbacks(get_resolver().url_patterns)
        if _is_project_code(callback) and getattr(callback, 'login_required', True) is False
    }

    assert opted_out == PUBLIC_PROJECT_VIEWS
