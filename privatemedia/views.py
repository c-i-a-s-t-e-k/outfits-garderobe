"""The only path through which private file bytes reach a browser."""

import logging

from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.views.decorators.cache import cache_control
from django.views.decorators.http import condition

from privatemedia.models import PrivateImage

logger = logging.getLogger(__name__)


def _owned_image(request, pk):
    """Return the row this requester may see, or None.

    Filtering on primary key *and* owner in one query is what makes "no such
    file" and "not your file" the same answer. @condition runs its validator
    functions before the view body, so the result is cached on the request and
    all three call sites share a single lookup.
    """
    cached = getattr(request, '_privatemedia_image', None)
    if cached is None or cached[0] != pk:
        cached = (pk, PrivateImage.objects.filter(pk=pk, owner=request.user).first())
        request._privatemedia_image = cached
    return cached[1]


def _etag(request, pk):
    """Validator for a row the requester owns; None otherwise.

    Returning None for a denial keeps the 404 free of any header that would
    confirm the row exists. The stored name is a fresh UUID on every upload, so
    replacing the file invalidates the ETag without touching the filesystem.
    """
    image = _owned_image(request, pk)
    return None if image is None else f'{image.pk.hex}:{image.image.name}'


def _last_modified(request, pk):
    image = _owned_image(request, pk)
    return None if image is None else image.uploaded_at


@login_required
# Above @condition on purpose: @condition returns its 304 before the view body
# runs, so a header set inside the body would be missing from exactly the
# response a cache is most likely to reuse.
@cache_control(private=True, max_age=0, must_revalidate=True)
@condition(etag_func=_etag, last_modified_func=_last_modified)
def serve_private_image(request, pk):
    """Stream a private image to its owner.

    The UUID primary key is the only input taken from the URL — no filename, no
    path segment — which makes traversal structurally impossible rather than
    something to sanitise.
    """
    image = _owned_image(request, pk)
    if image is None:
        raise Http404

    try:
        handle = image.image.open('rb')
    except (FileNotFoundError, OSError):
        # The row is in Postgres and the bytes are on a separate volume, so the
        # two can desynchronise (a reattach, a restore, a half-finished upload).
        # Answer exactly as for a row that does not exist, but say so in the log
        # — otherwise the data loss is silent.
        logger.warning('PrivateImage %s has no file at %s', image.pk, image.image.name)
        raise Http404 from None

    return FileResponse(handle, as_attachment=False)
