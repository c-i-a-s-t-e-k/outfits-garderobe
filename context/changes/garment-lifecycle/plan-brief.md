# Garment Lifecycle — Plan Brief

> Full plan: `context/changes/garment-lifecycle/plan.md`
> Research: `context/changes/garment-lifecycle/research.md`

## What & Why

Użytkownik może edytować ubranie (także podmienić zdjęcie) i je usunąć. Outfity, które używały usuniętego ubrania, zostają z pozostałymi ubraniami i zapamiętują, czego im brakuje. W siatce wyróżniają się jako niekompletne i dają natychmiastowy wybór: uzupełnij zamiennikiem, zostaw bez tej rzeczy albo usuń outfit. To slice **S-06** (Jira OG-7, FR-004, US-01). Żeby naprawa była możliwa, slice buduje też pełną edycję i usuwanie outfitu (zakres FR-006).

## Starting Point

Nic dziś nie edytuje ani nie usuwa ubrania. Usunięcie przez ORM kasuje wiersze powiązań bez śladu, więc niekompletności nie da się wyliczyć po fakcie. Outfit ma tylko tworzenie (`OutfitForm`, min. 2 ubrania), a usuwania nie ma w ogóle. S-04 (w worktree, Phase 1 w `4fba006`) dostarcza `discard_private_image()`, `NormalizedPhotoMixin`, `Outfit.photo` i kafelki ze zdjęciem.

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
| Granica S-06/S-07 | Pełna edycja (nazwa + skład) i usuwanie outfitu w S-06; S-07 zostaje otwarty w roadmapie | Wybór developera; S-07 zdecyduje o reszcie przy własnym planowaniu. | Plan |
| Minimum ubrań | Edycja ≥ 1, kompozycja ≥ 2; *Keep without it* ukryte przy 0 ubrań | Da się przemianować outfit z 1 ubraniem; nie powstaje „kompletny” pusty outfit. | Plan |
| Usuwanie ubrania | Strona edycji → potwierdzenie z listą outfitów (GET + POST) | FR-004 widoczne przed decyzją; precedens potwierdzenia z S-04. | Plan |
| Usuwanie outfitu | Potwierdzenie z listą tagów (bez checkboxa) + `discard_private_image` zdjęcia | FR-006 i luka zapisana w planie S-04. | Research / Plan |
| Siatka | Plakietka w `.outfit-preview` + baner „N outfits need attention” → `?incomplete=1` (łączy się z `?tag=`) | Widoczne od wejścia, na kafelku ze zdjęciem i z kolażem. | Plan |
| Kolejność z S-04 | Start po merge S-04; worktree `../.worktrees/garment-lifecycle`, branch `feat/garment-lifecycle`, migracja `0004` | Zero duplikacji prymitywów i konfliktów. | Plan |

## Scope

**In scope:**
- `MissingGarment`, receiver, migracja `0004`, inline w adminie
- edycja ubrania (opcjonalna podmiana zdjęcia), usuwanie z potwierdzeniem i sprzątaniem pliku
- edycja outfitu (`OutfitEditForm`, wspólny `_garment_picker.html`), usuwanie z ostrzeżeniem o tagach
- sekcja braków, picker zamiennika, *Keep without it*, plakietka, baner, `?incomplete=1`
- 6 nowych tras w `tests/owner_scoped_routes.py`, tombstone w `snapshot_of`/`OWNED_MODELS`/`_row_counts`
- folder ryzyka `tests/garment_deletion_keeps_outfits/`
- PR, checki na PR env, close-out S-06 i OG-7

**Out of scope:**
- soft delete, kosz, cofnięcie
- tombstone przy odznaczeniu w edycji; zamykanie braków przez edycję
- tagi w formularzu edycji; checkbox przy usuwaniu outfitu
- zmiany S-07 / OG-8 w roadmapie i Jira
- kasowanie plików przy usuwaniu z admina/ORM i przy usuwaniu konta
- backfill, plakietki na liście ubrań, sortowanie niekompletnych, tłumaczenie UI

## Architecture / Approach

`Garment.delete()` → `pre_delete` → `MissingGarment.bulk_create` dla każdego outfitu → Django usuwa powiązania. Widok usuwania ubrania robi to w transakcji: zapamiętuje zdjęcie, woła `garment.delete()`, potem `discard_private_image(photo)` (kolejność wymusza `RESTRICT`). Siatka prefetchuje `missing_garments` i liczy baner jednym `count`. Naprawa jest na stronie outfitu: kafelek to jeden `<a>`, więc tylko sygnalizuje. *Replace* i *Keep without it* blokują tombstone (`select_for_update`); nieaktualny brak kończy się przekierowaniem bez błędu.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Missing-garment record and deletion rule | Model, receiver, migracja, kontrakty modeli | Insert w `pre_delete` przy kaskadzie konta — pinowane testem z `check_constraints()` |
| 2. Garment edit and delete | Edycja z podmianą zdjęcia, potwierdzenie z listą outfitów | Kolejność podmiany/usuwania pliku; `clean_photo` z pustym uploadem |
| 3. Outfit edit and delete | `OutfitEditForm`, wspólny picker, usuwanie z ostrzeżeniem | `_store_outfit` nie może wyczyścić tagów w edycji |
| 4. Incomplete outfits in the grid and on the outfit page | Plakietka, baner, filtr, sekcja braków, picker, dismiss, Risk #5 | Stała liczba zapytań; plakietka czytelna na zdjęciu przy 360 px |
| 5. Pull request and PR-environment verification | PR, checki na PR env, close-out S-06 + OG-7 | Pusta baza PR env; ewentualna kolizja migracji `0004` |

**Prerequisites:** S-04 (`feat/outfit-photo`) zmergowany do `origin/master`; utworzony worktree `feat/garment-lifecycle`.
**Estimated effort:** ~3–4 sesje w 5 fazach.

## Open Risks & Assumptions

- Plan opiera się na kontraktach S-04 z jego planu. Jeśli S-04 zmerguje się z odchyleniami (nazwy, `_seed_wardrobe`, `_render_detail`), trzeba je zweryfikować na starcie Phase 1.
- Opis usuniętego ubrania zostaje w tombstonie, dopóki brak nie zostanie zamknięty. To dane właściciela, objęte kontraktem prywatności.
- Usunięcie ubrania z admina/ORM i usunięcie konta zostawia plik zdjęcia na wolumenie (znana luka, jak w S-04).
- S-07 zostaje otwarty, choć edycja i usuwanie outfitu są już w kodzie. `/10x-plan outfit-lifecycle` musi to uwzględnić.

## Success Criteria (Summary)

- Na PR env (360 px): usunięcie ubrania wspólnego dla dwóch outfitów → oba zostają z pozostałymi ubraniami, z plakietką i banerem → naprawa przez *Replace* i *Keep without it* zdejmuje oznaczenie.
- Edycja ubrania (ze zdjęciem) i outfitu działa; usunięcie otagowanego outfitu ostrzega i kasuje plik zdjęcia.
- Drugie konto dostaje 404 na wszystkie nowe strony i akcje; `tests/garment_deletion_keeps_outfits/` i kontrakty prywatności są zielone.
