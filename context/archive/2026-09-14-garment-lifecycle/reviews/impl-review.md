<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Garment Lifecycle Implementation Plan

- **Plan**: context/changes/garment-lifecycle/plan.md
- **Scope**: Phases 0–4 of 6 (Phase 5 w toku: PR #8 otwarty, manualne 5.8–5.11 czekają)
- **Date**: 2026-09-14
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical, 2 warnings, 8 observations

Weryfikacja automatyczna (uruchomiona podczas review): `uv run pytest` 410 passed; `migrate` nic do zastosowania; `makemigrations --check --dry-run` brak zmian; `manage.py check` 0 problemów; `collectstatic` OK; `ruff check` czysto; `ruff format --check` czysto. Komendy `manage.py` wymagają `DEBUG=True uv run --env-file …` (lessons).

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | WARNING |
| Scope Discipline | PASS |
| Safety & Quality | WARNING |
| Architecture | WARNING |
| Pattern Consistency | WARNING |
| Success Criteria | WARNING |

## Findings

### F1 — Outfit edit zapisuje nieaktualny wiersz: wskrzesza usunięty outfit i nadpisuje zdjęcie

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: outfits/views.py:151 (`outfit_edit`) → outfits/views.py:379 (`_store_outfit`)
- **Detail**: `outfit_edit` wczytuje outfit bez blokady i zapisuje go przez `form.save(commit=False)` + `outfit.save()`, czyli UPDATE wszystkich kolumn z wartościami wczytanymi przed walidacją. Wszystkie inne ścieżki zapisu (zdjęcie, usuwanie) przechodzą przez `_locked_outfit`. Skutki (odtworzone przez agenta na testowej bazie): (1) gdy outfit zostanie usunięty między walidacją a zapisem, UPDATE nie trafia w żaden wiersz i Django robi INSERT — outfit wraca z nową nazwą i ubraniami, bez tagów, brakujących slotów i zdjęcia (łamie NFR *Trwałość danych* w drugą stronę: dane wracają wbrew jawnej akcji); (2) gdy w drugiej karcie zdjęcie zostanie wymienione/usunięte, `full_clean()` odrzuca nieaktualne `photo_id`, a `except (IntegrityError, ValidationError)` pokazuje mylące „You already have an outfit with this name."; (3) wniosek z tego samego mechanizmu (niezreprodukowany): gdy outfit nie miał zdjęcia, a druga karta właśnie je dodała, edycja zapisze `photo_id = NULL` i nowe zdjęcie zostaje osierocone (wiersz + plik). Okno jest wąskie (dwie karty / dwa urządzenia), ale skutek to cicha utrata lub przywrócenie danych.
- **Fix A ⭐ Recommended**: W `_store_outfit` dla edycji pobrać wiersz przez `_locked_outfit(owner, pk)` wewnątrz transakcji (404/redirect, gdy zniknął), przepisać na niego tylko `name` i ustawić `garments`; `except` zawęzić do konfliktu nazwy.
  - Strength: Ten sam wzorzec co `_store_outfit_photo` i `_delete_outfit` — każda zapisywana krotka jest świeżo zablokowana; usuwa wszystkie trzy warianty naraz.
  - Tradeoff: Edycja przestaje korzystać wprost z `ModelForm.save()`/`save_m2m()`; `_store_outfit` rozgałęzia się na compose i edit.
  - Confidence: HIGH — wzorzec już działa w tym pliku, a scenariusz jest odtworzony.
  - Blind spot: Test regresji musi wstrzyknąć delete między `is_valid()` a `_store_outfit()`; blokady wierszy nie są realne na SQLite.
- **Fix B**: Zapisywać edycję przez `outfit.save(update_fields=['name'])` (Django zgłasza błąd, gdy UPDATE nie trafi w wiersz) i obsłużyć ten błąd jako redirect; zawęzić `except`.
  - Strength: Minimalna zmiana; nie nadpisuje już `photo_id`, więc wariant (3) znika.
  - Tradeoff: `Outfit.save()` nadal woła `full_clean()`, który waliduje nieaktualne `photo_id` — wariant (2) wymaga osobnej obsługi; brak blokady względem równoległego delete.
  - Confidence: MED — zależy od interakcji `update_fields` z `full_clean()` w `Outfit.save()`.
  - Blind spot: Nie sprawdzono, jak auto-nazwa `outfit-N` w `clean()` zachowuje się przy `update_fields`.
- **Decision**: FIXED (Fix A) — nowe `_update_outfit(owner, pk, form)` w `outfits/views.py`: zablokowany re-fetch przez `_locked_outfit`, przepisuje tylko `name` i `garments`; `_store_outfit` wrócił do wersji z `master` (tylko compose). Testy regresji `test_an_edit_does_not_bring_back_an_outfit_deleted_meanwhile` i `test_an_edit_keeps_a_photo_replaced_meanwhile` — czerwone przed poprawką (302/200), zielone po; `outfits/tests` + `tests/` 290 passed.

### F2 — Manualne kontrole faz 2 i 3 odhaczone bez zapisanych dowodów

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Success Criteria
- **Location**: context/changes/garment-lifecycle/plan.md:833-836, 851-854
- **Detail**: Punkty 2.8–2.11 i 3.7–3.10 są `[x]` z SHA commitów, ale ani `change.md`, ani treści commitów `42fb263`/`f995583` nie opisują ich wykonania (dla faz 0, 1 i 4 `change.md` ma daty, środowisko i wynik — np. „Manual 4.9–4.12 run in headless Chromium at 360 px on :8004 and confirmed by the developer"). Lesson „Run manual checks yourself" wymaga raportu z dowodami. Możliwe, że kontrole wykonano, ale nie ma śladu.
- **Fix**: Uruchomić 2.8–2.11 i 3.7–3.10 w headless Chromium na :8004 (albo potwierdzić z developerem, że się odbyły) i dopisać datowaną notatkę z wynikami do `change.md`.
- **Decision**: SKIPPED

### F3 — Edycja ubrania bez nowego zdjęcia daje 500 przy równoległym usunięciu lub wymianie zdjęcia

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: garments/views.py:46
- **Detail**: Gałąź bez zdjęcia woła `form.save()` bez blokady, zapisując także `photo_id` wczytane wcześniej. Jeśli ubranie usunięto lub wymieniono mu zdjęcie w innej karcie, `Garment.save()` → `full_clean()` odrzuca usunięty `PrivateImage` nieprzechwyconym `ValidationError` (500). Ubranie nie wraca (w odróżnieniu od F1), więc to tylko zły komunikat. Gałąź ze zdjęciem (`_replace_garment_photo`) blokuje wiersz poprawnie.
- **Fix**: Przepuścić też zapis bez zdjęcia przez `_locked_garment(owner, pk)` w transakcji i przepisać na świeży wiersz tylko `type`, `type_other`, `description` (404/redirect, gdy zniknął).
- **Decision**: FIXED — nowe `_update_garment(owner, form)` w `garments/views.py`: zablokowany re-fetch przez `_locked_garment`, przepisuje tylko `Meta.fields`. Przy okazji wyszło, że usunięcie przez ORM/admina (zdjęcie zostaje) wskrzeszało ubranie jak w F1 — to też zamknięte. Testy regresji `test_an_edit_of_a_garment_deleted_meanwhile_is_404_and_does_not_bring_it_back` i `test_an_edit_keeps_a_photo_replaced_meanwhile` — czerwone przed, zielone po; `garments/tests` + `tests/` 164 passed.

### F4 — Replace/dismiss blokują slot bez outfitu (kolejność blokad inna niż outfit delete)

- **Severity**: 💡 OBSERVATION
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: outfits/views.py:242, outfits/views.py:269, outfits/views.py:284
- **Detail**: `_locked_slot` blokuje tylko wiersz `MissingGarment`; `_delete_outfit` blokuje najpierw outfit, a jego kaskada potrzebuje slotów. Replace dodatkowo wstawia wiersz linku, którego FK wymaga key-share lock na outfit. Na PostgreSQL równoległy replace i delete tego samego outfitu mogą się zakleszczyć — jedna transakcja kończy się 500 (wniosek z analizy, nie da się odtworzyć na SQLite). Poza tym `outfit.garments.exists()` w dismiss odpowiada z prefetchu sprzed blokady; reguła „brak outfitu bez ubrań, który wygląda na kompletny" i tak się trzyma, bo usunięcie ubrania zawsze dopisuje slot.
- **Fix**: W obu widokach najpierw `_locked_outfit(request.user, pk)`, potem `_locked_slot`, a sprawdzenie ubrań zrobić świeżym zapytaniem pod blokadą.
  - Strength: Jedna kolejność blokad (outfit → slot) na wszystkich ścieżkach zapisu outfitu; zgodne z komentarzem przy `_locked_outfit`.
  - Tradeoff: Jedno zapytanie więcej na akcję; replace/dismiss różnych slotów tego samego outfitu wykonują się po kolei.
  - Confidence: MED — rozumowanie o blokadach PostgreSQL, bez reprodukcji.
  - Blind spot: CI działa na SQLite, więc test tego nie złapie; weryfikacja tylko na środowisku PR z Postgresem.
- **Decision**: SKIPPED

### F5 — Receiver `pre_delete` przy usuwaniu konta wykonuje zbędne zapisy i opiera się na kruchej kolejności

- **Severity**: 💡 OBSERVATION
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Architecture
- **Location**: outfits/signals.py:76
- **Detail**: Przy usuwaniu konta receiver dla każdego ubrania robi zapytanie o outfity i `bulk_create` tombstone'ów, które ta sama kaskada chwilę później kasuje. Działa to tylko dlatego, że `Collector.delete()` wysyła wszystkie `pre_delete` przed fast delete — plan (Key Discoveries) i docstring modelu to opisują, a test konta z mutacją (change.md) pilnuje regresji. Koszt rośnie liniowo z liczbą ubrań w koncie, a przyszły receiver na `MissingGarment` złamie delete na PostgreSQL.
- **Fix**: W receiverze wrócić wcześnie, gdy `kwargs['origin']` nie jest instancją `Garment` ani querysetem `Garment` (Django przekazuje `origin` do sygnałów delete).
  - Strength: Usuwa zbędne zapisy i zależność od kolejności kolektora; ścieżki UI, admina i ORM nadal zapisują tombstone'y.
  - Tradeoff: Reguła przestaje być „jakkolwiek ubranie zostanie usunięte" — przyszła kaskada z innego modelu na `Garment` pominie zapis; to zmiana intencji planu.
  - Confidence: MED — `origin` jest publicznym argumentem sygnału, ale trzeba potwierdzić jego wartość dla querysetu z admina.
  - Blind spot: Pozostawienie bez zmian jest akceptowalne — kruchość jest już przypięta testem i docstringiem.
- **Decision**: SKIPPED

### F6 — Podwójne tapnięcie na stronach potwierdzenia usunięcia kończy się 404

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: templates/garments/delete.html:31, templates/outfits/delete.html:24
- **Detail**: Drugi POST nie przechodzi `_owned_garment`/`_owned_outfit`, więc użytkownik na telefonie ląduje na 404 zamiast na liście. Formularze uploadu mają `data-submit-once`, a `outfit_photo_remove` i `outfit_missing_replace` celowo traktują powtórzenie jako „nie błąd".
- **Fix**: Dodać `data-submit-once` do obu formularzy usuwania (i załadować `js/photo-shrink.js` lub wydzielony skrypt, jeśli strona go nie ma).
- **Decision**: FIXED — `data-submit-once` + `js/photo-shrink.js` w `templates/garments/delete.html` i `templates/outfits/delete.html`; testy `test_delete_confirmation_is_sent_only_once` w `garments/tests/test_views.py` i `outfits/tests/test_views.py`. Dwa istniejące testy outfitu zawężone (regex formularza przyjmuje atrybuty; sprawdzenie „photo” ograniczone do `<main>…</main>`, bo nazwa skryptu trafia po `</main>`). `garments/tests` + `outfits/tests` + `tests/` 345 passed.

### F7 — Asercja `'Replace' in page` przechodzi zawsze

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Success Criteria
- **Location**: tests/garment_deletion_keeps_outfits/test_incomplete_outfit_offers_repair_and_delete.py:104
- **Detail**: Słowo „Replace" jest w zdaniu wstępu sekcji („Replace it, keep…") i w przycisku „Replace photo", więc asercja jest pusta. Punkt planu i tak pokrywają `'Keep without it' not in page` oraz sprawdzenie, że wysłany dismiss nic nie zmienia — ale test obiecuje więcej, niż sprawdza.
- **Fix**: Asertować link `href` do `outfits:missing_replace` dla slotu oraz link do `outfits:delete`, jak w `test_the_outfit_page_offers_replace_keep_and_delete`.
- **Decision**: FIXED — `'Replace' in page` zastąpione asercjami na `href` do `outfits:missing_replace` dla obu slotów, brak `outfits:missing_dismiss` i `href` do `outfits:delete`; `tests/garment_deletion_keeps_outfits` 8 passed.

### F8 — Drobne, nieudokumentowane odstępstwa od planu

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: garments/views.py:64, garments/tests/test_views.py:204, outfits/tests/test_views.py:1189, static/css/app.css:249
- **Detail**: Intencja zachowana, ale `change.md` tego nie odnotowuje: (a) liczba pojedyncza „1 outfit is now incomplete." obok planowanego „N outfits…"; (b) link kafelka sprawdza nowy test zamiast rozszerzenia `test_list_query_count_does_not_grow_with_garments`, a zero vs trzy sloty — nowy `test_detail_query_count_is_the_same_with_and_without_missing_slots` zamiast rozszerzenia `:632`; (c) pin grida z `?incomplete=1` ma bazę „jeden niekompletny outfit", bo filtr bez trafień nie renderuje kafelka (komentarz w teście); (d) `.notice` ma własny wygląd (bursztynowa lewa krawędź), bo `.messages` nie ma stylu, do którego można by nawiązać.
- **Fix**: Dopisać jedną datowaną notatkę z punktami (a)–(d) do `change.md`.
- **Decision**: SKIPPED

### F9 — Układ testów ryzyka odbiega od tests/CLAUDE.md

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: tests/garment_deletion_keeps_outfits/conftest.py:15, tests/garment_deletion_keeps_outfits/test_incomplete_outfit_offers_repair_and_delete.py:49
- **Detail**: (a) `conftest.py` importuje fixture `snapshot_of` z sąsiedniego folderu `foreign_id_writes/conftest.py` z `noqa` — fixture współdzielony między ryzykami powinien żyć w `tests/conftest.py`; (b) `test_incomplete_outfit_offers_repair_and_delete.py` ma cztery testy (grid, strona outfitu, naprawa, outfit bez ubrań) — reguła „jeden plik = jeden scenariusz" jest tu naciągnięta, choć plan sam nazwał taki plik; (c) usunięcie konta i queryset delete są sprawdzane zarówno w `outfits/tests/test_missing_garment_model.py`, jak i w `test_garment_deleted_outside_the_page_still_marks_outfits.py` — duplikat wynika z planu (Phase 1 i Phase 4).
- **Fix**: Przenieść `snapshot_of` (i `assert_no_cross_owner_links`) do `tests/conftest.py`; pozostałe punkty zostawić jako świadomą decyzję planu.
- **Decision**: FIXED (punkt a) — `tests/foreign_id_writes/conftest.py` przeniesiony (`git mv`) do `tests/conftest.py`; import z `noqa` usunięty z `tests/garment_deletion_keeps_outfits/conftest.py`; wzmianka w `tests/CLAUDE.md` zaktualizowana. Punkty (b) i (c) zostają jako decyzja planu. `tests/` 111 passed.

### F10 — Drobne niespójności w nowych widokach

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: garments/views.py:43, outfits/views.py:155, outfits/views.py:251
- **Detail**: (a) Po nieudanej walidacji `garment_edit` renderuje `edit.html` z instancją, na którą `ModelForm` już naniósł wysłane wartości, więc alt aktualnego zdjęcia pokazuje wpisany typ/opis zamiast zapisanego; (b) `outfit_edit` i `outfit_missing_replace` wiążą formularz przez `request.POST or None` (pusty POST tylko renderuje stronę), a `garment_edit` i compose sprawdzają `request.method`; (c) POST `outfit_delete` wykonuje trzy nieużywane prefetche z `_owned_outfit`, a POST `ReplaceMissingGarmentForm` sortuje wszystkich kandydatów przed walidacją — koszt pomijalny.
- **Fix**: W `garment_edit` przekazywać do szablonu świeżo wczytany (lub przed-walidacyjny) obiekt dla zdjęcia i alt; ujednolicić wiązanie formularzy na `request.method == 'POST'`.
- **Decision**: FIXED (punkty a, b) — (a) `garment_edit` wiąże formularz z `copy.copy(garment)`, więc strona po odrzuconej edycji opisuje zapisane ubranie; test `test_a_refused_edit_still_describes_the_saved_garment` (czerwony przed: `alt=": typed"`). (b) `outfit_edit` i `outfit_missing_replace` wiążą formularz przez `request.method == 'POST'`, jak compose i `garment_edit`. Punkt (c) zostawiony. `garments/tests` + `outfits/tests` + `tests/` 346 passed.

## Triage Summary (2026-09-14)

| Decision | Findings |
|----------|----------|
| FIXED | F1 (Fix A), F3, F6, F7, F9 (a), F10 (a, b) |
| SKIPPED | F2, F4, F5, F8 |

Po triage: pełny `uv run pytest`, `makemigrations --check` i `ruff` — wyniki w notatce w `change.md`.
