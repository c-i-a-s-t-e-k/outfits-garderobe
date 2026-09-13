"""An anonymous visitor gets the login page from every owner-scoped route — and nothing else.

Writes are posted with a body that would succeed for the owner, so "nothing
stored" means the request was refused, not that it was malformed.
"""

from urllib.parse import urlsplit

import pytest
from django.conf import settings
from django.urls import reverse

from garments.models import Garment
from outfits.models import Outfit
from privatemedia.models import PrivateImage
from tests.owner_scoped_routes import ROUTES

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures('temp_media_root')]


def _row_counts():
    return {model.__name__: model.objects.count() for model in (PrivateImage, Garment, Outfit)}


@pytest.mark.parametrize('method', ['get', 'post'])
@pytest.mark.parametrize('name', ROUTES)
def test_anonymous_visitor_is_sent_to_login_and_nothing_is_stored(client, owner, name, method):
    declaration = ROUTES[name]
    seeded = declaration.seed(owner)
    url = reverse(name, kwargs=seeded.kwargs)
    before = _row_counts()

    if method == 'get':
        response = client.get(url)
    else:
        payload = declaration.foreign_payload(seeded, None) if declaration.foreign_payload else {}
        response = client.post(url, payload)

    assert response.status_code == 302
    assert urlsplit(response.headers['Location']).path == settings.LOGIN_URL
    body = response.content.decode()
    assert not [marker for marker in seeded.markers if marker in body]
    assert _row_counts() == before
