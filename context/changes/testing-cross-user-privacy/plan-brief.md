# Cross-user Privacy Contract — Plan Brief

> Full plan: `context/changes/testing-cross-user-privacy/plan.md`
> Research: `context/changes/testing-cross-user-privacy/research.md`

## Co i dlaczego

Faza 1 rolloutu z test-planu obejmuje ryzyka #1 i #2. Ma dowieść, że żadne zdjęcie ani rekord właściciela nie przechodzi między kontami, ani przy odczycie, ani przy zapisie. Każdy nowy widok z danymi właściciela ma dziedziczyć ten dowód automatycznie, zanim S-04…S-07 dodadzą kolejne ścieżki. Dziś ochrona działa, ale testy są rozproszone po slice'ach i nic nie wymusza pokrycia nowej trasy.

## Punkt wyjścia

**Właścicielstwo** zawsze pochodzi z `request.user`, a odmowa to jeden identyczny 404. Zapisy blokują dwie warstwy: queryset formularza oraz reguły modelu (`Garment.clean()` i guard `m2m_changed`).

**Uwierzytelnianie** zapewnia `@login_required` na każdym widoku. Widok, któremu zabraknie dekoratora, nie jest wykrywany.

**Testy** leżą w `<app>/tests/` i są nazwane od modułów. Fabryka ubrań jest zdublowana (`_garment` / `make_garment`).

**PR #2** (compose-outfit) jest nadal otwarty.

## Stan docelowy

