# Outfit Photo — Plan Brief

> Full plan: `context/changes/outfit-photo/plan.md`

## What & Why

Użytkownik dodaje do outfitu własne zdjęcie w tym stroju, a kafelek outfitu w siatce garderoby pokazuje od tej pory to zdjęcie zamiast kolażu z ubrań. To slice **S-04** (Jira OG-5, FR-007, FR-008, US-01). Dopiero on sprawia, że przegląd garderoby jest „przeglądem po zdjęciach outfitowych”, jak chce PRD, a nie siatką miniatur ubrań.

## Starting Point

`Outfit` nie ma zdjęcia, a kafelek to kwadratowy kolaż do 4 zdjęć ubrań. Brama `privatemedia` jest gotowa na drugą ścieżkę uploadu: `PrivateImage`, `stored_private_image()`, `normalize_photo()` i `photo-shrink.js`. S-02 używa ich przy ubraniach. Nigdzie w kodzie nie ma jeszcze kasowania plików z wolumenu. Kompozycja przekierowuje do garderoby.

## Desired End State

Po zapisaniu kompozycji użytkownik ląduje na stronie outfitu. Pod *Tags* jest sekcja *Photo* z uploadem. Po wgraniu zdjęcie jest widoczne w całości na stronie outfitu, a w garderobie jako pionowy kafelek 3:4, obok równie wysokich kafelków-kolaży. *Replace photo* podmienia zdjęcie. *Remove photo* prowadzi przez stronę potwierdzenia, a potem kafelek wraca do kolażu. Stary plik znika z wolumenu dopiero po commicie. Drugie konto dostaje 404 na wszystko.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) |
| --- | --- | --- |
| Liczba zdjęć | Jedno na outfit, z podmianą i usunięciem | Pokrywa FR-007 i pozwala poprawić nieudane zdjęcie bez czekania na S-07. |
| Miejsce uploadu | Strona outfitu; `outfit_compose` przekierowuje na stronę nowego outfitu | Kolejność z US-01 (złóż → zapisz → dodaj zdjęcie); zdjęcie powstaje po ubraniu się. |
| Układ strony outfitu | Sekcja *Photo* pod *Tags*, nad siatką ubrań | Wybór developera: tagi zostają tam, gdzie są dziś. |
| Kafelek | Wszystkie kafelki `.outfit-preview` pionowe 3:4; zdjęcie `cover`, kadr od góry | Sylwetka mieści się niemal cała, a siatka zostaje równa. |
| Stary plik | `discard_private_image()`: wiersz od razu, plik w `transaction.on_commit` | Nieudana podmiana nigdy nie gubi zdjęcia, a wolumen 5 GB nie zbiera sierot. |
| Usuwanie | Strona potwierdzenia `outfits:photo_remove` (GET + POST) | Jedyna nieodwracalna akcja dostaje prawdziwe potwierdzenie, zgodne z przyszłym S-07. |
| OG-9 | `data-submit-once` tylko w formularzu zdjęcia; podmiana po stronie serwera jest i tak idempotentna | Nowa ścieżka nie dokłada duplikatów; OG-9 dla pozostałych formularzy zostaje otwarte. |
| Relacja | `Outfit.photo` = `OneToOneField(PrivateImage, RESTRICT, null=True)` + reguła właściciela w `clean()` | Ten sam wzorzec co `Garment.photo`, własność sprawdzana w jednym miejscu. |
| Formularz | Wydzielony `NormalizedPhotoMixin` w `privatemedia/forms.py`, używany przez `GarmentForm` i `OutfitPhotoForm` | Te same reguły uploadu bez kopiowania kodu. |
| Dostarczenie | Worktree `../.worktrees/outfit-photo`, PR, checki manualne na Railway PR env przed mergem | Zgodnie z lekcją *Done means all checks pass on the PR deploy*. |

## Scope

