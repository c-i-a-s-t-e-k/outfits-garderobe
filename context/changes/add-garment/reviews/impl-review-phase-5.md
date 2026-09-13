<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Add Garment with Photo and Private Garment List

- **Plan**: context/changes/add-garment/plan.md
- **Scope**: Phase 5 of 5 (fazy 1–4: osobny raport `reviews/impl-review.md`, triażowany równolegle)
- **Date**: 2026-09-13
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical, 2 warnings, 4 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | PASS |
| Safety & Quality | WARNING |
| Architecture | PASS |
| Pattern Consistency | WARNING |
| Success Criteria | WARNING |

**Plan Adherence / Scope**: `--workers 2` jest w `railway.toml:12` i `Procfile:1`, polecenia są identyczne co do bajtu, a komentarz w `railway.toml:6-11` podaje powód i szczyt pamięci. Notatka „Production deploy” w change.md zawiera id deploymentów, pomiary i odstępstwa. Jedyny dodatek to `conn_max_age=300` + `conn_health_checks=True` (`9922fce`). Jest opisany w change.md jako odstępstwo, przypięty testem (`test_deploy_config.py:111-119`) i nie dodaje zmiennych środowiskowych, więc liczę go jako uzupełnienie planu, a nie rozjazd. Wpis w sekcji *Parked* w `roadmap.md` tylko zapisuje ustalenie 4.8.

**Success Criteria (automated)**, uruchomione 2026-09-13:
- 5.1 `uv run pytest`: 96 passed. Uwaga: na drzewie roboczym z niezacommitowanymi poprawkami F2/F3 z równoległej sesji, a nie na samym `9922fce`.
- 5.2 `uv run pytest accounts/tests/test_deploy_config.py`: 7 passed.
- 5.3 `/health/` na produkcji: 200 (0,16–0,17 s).
- 5.4: logi deployu nie były ponownie pobierane. Dowód jest w change.md, tylko dla `cc352903`.
- Dodatkowo `ruff check` i `ruff format --check`: czysto.

**Manual**: 5.5 i 5.9 nieodhaczone, powód opisany w change.md. Połowa 5.9 dotycząca pamięci jest zresztą pokryta: szczyt 198 MB z 8 GB. Uwagi do 5.6–5.8 w F2 i F4.

## Findings

### F1 — Domyślny 30-sekundowy timeout gunicorna zabija wolny upload bez JS lub HEIC

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: railway.toml:12, Procfile:1
- **Detail**: Brak `--timeout`, więc obowiązuje domyślne 30 s (`gunicorn/config.py:819-830`). Worker sync zgłasza, że żyje, tylko w pętli `accept` (`workers/sync.py`), nigdy w trakcie obsługi żądania. Django czyta ciało uploadu wewnątrz aplikacji, więc worker, który po 30 s wciąż odbiera plik, jest zabijany: użytkownik dostaje 502, a ubranie nie zapisuje się.
  - Komentarz w `railway.toml` sam zakłada, że worker jest zajęty „przez cały transfer”, czyli że proxy Railway nie buforuje ciała żądania.
  - change.md ma już pomiar ponad progiem: ten sam plik 6 MB bez JS pod *Fast 4G* szedł **36,8 s** (4.6).
  - Pełny oryginał leci też przy HEIC w Chrome (2,46 MB, 4.9). Skrypt zmniejsza tylko zdjęcia, które przeglądarka umie zdekodować.
  - Na produkcji takie uploady nie zostały sprawdzone. Zmierzono tylko ścieżkę z JS (45–188 KB).
- **Fix**: Dodać `--timeout 120` do obu plików, z komentarzem (wolny upload na komórce ponad 30 s blokuje workera sync), a potem sprawdzić na produkcji upload 6 MB bez JS z dławieniem *Fast 4G*.
  - Strength: Zamyka jedyną znaną ścieżkę, na której ubranie przepada przy prawidłowym pliku; zmiana jednej flagi w dwóch miejscach.
  - Tradeoff: Naprawdę zawieszony worker zostanie ubity dopiero po 120 s; przy 2 workerach to dłuższe okno na zajęty worker.
  - Confidence: MED — mechanizm gunicorna jest pewny, a pomiar 36,8 s pochodzi z `runserver`, nie z produkcji.
  - Blind spot: Nie wiadomo, czy edge Railway buforuje ciało żądania. Jeśli tak, worker czyta już gotowe bajty i problemu nie ma.
- **Decision**: FIXED — `--timeout 120` w `railway.toml` (z komentarzem) i `Procfile`. Do zrobienia po deployu: sprawdzić na produkcji upload 6 MB bez JS pod *Fast 4G*.

### F2 — 5.8 odhaczone, a połowa o 404 na cudzy URL zdjęcia nie ma dowodu z produkcji

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Success Criteria
- **Location**: context/changes/add-garment/plan.md (Progress 5.8), context/changes/add-garment/change.md:38
- **Detail**: Kryterium 5.8 wymaga pustej listy **i** 404 na URL zdjęcia pierwszego konta. change.md zapisuje tylko „drugie konto na produkcji widzi pustą listę”. Właśnie 404 jest produkcyjnym dowodem guardraila prywatności z PRD. Lokalnie pokrywa to 3.13 i testy, ale na produkcji nie ma to zapisanego potwierdzenia.
- **Fix**: Otworzyć na produkcji URL zdjęcia pierwszego konta jako drugie konto, zobaczyć 404 i dopisać to w change.md przy 5.8 (albo odznaczyć 5.8 do czasu sprawdzenia).
- **Decision**: SKIPPED

