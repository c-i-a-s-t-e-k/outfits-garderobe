# Dodawanie ubrania ze zdjęciem i prywatna lista ubrań — Plan Brief

> Full plan: `context/changes/add-garment/plan.md`
> Change identity: `context/changes/add-garment/change.md`
> Roadmap item: S-02, milestone M-1, stream A — Jira OG-3

## What & Why

Zalogowany użytkownik dodaje ubranie — zdjęcie, typ i opcjonalny krótki opis — i widzi prywatną listę swoich ubrań ze zdjęciami (FR-003, US-01). To pierwsze prawdziwe wgrywanie zdjęć w produkcie, a kluczowy przypadek użycia z PRD to telefon. Dlatego plan pilnuje dwóch rzeczy: żeby wgranie mieściło się w pięciu sekundach i żeby zapisane zdjęcie było prywatne, łącznie z lokalizacją GPS.

## Starting Point

Brama prywatnych zdjęć z F-01 już działa. `PrivateImage` ma właściciela, limit 10 MB i sprawdzanie typu pliku, a jej docstring każe S-02 podpiąć się pod nią kluczem obcym. Zdjęcia nie są w żaden sposób przetwarzane: zapisuje się pełna rozdzielczość razem z EXIF i GPS, a HEIC nie jest obsługiwany. `/wardrobe/` to placeholder zarezerwowany dla S-03. Aplikacja nie ma JavaScriptu, a gunicorn działa na domyślnym jednym workerze.

## Desired End State

Po zalogowaniu użytkownik trafia na listę ubrań. Wybiera *Add garment*, robi lub wybiera zdjęcie, wskazuje typ i zapisuje. Przeglądarka zmniejsza zdjęcie przed wysłaniem, a serwer i tak obraca je do pionu, skaluje do 1600 px, usuwa wszystkie metadane i zapisuje jako JPEG za bramą. Nowy kafelek pojawia się pierwszy, drugie konto nie widzi niczego. Wszystko działa od 360 px, bez JavaScriptu i ze zdjęciami HEIC.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| Typ ubrania | Zamknięta lista + tekst przy „Other” | Jedno tapnięcie na telefonie, a nic nie jest wciskane na siłę do ogólnego worka. | Plan |
| Tekst przy „Other” | Porządkowanie spacji + zamiana na pasujący typ z listy (bez względu na wielkość liter) | „Shirt” nigdy nie istnieje naraz jako typ i jako „Other”, więc przyszły filtr zostaje czysty. | Plan |
| Opis | Opcjonalny, do 200 znaków | Zdjęcie i typ wystarczą, żeby cel „poniżej 2 minut” przetrwał dodawanie serii ubrań. | Plan |
| Zmniejszanie zdjęć | Przeglądarka + serwer | Tylko przeglądarka skraca samo wysyłanie przez sieć komórkową; serwer pozostaje gwarancją. | Plan |
| Zapisywana kopia | Jedna: ≤ 1600 px, JPEG, bez EXIF/GPS, z profilem ICC | Małe pliki i zero lokalizacji na dysku; oryginał świadomie przepada. | Plan |
| HEIC | Obsługa przez `pillow-heif` | Zdjęcie z dowolnego urządzenia Apple po prostu działa, bez ręcznej konwersji. | Plan |
| Adresy i lądowanie | `/garments/` jako strona po zalogowaniu do czasu S-03 | Placeholder `/wardrobe/` zachowuje swój kontrakt, a użytkownik ląduje na czymś prawdziwym. | Plan |
| Po zapisie | Lista + komunikat + przycisk *Add garment* na górze | Użytkownik od razu widzi, że zdjęcie się zapisało. | Plan |
| Pole zdjęcia | `accept="image/*"` bez `capture` | Działają i aparat, i galeria. | Plan |
| Rozmiar listy | Jedna strona, `loading="lazy"` | Garderoba hobbysty to dziesiątki, najwyżej setki sztuk. | Plan |
| Testy | Dogłębnie reguły, smoke dla stron; skrypt ręcznie na telefonach | Prywatność i przetwarzanie mogą zepsuć się po cichu, a JS weryfikuje się na prawdziwym iOS. | Plan |
| Aplikacja i model | Nowa aplikacja `garments`; `photo` jako `OneToOneField` z `RESTRICT` | `PROTECT` blokowałby usuwanie użytkownika, `RESTRICT` dopuszcza dokładnie ten przypadek. | Plan |
| Przetwarzanie | `normalize_photo` w `privatemedia` | S-04 odziedziczy je tak samo jak kontrolę własności. | Plan |
| Gunicorn | `--workers 2` | Jedno wgrywanie nie blokuje całej aplikacji. | Plan |

