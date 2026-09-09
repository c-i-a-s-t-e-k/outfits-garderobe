"""Settings for the test run — the real settings, with the deploy secrets stubbed.

`settings.py` deliberately reads `SECRET_KEY` and (outside DEBUG) `MEDIA_ROOT`
from `os.environ` with no fallback, so a misconfigured deploy fails at boot
rather than running degraded. There is no dotenv loader, so importing it in a
bare shell raises `KeyError`. Without this module `uv run pytest` only worked
for a developer who happened to have those exported — it would fail in CI.

Everything else is inherited unchanged, so the config-guard tests still assert
against the real `STORAGES`, the real URLconf, and the real `STATIC_ROOT`.
"""

import os
import tempfile

os.environ.setdefault('SECRET_KEY', 'test-only-key-not-used-outside-pytest')
# Individual tests point MEDIA_ROOT at tmp_path; this only needs to be a real
# path so the settings module can be imported at all.
os.environ.setdefault('MEDIA_ROOT', tempfile.mkdtemp(prefix='outfits-test-media-'))

from outfits_garderobe.settings import *  # noqa: E402, F403

# The suite runs with DEBUG=False, which switches on the production transport
# hardening — and SECURE_SSL_REDIRECT would turn every test client request into a
# 301 to https:// before it ever reached a view. The redirect is a deploy-level
# concern verified by `manage.py check --deploy`, not by these tests; the cookie
# flags above it are left on, since they do not affect routing.
SECURE_SSL_REDIRECT = False
