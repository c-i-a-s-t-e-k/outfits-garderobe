---
project: "Outfits Garderobe"
version: 1
status: draft
created: 2026-09-04
updated: 2026-09-05
prd_version: 1
main_goal: speed
top_blocker: time
milestone_id: end-to-end-wardrobe-flow
milestone_seq: 1
milestone_status: open
---

# Roadmap: Outfits Garderobe

> Powstała z `context/foundation/prd.md` (v1) oraz z automatycznej inwentaryzacji kodu w repozytorium.
> Dokument edytuje się w miejscu; archiwizuje, gdy zostanie zastąpiony.
> Elementy poniżej są ułożone w kolejności zależności. Tabela „At a glance" jest indeksem.

## Milestone

**M-1: Pełny przepływ garderoby — od rejestracji do filtrowania po tagach** — Status: open

- **Intent:** Doprowadzić do stanu, w którym cały przepływ z głównego kryterium sukcesu PRD działa na jednym koncie: rejestracja, dodanie ubrań ze zdjęciami, wizualne złożenie outfitu, własne zdjęcie w stroju, przeglądanie garderoby po zdjęciach outfitowych i filtrowanie po tagach — przy zachowaniu prywatności zdjęć.
- **Source materials:** `context/foundation/prd.md` (v1)
- **Done when:** każdy element F-NN i S-NN poniżej ma status `done`.
- **Scope anchors:** FR-001 – FR-010 (wszystkie konieczne), US-01, US-02, wymagania pozafunkcjonalne dotyczące prywatności i responsywności, sekcja „Access Control".

## Vision recap

Osoby dbające o styl hobbystycznie zapominają wcześniej dobrane zestawienia, bo fizycznie nie da się trzymać ubrań posegregowanych per strój — jedna koszula należy do wielu outfitów naraz. Istniejące aplikacje garderobiane katalogują pojedyncze ubrania, a składanie i przywoływanie strojów traktują drugoplanowo. Outfits Garderobe odwraca ten porządek: kompozycja stroju jest głównym obiektem, a katalog ubrań tylko materiałem do niej.

## North star

**S-03: Użytkownik składa outfit z dodanych ubrań i widzi go w siatce garderoby** — to jest ten element, który przy przyjętym celu „szybkie domknięcie przepływu" dowozi się najwcześniej, jak pozwalają zależności.

> Gwiazda przewodnia to najmniejszy kompletny fragment przepływu, którego dowiezienie dowodzi, że główne założenie produktu jest prawdziwe. Stoi tak wcześnie, jak pozwalają jej zależności, bo cała reszta funkcji ma znaczenie tylko wtedy, gdy ta jedna działa. Tutaj: dopóki użytkownik nie potrafi złożyć stroju z własnych ubrań i go odnaleźć, produkt nie różni się od katalogu ubrań, którym PRD wprost nie chce być.

## At a glance

| ID   | Change ID          | Outcome (użytkownik może …)                                                              | Prerequisites | PRD refs                          | Status   |
| ---- | ------------------ | ---------------------------------------------------------------------------------------- | ------------- | --------------------------------- | -------- |
| F-01 | private-media-gate | (fundament) zdjęcia leżą poza publicznym katalogiem, a dostęp do pliku sprawdza właściciela | —             | Prywatność (NFR), Access Control, FR-003, FR-007 | planning    |
| S-01 | user-accounts      | zarejestrować się, zalogować, wylogować i zmienić hasło                                    | —             | FR-001, FR-002, Access Control    | ready    |
| S-02 | add-garment        | dodać ubranie (zdjęcie, typ, opis) i zobaczyć swoją prywatną listę ubrań                   | S-01, F-01    | FR-003, US-01                     | proposed |
| S-03 | compose-outfit     | wizualnie złożyć outfit z ubrań i zobaczyć go w siatce garderoby                           | S-02          | FR-005, FR-008, US-01             | proposed |
| S-04 | outfit-photo       | dodać do outfitu własne zdjęcie w tym stroju i widzieć je jako kafelek w siatce            | S-03, F-01    | FR-007, FR-008, US-01             | proposed |
| S-05 | outfit-tags        | tagować outfity i filtrować siatkę garderoby po wybranym tagu                              | S-03          | FR-009, FR-010, US-02             | proposed |
| S-06 | garment-lifecycle  | edytować i usunąć ubranie, a dotknięte outfity widzieć jako niekompletne z szybką naprawą  | S-03          | FR-004, US-01                     | proposed |
| S-07 | outfit-lifecycle   | edytować i usunąć outfit, z ostrzeżeniem przy usuwaniu otagowanego                         | S-03, S-05    | FR-006, US-01, US-02              | proposed |

