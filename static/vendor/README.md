# Vendored assets

Third-party files committed to the repository rather than loaded from a CDN. An
external stylesheet in the render path is a third-party dependency on every page
load, and `CompressedManifestStaticFilesStorage` cannot hash what it does not
have — a CDN URL stays unhashed and uncached alongside everything else.

| File | Package | Version | Source | Retrieved |
| --- | --- | --- | --- | --- |
| `pico.min.css` | [Pico CSS](https://picocss.com) | v2.1.1 (2025-03-15) | `https://cdn.jsdelivr.net/npm/@picocss/pico@2.1.1/css/pico.min.css` | 2026-09-12 |

## Upgrading

Fetch the new release to the same path, then re-run
`uv run python manage.py collectstatic --noinput` before committing: manifest
storage rewrites every `url()` it finds, so a build that ships a source map
reference or an external font URL fails the *deploy*, not a page. The v2.1.1
file was checked for both and has neither.