- **Middleware.** `LoginRequiredMiddleware` jest aktywny. Z projektu wyłączone są tylko `health` i `home`, a healthcheck Railway nadal dostaje 200.
- **Struktura testów.** Nowy pakiet `tests/`:
  - `tests/CLAUDE.md`
  - `tests/factories.py`
  - `tests/owner_scoped_routes.py` (rejestr tras)
  - `tests/cross_user_visibility/` (ryzyko #1) i `tests/foreign_id_writes/` (ryzyko #2), jeden plik na jeden scenariusz awarii.
- **Sieć.** Nowa chroniona trasa bez wpisu w rejestrze wywraca `uv run pytest`. Wpis w rejestrze automatycznie obejmuje trasę kontraktami:
  - anonim trafia na login;
  - obcy dostaje 404 identyczny z nieistniejącym id albo stronę bez markerów właściciela;
  - obcy zapis nie zmienia bazy.

## Kluczowe decyzje

| Decyzja | Wybór | Dlaczego (1 zdanie) | Źródło |
| --- | --- | --- | --- |
| Kolejność względem PR #2 | Czekamy na merge i rebase | Rejestr i fabryka celują w finalne 8 tras, bez konfliktu w `conftest.py` | Research / Plan |
| Układ testów | `tests/<risk-slug>/`, plik = scenariusz, plus `tests/CLAUDE.md` | Folder to ryzyko z §2, plik to scenariusz, a nie moduł z funkcjami | Plan (developer) |
| Kiedy sieć failuje | Tylko niezarejestrowana chroniona trasa (plus zarejestrowana z opt-outem i nieaktualny wpis) | Mniej tarcia; publiczność wymaga jawnego `@login_not_required` | Plan (developer) |
| Odmowa dla obcego | 404 identyczny z losowym UUID, bez `ETag`/`Last-Modified`, bez markerów | Utrzymuje istniejącą własność „nie twoje ≡ nie istnieje” dla każdej trasy | Research / Plan |
| Relacja do testów slice'ów | Sieć + kontrakt; testy slice'ów zostają, zmienia się tylko import fabryki | Jedno miejsce dowodu bez przepisywania działających testów | Plan |
| Default-deny | `LoginRequiredMiddleware` + `@login_not_required` na `health`/`home` | Zapomniany dekorator przestaje być dziurą | Plan (developer) |
| Istniejące `@login_required` | Zostają | Obrona w głąb, gdyby middleware zniknął; dodatkowo pilnuje go pin test | Plan |

## Zakres

**W zakresie:**
- middleware i dwa opt-outy;
- `tests/factories.py` i przepięcie importów w testach slice'ów;
- rejestr tras i sieć;
- kontrakty: anonim, obcy odczyt, zdjęcia z własnych stron, warianty URL media;
- kontrakt obcego zapisu, ignorowanie `owner`/`photo`/`id` w `garments:add`, re-render compose bez obcego ubrania;
- `tests/CLAUDE.md`, §6.1/§6.6 test-planu i wskaźnik w root `CLAUDE.md`.

**Poza zakresem:**
- przepisywanie testów slice'ów;
- admin i mechanika allauth (§7);
- `bulk_create` na tabeli M2M;
- `MEDIA_ROOT` względem `STATICFILES_DIRS` (Faza 2);
- ścieżki S-04…S-07 (jeszcze nie istnieją);
- CI, hooki, `testpaths`.

## Architektura / podejście

Rejestr `tests/owner_scoped_routes.py` mapuje nazwę trasy na deklarację: rodzaj (`read`/`write`), seeder zwracający kwargs i markery właściciela oraz, dla zapisów, wrogi payload. Pliki scenariuszy parametryzują się po rejestrze. Test sieci porównuje rejestr z resolverem; trasa jest chroniona, gdy `login_required` nie jest `False`. Scenariusze zapisu sprawdzają dwa niezmienniki bazy: snapshot danych właściciela się nie zmienia i nigdzie nie ma powiązania między obiektami różnych właścicieli.

## Fazy w skrócie

| Faza | Co dostarcza | Główne ryzyko |
| --- | --- | --- |
| 1. Default-deny login and test scaffold | Middleware, opt-outy, `tests/factories.py`, pin middleware | Healthcheck lub `/` bez opt-outu, czyli deploy nie wstaje |
| 2. Risk #1 — cross-user visibility | Rejestr, sieć, kontrakty odczytu, warianty URL media | Kontrakt przechodzi pusto (brak `src`/markerów), co łapią asercje „co najmniej jeden” |
| 3. Risk #2 — foreign-id writes | Niezmienniki bazy, kontrakt obcego zapisu, dwa scenariusze luk | Asercja na status zamiast ponownego odczytu bazy |
| 4. Cookbook and test guide | `tests/CLAUDE.md`, §6.1/§6.6, wskaźnik w `CLAUDE.md` | Przewodnik rozjedzie się z rejestrem |

**Warunki wstępne:** PR #2 zmergowany do `master`, gałąź `feat/teasting-cross-user-privacy` zrebase'owana.
**Szacowany nakład:** ~2–3 sesje na 4 fazy.

## Otwarte ryzyka i założenia

- Sieć nie łapie nowej trasy **publicznej**, która jawnie ma `@login_not_required`. Łagodzi to pin test zbioru opt-outów (`{health, home}`), którego zmiana wymaga świadomej edycji.
- Anonimowe `/admin/` przekierowuje teraz na login allauth zamiast `/admin/login/`. To akceptowalne, bo admin jest w §7.
- Zakładamy, że po merge'u PR #2 zestaw tras projektu to nadal 8 tras z research. Jeśli nie, rejestr uzupełniamy w Fazie 2.
- Kontrakt porównuje body 404 bajt w bajt. Działa dzięki `DEBUG=False` i braku własnego `404.html`; przyszły szablon 404 musi być statyczny.

## Kryteria sukcesu (skrót)

- Dodanie chronionej trasy bez wpisu w rejestrze wywraca testy; po wpisie trasa jest objęta kontraktami anonima, obcego odczytu i obcego zapisu.
- Kontrolowane sabotaże (usunięcie filtra po właścicielu, `404.html` z nazwą outfitu, `owner` w formularzu, opt-out na widoku) wywracają wskazany test.
- Healthcheck Railway pozostaje zielony po wdrożeniu middleware.
