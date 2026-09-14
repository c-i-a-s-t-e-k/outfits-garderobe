# Garment Lifecycle — Plan Brief

> Full plan: `context/changes/garment-lifecycle/plan.md`
> Research: `context/changes/garment-lifecycle/research.md`

## What & Why

Użytkownik może edytować ubranie (także podmienić zdjęcie) i je usunąć. Outfity, które używały usuniętego ubrania, zostają z pozostałymi ubraniami i zapamiętują, czego im brakuje. W siatce wyróżniają się jako niekompletne i dają natychmiastowy wybór: uzupełnij zamiennikiem, zostaw bez tej rzeczy albo usuń outfit. To slice **S-06** (Jira OG-7, FR-004, US-01). Żeby naprawa była możliwa, slice buduje też pełną edycję i usuwanie outfitu (zakres FR-006).

## Starting Point

Nic dziś nie edytuje ani nie usuwa ubrania. Usunięcie przez ORM kasuje wiersze powiązań bez śladu, więc niekompletności nie da się wyliczyć po fakcie. Outfit ma tylko tworzenie (`OutfitForm`, min. 2 ubrania), a usuwania nie ma w ogóle. S-04 (w równoległym worktree: Phase 1 w `4fba006`, Phase 2 w toku, jeszcze niezmergowany) dostarcza `discard_private_image()`, `NormalizedPhotoMixin`, `Outfit.photo` i kafelki ze zdjęciem.

## Desired End State

Kafelek na liście ubrań prowadzi do strony edycji. *Delete garment* pokazuje potwierdzenie z nazwami outfitów, które staną się niekompletne, i kasuje plik zdjęcia po commicie. W garderobie dotknięte kafelki (kolaż i zdjęcie) mają plakietkę „Incomplete · N missing”. Nad siatką baner linkuje do `?incomplete=1`. Strona outfitu zaczyna się sekcją *Missing garments* („Shoes — brown loafers”), a przy każdym braku są *Replace* i *Keep without it*, do tego *Delete outfit*. Są też *Edit outfit* i *Delete outfit* z ostrzeżeniem o tagach. Drugie konto dostaje 404 wszędzie.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| Zapis niekompletności | Tombstone `MissingGarment` (typ, `type_other`, opis, `removed_at`) per outfit, bez własnego `owner` | Strona mówi, CZEGO brakuje, a picker podpowiada ten sam typ; właściciel wynika z outfitu. | Research (opcja B) / Plan |
| Gdzie reguła | Receiver `pre_delete` na `Garment` w `outfits/signals.py` (`bulk_create`) | Działa dla widoku, admina, `QuerySet.delete()` i kaskady konta. | Research / Plan |
| Kasowanie braku | Per brak: *Replace* zamyka jeden, *Keep without it* zamyka bez dodawania | Stan zawsze prawdziwy; outfit OK bez paska nie wisi wiecznie. | Plan |
| Zamiennik | Osobny picker per brak (`outfits:missing_replace`), ten sam typ na górze | Każda akcja ma jedno znaczenie; edycja outfitu nie zamyka braków. | Plan |
| Odznaczenie w edycji | Nie tworzy tombstone'a | Świadoma decyzja użytkownika to nie „brak”. | Plan |
| Granica S-06/S-07 | Pełna edycja (nazwa + skład) i usuwanie outfitu w S-06; close-out zamyka też S-07 i OG-8 | Wybór developera; badanie `outfit-lifecycle` (2026-09-14) nie znalazło zakresu na osobny slice. | Plan / Research |
| Minimum ubrań | Edycja ≥ 1, kompozycja ≥ 2; *Keep without it* ukryte przy 0 ubrań | Da się przemianować outfit z 1 ubraniem; nie powstaje „kompletny” pusty outfit. | Plan |
| Pusta nazwa w edycji | `OutfitEditForm.clean_name()` zwraca bieżącą nazwę; etykieta „Name”, bez help textu o `outfit-N` | Bez tego `_store_outfit` uznałby puste pole za auto-nazwę i przemianował outfit na najniższy wolny `outfit-N`. | Plan review F2 |
| Edycja a braki | Dodanie ubrania w *Edit outfit* nie zamyka braku; `edit.html` pokazuje notkę `.notice` z linkiem do *Replace* / *Keep without it* | Reguła zostaje jednoznaczna, a użytkownik wie, czemu plakietka nie znika. | Plan review F3 |
| Usuwanie ubrania | Strona edycji → potwierdzenie z listą outfitów (GET + POST) | FR-004 widoczne przed decyzją; precedens potwierdzenia z S-04. | Plan |
| Usuwanie outfitu | Potwierdzenie z listą tagów (bez checkboxa) + `discard_private_image` zdjęcia | FR-006 i luka zapisana w planie S-04. | Research / Plan |
| Siatka | Plakietka w `.outfit-preview` + baner „N outfits need attention” → `?incomplete=1` (łączy się z `?tag=`) | Widoczne od wejścia, na kafelku ze zdjęciem i z kolażem. | Plan |
| Kolejność z S-04 | Phase 0: czeka na merge S-04, potem `git merge origin/master` do `feat/garment-lifecycle` (branch z `787aa1f`) i weryfikacja kontraktów S-04; migracja `0004` | Zero duplikacji prymitywów i konfliktów; odchylenia S-04 wychodzą przed pierwszą linią kodu. | Plan |
| Synchronizacja z master | Merge (Phase 0 i 5), nigdy rebase | Nie przepisuje wypchniętej historii, bez force-pusha. | Plan |

## Scope

