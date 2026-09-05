"""Storage for user-uploaded photos, and the single record of who owns each one."""

import uuid
from pathlib import Path

from django.conf import settings
from django.db import models

from privatemedia.validators import validate_max_size


def upload_to_uuid(instance, filename):
    """Build a storage path that carries no information beyond the file type."""
    ext = Path(filename).suffix.lower().lstrip('.')
    name = f'{uuid.uuid4().hex}.{ext}' if ext else uuid.uuid4().hex
    return f'private/{name}'


class PrivateImage(models.Model):
    """One uploaded photo plus the ownership answer the gate view depends on.

    Downstream slices (S-02 garments, S-04 outfit photos) attach foreign keys to
    this model rather than each re-declaring a file field — so the ownership
    check lives in exactly one place.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='private_images',
    )
    image = models.ImageField(upload_to=upload_to_uuid, validators=[validate_max_size])
    # Metadata only: the name the browser supplied never reaches the filesystem.
    original_filename = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']
        indexes = [models.Index(fields=['owner', '-uploaded_at'])]

    def __str__(self):
        return self.original_filename or str(self.pk)

    def save(self, *args, **kwargs):
        # upload_to runs during the insert and discards the client-supplied
        # name, so capture it here while the field still holds it.
        if self.image and not self.original_filename:
            self.original_filename = Path(self.image.name).name[:255]
        super().save(*args, **kwargs)
