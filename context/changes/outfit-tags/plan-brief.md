# Outfit Tags and Wardrobe Filtering — Plan Brief

> Full plan: `context/changes/outfit-tags/plan.md`

## Co i dlaczego

Użytkownik taguje outfity (przy komponowaniu albo później na stronie outfitu), usuwa tagi, widzi je pod kafelkami i filtruje siatkę garderoby po jednym lub kilku tagach naraz. Pokazują się tylko outfity, które mają wszystkie wybrane tagi. To slice roadmapy **S-05** (Jira OG-6: FR-009, FR-010, US-02) i ostatni brakujący krok głównego kryterium sukcesu PRD. Ryzyko z roadmapy i z test-planu (#6): swobodnie wpisywane tagi rozjeżdżają się na warianty tego samego słowa i psują filtrowanie.

## Punkt wyjścia

Tagów nie ma nigdzie. `Outfit` ma nazwę i ubrania, a reguły siedzą w modelu: ograniczenia w bazie, `full_clean()` w `save()`, strażnik `m2m_changed` na ubraniach innego użytkownika. Strona outfitu jest tylko do odczytu (edycja przyjdzie w S-07). Siatka to jeden link na kafelek, bez JavaScriptu. Równolegle w osobnym worktree powstaje sieć testów prywatności (`tests/owner_scoped_routes.py`), która wymaga rejestracji każdej nowej strzeżonej trasy.

## Stan docelowy

Na *Compose outfit* jest opcjonalne pole *Tags* („Letnie, smart casual”). Strona outfitu pokazuje chipy tagów z przyciskiem usuwania i pole *Add tags* z podpowiedziami. W garderobie każdy kafelek ma w jednej linii swoje tagi, a nad siatką jest pasek tagów. Kliknięcie zawęża widok, drugie kliknięcie zawęża dalej (AND), kliknięcie zaznaczonego chipa go zdejmuje, a *All* czyści filtr. Pasek oferuje wyłącznie tagi, które zostawiają na ekranie co najmniej jeden outfit. Drugie konto nie widzi niczego z tego i nie może tagować cudzych outfitów.

## Kluczowe decyzje

| Decyzja | Wybór | Dlaczego | Źródło |
| --- | --- | --- | --- |
| Tożsamość tagu | Wielkość liter i białe znaki bez znaczenia; `smart casual` ≠ `smart-casual` | Łapie najczęstsze warianty bez zgadywania | Plan |
| Pisownia | Wygrywa pierwsza wpisana („Letnie” zostaje „Letnie”) | Użytkownik zachowuje swoją pisownię, tak jak przy nazwach outfitów | Plan |
| Filtr | Kilka tagów naraz, AND | Precyzyjne zawężanie dużej garderoby | Plan |
| Pasek przy aktywnym filtrze | Tylko tagi, które dalej zawężają | Brak ślepych zaułków z pustą siatką; krótszy pasek na 360 px | Plan |
| Osierocone tagi | Znikają (usuwane, gdy żaden outfit ich nie ma) | Pasek nigdy nie oferuje pustego filtra; bez ekranu zarządzania tagami | Plan |
| Gdzie tagować | Compose + strona outfitu (dodaj/usuń, `<datalist>`) | Pokrywa US-01 i US-02 bez JS i bez czekania na S-07 | Plan |
| Tagi na kafelkach | Tak, jedna linia pod nazwą, zwykły tekst | Widoczne przy przeglądaniu; nie są linkami, bo kafelek to już link | Plan |
| Klucz porównania | Kolumna `normalized` liczona w Pythonie (`casefold`), unikalna per właściciel | SQLite składa wielkość liter tylko dla ASCII (`Ślub`≠`ślub`), PostgreSQL nie; zgodnie z CLAUDE.md nie opieramy się na zachowaniu SQLite | Plan |
| Limity | Tag ≤ 30 znaków, ≤ 20 tagów na outfit, przecinek rozdziela | Ochrona przed nadużyciem przy minimalnej złożoności | Plan |
| Change ID | Folder zmieniony na `outfit-tags` | Zgodny z roadmapą, gałęzią i synchronizacją Jira | Plan |

## Zakres

**W zakresie:** model `Tag` + `Outfit.tags`, strażnik własności, sprzątanie nieużywanych tagów, tagi przy compose, dodawanie i usuwanie na stronie outfitu, pasek filtrów AND, tagi na kafelkach, testy dwóch kont i liczby zapytań, PR i weryfikacja produkcji.

**Poza zakresem:** zmiana nazwy lub scalanie tagów, ekran zarządzania tagami, filtr OR, ostrzeżenie przy usuwaniu otagowanego outfitu (S-07), zdjęcie w stroju (S-04), niekompletne outfity (S-06), naprawa składania wielkości liter w nazwach outfitów na SQLite, aktualizacja §6 test-planu.

## Architektura / podejście

`Tag` żyje w aplikacji `outfits` (`owner`, `name`, `normalized`, unikalne `(owner, normalized)`). `Tag.resolve(owner, names)` mapuje wpisane nazwy na istniejące tagi po kluczu albo tworzy brakujące, odporne na wyścig. Jedno pole `TagNamesField` parsuje wpisy w obu formularzach. Sygnały pilnują własności (`pre_add`) i sprzątają osierocone tagi (`post_remove`/`post_clear`, `post_delete` na `Outfit`). Garderoba czyta `?tag=…&tag=…`, dokłada jeden `.filter(tags=…)` na tag, a pasek liczy w Pythonie z prefetchowanych tagów widocznych outfitów, więc nie ma dodatkowego zapytania.

## Fazy w skrócie

| Faza | Co dostarcza | Główne ryzyko |
| --- | --- | --- |
| 1. `Tag` model and rules | Model, ograniczenia, resolver, strażnik, sprzątanie, migracja, admin | Porównanie przez `iexact`/`Lower()` przejdzie na SQLite, ale rozjedzie się na PostgreSQL |
| 2. Tagging on compose and the outfit page | Pole Tags w compose, dodaj/usuń na stronie outfitu, testy zapisów obcych id | Nazwa pola `tags` w `ModelForm` koliduje z relacją; stąd `tag_names` |
| 3. Wardrobe filter bar and tile tags | Filtr AND, zawężający pasek, tagi na kafelkach, CSS 360 px | Oczekiwane zbiory liczone tym samym zapytaniem co widok (anty-wzorzec z test-planu) |
| 4. Pull request and production | Rebase, rejestracja tras w sieci prywatności (jeśli już jest), PR, weryfikacja produkcji | Konflikty z równoległą gałęzią `feat/teasting-cross-user-privacy` |

**Warunki wstępne:** S-03 done (jest). Praca w osobnym worktree `/home/ciastek/Projects/.worktrees/outfit-tags` (gałąź `feat/outfit-tags`), równolegle do slice'a `testing-cross-user-privacy`. Szczegóły w sekcji „Parallel Work & Delivery” planu: `uv sync` i `collectstatic` przed testami, absolutna ścieżka do `.env`, serwer na porcie 8002.
**Szacowany nakład:** ~3–4 sesje w 4 fazach.

## Otwarte ryzyka i założenia

- Równoległy slice `testing-cross-user-privacy` ma zrobione fazy 1–3, a została mu tylko dokumentacja. Faza 1 tagów startuje od razu. Na starcie fazy 2, jeśli privacy jest już w `master`, robimy rebase: `make_garment` importujemy z `tests.factories`, a trasy `outfits:tags_add` i `outfits:tag_remove` rejestrujemy w `tests/owner_scoped_routes.py`. Jeśli privacy nie jest jeszcze w `master`, te same kroki robi faza 4 przy rebase.
- Filtr AND z kilkoma tagami to jeden JOIN na tag. Przy skali hobbystycznej to bez znaczenia; zakładamy, że nikt nie wybiera kilkunastu tagów naraz.
- Tag usunięty z ostatniego outfitu i wpisany ponownie może dostać inną pisownię. To świadomy koszt decyzji „znikają”.

## Kryteria sukcesu (podsumowanie)

- Użytkownik taguje outfit przy tworzeniu i później, a `Letnie`/`letnie` to jeden tag z pierwotną pisownią.
- Filtr po jednym lub kilku tagach pokazuje dokładnie własne outfity z wszystkimi wybranymi tagami, a pasek nie prowadzi do pustej siatki.
- Drugie konto nie widzi cudzych tagów ani outfitów i nie może ich zmienić. Potwierdzone testami i na produkcji.
