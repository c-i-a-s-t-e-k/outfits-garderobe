"""Authentication is not ownership: a signed-in stranger sees nothing of the owner.

A route that takes the owner's id must answer the stranger exactly as it answers
an id that never existed — same status, same bytes, no validator header — so a
probe cannot even learn the object exists. A POST-only route is probed with its
hostile payload instead of a GET. A route without an id shows the
stranger their own data and none of the owner's.
"""

import uuid

import pytest
from django.urls import reverse

from tests.owner_scoped_routes import ROUTES

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures('temp_media_root')]


def _leaked(markers, body):
    return [marker for marker in markers if marker in body]


@pytest.mark.parametrize('name', ROUTES)
def test_stranger_learns_nothing_of_the_owner(client, owner, stranger, name):
    declaration = ROUTES[name]
    theirs = declaration.seed(owner)

    if theirs.kwargs:
        _assert_owner_id_answers_like_a_missing_one(client, stranger, name, theirs, declaration)
    else:
        _assert_page_shows_only_the_strangers_own_data(client, owner, stranger, name, theirs)


def _assert_owner_id_answers_like_a_missing_one(client, stranger, name, theirs, declaration):
    client.force_login(stranger)
    missing_kwargs = {key: uuid.uuid4() for key in theirs.kwargs}

    if declaration.post_only:
        payload = declaration.foreign_payload(theirs, stranger)
        not_yours = client.post(reverse(name, kwargs=theirs.kwargs), payload)
        never_existed = client.post(reverse(name, kwargs=missing_kwargs), payload)
    else:
        not_yours = client.get(reverse(name, kwargs=theirs.kwargs))
        never_existed = client.get(reverse(name, kwargs=missing_kwargs))

    assert not_yours.status_code == never_existed.status_code == 404
    assert not_yours.content == never_existed.content
    for response in (not_yours, never_existed):
        assert 'ETag' not in response.headers
        assert 'Last-Modified' not in response.headers
    assert not _leaked(theirs.markers, not_yours.content.decode())


def _assert_page_shows_only_the_strangers_own_data(client, owner, stranger, name, theirs):
    # The stranger has data of their own, so the page they get is the populated
    # one — an empty page would pass the absence check without proving anything.
    own = ROUTES[name].seed(stranger)
    url = reverse(name)

    client.force_login(owner)
    owner_body = client.get(url).content.decode()
    client.force_login(stranger)
    response = client.get(url)
    stranger_body = response.content.decode()

    assert response.status_code == 200
    assert not _leaked(theirs.markers, stranger_body)
    # Both users were seeded alike, so the stranger's page must show their own
    # counterpart of every marker the owner's page shows.
    assert [marker in owner_body for marker in theirs.markers] == [
        marker in stranger_body for marker in own.markers
    ]
