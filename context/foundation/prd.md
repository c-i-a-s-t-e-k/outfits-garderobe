---
project: "Outfits Garderobe"
version: 1
status: draft
created: 2026-05-26
context_type: greenfield
product_type: web-app
target_scale:
  users: small
  qps: low
  data_volume: small
timeline_budget:
  mvp_weeks: 5
  hard_deadline: 2026-07-05
  after_hours_only: false
---

## Vision & Problem Statement

Osoby dbające o styl hobbystycznie mają trudność z zapamiętaniem wcześniej dobranych strojów. Fizyczna segregacja ubrań per outfit jest niemożliwa — preferują trzymanie koszul z koszulami, podkoszulków z podkoszulkami, a jedno ubranie może należeć do wielu outfitów. Efekt: dobre zestawienia są zapominane i nie da się do nich wrócić.

Istniejące aplikacje garderobiane skupiają się na katalogowaniu pojedynczych ubrań — dodawanie, tagowanie, przeglądanie. Kompozycja strojów (grupowanie ubrań w outfit, przeglądanie garderoby przez pryzmat outfitów, wizualne składanie zestawień) jest drugoplanowa lub niezręczna. Outfits Garderobe stawia kompozycję stroju w centrum, nie katalog ubrań.

## User & Persona

### Primary persona
Osoba dbająca o styl hobbystycznie — aktywnie planuje outfity z własnej garderoby, nie jest stylistą ani personal shopperem. Moment kontaktu z produktem: stoi przed szafą, szuka inspiracji lub chce przywołać wcześniej skomponowany strój. Kluczowa potrzeba: zapamiętać i przywołać zestawienia ubrań, a nie katalogować pojedyncze sztuki.

## Success Criteria

### Primary
- Użytkownik rejestruje się, dodaje ubrania ze zdjęciami, składa outfit wizualnie, dodaje swoje zdjęcie w stroju, przegląda garderobę po zdjęciach outfitowych i taguje outfity — cały flow działa end-to-end.

### Secondary
- Nowy użytkownik po tygodniu od rejestracji ma co najmniej 2 outfity ze zdjęciami w swojej wirtualnej garderobie.
- Dodanie ubrania (zdjęcie + typ + opis) zajmuje mniej niż 2 minuty.

### Guardrails
- Prywatność zdjęć: zdjęcia użytkownika (ubrania + zdjęcia w strojach) są prywatne i niedostępne dla innych użytkowników.
- Interfejs mobilny jest używalny — dodawanie zdjęć przez telefon to kluczowy use case.

## User Stories

### US-01: Użytkownik składa outfit i przegląda garderobę

- **Given** zalogowany użytkownik z co najmniej 2 dodanymi ubraniami
- **When** otwiera kreator outfitu, wybiera ubrania wizualnie, zapisuje outfit, dodaje swoje zdjęcie w tym stroju i taguje outfit
- **Then** outfit pojawia się w przeglądzie garderoby ze zdjęciem outfitowym i jest dostępny przez filtrowanie po tagach

#### Acceptance Criteria
- Jedno ubranie może być w wielu outfitach jednocześnie
- Outfit bez zdjęcia użytkownika wyświetla się z podglądem złożonym z ubrań
- Zdjęcie outfitowe jest prywatne — niedostępne dla innych użytkowników
- Interfejs kreacji outfitu działa na telefonie

### US-02: Użytkownik taguje i filtruje outfity

- **Given** zalogowany użytkownik z co najmniej 2 outfitami
- **When** taguje outfity (np. "letnie", "smart-casual") i filtruje widok po wybranym tagu
- **Then** widzi tylko outfity z danym tagiem w przeglądzie garderoby

#### Acceptance Criteria
- Jeden outfit może mieć wiele tagów
- Filtrowanie po tagu działa w widoku przeglądania (siatka zdjęć outfitowych)
- Tagi można dodawać i usuwać z outfitu

## Functional Requirements

### Konto użytkownika
- FR-001: Użytkownik może się zarejestrować i zalogować (email + hasło / OAuth). Priority: must-have
  > Socrates: Counter-argument: auth to bariera — odstraszy użytkowników przed wypróbowaniem. Resolution: kept; dane są osobiste (zdjęcia ubrań, zdjęcia w strojach), prywatność wymaga konta. Rozwiązanie bariery (demo/guest) to osobna decyzja UX, nie FR.
- FR-002: Użytkownik może się wylogować i zmienić hasło. Priority: must-have
  > Socrates: Brak kontrargumentu; standardowe operacje konta, tanie w implementacji.

### Ubrania
- FR-003: Użytkownik może dodać ubranie (zdjęcie + typ + opis). Priority: must-have
  > Socrates: Counter-argument: pole "skład" jest zbędne. Resolution: usunięte — zdjęcie, typ i opis wystarczą do identyfikacji ubrania. Skład przeniesiony do potencjalnych przyszłych rozszerzeń.