**In scope:**
- pole `Outfit.photo`, migracja `0003`, admin
- upload, podmiana i usunięcie z potwierdzeniem
- przekierowanie po kompozycji na stronę outfitu
- blokada ponownego wysłania formularza zdjęcia
- kafelki 3:4 ze zdjęciem albo kolażem
- rejestracja tras w `tests/owner_scoped_routes.py` i testy
- PR z weryfikacją na PR env i close-out

**Out of scope:**
- wiele zdjęć, galeria, kosz lub historia
- pole zdjęcia w kompozycji
- OG-9 w innych formularzach
- kasowanie plików przy usuwaniu konta lub outfitu (luka zapisana dla S-07)
- edycja i kadrowanie zdjęcia, przycisk aparatu, tłumaczenie UI

## Architecture / Approach

`OutfitPhotoForm` (miksin z `normalize_photo`) → `outfit_photo_upload`. Widok najpierw rozwiązuje outfit właściciela (404 zanim cokolwiek zdekoduje), potem w jednej transakcji:
1. blokuje wiersz outfitu (`select_for_update`),
2. zapisuje nowe zdjęcie przez `stored_private_image`,
3. podpina je do outfitu,
4. wywołuje `discard_private_image(stare)`, które kasuje plik po commicie.

`outfit_photo_remove`: GET pokazuje potwierdzenie; POST najpierw odpina zdjęcie (bo `RESTRICT`), potem `discard_private_image`. W siatce `wardrobe.html` sprawdza `photo_id`: jest zdjęcie, to jeden `<img>` z `photo_url`; nie ma, to istniejący kolaż. Oba warianty są w tym samym pudełku 3:4 i nie dodają zapytań do bazy.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Outfit photo model and file lifecycle | Pole, reguła właściciela, `discard_private_image`, miksin, migracja | Testy kasowania plików przejdą „na pusto” bez `django_capture_on_commit_callbacks` |
| 2. Add, replace and remove on the outfit page | Upload, podmiana, strona potwierdzenia, redirect po kompozycji, submit-once, trasy w sieci prywatności | Kolejność operacji przy podmianie; cudzy upload nie może niczego zapisać ani zdekodować |
| 3. Portrait tiles in the wardrobe | Kafelek ze zdjęciem lub kolażem w 3:4 | Kolaże 2/3/4 i znacznik `+N` w pionowym kafelku |
| 4. Pull request and PR-environment verification | PR, checki na PR env, close-out i Jira OG-5 w tym samym PR | Pusta baza na PR env; ewentualna kolizja migracji `0003` z S-06 |

**Prerequisites:** S-03, S-05 i F-01 zmergowane (są na `origin/master` `787aa1f`); worktree `feat/outfit-photo` utworzony.
**Estimated effort:** ~2–3 sesje w 4 fazach.

## Open Risks & Assumptions

- Równoległy S-06 może dodać własną migrację `outfits.0003_*`. Wtedy migrację tego slice'a trzeba wygenerować od nowa po rebase.
- Usunięcie outfitu (ORM lub admin dziś, UI w S-07) zostawi plik zdjęcia. Plan S-07 musi wywołać `discard_private_image`.
- Kadr `center top` zakłada typowe zdjęcie całej sylwetki. Zdjęcie poziome zostanie mocno przycięte w kafelku, ale na stronie outfitu jest widoczne w całości.
- Baza produkcyjna przeniesiona do EU (developer, 2026-09-14), więc transakcje uploadu mieszczą się w budżecie 5 s. Koszt uploadu to głównie transfer i dekodowanie zdjęcia.

## Success Criteria (Summary)

- Na PR env (360 px): kompozycja → strona outfitu → upload prawdziwego zdjęcia z telefonu → zdjęcie jako kafelek; podmiana i usunięcie działają.
- Drugie konto dostaje 404 na stronę outfitu, stronę usuwania i URL zdjęcia pierwszego konta.
- Po podmianie i usunięciu stary plik nie leży na wolumenie, a nieudany upload nie zostawia ani wiersza, ani pliku.
