"""Storage for user-uploaded photos, and the single record of who owns each one."""

import uuid
from contextlib import contextmanager
from pathlib import Path

from django.conf import settings
from django.core.validators import validate_image_file_extension
from django.db import models, transaction
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


@contextmanager
def stored_private_image(owner, file, original_filename=''):
    """Store a PrivateImage for use inside the block, or leave nothing behind.

    The file is written to the volume during the insert, before anything the
    caller links to it exists. A rollback removes rows but never bytes, so if the
    insert or anything in the block fails, the written file is deleted before the
    exception propagates. Garments and outfit photos store through this instead
    of each cleaning up after themselves.
    """
    image = PrivateImage(owner=owner, image=file, original_filename=original_filename)
    try:
        with transaction.atomic():
            image.save()
            yield image
    except BaseException:
        # FieldFile._committed turns True as soon as storage has written the
        # file, which also covers an insert that failed after the write.
        if image.image._committed:
            image.image.delete(save=False)
        raise


def discard_private_image(image):
    """Retire a PrivateImage: the row now, the file only once the change commits.

    Call inside a transaction. If it rolls back, the row comes back and the file
    was never touched, so a failed replace or remove never loses the photo. After
    commit nothing points at the file, so it is deleted rather than left on the
    volume. Unlink the image from any RESTRICT relation (Garment.photo,
    Outfit.photo) first, or the row delete is refused.
    """
    storage = image.image.storage
    name = image.image.name
    image.delete()
    # FileSystemStorage.delete() ignores a file that is already gone.
    transaction.on_commit(lambda: storage.delete(name))