## Streams

Pomoc nawigacyjna — grupuje elementy dzielące łańcuch zależności. Wiążąca kolejność żyje w grafie zależności poniżej; ta tabela to proponowana kolejność czytania w równoległych torach.

| Stream | Theme                          | Chain                    | Note                                                                                             |
| ------ | ------------------------------ | ------------------------ | ------------------------------------------------------------------------------------------------ |
| A      | Ubrania i prywatne zdjęcia     | `F-01` → `S-02` → `S-06` | Tor zdjęć: brama prywatności, pierwsze wgranie, potem cykl życia ubrania. `S-06` dołącza po `S-03`. |
| B      | Konto                          | `S-01`                   | Głowa całego grafu — bez konta żaden inny element nie ma czyich danych pokazywać.                 |
| C      | Kompozycja i przeglądanie      | `S-03` → `S-04`          | Tor gwiazdy przewodniej; dołącza do toru A po `S-02` i przy celu „szybkie domknięcie" ma pierwszeństwo. |
| D      | Tagi i cykl życia outfitu      | `S-05` → `S-07`          | Domyka drugą historyjkę PRD; dołącza do toru C po `S-03`.                                          |

## Baseline

Co jest już w repozytorium na dzień `2026-09-04` (automatyczna inwentaryzacja, potwierdzona przez autora).
Fundamenty poniżej zakładają, że to istnieje, i tego nie budują od nowa.

- **Frontend:** absent — brak katalogu szablonów, brak arkuszy stylów i zasobów, `TEMPLATES` ma pustą listę katalogów (`outfits_garderobe/settings.py:62`).
- **Backend / API:** partial — jest pakiet konfiguracyjny Django 6.0.5; router adresów obsługuje tylko `/health/` i panel administracyjny (`outfits_garderobe/urls.py:26`). Brak jakiejkolwiek aplikacji domenowej.
- **Data:** partial — połączenie z bazą czytane ze zmiennej środowiskowej, w środowisku deweloperskim SQLite (`outfits_garderobe/settings.py:83`). Brak modeli domenowych i brak jakiejkolwiek konfiguracji przechowywania plików wgrywanych przez użytkownika.
- **Auth:** partial — wbudowany moduł kont Django wraz z warstwą pośrednią uwierzytelniania i walidatorami haseł jest włączony (`outfits_garderobe/settings.py:40,49,93`), ale nie ma widoków ani adresów logowania i rejestracji, nie ma logowania zewnętrznego i nie ma nigdzie sprawdzania własności danych.
- **Deploy / infra:** present — wdrożenie na Railway działa: `railway.toml` z automatycznym wykrywaniem projektu, serwer aplikacyjny i serwowanie plików statycznych w zależnościach, punkt kontrolny `/health/`, zbieranie statyków i migracje uruchamiane przed startem.
- **Observability:** absent — brak konfiguracji logowania, brak śledzenia błędów, brak metryk. Zostają tylko logi platformy.

## Foundations

### F-01: Brama prywatnych zdjęć

