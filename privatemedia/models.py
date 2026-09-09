"""Storage for user-uploaded photos, and the single record of who owns each one."""

import uuid
from pathlib import Path

from django.conf import settings
from django.core.validators import validate_image_file_extension
from django.db import models
from django.urls import reverse

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
    # validate_image_file_extension is a *form* field default in Django, not a
    # model one, so it has to be named explicitly for the plain ORM path to get
    # it. upload_to preserves the extension and the gate serves the file inline,
    # so the extension decides the Content-Type a browser sees.
    image = models.ImageField(
        upload_to=upload_to_uuid,
        validators=[validate_max_size, validate_image_file_extension],
    )
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
        # Django runs field validators only from ModelForm._post_clean(), so a
        # plain objects.create() would skip both the size ceiling and the
        # image-type check. Enforcing them here is what lets S-02 and S-04
        # inherit the rules instead of each restating them in a form.
        self.full_clean()
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        """The only working URL for this image — always use this, never `.url`.

        `image.url` is `MEDIA_URL` + the storage name (`/media/private/<hex>.png`)
        and resolves to nothing: the gate is keyed on this row's UUID, not on the
        file's path. Nothing serves MEDIA_ROOT, and nothing ever should.
        """
        return reverse('privatemedia:image', args=[self.pk])
