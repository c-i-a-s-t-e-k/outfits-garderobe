"""Fixtures shared by more than one app's tests."""

import pytest


@pytest.fixture
def temp_media_root(settings, tmp_path):
    """Keep a test's uploads out of the real MEDIA_ROOT.

    Not autouse here: test_storage_config checks the real MEDIA_ROOT against
    STATIC_ROOT and WhiteNoise, so modules that store files opt in with
    pytest.mark.usefixtures('temp_media_root').
    """
    settings.MEDIA_ROOT = tmp_path / 'media'
    return settings.MEDIA_ROOT


@pytest.fixture
def owner(django_user_model):
    return django_user_model.objects.create_user(username='owner', password='pw-owner-12345')


@pytest.fixture
def stranger(django_user_model):
    return django_user_model.objects.create_user(username='stranger', password='pw-other-12345')
