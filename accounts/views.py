"""The application's entry point.

Every redirect below reverses a route name rather than writing the path out:
the `wardrobe` name is the contract, wherever the view behind it lives.
"""

from django.conf import settings
from django.shortcuts import redirect


def home(request):
    """`/` holds no content of its own — it reads authentication state.

    Anonymous visitors land on the login page, which is the *Access Control*
    section of the PRD ("niezalogowany użytkownik trafia na stronę
    logowania/rejestracji") expressed as a route rather than as a template.

    Signed-in visitors go to the wardrobe — the outfit grid, which is what the
    product is about. LOGIN_REDIRECT_URL points at the same place.
    """
    if request.user.is_authenticated:
        return redirect('wardrobe')
    return redirect(settings.LOGIN_URL)