**In scope:**
- `MissingGarment`, receiver, migracja `0004`, inline w adminie
- edycja ubrania (opcjonalna podmiana zdjęcia), usuwanie z potwierdzeniem i sprzątaniem pliku
- edycja outfitu (`OutfitEditForm`, wspólny `_garment_picker.html`), usuwanie z ostrzeżeniem o tagach
- sekcja braków, picker zamiennika, *Keep without it*, plakietka, baner, `?incomplete=1`
- 6 nowych tras w `tests/owner_scoped_routes.py`, tombstone w `snapshot_of`/`OWNED_MODELS`/`_row_counts`
- folder ryzyka `tests/garment_deletion_keeps_outfits/`
- PR, checki na PR env, close-out S-06 i S-07 oraz OG-7 i OG-8

**Out of scope:**
- soft delete, kosz, cofnięcie
- tombstone przy odznaczeniu w edycji; zamykanie braków przez edycję
- tagi w formularzu edycji; checkbox przy usuwaniu outfitu
- osobny plan S-07 (`/10x-plan outfit-lifecycle` nie jest uruchamiany)
- kasowanie plików przy usuwaniu z admina/ORM i przy usuwaniu konta
- backfill, plakietki na liście ubrań, sortowanie niekompletnych, tłumaczenie UI

## Architecture / Approach

`Garment.delete()` → `pre_delete` → `MissingGarment.bulk_create` dla każdego outfitu → Django usuwa powiązania. Widok usuwania ubrania robi to w transakcji: zapamiętuje zdjęcie, woła `garment.delete()`, potem `discard_private_image(photo)` (kolejność wymusza `RESTRICT`). Siatka prefetchuje `missing_garments` i liczy baner jednym `count`. Naprawa jest na stronie outfitu: kafelek to jeden `<a>`, więc tylko sygnalizuje. *Replace* i *Keep without it* blokują tombstone (`select_for_update`); nieaktualny brak kończy się przekierowaniem bez błędu.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 0. Merge master after S-04 | Commit zaległych edycji docs, branch z S-04 (merge `origin/master`), zielony suite, potwierdzone kontrakty S-04 | S-04 jeszcze niezmergowany (stop) lub zmergowany z odchyleniami |
| 1. Missing-garment record and deletion rule | Model, receiver, migracja, kontrakty modeli | Insert w `pre_delete` przy kaskadzie konta — pinowane testem z `check_constraints()` |
| 2. Garment edit and delete | Edycja z podmianą zdjęcia, potwierdzenie z listą outfitów | Kolejność podmiany/usuwania pliku; `clean_photo` z pustym uploadem |
| 3. Outfit edit and delete | `OutfitEditForm`, wspólny picker, usuwanie z ostrzeżeniem | `_store_outfit` nie może wyczyścić tagów w edycji |
| 4. Incomplete outfits in the grid and on the outfit page | Plakietka, baner, filtr, sekcja braków, picker, dismiss, Risk #5 | Stała liczba zapytań; plakietka czytelna na zdjęciu przy 360 px |
| 5. Pull request and PR-environment verification | PR, checki na PR env (360 px), close-out S-06 + S-07 (prerequisites i PRD refs S-06, wpis *Parked* o plikach-sierotach, stamp `outfit-lifecycle/change.md`), OG-7 + OG-8 | Pusta baza PR env; ewentualna kolizja migracji `0004` |

**Prerequisites:** S-04 (`feat/outfit-photo`) zmergowany do `origin/master` (sprawdza Phase 0); worktree `feat/garment-lifecycle` już istnieje.
**Estimated effort:** ~3–4 sesje w 6 fazach (Phase 0 bez kodu).

## Open Risks & Assumptions

- Plan opiera się na kontraktach S-04 z jego planu i niezmergowanego worktree. Phase 0 weryfikuje je po merge'u (m.in. `_seed_wardrobe`, `_render_detail`, markup kafelka z fazy 3 S-04, jeszcze nienapisany). Odchylenia trafiają do `change.md` i poprawiają kontrakty faz 1–4 przed startem.
- Numery linii w planie są z `787aa1f`; po merge'u S-04 (≈ +314 linii w `outfits/tests/test_views.py`) testy liczników zapytań trzeba szukać po nazwach.
- Opis usuniętego ubrania zostaje w tombstonie, dopóki brak nie zostanie zamknięty. To dane właściciela, objęte kontraktem prywatności.
- Usunięcie ubrania z admina/ORM i usunięcie konta zostawia plik zdjęcia na wolumenie (znana luka, jak w S-04).
- S-07 nie dostaje osobnego planu: close-out tego PR ustawia go na `done` (notka o PR) i przesuwa OG-8; po merge'u `/10x-archive outfit-lifecycle`. Przed przeklikaniem ostrzeżenia chroni tylko strona potwierdzenia — świadomie bez checkboxa i podglądu outfitu (decyzja 2026-09-14, zapisana w plan.md).
- Plan review 2026-09-14 (`reviews/plan-review.md`): 7 ustaleń, wszystkie wprowadzone do planu; werdykt po poprawkach SOUND.

## Success Criteria (Summary)

- Na PR env (360 px): usunięcie ubrania wspólnego dla dwóch outfitów → oba zostają z pozostałymi ubraniami, z plakietką i banerem → naprawa przez *Replace* i *Keep without it* zdejmuje oznaczenie.
- Edycja ubrania (ze zdjęciem) i outfitu działa; usunięcie otagowanego outfitu ostrzega i kasuje plik zdjęcia.
- Drugie konto dostaje 404 na wszystkie nowe strony i akcje; `tests/garment_deletion_keeps_outfits/` i kontrakty prywatności są zielone.
