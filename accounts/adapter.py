"""The account adapter — the one piece allauth cannot be configured into.

This project keeps the stock `auth.User` rather than swapping in a custom model:
production already holds `PrivateImage` rows with a real FK to it, and allauth's
own `account_emailaddress` table supplies the unique constraint on email that
plain `auth.User` would have lacked. What that leaves is a `username` column
that is `NOT NULL` and `UNIQUE` but that this product never shows to anyone.

allauth would fill it for us, but not the way we chose: with `username` absent
from `ACCOUNT_SIGNUP_FIELDS`, `DefaultAccountAdapter.populate_username()`
derives one from the email's *local part* — `ada` out of `ada@example.com` —
and then disambiguates collisions with a numeric suffix. We write the full
address instead, so the column carries the identity rather than a shadow of it.
"""

from allauth.account.adapter import DefaultAccountAdapter
from django.contrib.auth import get_user_model
from django.http import HttpRequest


def username_max_length() -> int:
    """`User.username`'s own `max_length`, read rather than hardcoded.

    `accounts.forms.SignupForm` rejects addresses that will not fit here, and
    that bound has to be the model's, not a constant that drifts from it.
    """
    return get_user_model()._meta.get_field('username').max_length


class AccountAdapter(DefaultAccountAdapter):
    """Writes the full email address into `User.username`."""

    def populate_username(self, request: HttpRequest, user) -> None:
        """Assign the email address itself as the username.

        `UnicodeUsernameValidator` permits `[\\w.@+-]`, which covers every
        character an email address is made of, so an ordinary address is a
        legal username. Length is the one thing that can fail — and it is
        rejected in the signup form rather than here, because this runs during
        save, after validation, where an exception is a 500 on a public form.
        The assertion below is therefore an invariant, not a user-facing check:
        if it ever trips, the form-level guard has been bypassed or removed.
        """
        email = user.email
        assert len(email) <= username_max_length(), (
            f'email {email!r} exceeds User.username max_length; '
            'accounts.forms.SignupForm should have rejected it'
        )
        user.username = email
