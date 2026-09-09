"""Pin the storage configuration so a later change cannot silently re-expose media."""

import importlib
from pathlib import Path

from django.conf import settings
from django.test import override_settings
from django.urls import clear_url_caches, get_resolver
from django.views.static import serve


def _flatten(patterns):
    for entry in patterns:
        if hasattr(entry, 'url_patterns'):
            yield from _flatten(entry.url_patterns)
        else:
            yield entry


def _assert_nothing_serves_files(patterns):
    for pattern in patterns:
        assert pattern.callback is not serve, f'{pattern.pattern} serves files straight off disk'
        assert 'document_root' not in (pattern.default_args or {})


def test_media_root_is_configured_and_outside_static_root():
    media_root = Path(settings.MEDIA_ROOT)
    static_root = Path(settings.STATIC_ROOT)

    assert str(media_root)
    assert media_root != static_root
    assert not media_root.is_relative_to(static_root)
    assert not static_root.is_relative_to(media_root)


def test_no_url_pattern_serves_media_root_directly():
    """django.conf.urls.static.static() would hand out uploads without a check."""
    _assert_nothing_serves_files(_flatten(get_resolver().url_patterns))


@override_settings(DEBUG=True)
def test_no_url_pattern_serves_media_root_even_under_debug():
    """The guard above cannot fail on its own, so this one carries it.

    `static()` returns `[]` whenever DEBUG is false (django/conf/urls/static.py),
    and the suite runs with DEBUG=False — so someone appending
    `+ static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)` to the root
    URLconf would never be caught. Re-import the URLconf under DEBUG=True, where
    that helper actually produces a pattern.
    """
    clear_url_caches()
    try:
        urlconf = importlib.reload(importlib.import_module(settings.ROOT_URLCONF))
        _assert_nothing_serves_files(_flatten(urlconf.urlpatterns))
    finally:
        clear_url_caches()
        importlib.reload(importlib.import_module(settings.ROOT_URLCONF))


def test_storages_defines_both_required_backends():
    assert set(settings.STORAGES) >= {'default', 'staticfiles'}
    assert 'whitenoise' in settings.STORAGES['staticfiles']['BACKEND']


def test_whitenoise_does_not_cover_media_root():
    """WHITENOISE_ROOT being unset is the only reason whitenoise ignores uploads.

    Pointing it at MEDIA_ROOT (or any ancestor) would serve every private photo
    publicly, in production, with no ownership check and nothing else failing.
    """
    whitenoise_root = getattr(settings, 'WHITENOISE_ROOT', None)
    if not whitenoise_root:
        return

    media_root = Path(settings.MEDIA_ROOT).resolve()
    served_root = Path(whitenoise_root).resolve()
    assert not media_root.is_relative_to(served_root), (
        f'WHITENOISE_ROOT={served_root} would serve MEDIA_ROOT={media_root} publicly'
    )
