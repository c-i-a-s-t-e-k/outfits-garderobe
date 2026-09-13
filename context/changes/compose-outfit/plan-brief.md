# Compose Outfit and Wardrobe Grid — Plan Brief

> Full plan: `context/changes/compose-outfit/plan.md`

## Co i dlaczego

Zalogowany użytkownik zaznacza zdjęcia swoich ubrań, opcjonalnie nazywa zestaw i zapisuje go jako outfit, a potem widzi go jako kafelek w siatce `/wardrobe/`, która wraca do roli strony startowej. To slice S-03 (Jira OG-4, FR-005, FR-008, US-01) — gwiazda przewodnia roadmapy: dopóki nie da się złożyć stroju z własnych ubrań i go odnaleźć, produkt jest tylko katalogiem ubrań.

## Punkt wyjścia

Istnieje `garments.Garment` z właścicielem i `photo_url` bez dodatkowego zapytania, prywatna brama zdjęć oraz zarezerwowana, zastępcza strona `/wardrobe/` (nazwa trasy `wardrobe`). Logowanie i `/` tymczasowo prowadzą na listę ubrań — komentarze z S-02 zapowiadają, że S-03 to odwróci.

## Stan docelowy

Po zalogowaniu użytkownik trafia na *Wardrobe*. *Compose outfit* pokazuje siatkę jego ubrań z checkboxami (2 w rzędzie przy 360 px, licznik „N selected" w przyklejonym pasku, bez JavaScriptu). Zapisany outfit pojawia się pierwszy jako kwadratowy kafelek z maks. 4 zdjęciami ubrań i plakietką „+N", a tapnięcie otwiera stronę tylko do odczytu ze wszystkimi ubraniami. Drugie konto nie widzi niczego z tego, a POST z cudzym id ubrania niczego nie zapisuje.

## Kluczowe decyzje

| Decyzja | Wybór | Dlaczego | Źródło |
| --- | --- | --- | --- |
| Minimalny rozmiar outfitu | co najmniej 2 ubrania (w formularzu) | zgodnie z US-01; outfit to zestawienie | Plan |
| Duplikaty zestawów | dozwolone bez ostrzeżenia | S-04/S-05 i tak mogą je różnić zdjęciem i tagami | Plan |
| Nazwa | zawsze jest; pusta → najniższy wolny `outfit-N` | decyzja developera | Plan |
| Unikalność nazw | unikalne per użytkownik bez rozróżniania wielkości liter; numery po usunięciu wracają | „najniższy wolny" dosłownie; nazwa to klucz do przypomnienia | Plan |
| Podgląd w kafelku | 2×2 z pierwszych 4 wg typu (okrycie → sukienka → góra → dół → buty → dodatki) + „+N" | stałe 4 żądania na kafelek, najbardziej rozpoznawalne ubrania pierwsze | Plan |
| Wybór ubrań | jedna strona, siatka zdjęć z checkboxami, CSS `:has(:checked)` + liczniki CSS | działa bez JS, reużywa `.garment-grid`, duże pola dotyku | Plan |
| Strona startowa | `/wardrobe/` (nazwa `wardrobe`); nawigacja *Wardrobe*, *Garments* | kontrakt zarezerwowanej trasy, outfit ponad katalogiem | Plan |
| Tapnięcie kafelka | strona szczegółów tylko do odczytu `/wardrobe/<uuid>/` | jedyny sposób zobaczenia ubrań ponad 4; miejsce dla S-04/S-05/S-07 | Plan |
| Testy prywatności | S-03 ma własne testy dwóch kont; siatka enumerująca trasy zostaje w fazie 1 test-planu | brak blokującej zależności, ryzyka #1/#2 pokryte od pierwszego dnia | Plan |

## Zakres

**W zakresie:** model `Outfit` (M2M do `Garment`, reguły nazw, strażnik własności `m2m_changed`), strona `compose`, strona szczegółów, siatka garderoby z podglądem, przywrócenie strony startowej, testy dwóch kont, wdrożenie.

**Poza zakresem:** zdjęcie w stroju (S-04), tagi (S-05), edycja/usuwanie ubrań i flaga niekompletności (S-06), edycja/usuwanie/zmiana nazwy outfitu (S-07), ostrzeganie o duplikatach, grupowanie/wyszukiwanie w pickerze, paginacja, testy na prawdziwych telefonach (odłożone).

## Architektura / podejście

Nowa aplikacja `outfits`. Reguły, które mogą żyć w modelu, żyją w modelu: porządkowanie i domyślna nazwa w `clean()`, unikalność `(owner, Lower('name'))` i niepusta nazwa jako ograniczenia bazy, własność ubrań jako odbiornik `m2m_changed` `pre_add`. Minimum 2 ubrań i czytelny błąd zajętej nazwy są w `OutfitForm` — `ModelForm` pomija ograniczenia dotyczące pola `owner`, którego nie ma w formularzu. Trasa `wardrobe` przenosi się do `outfits.views` bez zmiany nazwy; `compose` i `detail` dochodzą pod `/wardrobe/` w przestrzeni `outfits`. Siatka to dwa zapytania (outfity + prefetch ubrań), kolejność podglądu liczona w Pythonie.

## Fazy w skrócie

| Faza | Co dostarcza | Główne ryzyko |
| --- | --- | --- |
| 1. `Outfit` model | model, ograniczenia, domyślne nazwy, strażnik M2M, admin, testy modelu | strażnik M2M nie obejmuje ścieżki `through.objects.bulk_create` |
| 2. Compose and detail pages | picker, zapis, strona szczegółów, testy dwóch kont i cudzego id | ograniczenie nazwy pomijane przez `ModelForm`; wyścig domyślnej nazwy |
| 3. Wardrobe grid and landing | siatka z kafelkami 2×2 + „+N", puste stany, powrót strony startowej | kolaż czytelny przy 360 px i spójny z przyszłym kafelkiem ze zdjęciem (S-04) |
| 4. Pull request and production | rebase na `origin/master`, PR do `master` przez `gh pr create`; po merge'u przez developera: wdrożenie, kontrola prywatności na dwóch kontach, 360 px w headless Chromium | PR zawierający niezmergowane commity `feat/user-accounts`; migracja z ograniczeniem wyrażeniowym na PostgreSQL |

**Wymagania wstępne:** S-02 done (spełnione).
**Praca równoległa:** worktree `/home/ciastek/Projects/outfits-garderobe-compose-outfit`, gałąź `feat/compose-outfit` (z `feat/user-accounts` @ `c8c7079`); równolegle trwa inna praca w głównym checkoucie. Własna baza SQLite i media w worktree (trzeba `migrate` i konta testowe), `runserver 8001`, bez gołego `git stash`. Szczegóły i lista plików narażonych na konflikty: sekcja *Parallel Work & Delivery* w `plan.md`.
**Dostarczenie:** żadnego bezpośredniego pusha na `master` — faza 4 kończy się PR-em, a merge (i tym samym deploy na Railway) należy do developera.
**Szacowany nakład:** ~3–4 sesje w 4 fazach.

## Otwarte ryzyka i założenia

- Minimum 2 ubrań obowiązuje tylko w formularzu; admin/ORM mogą utworzyć mniejszy outfit — S-06 i tak musi obsłużyć outfity, które się kurczą.
- Ponowne użycie numeru `outfit-N` po usunięciu (S-07) może mylić („outfit-2 to kiedyś był niebieski") — świadomie przyjęte.
- Faza 1 test-planu (`testing-cross-user-privacy`) nie ruszyła; może później przepisać testy S-03 na wspólny wzorzec.
- Weryfikacja na prawdziwych telefonach odłożona na produkcję; ekran 360 px sprawdzany w headless Chromium.
- `master` przewinięty (fast-forward) 2026-09-13 do commita z tym planem, więc zawiera już historię `feat/user-accounts`; PR S-03 powinien nieść tylko commity S-03 — faza 4 i tak to sprawdza i w razie obcych commitów pyta developera.
- Równoległa praca może zmieniać te same pliki (`roadmap.md`, `base.html`, `app.css`, `settings.py`, `urls.py`, testy smoke) — konflikty rozwiązywane przy rebase w fazie 4.

## Kryteria sukcesu (skrót)

- Użytkownik składa outfit z co najmniej 2 ubrań i widzi go pierwszy w siatce garderoby, z podglądem ze zdjęć ubrań.
- Jedno ubranie jest w wielu outfitach; pusta nazwa daje najniższy wolny `outfit-N`.
- Drugie konto nie widzi outfitów, stron szczegółów ani ubrań w pickerze pierwszego, a POST z cudzym id niczego nie zmienia.