- **Outcome:** (fundament) pliki wgrywane przez użytkownika lądują poza publicznie serwowanym katalogiem, a każde ich pobranie przechodzi przez widok, który wymaga zalogowania i sprawdza własność pliku; próba pobrania cudzego pliku kończy się odmową.
- **Change ID:** private-media-gate
- **PRD refs:** Prywatność (NFR), Access Control, FR-003, FR-007
- **Unlocks:** S-02 i S-04 — oba wgrywają zdjęcia i bez tej bramy nie da się ich wypuścić zgodnie z wymaganiem prywatności. Tworzy też ścieżkę weryfikacji: test z dwoma kontami, w którym drugie konto nie pobiera pliku pierwszego.
- **Prerequisites:** —
- **Parallel with:** S-01
- **Blockers:** —
- **Unknowns:**
  - Gdzie fizycznie leżą pliki na platformie wdrożeniowej — wolumen przypięty do usługi czy zewnętrzny magazyn obiektowy? Materiał o infrastrukturze wskazuje limit jednego wolumenu na usługę. Owner: user. Block: no.
- **Risk:** stoi przed pierwszym wgraniem zdjęcia, bo dołożenie bramy później oznaczałoby przenoszenie już wgranych plików i zmianę wszystkich adresów; ryzykiem jest wybór miejsca składowania, który przy jednym wolumenie na usługę może wymusić zewnętrzny magazyn.
- **Status:** planning

## Slices

### S-01: Konto użytkownika

- **Outcome:** użytkownik może się zarejestrować, zalogować, wylogować i zmienić hasło; niezalogowany trafia na stronę logowania zamiast na treść.
- **Change ID:** user-accounts
- **PRD refs:** FR-001, FR-002, Access Control
- **Prerequisites:** —
- **Parallel with:** F-01
- **Blockers:** —
- **Unknowns:**
  - Czy logowanie zewnętrzne wchodzi do tego kamienia milowego, czy wystarczy email z hasłem? FR-001 dopuszcza jedno albo drugie. Owner: user. Block: no.
- **Risk:** to pierwszy element z widocznym interfejsem, więc powstaje przy nim szablon bazowy i style działające od 360 pikseli, z których korzystają wszystkie kolejne widoki; ryzykiem jest rozlanie się tej pracy na pełny system projektowy zamiast minimalnej bazy.
- **Status:** ready

### S-02: Ubranie ze zdjęciem

- **Outcome:** użytkownik może dodać ubranie ze zdjęciem, typem i opisem, a potem zobaczyć swoją prywatną listę ubrań ze zdjęciami.
- **Change ID:** add-garment
- **PRD refs:** FR-003, US-01
- **Prerequisites:** S-01, F-01
- **Parallel with:** —
- **Blockers:** —
- **Unknowns:**
  - Czy typ ubrania to zamknięta lista wyboru, czy dowolny tekst? PRD mówi tylko „typ + opis". Owner: user. Block: no.
- **Risk:** to pierwszy realny test wgrywania zdjęcia z telefonu, czyli kluczowego przypadku użycia wskazanego w kryteriach sukcesu; ryzykiem są duże pliki prosto z aparatu, które bez zmniejszania łamią wymaganie odpowiedzi poniżej pięciu sekund.
- **Status:** proposed

### S-03: Kompozycja outfitu i siatka garderoby

- **Outcome:** użytkownik może wizualnie złożyć outfit z dodanych ubrań, zapisać go i zobaczyć w siatce garderoby, gdzie outfit bez własnego zdjęcia pokazuje podgląd złożony ze zdjęć ubrań; jedno ubranie może należeć do wielu outfitów naraz.
- **Change ID:** compose-outfit
- **PRD refs:** FR-005, FR-008, US-01
- **Prerequisites:** S-02
- **Parallel with:** —
- **Blockers:** —
- **Unknowns:** —
- **Risk:** to jest teza produktu — kompozycja stroju zamiast katalogu ubrań — więc leży najwcześniej, jak pozwalają zależności; ryzykiem jest wizualny wybór ubrań na ekranie 360 pikseli, gdzie siatka miniatur i zaznaczanie łatwo stają się nieużywalne.
- **Status:** proposed

