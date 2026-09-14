# tests/ — risk tests

Tests here are organised by **risk**, not by module. Strategy and risk numbers: `context/foundation/test-plan.md` §2; cookbook: §6.

## Layout rule

- **A folder is a test-plan §2 risk.** Current folders:
  - `cross_user_visibility/`: #1, a photo or owner record visible to another user or to an anonymous visitor.
  - `foreign_id_writes/`: #2, a write carrying another user's ids changes their data.
  - `garment_deletion_keeps_outfits/`: #5, deleting a garment deletes its outfits or leaves them looking complete.
- **A file is one failure scenario**, named as a sentence describing the protection: `test_<scenario>.py`, e.g. `test_stranger_sees_nothing_of_the_owner.py`. Its docstring says what the scenario proves.
- **Per-app `tests/` packages** (`garments/tests/`, `outfits/tests/`, …) keep module-level behaviour: forms, models, a single view's happy path. Don't put cross-cutting risk scenarios there.

## Adding an owner-scoped route

Authentication is default-deny (`LoginRequiredMiddleware`), so every new project view is guarded, and `test_new_guarded_route_cannot_skip_the_contract.py` **fails until the route is registered**.

The only file to edit is `tests/owner_scoped_routes.py`. Add an entry to `ROUTES`, keyed by the name `reverse` takes (`'outfits:delete'`):

- `kind`: `'read'` if the view only shows data, `'write'` if a POST stores or deletes something.
- `seed(user) -> Seeded`: builds the user's data. It returns the `reverse` kwargs (e.g. `{'pk': outfit.pk}`, or `{}` if the route has none) and the `markers` that must never reach anyone else: names, descriptions, photo URLs, pks. Reuse `_seed_wardrobe` with `kwargs_for=` where it fits.
- `shows_photos`: `True` if the owner's page renders their photos as `<img src>`. The photo test also checks a `False` claim.
- `post_only`: `True` for a `@require_POST` action with no page of its own (e.g. `'outfits:tag_remove'`). The photo test then requires GET → 405 and `shows_photos=False`, and the stranger test probes it with `foreign_payload` instead of a GET.
- `foreign_payload(seeded, requester) -> dict` (writes only): a POST body aimed at the seeded user's objects. `requester` is the stranger posting it, or `None`. When it isn't `None`, mix in one of the stranger's own objects.

With the entry in place, these scenarios pick the route up with no per-route test code:

| Scenario file | Routes | What it proves |
|---|---|---|
| `cross_user_visibility/test_anonymous_visitor_only_reaches_login.py` | all | GET and POST → 302 to login, no markers, no rows stored |
| `cross_user_visibility/test_stranger_sees_nothing_of_the_owner.py` | all | with kwargs: the owner's id answers exactly like a random UUID (404, same bytes, no validators; POSTed for `post_only`); without: 200 with only the stranger's own data |
| `cross_user_visibility/test_photos_shown_to_the_owner_stay_owner_only.py` | all | every gated `<img src>` → 200 owner, 404 stranger, login for anonymous |
| `foreign_id_writes/test_write_aimed_at_another_users_objects_changes_nothing.py` | `kind='write'` | the owner's snapshot is unchanged, no cross-owner link, anything accepted belongs to the stranger |

**Public views** opt out with `@login_not_required`. They must also be added to `PUBLIC_PROJECT_VIEWS` in `cross_user_visibility/test_login_is_required_unless_a_view_opts_out.py`, with a one-line reason. A registered owner-scoped route that opts out fails the net.

## Adding a scenario file

- Put it in the folder of the risk it protects against, with a sentence name. A new risk means a new folder, and it must exist in test-plan §2 first.
- If the scenario applies to every route, parametrize over `ROUTES` (or filter by `kind`) instead of naming routes.
- Assert behaviour taken from the PRD or the risk, never values copied from the implementation.
- **Never assert the status code alone.** Re-read the database (`tests/conftest.py` has `snapshot_of` and `assert_no_cross_owner_links`, available in every risk folder), and check that the owner's markers are absent from the body.
- Make sure the check can't pass vacuously. Give the stranger data of their own, and require at least one collected item.

## Factories and fixtures

- `tests/factories.py`: `make_image(user)`, `make_garment(user, type=..., **fields)`, `make_outfit(user, garments=(), **fields)`. Per-app tests import them from here too; don't copy them.
- The root `conftest.py` provides `owner`, `stranger` and `temp_media_root`. Factories write real files, so modules that use them declare `pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures('temp_media_root')]`.

## Run

```bash
uv run pytest                                   # whole suite
uv run pytest tests/cross_user_visibility       # one risk folder
uv run pytest tests/foreign_id_writes/test_posted_owner_and_photo_fields_are_ignored.py   # one scenario
uv run pytest tests -k "outfits:delete"         # every contract case for one route
```