### F3 — Zgodność poleceń startowych Procfile i railway.toml pilnowana tylko komentarzem

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: railway.toml:12, Procfile:1, accounts/tests/test_deploy_config.py
- **Detail**: Plan wymaga, żeby oba polecenia były identyczne. Dziś są, ale żaden test nie czyta `Procfile` ani `railway.toml`, a pilnuje tego tylko komentarz „Keep in step with the Procfile”. Ryzyko rośnie przy F1 (nowa flaga w dwóch miejscach) i przy migracji `railway config migrate` przed 2026-12-01. `test_deploy_config.py` jest naturalnym miejscem: już przypina ustawienia produkcyjne.
- **Fix**: Dodać do `test_deploy_config.py` test, który wyciąga `startCommand` z `railway.toml` (`tomllib`) i linię `web:` z `Procfile` i porównuje je.
- **Decision**: SKIPPED

### F4 — Zapis weryfikacji fazy 5 odbiega od brzmienia kryteriów 5.6 i 5.7, a SHA wskazują commit z samą dokumentacją

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Success Criteria
- **Location**: context/changes/add-garment/change.md:36-37, context/changes/add-garment/plan.md (Progress 5.1–5.8)
- **Detail**:
  - 5.6 mówi o „freshly taken photo”. Na Androidzie aparat nie jest proponowany (4.8), więc zdjęcie musiało pochodzić z galerii, a change.md tego nie mówi.
  - 5.7 każe pobrać zdjęcie przez bramę i otworzyć je Pillow. Sprawdzono je przez `railway ssh` na wolumenie. Wynik jest równoważny, ale ścieżka inna.
  - 5.1–5.8 mają SHA `1f0d575`, który zmienia tylko dokumenty. Zdeployowane były `57fcfa7` i `9922fce`.

  Nic z tego nie podważa wyników, ale zapis nie odpowiada temu, co zrobiono.
- **Fix**: Dopisać w change.md dwa zdania (5.6: zdjęcie z galerii; 5.7: sprawdzone na wolumenie przez ssh) i poprawić SHA w Progress na `57fcfa7`/`9922fce`.
- **Decision**: FIXED — change.md: 5.6 zdjęcie z galerii, 5.7 sprawdzone na wolumenie zamiast przez bramę; Progress: 5.4 → `57fcfa7`, 5.1–5.3 i 5.6–5.8 → `9922fce`.

### F5 — `conn_max_age=300` wymusza ponowne łączenie (~1,1 s) na żądaniu użytkownika co 5 minut na workera

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: outfits_garderobe/settings.py:147-152
- **Detail**: Komentarz jest poprawny: `close_at` liczy się od otwarcia połączenia (`django/db/backends/base/base.py:249`), a połączenie po terminie zamyka się na granicy żądania. Skutek: co 5 minut jedno żądanie na każdego z 2 workerów płaci pełne ~1,1 s otwarcia połączenia przez region. Przy aktywnym użytkowniku to zauważalne szarpnięcie w przeglądaniu kafelków. Z `conn_health_checks=True` zerwane połączenia i tak są wykrywane, więc krótki `conn_max_age` niewiele chroni.
- **Fix**: Podnieść do `conn_max_age=3600` (albo `None`), zaktualizować komentarz i asercję w `test_deploy_config.py`.
- **Decision**: SKIPPED

### F6 — Połączenie z Postgresem przez region bez timeoutów i bez wymuszonego TLS

- **Severity**: 💡 OBSERVATION
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: outfits_garderobe/settings.py:147-152
- **Detail**: Diff dotknął wywołania `dj_database_url.config`, ale nie ustawił `OPTIONS`:
  - **Brak timeoutów i keepalive.** Nie ma `connect_timeout` ani TCP keepalive. Połączenie zerwane po cichu przez pośrednika powoduje, że health-check `SELECT 1` wisi, aż gunicorn po 30 s ubije workera (jedno 502).
  - **TLS niewymuszony.** Nie ma `ssl_require`, więc obowiązuje domyślne `sslmode=prefer` z libpq. Ktoś na trasie może wymusić nieszyfrowane połączenie, a trasa biegnie `europe-west4` ↔ `sfo`.

  Oba problemy były już przed tą zmianą. Czas otwarcia połączenia 1,06–1,22 s sugeruje publiczne proxy z TLS, ale tego nie sprawdzono.
- **Fix**: Najpierw ustalić, czy `DATABASE_URL` idzie przez prywatną sieć Railway, czy publiczne proxy. Jeśli przez proxy: `ssl_require=True` oraz `OPTIONS={'connect_timeout': 10, 'keepalives': 1, 'keepalives_idle': 60}`, przypięte w `test_deploy_config.py`.
  - Strength: Szyfrowanie ruchu z danymi użytkowników między kontynentami i ograniczenie zawieszonego workera do 10 s zamiast 30 s.
  - Tradeoff: `ssl_require=True` wyłoży aplikację, jeśli połączenie idzie przez prywatną sieć bez TLS; wymaga weryfikacji przed deployem.
  - Confidence: MED — zachowanie libpq i Django sprawdzone w kodzie, topologia sieci Railway nie.
  - Blind spot: Nie czytano `.env` ani zmiennych Railway, więc trasa `DATABASE_URL` jest nieznana. Planowane przeniesienie Postgresa do `europe-west4` może zmienić odpowiedź.
- **Decision**: SKIPPED
