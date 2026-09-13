"""Authentication is default-deny: a view is closed to anonymous visitors unless it opts out.

This is the layer the route net relies on. A forgotten `@login_required` is harmless
only while `LoginRequiredMiddleware` runs, and a public view is a deliberate,
visible `@login_not_required`.
"""

from django.conf import settings

from tests.owner_scoped_routes import is_guarded, project_routes

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


def test_login_required_middleware_runs_after_authentication():
    middleware = list(settings.MIDDLEWARE)

    assert LOGIN_REQUIRED_MIDDLEWARE in middleware
    assert middleware.index(AUTHENTICATION_MIDDLEWARE) < middleware.index(LOGIN_REQUIRED_MIDDLEWARE)


def test_only_the_known_public_project_views_opt_out_of_login():
    opted_out = {
        f'{route.callback.__module__}.{route.callback.__qualname__}'
        for route in project_routes()
        if not is_guarded(route.callback)
    }

    assert opted_out == PUBLIC_PROJECT_VIEWS
