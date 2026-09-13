# Add Garment with Photo and Private Garment List Implementation Plan

## Overview

A signed-in user adds a garment — a photo, a type and an optional short description — and then sees a private list of their own garments with photos. This is roadmap slice **S-02** (Jira OG-3), covering FR-003 and the garment half of US-01. It is the first real upload in the product, and the PRD's key use case is doing it from a phone, so the plan is shaped around keeping that upload fast and the stored photo private.

## Current State Analysis

- **The private media gate exists and is built to be inherited.** `privatemedia.PrivateImage` (`privatemedia/models.py:21`) is one uploaded photo plus its owner; its docstring tells S-02 to attach a foreign key to it rather than declare a file field. `save()` runs `full_clean()` (`privatemedia/models.py:54-64`), so the 10 MB ceiling (`privatemedia/validators.py:7`) and the image-extension check apply to every ORM path. The only working URL for a photo is `get_absolute_url()` → `privatemedia:image`; `.url` resolves to nothing and a test pins that (`privatemedia/tests/test_gate.py:110`).
- **No photo processing exists.** Whatever is uploaded is stored as-is: full camera resolution, EXIF orientation flag, GPS coordinates. Pillow 12.3.0 is installed; HEIC is not readable.
- **`/wardrobe/` is a reserved placeholder** (`accounts/views.py:25`, `templates/wardrobe.html`) that S-03 fills with the outfit grid. `LOGIN_REDIRECT_URL = 'wardrobe'` (`outfits_garderobe/settings.py:256`) and `home` redirects there (`accounts/views.py:21`); two smoke tests assert that landing (`accounts/tests/test_smoke.py:85`, `:220`).
- **No JavaScript exists.** Styling is Pico plus a deliberately small `static/css/app.css`. Templates live in the project-level `templates/` directory.
- **Gunicorn runs at its defaults** — no `--workers` in `railway.toml` or `Procfile`, i.e. one sync worker. One slow mobile upload holds the only worker for its whole duration, and every photo tile in a list is its own request through the gate.
- **Production storage is a 5000 MB Railway volume** at `/data` (roadmap, F-01). At 3–5 MB per raw camera photo that is ~1000–1500 photos; at ~200–400 KB per normalized photo it is well over ten thousand.

## Desired End State

A signed-in user taps *Garments* in the header (or simply logs in — the garment list is the landing page until S-03), taps *Add garment*, takes or picks a photo, chooses a type from a list (or *Other* and types a name), optionally writes up to 200 characters, and saves. The browser shrinks the photo before sending it; the server rotates it upright, resizes it to at most 1600 px on the long edge, strips every piece of metadata including GPS, and stores it as a JPEG behind the private gate. The user lands on their garment list with a "Garment added" message and sees the new tile first. A second account sees none of it, neither in the list nor through the photo URL. The flow works at 360 px, with JavaScript off, and with HEIC photos from Apple devices.

Verification: the automated suite proves the ownership, processing and type rules; a real iPhone and a real Android phone add a garment against production over mobile data in under five seconds from tapping *Save*.

### Key Discoveries:

- `PrivateImage.save()` captures `original_filename` only when it is empty (`privatemedia/models.py:57`), so after normalization renames the file to `photo.jpg` the caller must pass the user's filename explicitly or the metadata becomes meaningless.
- Django 6.0.8's `PROTECT` raises even when the protected row is itself being deleted by a cascade from the same user deletion; `RESTRICT` permits exactly that case (`django/db/models/deletion.py:34-49`). The garment→photo link must use `RESTRICT`.
- `django.core.validators.get_available_image_extensions()` reads Pillow's registry at call time (`django/core/validators.py:639`), so registering the HEIF opener at app startup is enough for both `forms.ImageField` and the model's extension validator to accept `.heic`.
- pillow-heif 1.7.0 requires `pillow>=11.1.0` and ships manylinux x86_64 wheels for CPython 3.12, so the nixpacks `uv sync --frozen` build needs no system packages.
- The existing test conventions to follow: `pytestmark = pytest.mark.django_db`, fixtures over setup methods, an autouse fixture pointing `MEDIA_ROOT` at `tmp_path` (`privatemedia/tests/test_gate.py:29`), Pillow-generated image bytes rather than binary fixtures.
- URL names are the landing contract: `settings.py:254` says S-03 repoints the landing page "by changing one string". This plan uses the same mechanism in the other direction.

## What We're NOT Doing