- FR-004: Użytkownik może edytować i usunąć ubranie. Priority: must-have
  > Socrates: Counter-argument: usunięcie ubrania łamie outfity, które go używają. Resolution: kept z regułą domenową — usunięcie ubrania usuwa je z outfitów; outfit zostaje, ale UI pokazuje, że jest niekompletny i daje szybki dostęp do uzupełnienia lub usunięcia outfitu.

### Outfity
- FR-005: Użytkownik może złożyć outfit z ubrań (wizualny interfejs); jedno ubranie może należeć do wielu outfitów. Priority: must-have
  > Socrates: Brak kontrargumentu; wizualny interfejs to core wartość, many-to-many to kluczowy wymóg wynikający z problemu.
- FR-006: Użytkownik może edytować i usunąć outfit. Priority: must-have
  > Socrates: Counter-argument: usunięcie outfitu powinno ostrzegać o tagach. Resolution: kept z ostrzeżeniem — UI ostrzega przy usuwaniu outfitu, który jest otagowany.
- FR-007: Użytkownik może dodać swoje zdjęcie w danym stroju do outfitu. Priority: must-have
  > Socrates: Brak kontrargumentu; zdjęcie w stroju to core UX — przeglądanie garderoby opiera się na tych zdjęciach.

### Przeglądanie
- FR-008: Użytkownik może przeglądać garderobę przez pryzmat zdjęć outfitowych. Priority: must-have
  > Socrates: Counter-argument: co jeśli outfit nie ma zdjęcia? Pusta siatka? Resolution: kept — outfit bez zdjęcia użytkownika wyświetla podgląd złożony ze zdjęć ubrań. Siatka nigdy nie jest pusta.
- FR-009: Użytkownik może przeglądać outfity z filtrowaniem po tagach. Priority: must-have
  > Socrates: Korekta w rundzie — pierwotnie brzmiał "przeglądanie ubrań z filtrowaniem po kolekcji". Poprawione: przeglądanie outfitów (nie ubrań) z filtrowaniem po tagach (nie kolekcjach).

### Tagi
- FR-010: Użytkownik może tagować outfity i filtrować widok outfitów po tagach. Priority: must-have
  > Socrates: Counter-argument: kolekcje to gloryfikowane tagi. Resolution: zmienione z kolekcji na tagi — prostszy model, ta sama zdolność filtrowania.

## Non-Functional Requirements

- Prywatność: zdjęcia ubrań i zdjęcia użytkownika w strojach są widoczne wyłącznie dla właściciela. Zero cross-user leaks.
- Responsywność: interfejs jest używalny na ekranach od 360px (telefon) do 1920px+ (desktop).
- Szybkość: każda interakcja użytkownika (dodanie, przeglądanie, filtrowanie) daje odpowiedź w mniej niż 5 sekund.
- Trwałość danych: raz dodane ubrania, outfity i zdjęcia nie są tracone bez jawnej akcji użytkownika.

## Business Logic

Aplikacja wizualnie komponuje strój z ubrań, przechowuje go jako trwałą referencję i dba o spójność outfitu — gdy ubranie zostaje usunięte, outfit jest oznaczany jako niekompletny z natychmiastową opcją naprawy lub usunięcia.

Inputs: zdjęcia i metadane ubrań (typ, opis) oraz wizualna selekcja ubrań do outfitu. Output: trwała kompozycja stroju (outfit) ze stanem spójności — kompletny lub niekompletny. Użytkownik napotyka regułę w przeglądzie outfitów: niekompletne outfity wyróżniają się wizualnie i oferują szybkie naprawienie (dodaj zamiennik) lub usunięcie outfitu.

Relacje:
- Ubranie → outfity: many-to-many (1 ubranie w wielu outfitach)
- Outfit → tagi: many-to-many (1 outfit z wieloma tagami)
- Usunięcie ubrania: kaskadowe usunięcie z outfitów + oznaczenie outfitu jako niekompletny

## Access Control

Login z kontem użytkownika (email + hasło lub OAuth). Płaski model — wszyscy zarejestrowani użytkownicy są równi, każdy widzi wyłącznie swoje ubrania i stroje. Brak ról (admin, moderator itp.). Niezalogowany użytkownik trafia na stronę logowania/rejestracji.

## Non-Goals

- Brak automatycznego rozpoznawania ubrań ze zdjęć (AI/ML) — użytkownik wpisuje typ i opis ręcznie. Rozpoznawanie to osobny moduł, nie core wartość.
- Brak społeczności / współdzielenia outfitów — zero udostępniania strojów innym użytkownikom, lajków, komentarzy, feedów. Produkt jest prywatny.
- Brak integracji ze sklepami internetowymi — nie sugerujemy zakupów, nie importujemy ubrań z e-commerce.
- Brak systemu pluginów — modularna architektura przeniesiona do v2. Kod może być przygotowany na rozszerzalność, ale system pluginów nie wchodzi w MVP.

## Open Questions

No unresolved questions at this time. All quality cross-check elements passed during shaping.
