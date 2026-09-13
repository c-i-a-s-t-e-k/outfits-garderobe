"""Smoke coverage for the account flow: every screen resolves, every redirect lands.

Scoped to smoke by explicit decision (see the plan's *Open Risks*). This suite
proves the routing contract, not the authorization model — `privatemedia`'s own
suite carries that.
"""

import pytest
from allauth.account.models import EmailAddress
from django.conf import settings
from django.contrib.auth import get_user_model
from django.urls import reverse

from accounts.adapter import username_max_length

pytestmark = pytest.mark.django_db


@pytest.fixture
def password():
    return 'correct-horse-battery-staple'


@pytest.fixture
def user(django_user_model, password):
    """A user in the state the real flow produces: email as username, verified."""
    account = django_user_model.objects.create_user(
        username='ada@example.com',
        email='ada@example.com',
        password=password,
    )
    EmailAddress.objects.create(user=account, email=account.email, verified=True, primary=True)
    return account


# --- allauth screens resolve for the appropriate actor ---------------------


@pytest.mark.parametrize(
    'route',
    ['account_login', 'account_signup', 'account_reset_password'],
)
def test_anonymous_screens_render(client, route):
    assert client.get(reverse(route)).status_code == 200


@pytest.mark.parametrize(
    'route',
    ['account_change_password', 'account_email', 'account_logout'],
)
def test_authenticated_screens_render(client, user, route):
    client.force_login(user)

    assert client.get(reverse(route)).status_code == 200


def test_logout_is_not_performed_by_a_get(client, user):
    """ACCOUNT_LOGOUT_ON_GET is False, and a GET logout is a real hazard.

    Any prefetch, or an <img src> pointed at the logout URL, would otherwise end
    a session unasked. The GET renders a confirmation page; only the POST ends
    the session.
    """
    client.force_login(user)

    client.get(reverse('account_logout'))
    assert client.get(reverse('wardrobe')).status_code == 200

    response = client.post(reverse('account_logout'))

    assert response.status_code == 302
    assert client.get(reverse('wardrobe')).status_code == 302


# --- the entry point reads authentication state ----------------------------


def test_root_sends_anonymous_visitors_to_login(client):
    response = client.get('/')

    assert response.status_code == 302
    assert response.headers['Location'] == settings.LOGIN_URL


def test_root_sends_authenticated_visitors_to_the_wardrobe(client, user):
    """The outfit grid is the landing page — S-03 pointed `/` back at it."""
    client.force_login(user)

    response = client.get('/')

    assert response.status_code == 302
    assert response.headers['Location'] == reverse('wardrobe')


def test_wardrobe_renders_for_an_authenticated_visitor(client, user):
    client.force_login(user)

    assert client.get(reverse('wardrobe')).status_code == 200


def test_wardrobe_redirects_an_anonymous_visitor(client):
    response = client.get(reverse('wardrobe'))

    assert response.status_code == 302
    assert response.headers['Location'].startswith(settings.LOGIN_URL)


# --- the redirect F-01 was pointing at nothing -----------------------------


def test_login_url_resolves_to_a_real_page(client):
    """The assertion that keeps a LOGIN_URL change from silently re-breaking F-01.

    `privatemedia`'s gate has redirected anonymous requests to
    `settings.LOGIN_URL` since F-01, but nothing served that URL until this
    change — its test asserted only the prefix, so a 404 destination passed.
    """
    assert client.get(settings.LOGIN_URL).status_code == 200


def test_private_media_anonymous_redirect_lands_on_the_login_page(client):
    """Follow the gate's redirect all the way to a rendered page, not a prefix."""
    url = reverse('privatemedia:image', args=['00000000-0000-0000-0000-000000000000'])

    response = client.get(url, follow=True)

    assert response.status_code == 200
    assert response.redirect_chain
    assert response.redirect_chain[-1][0].startswith(settings.LOGIN_URL)


# --- identity is the email address -----------------------------------------


def test_signup_writes_the_full_email_into_username(client):
    """allauth's default would store the local part; the adapter stores the address."""
    response = client.post(
        reverse('account_signup'),
        {
            'email': 'grace@example.com',
            'password1': 'correct-horse-battery-staple',
            'password2': 'correct-horse-battery-staple',
        },
    )

    assert response.status_code == 302
    account = get_user_model().objects.get(email='grace@example.com')
    assert account.username == 'grace@example.com'


def test_signup_refuses_an_email_too_long_for_the_username_column(client):
    """A field error, not the 500 that raising in the adapter would produce.

    allauth's email field accepts Django's 254-character default, so addresses
    longer than `User.username`'s 150 do reach validation.
    """
    too_long = 'a' * (username_max_length() - 11) + '@example.com'
    assert len(too_long) > username_max_length()

    response = client.post(
        reverse('account_signup'),
        {
            'email': too_long,
            'password1': 'correct-horse-battery-staple',
            'password2': 'correct-horse-battery-staple',
        },
    )

    assert response.status_code == 200
    assert 'email' in response.context['form'].errors
    assert not get_user_model().objects.filter(email=too_long).exists()


def test_signup_refuses_an_email_already_taken_as_a_username(client, django_user_model):
    """A field error, not the IntegrityError the unique username column would raise.

    allauth's duplicate check reads `EmailAddress` and `User.email` only; an
    account whose username holds the address but whose email does not — here a
    `createsuperuser` row with a blank email — slips past it.
    """
    django_user_model.objects.create_user(username='admin@example.com', email='')

    response = client.post(
        reverse('account_signup'),
        {
            'email': 'admin@example.com',
            'password1': 'correct-horse-battery-staple',
            'password2': 'correct-horse-battery-staple',
        },
    )

    assert response.status_code == 200
    assert 'email' in response.context['form'].errors
    assert django_user_model.objects.count() == 1


def test_unverified_account_cannot_log_in(client, django_user_model, password):
    """ACCOUNT_EMAIL_VERIFICATION is mandatory — the row alone is not enough."""
    django_user_model.objects.create_user(
        username='unconfirmed@example.com',
        email='unconfirmed@example.com',
        password=password,
    )
    EmailAddress.objects.create(
        user=django_user_model.objects.get(email='unconfirmed@example.com'),
        email='unconfirmed@example.com',
        verified=False,
        primary=True,
    )

    response = client.post(
        reverse('account_login'),
        {'login': 'unconfirmed@example.com', 'password': password},
    )

    assert response.status_code == 302
    assert reverse('account_email_verification_sent') in response.headers['Location']
    assert client.get(reverse('wardrobe')).status_code == 302


def test_verified_account_logs_in_and_lands_on_the_wardrobe(client, user, password):
    response = client.post(
        reverse('account_login'),
        {'login': user.email, 'password': password},
    )

    assert response.status_code == 302
    assert response.headers['Location'] == reverse('wardrobe')
