"""Validation rules every private upload path inherits from the model layer."""

from django.core.exceptions import ValidationError

# Ceiling for a single upload. Phone cameras produce 3-5 MB photos, so this
# leaves generous headroom while keeping a single request bounded.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def validate_max_size(value):
    """Reject an upload larger than MAX_UPLOAD_BYTES.

    Must stay a named module-level function: the migration serialises a
    reference to it by import path, which a lambda or closure cannot provide.
    """
    if value.size > MAX_UPLOAD_BYTES:
        raise ValidationError(
            'File is too large (maximum %(limit)s MB).',
            code='file_too_large',
            params={'limit': MAX_UPLOAD_BYTES // (1024 * 1024)},
        )
