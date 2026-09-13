"""Every photo a page shows its owner is a gated URL nobody else can fetch.

This ties the page to the gate: a photo rendered for the owner must answer 200
to the owner, 404 to a stranger and the login redirect to a visitor. A route
that declares it shows no photos is held to that too, so the declaration
cannot drift out of date. A POST-only route has no page: it must refuse the GET
and declare no photos.
"""

from html.parser import HTMLParser
from urllib.parse import urlsplit

import pytest
from django.conf import settings
from django.test import Client
from django.urls import Resolver404, resolve, reverse

from tests.owner_scoped_routes import ROUTES

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures('temp_media_root')]


class _ImageSources(HTMLParser):
    def __init__(self):
        super().__init__()
        self.sources = []

    def handle_starttag(self, tag, attrs):
        if tag == 'img':
            self.sources.extend(value for key, value in attrs if key == 'src' and value)


def _gated_photo_sources(response):
    if response.streaming or not response['Content-Type'].startswith('text/html'):
        return []
    parser = _ImageSources()
    parser.feed(response.content.decode())
    return [src for src in parser.sources if _is_gate(src)]


def _is_gate(src):
    try:
        return resolve(urlsplit(src).path).view_name == 'privatemedia:image'
    except Resolver404:
        return False


@pytest.mark.parametrize('name', ROUTES)
def test_photos_on_the_owners_page_are_served_to_the_owner_only(client, owner, stranger, name):
    declaration = ROUTES[name]
    seeded = declaration.seed(owner)
    client.force_login(owner)

    page = client.get(reverse(name, kwargs=seeded.kwargs))
    if declaration.post_only:
        assert page.status_code == 405, f'{name} declares post_only but answered a GET'
        assert not declaration.shows_photos, f'{name} has no page to show photos on'
        return
    assert page.status_code == 200
    sources = _gated_photo_sources(page)

    if not declaration.shows_photos:
        assert not sources, f'{name} renders gated photos; declare shows_photos=True'
        return

    assert sources, f'{name} declares shows_photos but its page rendered none'
    stranger_client = Client()
    stranger_client.force_login(stranger)
    anonymous_client = Client()
    for src in sources:
        assert client.get(src).status_code == 200
        assert stranger_client.get(src).status_code == 404
        anonymous = anonymous_client.get(src)
        assert anonymous.status_code == 302
        assert urlsplit(anonymous.headers['Location']).path == settings.LOGIN_URL
