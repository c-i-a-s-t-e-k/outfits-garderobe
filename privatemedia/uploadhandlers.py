"""Refuse an oversized upload before any of it is read, not after it is on disk."""

from django.core.exceptions import RequestDataTooBig
from django.core.files.uploadhandler import FileUploadHandler

from privatemedia.validators import MAX_UPLOAD_BYTES

# validate_max_size only runs once Django has spooled the whole file to a temp
# file and ImageField has opened it, so on its own it cannot stop a
# multi-gigabyte body from filling the container's disk. The headroom over
# MAX_UPLOAD_BYTES covers the other form fields and the multipart framing, and
# means a file only slightly over the limit still gets validate_max_size's
# readable field error instead of a bare 400.
MAX_REQUEST_BYTES = MAX_UPLOAD_BYTES + 2 * 1024 * 1024


class RequestSizeLimitUploadHandler(FileUploadHandler):
    """First in FILE_UPLOAD_HANDLERS: sees Content-Length before the body is parsed."""

    def handle_raw_input(self, input_data, META, content_length, boundary, encoding=None):
        if content_length > MAX_REQUEST_BYTES:
            raise RequestDataTooBig(
                f'Upload request of {content_length} bytes exceeds {MAX_REQUEST_BYTES}.'
            )

    def receive_data_chunk(self, raw_data, start):
        return raw_data

    def file_complete(self, file_size):
        return None
