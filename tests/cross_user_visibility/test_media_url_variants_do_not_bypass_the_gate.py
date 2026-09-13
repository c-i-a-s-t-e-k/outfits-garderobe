"""No spelling of a photo's URL gets a stranger past the ownership check.

Each variant is something a cache, a browser or a curious user could send. The
owner's validator values are taken from the owner's own 200 response, not from
how the gate computes them.
"""

import pytest
from django.urls import reverse

from tests.factories import make_image

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures('temp_media_root')]


@pytest.fixture
def image(owner):
    return make_image(owner)


@pytest.fixture
def owner_validators(client, owner, image):
    client.force_login(owner)
    response = client.get(reverse('privatemedia:image', args=[image.pk]))
    assert response.status_code == 200
    validators = {'etag': response['ETag'], 'last_modified': response['Last-Modified']}
    client.logout()
    return validators


@pytest.fixture
def as_stranger(client, stranger):
    client.force_login(stranger)
    return client


def _assert_denied(response):
    assert response.status_code == 404
    assert 'ETag' not in response.headers
    assert 'Last-Modified' not in response.headers


def test_owners_etag_gets_a_404_not_a_304(owner_validators, as_stranger, image):
    gate = reverse('privatemedia:image', args=[image.pk])

    _assert_denied(as_stranger.get(gate, headers={'if-none-match': owner_validators['etag']}))


def test_owners_last_modified_gets_a_404_not_a_304(owner_validators, as_stranger, image):
    gate = reverse('privatemedia:image', args=[image.pk])
    headers = {'if-modified-since': owner_validators['last_modified']}

    _assert_denied(as_stranger.get(gate, headers=headers))


@pytest.mark.parametrize('method', ['head', 'post'])
def test_other_methods_get_a_404(as_stranger, image, method):
    gate = reverse('privatemedia:image', args=[image.pk])

    _assert_denied(getattr(as_stranger, method)(gate))


@pytest.mark.parametrize(
    'spelling',
    [
        pytest.param(lambda pk: str(pk).upper(), id='uppercase'),
        pytest.param(lambda pk: pk.hex, id='no-dashes'),
    ],
)
def test_other_spellings_of_the_id_get_a_404(as_stranger, image, spelling):
    gate = reverse('privatemedia:image', args=[image.pk])
    variant = gate.replace(str(image.pk), spelling(image.pk))
    assert variant != gate

    _assert_denied(as_stranger.get(variant))


def test_missing_trailing_slash_leads_only_to_the_404(as_stranger, image):
    gate = reverse('privatemedia:image', args=[image.pk])

    response = as_stranger.get(gate.rstrip('/'), follow=True)

    # The only hop is to the gated URL itself, where the ownership check answers.
    assert [url for url, _ in response.redirect_chain] == [gate]
    _assert_denied(response)


def test_the_storage_url_of_the_file_gets_a_404(as_stranger, image):
    assert image.image.url.startswith('/media/private/')

    _assert_denied(as_stranger.get(image.image.url))