- Editing or deleting a garment, and the incomplete-outfit rule — S-06.
- A garment detail page. The list tile is the whole garment view in this slice.
- Outfits, the outfit grid, or any change to `/wardrobe/` beyond one stale sentence — S-03.
- Filtering or searching garments by type. The closed type list makes it possible later; this slice does not build it.
- Thumbnails or multiple sizes per photo, and pagination of the list.
- Keeping the original, full-resolution photo.
- Automated browser tests (Playwright or similar) for the shrink script.
- Removing files from disk when a user is deleted — pre-existing F-01 behaviour, unchanged here.
- Object storage, a CDN, background jobs for image processing.
- Translating the UI; it stays in English like S-01.

## Implementation Approach

Build from the inside out, so each phase is testable on its own before anything user-visible depends on it.

1. **Processing lives in `privatemedia`**, next to the gate, as one function that turns any accepted upload into a normalized JPEG. S-04's outfit photos call the same function, the same way they already inherit the ownership check.
2. **A new `garments` app** holds the `Garment` model. Named `garments` rather than `wardrobe` so its URL namespace does not read like the existing `wardrobe` route name; S-03 adds an `outfits` app with a many-to-many to `garments.Garment`. Rules that must hold on every path (type/Other, owner consistency) live in the model's `clean()` and are enforced by `save()` calling `full_clean()` — the pattern `PrivateImage` established — plus a database check constraint so PostgreSQL enforces the Other rule even against a bulk update.
3. **Pages are plain server-rendered Django forms** — work with JavaScript off, render errors the usual way, redirect after POST.
4. **The browser shrink script is a progressive enhancement** layered on the working form. It only ever replaces the selected file with a smaller JPEG; any failure leaves the original in place and the server path, already proven in Phases 1–3, handles it.
5. **Production last**: an explicit gunicorn worker count, the deploy, and the real-phone check of the five-second budget.

## Critical Implementation Details

