"""The application's entry point and the wardrobe placeholder.

Both views live here for now. S-03 moves the wardrobe into its own app; the URL
*name* is the contract that survives that move, which is why every redirect
below reverses a route name rather than writing the path out.
"""

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render


def home(request):
    """`/` holds no content of its own — it reads authentication state.

    Anonymous visitors land on the login page, which is the *Access Control*
    section of the PRD ("niezalogowany użytkownik trafia na stronę
    logowania/rejestracji") expressed as a route rather than as a template.

    Signed-in visitors go to the garment list — the only real content until
    S-03 brings the outfit grid and points this, and LOGIN_REDIRECT_URL, back
    at `wardrobe`.
    """
    if request.user.is_authenticated:
        return redirect('garments:list')
    return redirect(settings.LOGIN_URL)


@login_required
def wardrobe(request):
    """The authenticated destination, reserved so S-02 and S-03 fill a page in.

    Deliberately a placeholder. Anything invested in it is thrown away when the
    real garment and outfit grids arrive.
    """
    return render(request, 'wardrobe.html')