### S-04: Własne zdjęcie w stroju

- **Outcome:** użytkownik może dodać do outfitu własne zdjęcie w tym stroju i od tej pory widzi je jako kafelek tego outfitu w siatce garderoby.
- **Change ID:** outfit-photo
- **PRD refs:** FR-007, FR-008, US-01
- **Prerequisites:** S-03, F-01
- **Parallel with:** S-05, S-06
- **Blockers:** —
- **Unknowns:** —
- **Risk:** dopiero to zdjęcie sprawia, że przegląd garderoby przestaje być siatką miniatur ubrań, a staje się tym, co opisuje PRD; ryzykiem jest podmiana kafelka — podgląd złożony i własne zdjęcie muszą wyglądać spójnie w tej samej siatce.
- **Status:** proposed

### S-05: Tagi i filtrowanie

- **Outcome:** użytkownik może dodawać i usuwać tagi na outficie oraz filtrować siatkę garderoby tak, by widzieć wyłącznie outfity z wybranym tagiem.
- **Change ID:** outfit-tags
- **PRD refs:** FR-009, FR-010, US-02
- **Prerequisites:** S-03
- **Parallel with:** S-04, S-06
- **Blockers:** —
- **Unknowns:** —
- **Risk:** domyka drugą historyjkę PRD i ostatni brakujący krok głównego kryterium sukcesu; ryzykiem jest swobodne wpisywanie tagów, które bez normalizacji rozjeżdża się na warianty tego samego słowa i psuje filtrowanie.
- **Status:** proposed

### S-06: Cykl życia ubrania i niekompletne outfity

- **Outcome:** użytkownik może edytować i usunąć ubranie, a outfity, które go używały, wyróżniają się w siatce jako niekompletne i dają natychmiastowy wybór: uzupełnij zamiennikiem albo usuń outfit.
- **Change ID:** garment-lifecycle
- **PRD refs:** FR-004, US-01
- **Prerequisites:** S-03
- **Parallel with:** S-04, S-05, S-07
- **Blockers:** —
- **Unknowns:** —
- **Risk:** leży po kompozycji, bo dopiero wtedy reguła spójności z logiki biznesowej ma co naruszać i da się ją sprawdzić na realnym outficie; ryzykiem jest to, że stan niekompletności musi być widoczny w siatce, a nie tylko zapisany w bazie.
- **Status:** proposed

### S-07: Cykl życia outfitu

- **Outcome:** użytkownik może edytować i usunąć outfit, a przy usuwaniu outfitu, który ma tagi, dostaje ostrzeżenie przed potwierdzeniem.
- **Change ID:** outfit-lifecycle
- **PRD refs:** FR-006, US-01, US-02
- **Prerequisites:** S-03, S-05
- **Parallel with:** S-04, S-06
- **Blockers:** —
- **Unknowns:** —
- **Risk:** leży po tagach, bo ostrzeżenie wymagane przez FR-006 dotyczy właśnie otagowanego outfitu i wcześniej nie miałoby czego wykrywać; ryzykiem jest przypadkowe usunięcie, gdy ostrzeżenie da się przekliknąć bez czytania.
- **Status:** proposed

## Backlog Handoff

| Roadmap ID | Change ID | Suggested issue title | Jira | Ready for `/10x-plan` | Notes |
| ---------- | --------- | --------------------- | ---- | --------------------- | ----- |
| F-01 | `private-media-gate` | Prywatna brama dostępu do zdjęć użytkownika | OG-1 | yes | Uruchom `/10x-plan private-media-gate` |
| S-01 | `user-accounts` | Rejestracja, logowanie, wylogowanie i zmiana hasła | OG-2 | yes | Uruchom `/10x-plan user-accounts` |
| S-02 | `add-garment` | Dodawanie ubrania ze zdjęciem i prywatna lista ubrań | OG-3 | no | Czeka na S-01 i F-01 |
| S-03 | `compose-outfit` | Wizualne składanie outfitu i siatka garderoby | OG-4 | no | Czeka na S-02 |
| S-04 | `outfit-photo` | Własne zdjęcie w stroju jako kafelek outfitu | OG-5 | no | Czeka na S-03 i F-01 |
| S-05 | `outfit-tags` | Tagowanie outfitów i filtrowanie siatki po tagu | OG-6 | no | Czeka na S-03 |
| S-06 | `garment-lifecycle` | Edycja i usuwanie ubrania z oznaczeniem niekompletnych outfitów | OG-7 | no | Czeka na S-03 |
| S-07 | `outfit-lifecycle` | Edycja i usuwanie outfitu z ostrzeżeniem o tagach | OG-8 | no | Czeka na S-03 i S-05 |