**Order of operations in `normalize_photo`.** `Image.draft()` only has an effect before pixel data is loaded, and `ImageOps.exif_transpose()` loads it — so draft first, then transpose, then resize. Draft lets libjpeg decode a 12 MP photo at 1/2 or 1/4 scale, which is what keeps server-side processing well under a second and memory bounded. Keep the ICC profile when re-encoding (`icc_profile=` from the source's `info`) but pass no `exif`: iPhone photos are Display P3, and dropping the profile visibly desaturates them, while dropping EXIF is the point.

**HEIC orientation.** libheif applies the container's rotation on decode. If pillow-heif still exposes an orientation value in EXIF, `exif_transpose` would rotate a second time. The Phase 1 tests must include an oriented HEIC case; if a fixture cannot be generated, the Phase 1 manual check with a real iPhone HEIC is the gate.

**No orphaned file on a failed save.** The `PrivateImage` row and file are written before the `Garment` row. A database rollback removes the row but never the bytes on the volume, so the add view must delete the stored file explicitly (`image.image.delete(save=False)`) when anything after the file write fails, then re-raise.

**ModelForm validation calls `Garment.clean()` before `owner` and `photo` are set.** The owner-consistency check must skip itself when either id is unset, or every form submission fails with a spurious error.

## Phase 1: Photo normalization in `privatemedia`

### Overview

Add HEIC support and a single reusable function that turns an accepted upload into an upright, metadata-free JPEG of at most 1600 px on the long edge, or raises a `ValidationError` a form can show. No user-visible change.

### Changes Required:

#### 1. HEIC dependency

**File**: `pyproject.toml`, `uv.lock`

**Intent**: Let the server read photos from Apple devices, which a Mac upload or a non-Safari browser sends as HEIC.

**Contract**: `uv add pillow-heif` (resolves to `>=1.7`). Never hand-edit `uv.lock`.

#### 2. Register the HEIF opener at startup

**File**: `privatemedia/apps.py`

**Intent**: Make HEIC a format Pillow — and therefore Django's image validation — recognizes, everywhere, before any request is served.

**Contract**: `PrivatemediaConfig.ready()` calls `pillow_heif.register_heif_opener()`. Afterwards `get_available_image_extensions()` includes `heic` and `heif`. A comment notes that the model's `validate_image_file_extension` and `forms.ImageField` both depend on this registration.

#### 3. The normalization function

**File**: `privatemedia/processing.py` (new)

**Intent**: One place that decides what a stored photo looks like, so garments now and outfit photos in S-04 store identical, private, small files.

**Contract**: `normalize_photo(upload) -> django.core.files.base.ContentFile`.
- Output: a JPEG named `photo.jpg` (so `upload_to_uuid` keeps a `.jpg` extension and the gate serves `image/jpeg`), long edge ≤ `MAX_EDGE_PX = 1600`, never upscaled, quality `JPEG_QUALITY = 85`, progressive and optimized, no EXIF/XMP/GPS, ICC profile preserved when present.
- Orientation applied from EXIF before resizing.
- Modes with transparency (`RGBA`, `LA`, `P` with transparency) are composited onto white; everything else converted to `RGB`.
- Raises `ValidationError` with code `invalid_image` for anything Pillow cannot identify or fully decode (unidentified, truncated, `OSError`), and code `image_too_many_pixels` for `Image.DecompressionBombError`. Pillow's default pixel ceiling (~179 MP hard limit) is kept and named in a comment — it is what stops a crafted image from exhausting the worker's memory.
- Leaves the input file's read position reset so a caller can still inspect it.

#### 4. Tests

**File**: `privatemedia/tests/test_processing.py` (new)

**Intent**: Prove every property the privacy guardrail and the five-second budget depend on, since none of them is visible in a browser.

**Contract**: Images generated with Pillow (and pillow-heif for HEIC) in memory. Cases:
- landscape and portrait inputs above the limit come out with a 1600 px long edge and preserved aspect ratio; an input below the limit is not upscaled
- an input with EXIF orientation 6 comes out rotated (width and height swapped) and carries no orientation tag
- an input with a GPS IFD comes out with no EXIF at all
- an input with an ICC profile keeps it
- an `RGBA` PNG with transparency comes out as an `RGB` JPEG
- a HEIC input decodes and comes out as JPEG; an oriented HEIC comes out upright and not rotated twice
- random bytes and a truncated JPEG raise `ValidationError` with code `invalid_image`
- with `Image.MAX_IMAGE_PIXELS` monkeypatched low, an oversized image raises code `image_too_many_pixels`
- the output can be stored via `PrivateImage.objects.create(...)` and passes its validators, and the stored name ends in `.jpg`
- `.heic` is in `get_available_image_extensions()`

### Success Criteria:

#### Automated Verification:

- The new processing tests pass: `uv run pytest privatemedia/tests/test_processing.py`
- The full suite still passes: `uv run pytest`
- System checks pass: `uv run python manage.py check`
- Linting passes: `uv run ruff check .`
- Formatting is clean: `uv run ruff format --check .`
- pillow-heif introduces no known vulnerability: `uv run pip-audit`

#### Manual Verification:

- A real iPhone HEIC photo and a real Android JPEG, run through `normalize_photo` in `uv run python manage.py shell`, come out upright, with natural colours, under ~500 KB, and with no EXIF when reopened with Pillow
- Normalizing a 12 MP camera JPEG takes under one second locally

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 2: `Garment` model

### Overview

Create the `garments` app with the `Garment` model, its rules, its migration and a staff-only admin registration. Still no user-visible page.

### Changes Required:

#### 1. The app

**File**: `garments/__init__.py`, `garments/apps.py`, `garments/migrations/__init__.py`, `outfits_garderobe/settings.py`

**Intent**: A home for garments that S-03's `outfits` app can depend on.

**Contract**: `GarmentsConfig` with `default_auto_field = 'django.db.models.BigAutoField'` like `privatemedia`; `'garments'` appended to `INSTALLED_APPS` after `'privatemedia'`.

#### 2. The model

**File**: `garments/models.py`

**Intent**: One garment: whose it is, which private photo shows it, what type it is, and an optional note — with the Other rules enforced on every path, not just the form.

**Contract**:
- `GarmentType(models.TextChoices)`, in this order: `tshirt` "T-shirt", `shirt` "Shirt", `sweater` "Sweater", `outerwear` "Jacket / coat", `trousers` "Trousers", `shorts` "Shorts", `skirt` "Skirt", `dress` "Dress", `shoes` "Shoes", `accessory` "Accessory", `other` "Other".
- Fields: `id` UUID primary key (as `PrivateImage`); `owner` FK to `settings.AUTH_USER_MODEL`, `CASCADE`, `related_name='garments'`; `photo` `OneToOneField(PrivateImage, on_delete=models.RESTRICT, related_name='garment')`; `type` `CharField(max_length=20, choices=GarmentType.choices)`; `type_other` `CharField(max_length=40, blank=True)`; `description` `CharField(max_length=200, blank=True)`; `created_at` `DateTimeField(auto_now_add=True)`.
- `Meta`: `ordering = ['-created_at']`; index on `['owner', '-created_at']`; `CheckConstraint` named `garment_type_other_matches_type` — `type_other` is non-empty exactly when `type == 'other'`.
- `clean()`, in order: collapse runs of whitespace and strip `type_other` and strip `description`; if `type != 'other'`, clear `type_other`; if `type == 'other'` and the tidied text case-insensitively equals the label or value of any other choice, set `type` to that choice and clear `type_other`; if `type == 'other'` and the text is empty, raise `ValidationError({'type_other': ...})`; if both `owner_id` and `photo_id` are set and `photo.owner_id != owner_id`, raise `ValidationError`.
- `save()` calls `full_clean()` before saving, with a comment pointing at the same reasoning in `PrivateImage.save()`.
- `display_type` property: `type_other` when `type == 'other'`, otherwise the choice label.
- `photo_url` property: `reverse('privatemedia:image', args=[self.photo_id])` — reverses the gate without fetching the `PrivateImage` row, and never touches `.url`.
- `__str__` returns `display_type`, plus the description when present.

#### 3. Migration

**File**: `garments/migrations/0001_initial.py`

**Intent**: Create the table and the check constraint on both SQLite and PostgreSQL.

**Contract**: Generated with `uv run python manage.py makemigrations garments`; depends on `privatemedia`'s latest migration and the auth user model.

#### 4. Admin

**File**: `garments/admin.py`

**Intent**: A staff-only inspection surface, matching `privatemedia/admin.py`.

**Contract**: `GarmentAdmin` with `list_display` of type, description, owner and creation time; `list_filter` on owner and type; `created_at` read-only.

#### 5. Tests

**File**: `garments/tests/__init__.py`, `garments/tests/test_model.py`

**Intent**: Pin the rules that keep type data clean for a future filter and keep a garment's photo tied to its owner.

**Contract**: Cases:
- folding, parametrized: `'shirt '`, `'SHIRT'`, `'tshirt'`, `'  jacket   /  coat '` each save as the matching choice with empty `type_other`
- a non-matching `'Wool   scarf '` saves as `other` with `type_other == 'Wool scarf'`
- `other` with blank or whitespace-only text raises a `type_other` error
- a non-Other type with leftover text saves with `type_other` cleared
- the check constraint holds at the database level: a `QuerySet.update()` that bypasses `clean()` raises `IntegrityError`
- a garment whose photo belongs to another user is rejected
- one `PrivateImage` cannot back two garments
- deleting the user removes their garments and their `PrivateImage` rows without error (the `RESTRICT` case)
- deleting a `PrivateImage` that a garment uses directly raises `RestrictedError`
- a 201-character description is rejected
- `display_type` and `photo_url` return the expected values, and `photo_url` makes no query

### Success Criteria:

#### Automated Verification:

- The migration applies cleanly: `uv run python manage.py migrate`
- Nothing is left unmigrated: `uv run python manage.py makemigrations --check --dry-run`
- The model tests pass: `uv run pytest garments/tests/test_model.py`
- The full suite still passes: `uv run pytest`
- System checks pass: `uv run python manage.py check`
- Linting passes: `uv run ruff check .`
- Formatting is clean: `uv run ruff format --check .`

#### Manual Verification:

- In `/admin/`, a staff user can create a garment against an existing `PrivateImage`; choosing *Other* with the text "shirt" saves it as *Shirt*
- The admin refuses *Other* with no text and shows the error on that field

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 3: Add and list pages

### Overview

Ship the user-visible slice with no JavaScript: the add form, the garment list, the header link, the landing change, and the tests that prove ownership and failure handling through HTTP.

### Changes Required:

#### 1. The form

**File**: `garments/forms.py`

**Intent**: Accept a photo plus garment fields, reject bad photos with a readable message before anything is stored, and hand the view a ready-to-store normalized file.

**Contract**: `GarmentForm(forms.ModelForm)` over `type`, `type_other`, `description`, plus a non-model `photo = forms.ImageField` rendered with `accept="image/*"` and **no** `capture` attribute. The `type` select starts with an empty "Choose a type" option and is required. `clean_photo()` first applies `validate_max_size` to the raw upload (so a 20 MB file is refused before decoding), then calls `normalize_photo`, keeping the upload's original name for the view. The `type_other` field carries a wrapper class the CSS uses to show it only when *Other* is selected.

#### 2. Views

**File**: `garments/views.py`

**Intent**: A private list of the requester's garments, and an add flow that either stores a complete garment or stores nothing.

**Contract**:
- `garment_list` (`@login_required`): `Garment.objects.filter(owner=request.user)` in model ordering, rendered with `garments/list.html`. The query count does not grow with the number of garments.
- `garment_add` (`@login_required`): GET renders an empty form; a valid POST, inside `transaction.atomic()`, creates the `PrivateImage` (owner = requester, the normalized file, `original_filename` = the upload's name truncated to 255), sets `owner` and `photo` on the form instance and saves it; if anything after the file is written raises, deletes the stored file and re-raises. On success: `messages.success(request, 'Garment added.')` and redirect to `garments:list`. An invalid POST re-renders the form with status 200.

#### 3. URLs

**File**: `garments/urls.py`, `outfits_garderobe/urls.py`

**Intent**: Give the slice its routes without touching `/wardrobe/`.

**Contract**: `app_name = 'garments'`; `''` → `garment_list` named `list`; `'add/'` → `garment_add` named `add`. Included as `path('garments/', include('garments.urls'))` above the catch-all `privatemedia` include.

#### 4. Templates

**File**: `templates/garments/list.html`, `templates/garments/add.html`

**Intent**: A phone-first list whose tiles show the photo and what the garment is, and a short form that fits at 360 px.

**Contract**:
- Both extend `base.html`.
- `list.html`: heading, a prominent *Add garment* link styled as a button at the top, an empty state with the same call to action, and a `<ul class="garment-grid">` of tiles. Each tile has an `<img>` whose `src` is `garment.photo_url`, with `loading="lazy"`, `decoding="async"` and `alt` built from type and description, plus a caption with `display_type` and the description.
- `add.html`: a `multipart/form-data` POST form with `{% csrf_token %}`, the four fields with labels and errors, a *Save garment* submit button and a *Cancel* link back to the list.

#### 5. Styles

**File**: `static/css/app.css`

**Intent**: The minimum layout Pico does not provide, in keeping with the file's own warning against growing into a design system.

**Contract**: `.garment-grid` as a CSS grid with `repeat(auto-fill, minmax(9rem, 1fr))` and no list styling; tile images square via `aspect-ratio: 1` and `object-fit: cover`, so lazy-loaded tiles do not shift the layout. The Other field is visible by default and hidden with `:has()` when the type select's `other` option is not selected — browsers without `:has()` simply always show it.

#### 6. Navigation and landing

**File**: `templates/base.html`, `outfits_garderobe/settings.py`, `accounts/views.py`, `templates/wardrobe.html`

**Intent**: Make garments reachable and make login land on real content until S-03 replaces it with the outfit grid.

**Contract**:
- A *Garments* link to `garments:list` first in the authenticated nav.
- `LOGIN_REDIRECT_URL = 'garments:list'`, with the adjacent comment updated to say S-03 points it back at the outfit grid.
- `home` redirects authenticated visitors to `garments:list`, docstring updated to match.
- The placeholder's "Adding garments … arrive in the next slices" sentence is replaced with a link to the garments page; the placeholder otherwise stays as is.

#### 7. Tests

**File**: `garments/tests/test_views.py` (new), `accounts/tests/test_smoke.py`

**Intent**: Prove through HTTP that garments are private, that a failed add leaves nothing behind, and that the landing change is deliberate.

**Contract**: Autouse `MEDIA_ROOT` → `tmp_path` fixture as in `privatemedia`. Cases:
- anonymous GET of list and add redirects to `settings.LOGIN_URL`
- the list shows the requester's garments newest first, and a second user's list contains neither the first user's description nor their photo URL
- the owner can fetch a tile's `src` (200) and a stranger gets 404
- a valid POST creates one `Garment` and one `PrivateImage`, both owned by the requester, stored as a JPEG with a long edge ≤ 1600 px and `original_filename` equal to the uploaded name; the response redirects to the list and the followed page shows "Garment added."
- a valid POST with a HEIC photo succeeds
- *Other* with the text "Shirt" is stored as `shirt`
- an invalid POST (*Other* with no text) returns 200 with a field error and leaves no `Garment`, no `PrivateImage` and no file under `MEDIA_ROOT`
- a corrupt photo and a raw upload over 10 MB each return a `photo` field error and store nothing
- when `Garment.save` is monkeypatched to raise after the photo is stored, no `PrivateImage` row and no file under `MEDIA_ROOT` remain
- the list's query count is the same for one garment as for five
- the add page's photo input has `accept="image/*"` and no `capture` attribute
- in `accounts/tests/test_smoke.py`, the two landing assertions (`test_root_sends_authenticated_visitors_to_the_wardrobe`, `test_verified_account_logs_in_and_lands_on_the_wardrobe`) now expect `reverse('garments:list')`, renamed to say so, with `/wardrobe/` itself still covered by the existing render and redirect tests

### Success Criteria:

#### Automated Verification:

- The view tests pass: `uv run pytest garments/tests/test_views.py`
- The updated smoke suite passes: `uv run pytest accounts/tests/`
- The full suite passes: `uv run pytest`
- System checks pass: `uv run python manage.py check`
- Nothing is left unmigrated: `uv run python manage.py makemigrations --check --dry-run`
- `collectstatic` succeeds under manifest storage: `uv run python manage.py collectstatic --noinput`
- Linting passes: `uv run ruff check .`
- Formatting is clean: `uv run ruff format --check .`

#### Manual Verification:

- Logging in lands on the garment list; the header shows *Garments*
- Adding a garment with a large desktop JPEG works and the new tile appears first with a "Garment added." message
- Picking *Other* reveals the text field; picking another type hides it
- A form error (e.g. *Other* with no text) shows next to the field
- Logged in as a second account, the list is empty and the first account's photo URL returns 404
- At 360 px the list shows a tidy grid and the form fits without horizontal scrolling
- With JavaScript disabled the whole flow still works

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 4: Browser-side photo shrinking

### Overview

Add the progressive-enhancement script that replaces a large selected photo with a ≤ 1600 px JPEG before the form is submitted, so the upload over mobile data is a few hundred kilobytes instead of several megabytes.

### Changes Required:

#### 1. The script

**File**: `static/js/photo-shrink.js` (new)

**Intent**: Remove the upload leg from the five-second budget without ever becoming a way for adding a garment to fail.

**Contract**:
- Attaches to file inputs marked with a `data-shrink-photo` attribute. Does nothing unless `createImageBitmap`, `HTMLCanvasElement.prototype.toBlob` and `DataTransfer` all exist.
- On the input's `change`:
  - decode with `createImageBitmap(file, { imageOrientation: 'from-image' })`
  - if the long edge is already ≤ 1600 px and the file is ≤ 1 MB, leave it untouched
  - otherwise draw it straight onto a canvas sized to fit 1600 px, export with `toBlob('image/jpeg', 0.85)`, wrap it as a `File` named after the original with a `.jpg` extension, and replace `input.files` through a `DataTransfer`
- While working, the form's submit button is disabled and a short status text ("Preparing photo…") is shown; both are restored whatever the outcome.
- If the user picks another photo mid-processing, the earlier result is discarded, not applied.
- Any failure — HEIC that the browser cannot decode, memory pressure, an unsupported API — leaves the original file selected and re-enables submit; the server path handles it.
- No inline script and no external dependency.

#### 2. Wiring

**File**: `templates/garments/add.html`, `garments/forms.py`

**Intent**: Load the script only where it is used, and mark the input it acts on.

**Contract**: The photo widget gains `data-shrink-photo`. `add.html` loads `{% static 'js/photo-shrink.js' %}` with `defer` in the `extra_body` block, and contains the (initially empty) status element the script writes to.

#### 3. Tests

**File**: `garments/tests/test_views.py`

**Intent**: Pin the wiring; the behaviour itself is verified by hand on real phones by decision.

**Contract**: The add page references the static script and its photo input carries `data-shrink-photo`.

### Success Criteria:

#### Automated Verification:

- The full suite passes: `uv run pytest`
- `collectstatic` picks up the script under manifest storage: `uv run python manage.py collectstatic --noinput`
- Linting passes: `uv run ruff check .`
- Formatting is clean: `uv run ruff format --check .`

#### Manual Verification:

- In desktop Chrome with a 4+ MB JPEG, the network panel shows the POST body well under 1 MB, and the stored photo is upright
- Under the *Fast 4G* network throttle, saving a large photo takes under five seconds from pressing *Save* until the list is shown
- On a real iPhone (Safari), against `runserver` on the local network, a garment added with a freshly taken photo stores an upright image
- On a real Android phone (Chrome), both *Take photo* and *Choose from library* are offered and both work
- A HEIC file dragged in from a Mac in Chrome still saves (fallback to the server path)
- With JavaScript disabled, adding a garment still works

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 5: Production

### Overview

Give gunicorn enough workers that one upload cannot block everyone else, deploy, and verify the whole slice against production on real phones over mobile data.

### Changes Required:

#### 1. Explicit gunicorn worker count

**File**: `railway.toml`, `Procfile`

**Intent**: With the default single sync worker, one upload — plus the per-tile image requests of any list page — queues behind itself. Two workers keep the list responsive while a photo is being received and processed.

**Contract**: Both start commands gain `--workers 2`, kept identical between the two files, with a comment in `railway.toml` giving the reason and noting that each worker's memory peak includes decoding one photo.

#### 2. Deploy

**File**: none — an operation

**Intent**: Ship the slice the same way S-01 Phase 5 did.

**Contract**: Push; Railway builds with nixpacks (`uv sync --frozen` installs the pillow-heif wheel), runs `migrate` as the pre-deploy command, and passes the `/health/` check. Photos land on the existing `/data` volume; there are no data migrations and no new environment variables.

#### 3. Change record

**File**: `context/changes/add-garment/change.md`

**Intent**: Leave a record of what production verification found, as S-01 did.

**Contract**: A dated "Production deploy" note in `## Notes` with the deployment id, the measured phone timings, and anything that deviated from this plan.

### Success Criteria:

#### Automated Verification:

- The full suite passes on the commit being deployed: `uv run pytest`
- The deploy-configuration guard still passes: `uv run pytest accounts/tests/test_deploy_config.py`
- The deployment reaches a healthy state — `/health/` returns 200 after deploy
- Deploy logs show pillow-heif installed, `collectstatic` and `migrate` (including `garments.0001_initial`) completing, and two gunicorn workers booting

#### Manual Verification:

- On a real iPhone over mobile data (Wi-Fi off), adding a garment with a freshly taken photo takes under five seconds from tapping *Save* to seeing the list
- The same on a real Android phone over mobile data
- The stored production photo is upright, a few hundred kilobytes, and carries no GPS metadata (checked by downloading it through the gate and opening it with Pillow)
- A second production account sees an empty list and gets 404 on the first account's photo URL
- The garment list with at least ten garments loads acceptably on the phone, and Railway metrics show no memory alarm during uploads

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Testing Strategy

### Unit Tests:

- `normalize_photo`: size limit, no upscaling, orientation, EXIF/GPS removal, ICC preservation, transparency, HEIC (including orientation), corrupt and truncated input, the pixel ceiling, compatibility with `PrivateImage` validators
- `Garment`: Other tidying and folding, the check constraint at the database level, owner/photo consistency, one-to-one uniqueness, `RESTRICT` behaviour on user deletion and on direct photo deletion, description length, `display_type`/`photo_url`

### Integration Tests:

- HTTP-level ownership: a stranger's list and photo URL
- The add flow end to end: a valid JPEG, a valid HEIC, the Other fold through the form
- Failure leaves nothing: invalid form, corrupt photo, oversized raw upload, a failure after the file is written
- The list query count stays constant as garments grow
- The landing change through `/` and through login

### Manual Testing Steps:

1. Log in → land on the garment list → *Add garment* → take a photo on a phone → choose *Shirt* → save → tile appears first.
2. Add a garment as *Other* / "shirt" → it is shown as *Shirt*.
3. Add a garment from a Mac HEIC in Chrome → saves and shows upright.
4. Disable JavaScript → add a garment → still works.
5. Log in as a second account → list empty → first account's photo URL is 404.
6. Time *Save* → list on real phones over mobile data, locally in Phase 4 and against production in Phase 5.

## Performance Considerations

- **Upload**: the browser script cuts the POST from 3–5 MB to roughly 200–400 KB; the server path keeps a no-JS or failed-script upload correct, just slower.
- **Server processing**: JPEG draft mode decodes at reduced scale, keeping normalization under a second and memory bounded. HEIC has no draft mode and is decoded at full size — slower, but it only arrives from desktops, where the browser script cannot shrink it.
- **List**: one query for the garments regardless of count (`photo_url` uses `photo_id`); tiles are lazy-loaded and fixed-size; each visible tile is one gate request with the gate's existing conditional GET, so repeat visits are 304s.
- **Workers**: two sync workers so an in-flight upload does not stall other requests. Revisit only if Railway memory metrics show pressure.
- **Storage**: normalized photos make the 5000 MB volume last for well over ten thousand garments.

## Migration Notes

- One new table (`garments_garment`) with a check constraint; no changes to existing tables and no data migration.
- Existing `PrivateImage` rows (if any in production) are unaffected and not linked to garments.
- Rollback: reverting the code leaves an unused table; `migrate garments zero` removes it. Uploaded files stay on the volume, as with any F-01 file.

## References

- Roadmap item: `context/foundation/roadmap.md` — S-02 (`add-garment`), Jira OG-3
- PRD: `context/foundation/prd.md` — FR-003, US-01, NFR *Prywatność*, *Responsywność*, *Szybkość*
- Gate and model to inherit from: `privatemedia/models.py:21`, `privatemedia/views.py:52`
- Test conventions: `privatemedia/tests/test_gate.py`, `accounts/tests/test_smoke.py`
- Landing contract: `outfits_garderobe/settings.py:254`, `accounts/views.py:13`
- Prior plans: `context/changes/private-media-gate/plan.md`, `context/changes/user-accounts/plan.md`
- Django `on_delete=RESTRICT`: https://docs.djangoproject.com/en/6.0/ref/models/fields/#django.db.models.RESTRICT
- Pillow `Image.draft`, `ImageOps.exif_transpose`: https://pillow.readthedocs.io/en/stable/reference/Image.html
- pillow-heif: https://pypi.org/project/pillow-heif/

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Photo normalization in `privatemedia`

#### Automated

- [x] 1.1 The new processing tests pass: `uv run pytest privatemedia/tests/test_processing.py`
- [x] 1.2 The full suite still passes: `uv run pytest`
- [x] 1.3 System checks pass: `uv run python manage.py check`
- [x] 1.4 Linting passes: `uv run ruff check .`
- [x] 1.5 Formatting is clean: `uv run ruff format --check .`
- [x] 1.6 pillow-heif introduces no known vulnerability: `uv run pip-audit`

#### Manual

- [x] 1.7 A real iPhone HEIC and a real Android JPEG normalize upright, with natural colours, under ~500 KB, with no EXIF
- [x] 1.8 Normalizing a 12 MP camera JPEG takes under one second locally

### Phase 2: `Garment` model

#### Automated

- [ ] 2.1 The migration applies cleanly: `uv run python manage.py migrate`
- [ ] 2.2 Nothing is left unmigrated: `uv run python manage.py makemigrations --check --dry-run`
- [ ] 2.3 The model tests pass: `uv run pytest garments/tests/test_model.py`
- [ ] 2.4 The full suite still passes: `uv run pytest`
- [ ] 2.5 System checks pass: `uv run python manage.py check`
- [ ] 2.6 Linting passes: `uv run ruff check .`
- [ ] 2.7 Formatting is clean: `uv run ruff format --check .`

#### Manual

- [ ] 2.8 In `/admin/`, *Other* with the text "shirt" saves as *Shirt*
- [ ] 2.9 The admin refuses *Other* with no text and shows the error on that field

### Phase 3: Add and list pages

#### Automated

- [ ] 3.1 The view tests pass: `uv run pytest garments/tests/test_views.py`
- [ ] 3.2 The updated smoke suite passes: `uv run pytest accounts/tests/`
- [ ] 3.3 The full suite passes: `uv run pytest`
- [ ] 3.4 System checks pass: `uv run python manage.py check`
- [ ] 3.5 Nothing is left unmigrated: `uv run python manage.py makemigrations --check --dry-run`
- [ ] 3.6 `collectstatic` succeeds under manifest storage: `uv run python manage.py collectstatic --noinput`
- [ ] 3.7 Linting passes: `uv run ruff check .`
- [ ] 3.8 Formatting is clean: `uv run ruff format --check .`

#### Manual

- [ ] 3.9 Logging in lands on the garment list; the header shows *Garments*
- [ ] 3.10 Adding a garment with a large desktop JPEG works and the new tile appears first with a "Garment added." message
- [ ] 3.11 Picking *Other* reveals the text field; picking another type hides it
- [ ] 3.12 A form error shows next to the field
- [ ] 3.13 A second account sees an empty list and gets 404 on the first account's photo URL
- [ ] 3.14 At 360 px the list shows a tidy grid and the form fits without horizontal scrolling
- [ ] 3.15 With JavaScript disabled the whole flow still works

### Phase 4: Browser-side photo shrinking

#### Automated

- [ ] 4.1 The full suite passes: `uv run pytest`
- [ ] 4.2 `collectstatic` picks up the script under manifest storage: `uv run python manage.py collectstatic --noinput`
- [ ] 4.3 Linting passes: `uv run ruff check .`
- [ ] 4.4 Formatting is clean: `uv run ruff format --check .`

#### Manual

- [ ] 4.5 In desktop Chrome with a 4+ MB JPEG, the POST body is well under 1 MB and the stored photo is upright
- [ ] 4.6 Under *Fast 4G* throttling, *Save* → list takes under five seconds
- [ ] 4.7 On a real iPhone (Safari) against local `runserver`, a freshly taken photo stores upright
- [ ] 4.8 On a real Android phone (Chrome), both *Take photo* and *Choose from library* work
- [ ] 4.9 A HEIC file from a Mac in Chrome still saves
- [ ] 4.10 With JavaScript disabled, adding a garment still works

### Phase 5: Production

#### Automated

- [ ] 5.1 The full suite passes on the commit being deployed: `uv run pytest`
- [ ] 5.2 The deploy-configuration guard still passes: `uv run pytest accounts/tests/test_deploy_config.py`
- [ ] 5.3 The deployment reaches a healthy state — `/health/` returns 200 after deploy
- [ ] 5.4 Deploy logs show pillow-heif installed, `collectstatic` and `migrate` completing, and two gunicorn workers booting

#### Manual

- [ ] 5.5 On a real iPhone over mobile data, *Save* → list takes under five seconds
- [ ] 5.6 On a real Android phone over mobile data, *Save* → list takes under five seconds
- [ ] 5.7 The stored production photo is upright, a few hundred kilobytes, and has no GPS metadata
- [ ] 5.8 A second production account sees an empty list and gets 404 on the first account's photo URL
- [ ] 5.9 The list with at least ten garments loads acceptably on the phone, and Railway memory metrics show no alarm during uploads
