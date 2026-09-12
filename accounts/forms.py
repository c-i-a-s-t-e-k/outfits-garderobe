"""The signup form hook — where an over-long email address is refused.

`ACCOUNT_SIGNUP_FORM_CLASS` is not a form allauth calls alongside its own; it is
the *base class* allauth's `BaseSignupForm` inherits from (see
`allauth.account.internal.flows.signup.base_signup_form_class`). So allauth's
own `clean_email()` wins over anything declared here with that name, and the
reachable hook is `clean()` — which allauth's `BaseSignupForm.clean()` calls
through `super()` after every per-field clean has run.

Why this lives in the form rather than in the adapter: `accounts.adapter` writes
the full email address into `User.username`, which is `max_length=150`, while
allauth's email field accepts Django's 254-character default. Addresses in the
151–254 range therefore reach the adapter, and the adapter runs during save,
after validation — raising there is an unhandled exception on a public form.
Refusing here turns the same case into an ordinary field error.

The same reasoning covers uniqueness. allauth refuses an address already in
`EmailAddress` or `User.email`, but never looks at `User.username` — which the
adapter fills with the address and which carries a unique constraint.
"""

from allauth.account.adapter import get_adapter
from django import forms
from django.contrib.auth import get_user_model

from accounts.adapter import username_max_length


class SignupForm(forms.Form):
    """Base of allauth's signup form; declares no fields of its own."""

    def clean(self) -> dict:
        cleaned_data = super().clean()
        email = cleaned_data.get('email')
        max_length = username_max_length()
        if email and len(email) > max_length:
            self.add_error(
                'email',
                f'This email address is too long. Please use one of at most '
                f'{max_length} characters.',
            )
        elif email and get_user_model().objects.filter(username__iexact=email).exists():
            # allauth checks EmailAddress and User.email, never User.username —
            # but the adapter writes the address there and the column is unique.
            # A username left behind by an email change, or a createsuperuser
            # account with a blank email, would otherwise be an IntegrityError.
            self.add_error('email', get_adapter().error_messages['email_taken'])
        return cleaned_data

    def signup(self, request, user) -> None:
        """Required by allauth's `base_signup_form_class` contract.

        allauth refuses to start if the configured form has no `signup()`. There
        is nothing extra to persist at signup — the email is the whole account —
        so this is deliberately empty rather than missing.
        """
