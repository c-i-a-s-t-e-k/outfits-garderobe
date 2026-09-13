# Outfits Garderobe

A Django wardrobe app for composing and revisiting *outfits* — groups of
garments — rather than cataloguing individual clothes. One garment can belong to
many outfits, and every photo a user uploads is private to them.

Product spec: [`context/foundation/prd.md`](context/foundation/prd.md) (in Polish).
Stack rationale: [`context/foundation/tech-stack.md`](context/foundation/tech-stack.md).

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) — it manages the virtualenv and dependencies.
  Do not use `pip` or `python -m venv` directly.

## Running locally

Paste this as one block. It installs dependencies, applies migrations and starts
the development server at <http://127.0.0.1:8000/>:

```bash
uv sync
export DEBUG=True SECRET_KEY=dev-only-not-a-real-secret
uv run python manage.py migrate
uv run python manage.py runserver
```

`SECRET_KEY` above is a throwaway placeholder for local development. The
application reads it from the environment with no fallback so that a
misconfigured deploy fails at boot instead of running on a default; production
values are set on the hosting platform and never live in this repository.

`DEBUG=True` matters for more than error pages — it also selects the local
defaults for two settings that are otherwise mandatory:

- **Email goes to the console.** Account confirmation and password-reset links
  are printed to the terminal running the server, so no mail provider is needed
  to walk the whole signup flow. Outside `DEBUG` the app sends through Brevo's
  HTTP API and requires `BREVO_API_KEY` (a v3 API key) and `DEFAULT_FROM_EMAIL`
  (a sender verified in Brevo).
- **Uploads go to `media/`** in the project directory instead of a mounted
  volume.

Create an administrator for `/admin/` with:

```bash
uv run python manage.py createsuperuser
```

Ordinary accounts are made through the app at `/accounts/signup/` — the identity
is an email address, and it must be confirmed before the first login.

## Tests, linting and audit

```bash
uv run pytest                     # test suite (pytest-django)
uv run pytest path/to/test.py     # a single module
uv run ruff check .               # lint
uv run ruff format .              # format
uv run pip-audit                  # dependency vulnerability audit
```

The suite has its own settings module, `outfits_garderobe.settings_test`, which
stubs the deploy-time environment variables — so `uv run pytest` works without
any of the exports above.

### Pre-commit gate

Install the git hook once per clone:

```bash
uv run pre-commit install
```

Each commit then runs, on the staged files only, `ruff check`, `ruff format
--check` and the affected tests (`scripts/pytest_staged.py`): the tests of an
app you touched, of every app that imports it, and the risk tests in `tests/`;
or the full suite when a shared file (settings, `conftest.py`, `tests/`,
dependencies, shared templates) is staged. Docs-only
commits skip all three. Run it by hand with `uv run pre-commit run`; fix format
failures with `uv run ruff format .`.

## Configuration

Settings are read from environment variables; see
[`.env.example`](.env.example) for the full list and the shape of each value. No
`.env` file is loaded automatically and none is committed.

## Layout

| Path | What it holds |
| --- | --- |
| `outfits_garderobe/` | Project configuration — settings, root URLconf, WSGI/ASGI |
| `accounts/` | Registration, login and the account adapter (django-allauth) |
| `privatemedia/` | The ownership-checked gate every private image is served through |
| `templates/`, `static/` | Project-level templates and static sources |
| `context/` | Product spec, roadmap and per-change implementation plans |