## Scope

**In scope:** `pillow-heif` i `normalize_photo`; aplikacja `garments` z modelem `Garment`, regułami, ograniczeniem w bazie i adminem; formularz, lista, link *Garments*, zmiana strony po zalogowaniu; skrypt `photo-shrink.js`; dwa workery gunicorna, wdrożenie i weryfikacja na telefonach.

**Out of scope:** edycja i usuwanie ubrania (S-06); strona szczegółów; outfity i `/wardrobe/` (S-03); filtrowanie po typie; miniatury i paginacja; zachowywanie oryginału; testy przeglądarkowe (Playwright); usuwanie plików przy usuwaniu użytkownika; magazyn obiektowy i zadania w tle; tłumaczenie UI.

## Architecture / Approach

Formularz przyjmuje zdjęcie. `clean_photo()` sprawdza rozmiar surowego pliku i woła `normalize_photo`. Widok w `transaction.atomic()` zapisuje `PrivateImage`, a potem `Garment`; jeśli coś pęknie po zapisaniu pliku, usuwa plik z dysku. Reguły typu i zgodności właściciela żyją w `Garment.clean()`, uruchamianym z `save()` (wzorzec `PrivateImage`), a ograniczenie `CheckConstraint` pilnuje reguły „Other” także w PostgreSQL. Lista to jedno zapytanie; kafelki biorą `photo_url` z `photo_id` przez bramę. `photo-shrink.js` to warstwa na działającym formularzu: każdy błąd zostawia oryginalny plik dla serwera.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Photo normalization in `privatemedia` | `pillow-heif`, `normalize_photo`, pełne testy przetwarzania | Podwójny obrót HEIC; utrata profilu ICC odbarwia zdjęcia z iPhone'a |
| 2. `Garment` model | Aplikacja `garments`, model, migracja, admin, testy reguł | `Garment.clean()` wołane z ModelForm przed ustawieniem `owner`/`photo` |
| 3. Add and list pages | Formularz, lista, nawigacja, lądowanie, testy HTTP | Osierocony plik na dysku po nieudanym zapisie |
| 4. Browser-side photo shrinking | `photo-shrink.js` z bezpiecznym powrotem do oryginału | Zachowanie iOS Safari (pamięć, orientacja) sprawdzalne tylko ręcznie |
| 5. Production | `--workers 2`, wdrożenie, pomiar na telefonach przez sieć komórkową | Pamięć dwóch workerów przy dekodowaniu dużych zdjęć |

**Prerequisites:** S-01 i F-01 są done; wolumen `/data` działa. Do fazy 4 i 5 potrzebne są prawdziwy iPhone i telefon z Androidem oraz dostęp do Railway.
**Estimated effort:** ~4–5 sesji; fazy 1 i 3 są największe.

## Open Risks & Assumptions

- Zakładamy, że iOS Safari przy `accept="image/*"` wysyła JPEG zamiast HEIC. Jeśli nie, zadziała ścieżka serwerowa, tylko wolniej.
- HEIC dekoduje się w pełnej rozdzielczości (bez trybu draft), więc na serwerze jest wolniejszy. Przychodzi jednak głównie z komputera, a tam limit pięciu sekund nie jest problemem.
- Pięć sekund zmierzymy dopiero w fazie 5 na realnej sieci komórkowej. Jeśli lista z wieloma kafelkami okaże się wolna, odpowiedzią będą miniatury w S-03, nie słabsza brama.
- Pełna rozdzielczość jest tracona na zawsze. To świadoma decyzja: do rozpoznania ubrania zdjęcie 1600 px wystarcza.
- Otwarte pytanie z roadmapy (typ ubrania) jest rozstrzygnięte w tym planie. Wpis w `roadmap.md` zostaje do aktualizacji przy archiwizacji.

## Success Criteria (Summary)

- Na prawdziwym telefonie przez sieć komórkową od *Save* do listy mija mniej niż pięć sekund, a zdjęcie jest w pionie.
- Drugie konto nie widzi ani ubrań, ani zdjęć pierwszego; zapisane zdjęcie nie zawiera GPS.
- Nieudane dodanie nie zostawia ani wiersza, ani pliku; zdjęcia HEIC i formularz bez JavaScriptu działają.