Ta tabela jest przekazaniem do narzędzia backlogowego. Jeden wiersz na każdy element roadmapy, bez powielania szczegółów z treści powyżej. Zgłoszenia założone w projekcie Jira **OG (outfits-garderobe)** dnia 2026-09-04; zależności z pola `Prerequisites` odwzorowano tam jako powiązania typu „Blocks".

## Open Roadmap Questions

PRD nie ma nierozstrzygniętych pytań. Poniższe wyszły w trakcie układania roadmapy i żadne nie zatrzymuje planowania — każde ma bezpieczne ustawienie domyślne, które `/10x-plan` może przyjąć i zapisać.

1. **Czy logowanie zewnętrzne wchodzi do tego kamienia milowego, czy wystarczy email z hasłem?** FR-001 dopuszcza jedno albo drugie, a przy celu „szybkie domknięcie przepływu" bezpiecznym domyślnym jest email z hasłem. Owner: user. Dotyczy: S-01.
2. **Gdzie fizycznie leżą pliki zdjęć na platformie wdrożeniowej — wolumen przypięty do usługi czy zewnętrzny magazyn obiektowy?** Materiał o infrastrukturze wskazuje limit jednego wolumenu na usługę i przyjmuje wolumen za wystarczający przy skali poniżej dziesięciu gigabajtów. Owner: user. Dotyczy: F-01, S-02, S-04.
3. **Czy typ ubrania to zamknięta lista wyboru, czy dowolny tekst?** PRD mówi tylko „typ + opis"; wybór wpływa na to, czy da się później po typie filtrować. Owner: user. Dotyczy: S-02.

## Parked

- **Automatyczne rozpoznawanie ubrań ze zdjęć** — Poza zakresem wg PRD; użytkownik wpisuje typ i opis ręcznie, rozpoznawanie to osobny moduł.
- **Społeczność i współdzielenie outfitów** — Poza zakresem wg PRD; produkt jest prywatny, bez udostępniania, polubień i komentarzy.
- **Integracje ze sklepami internetowymi** — Poza zakresem wg PRD; nie sugerujemy zakupów i nie importujemy ubrań.
- **System pluginów i architektura modularna** — Poza zakresem wg PRD, przeniesione do wersji drugiej.
- **Logowanie zdarzeń, śledzenie błędów i metryki aplikacji** — Żadne wymaganie z PRD tego nie wymusza, a przyjęty cel „szybkie domknięcie przepływu" każe odłożyć wszystko, czego przepływ nie potrzebuje. Platforma wdrożeniowa daje własne logi na siedem dni.
- **Zrównanie bazy deweloperskiej z produkcyjną** — Środowisko deweloperskie zostaje na SQLite; połączenie i tak jest czytane ze zmiennej środowiskowej, więc produkcja dostaje PostgreSQL bez osobnej pracy. Warto pilnować, by modele nie opierały się na luźnym typowaniu SQLite.

## Milestone History

(Pusta — to pierwszy kamień milowy. Wpisy dopisuje się przy zamykaniu, bez edycji wcześniejszych.)

## Done

(Pusta przy pierwszym wygenerowaniu. Wpisy dopisuje `/10x-archive` przy archiwizowaniu zmiany.)
