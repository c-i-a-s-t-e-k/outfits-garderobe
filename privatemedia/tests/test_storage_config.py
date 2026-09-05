"""Pin the storage configuration so a later change cannot silently re-expose media."""

from pathlib import Path

from django.conf import settings
from django.urls import get_resolver
from django.views.static import serve


def _all_patterns(resolver):
    for entry in resolver.url_patterns:
        if hasattr(entry, 'url_patterns'):
            yield from _all_patterns(entry)
        else:
            yield entry


def test_media_root_is_configured_and_outside_static_root():
    media_root = Path(settings.MEDIA_ROOT)
    static_root = Path(settings.STATIC_ROOT)

    assert str(media_root)
    assert media_root != static_root
    assert not media_root.is_relative_to(static_root)
    assert not static_root.is_relative_to(media_root)


def test_no_url_pattern_serves_media_root_directly():
    """django.conf.urls.static.static() would hand out uploads without a check."""
    for pattern in _all_patterns(get_resolver()):
        assert pattern.callback is not serve, f'{pattern.pattern} serves files straight off disk'
        assert 'document_root' not in (pattern.default_args or {})


def test_storages_defines_both_required_backends():
    assert set(settings.STORAGES) >= {'default', 'staticfiles'}
    assert 'whitenoise' in settings.STORAGES['staticfiles']['BACKEND']
