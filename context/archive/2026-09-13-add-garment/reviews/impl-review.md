<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Add Garment with Photo and Private Garment List

- **Plan**: context/changes/add-garment/plan.md
- **Scope**: Phases 1–4 of 5 (faza 5 w toku w równoległej sesji — deploy przeszedł, 5.5–5.9 nieodhaczone, więc poza zakresem)
- **Date**: 2026-09-13
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical, 4 warnings, 6 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | PASS |
| Safety & Quality | WARNING |
| Architecture | WARNING |
| Pattern Consistency | WARNING |
| Success Criteria | WARNING |

**Plan Adherence / Scope**: wszystkie punkty planu zrobione, żadnych brakujących testów. Trzy drobne rozjazdy, każdy zachowuje intencję planu: ICC zostaje tylko dla profili RGB (`privatemedia/processing.py:87`), obcięcie nazwy pliku do 255 znaków robi formularz zamiast widoku, klasę wrappera pola *Other* dodaje szablon zamiast formularza. Trzy nieszkodliwe dodatki: `flex-wrap` w menu nagłówka (opisany w change.md), skrypt zostawia oryginał, gdy JPEG nie wyszedł mniejszy, a submit jest blokowany w trakcie przetwarzania.

**Success Criteria (automated)**, uruchomione 2026-09-13:
- `uv run pytest`: 92 passed
- `ruff check` i `ruff format --check`: czysto
- `pip-audit`: brak podatności
- `manage.py check`: brak problemów
- `makemigrations --check`: brak zmian
- `collectstatic`: OK, `photo-shrink.<hash>.js` jest w manifeście

Komendy `manage.py` szły z `DJANGO_SETTINGS_MODULE=outfits_garderobe.settings_test`, bo lokalny `.env` nie ustawia `DEBUG=True` ani `MEDIA_ROOT`, a `settings.py` wtedy wymaga `MEDIA_ROOT`. To konfiguracja lokalna, nie wada tej zmiany.

**Manual**: 4.7 i 4.8 są nieodhaczone świadomie, decyzja jest opisana w change.md. Uwaga do 1.7 w F7.

## Findings

### F1 — Obraz 89–179 MP (nie-JPEG) zjada ponad 2 GB RAM na żądanie

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: privatemedia/processing.py:14-16, :33-40
- **Detail**: Komentarz i plan zakładają, że domyślny sufit Pillow chroni pamięć workera. W rzeczywistości między ~89 a ~179 MP Pillow tylko ostrzega (`DecompressionBombWarning`) i dekoduje całość. `draft()` działa wyłącznie dla JPEG, a `exif_transpose()` i `_flatten_to_rgb` robią kolejne pełnowymiarowe kopie. Pomiar agenta: PNG RGBA 13000×13000 ważący 0,69 MB (przechodzi limit 10 MB) podniósł szczyt pamięci o ~2,1 GB. Przy 2 workerach z fazy 5 każdy zweryfikowany użytkownik może położyć usługę. To nie CRITICAL, bo wymaga konta i nic nie wycieka, ale to największe ryzyko w tej zmianie. Przy okazji: JPEG 200 MP (tryb 200 MP w Samsungu) wysłany bez JS jest dziś odrzucany jako „uszkodzony” (patrz F5).
- **Fix**: Własny limit pikseli w `normalize_photo`: sprawdzić `source.size` zaraz po `Image.open`, jeszcze przed `draft`/`load`, i odrzucać powyżej np. 50 MP (48 MP z iPhone'a przechodzi) kodem `image_too_many_pixels`. Dodać test na obraz w zakresie ostrzeżenia, a nie tylko błędu.
  - Strength: Zamyka całą klasę problemu w jednym miejscu, które S-04 dziedziczy; limit jest jawny i nazwany.
  - Tradeoff: Trzeba wybrać próg. Zbyt niski odrzuci prawdziwe zdjęcia robione bez JS; JS i tak zmniejsza zdjęcia z telefonu.
  - Confidence: HIGH — zachowanie Pillow (ostrzeżenie do 2× `MAX_IMAGE_PIXELS`) jest udokumentowane, pomiar powtarzalny.
  - Blind spot: Limit pamięci serwisu na Railway nie jest sprawdzony, więc nie wiadomo, czy dziś kończy się to OOM-killem, czy tylko spowolnieniem.
- **Decision**: SKIPPED

### F2 — Uszkodzony HEIC daje 500 zamiast błędu pola

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: privatemedia/processing.py:46
- **Detail**: pillow-heif rzuca `EOFError` („Decoder plugin generated an error: Unexpected end of file”) i `RuntimeError` („Security limit exceeded…”). Żaden z nich nie jest łapany jako `invalid_image`. Zweryfikowane: 300 losowo zmutowanych plików HEIC przepuszczonych przez `GarmentForm.is_valid()` dało 2 nieobsłużone `EOFError`, a fuzz agenta na `/garments/add/` dał 2 odpowiedzi 500 na 400 plików. Przy innych formatach problem nie wystąpił.
- **Fix**: Dopisać `EOFError` i `RuntimeError` do krotki w `except` oraz test regresyjny ze zmutowanym HEIC, który rzuca `EOFError`.
- **Decision**: FIXED — `except` w `privatemedia/processing.py` łapie też `EOFError` i `RuntimeError`; nowy `test_corrupt_heic_is_an_invalid_image` (odwrócona długość NAL w `mdat`) pada na starym kodzie i przechodzi na nowym.

### F3 — Akceptowany jest każdy format Pillow, a EPS/PS uruchamia Ghostscript

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: privatemedia/processing.py:33
- **Detail**: `Image.open(upload)` bez `formats=` przyjmuje wszystko, co Pillow zna, a `get_available_image_extensions()` zawiera `eps` i `ps`. Agent potwierdził lokalnie, że `normalize_photo` na pliku `.eps` wywołuje `gs`. Obejścia `-dSAFER` w Ghostscripcie to powracająca klasa CVE. Rzadkie dekodery (PSD, FITS, SGI, TGA…) zwiększają powierzchnię ataku, a produktowi nic nie dają. Nie sprawdzono, czy obraz produkcyjny (nixpacks) ma `gs`; prawdopodobnie nie.
- **Fix**: `Image.open(upload, formats=('JPEG', 'MPO', 'PNG', 'WEBP', 'HEIF', 'GIF'))` plus test, że EPS/PSD dostają `invalid_image`.
- **Decision**: FIXED — `ACCEPTED_FORMATS = ('JPEG', 'PNG', 'WEBP', 'HEIF', 'GIF')` w `privatemedia/processing.py`. Bez `MPO`: Pillow nie ma osobnego openera MPO, pliki z iPhone'a otwiera wtyczka JPEG (sprawdzone). Nowy test `test_formats_outside_the_allowlist_are_an_invalid_image` [EPS, TIFF]. `forms.ImageField.verify()` nie uruchamia `gs`, więc lista w jednym miejscu wystarcza.

### F4 — Brak limitu rozmiaru ciała żądania przed zapisem uploadu na dysk

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: garments/forms.py:41, outfits_garderobe/settings.py
- **Detail**: `DATA_UPLOAD_MAX_MEMORY_SIZE` nie obejmuje części plikowych. Upload powyżej 2,5 MB Django zapisuje w całości do pliku tymczasowego, potem `forms.ImageField.to_python` robi na nim `Image.open()` i `verify()`, a dopiero później działa `validate_max_size`. Plik wielogigabajtowy trafi więc najpierw na dysk kontenera i przez cały czas trwania zajmuje jednego z 2 workerów.
- **Fix**: Własny upload handler (lub mały middleware dla multipart), który przerywa żądanie z `CONTENT_LENGTH` powyżej ~12 MB, zanim cokolwiek zostanie zapisane; do tego test.
  - Strength: Odrzuca żądanie, zanim zajmie dysk i czas workera; działa też dla uploadów S-04.
  - Tradeoff: Nowy element w ścieżce żądania; komunikat dla użytkownika przy przerwaniu jest mniej przyjazny niż błąd pola.
  - Confidence: MED — mechanizm Django jest pewny, ale nie wiadomo, czy Railway nie ma już własnego limitu.
  - Blind spot: Nie sprawdzono limitu ciała żądania na krawędzi Railway.
- **Decision**: FIXED — nowy `privatemedia/uploadhandlers.py` (`RequestSizeLimitUploadHandler`, `MAX_REQUEST_BYTES = MAX_UPLOAD_BYTES + 2 MiB`) jako pierwszy w `FILE_UPLOAD_HANDLERS`; powyżej limitu `RequestDataTooBig` → 400 przed parsowaniem ciała. Pliki 10–12 MiB nadal dostają błąd pola. Test `test_request_over_the_size_ceiling_is_refused_before_it_is_parsed` pada bez handlera (302) i przechodzi z nim.

### F5 — Komunikat `image_too_many_pixels` nigdy nie dociera do formularza

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: garments/forms.py:38, privatemedia/processing.py:41
- **Detail**: `forms.ImageField.to_python` wywołuje `Image.open()` przed `clean_photo` i zamienia każdy wyjątek, w tym `DecompressionBombError`, na `invalid_image`. Plan zakładał, że użytkownik zobaczy „too many pixels”, a zobaczy „not an image or corrupted”. Pamięci to nie dotyczy. Po wprowadzeniu F1 (własny, niższy próg) pliki 50–179 MP dostaną właściwy komunikat; ponad 179 MP nadal dostaną `invalid_image`.
- **Fix**: Zrobić F1 i przyjąć, że pliki ponad 179 MP dostają ogólny komunikat, albo zastąpić `forms.ImageField` zwykłym `FileField` i zostawić rozpoznanie obrazu `normalize_photo`.
- **Decision**: FIXED — `GarmentForm.photo` jest teraz `forms.FileField`; rozpoznanie obrazu i komunikaty daje wyłącznie `normalize_photo`. Poprawiony komentarz w `privatemedia/apps.py`. Nowy test `test_photo_with_too_many_pixels_says_so` pada z `ImageField` i przechodzi z `FileField`.

### F6 — Sprzątanie osieroconego pliku jest w widoku garments i opiera się na prywatnym `_committed`

- **Severity**: 💡 OBSERVATION
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Architecture
- **Location**: garments/views.py:34-58
- **Detail**: Dzisiejsza ścieżka działa poprawnie: `_committed` staje się True zaraz po zapisie do storage, więc sprzątanie obejmuje też nieudany INSERT `PrivateImage`. Ale:
  - Zasada „reguły zdjęć żyją w `privatemedia`, S-04 je dziedziczy” tu nie obowiązuje. Outfit photos w S-04, admin i każde `PrivateImage.objects.create()` zostawią plik po nieudanym INSERT.
  - Rozwiązanie zależy od prywatnego atrybutu Django.
  - Test pokrywa tylko porażkę `Garment.save`, a nie INSERT `PrivateImage`.
- **Fix**: Przenieść „zapisz zdjęcie albo nie zostawiaj nic” do helpera w `privatemedia` (np. `store_private_image(owner, file, original_filename)` jako context manager), użyć go w `garment_add` i dodać test porażki INSERT po zapisie pliku.
  - Strength: S-04 dostaje tę gwarancję za darmo, jak kontrolę właściciela z F-01; `_committed` zostaje w jednym miejscu.
  - Tradeoff: Refaktor działającego kodu przed faktyczną potrzebą; można go zrobić dopiero w S-04.
  - Confidence: HIGH — kod i testy przeczytane, zachowanie `_committed` sprawdzone w Django 6.0.
  - Blind spot: Nie wiadomo jeszcze, jak S-04 zapisze zdjęcie outfitu (w transakcji z czym).
- **Decision**: FIXED — context manager `stored_private_image(owner, file, original_filename)` w `privatemedia/models.py`; `garments/views.py::_store_garment` go używa. Trzy nowe testy w `privatemedia/tests/test_model.py` (sukces, porażka w bloku, porażka INSERT po zapisie pliku przez `connection.execute_wrapper`); oba testy porażki padają po wyłączeniu sprzątania.

### F7 — 1.7 odhaczone bez śladu użycia prawdziwych zdjęć z telefonów

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Success Criteria
- **Location**: context/changes/add-garment/plan.md (Progress 1.7)
- **Detail**: 1.7 wymaga „a real iPhone HEIC and a real Android JPEG”. Change.md opisuje tylko fazę 4, gdzie zdjęcia były wygenerowane (JPEG z EXIF 6, HEIC), i odnotowuje, że telefonu nie udało się podłączyć. Nie ma dowodu, że 1.7 sprawdzono na prawdziwych plikach; to samo ryzyko pokrywa zresztą 5.5–5.7 na produkcji.
- **Fix**: Dopisać w change.md, na jakich plikach sprawdzono 1.7, albo odznaczyć 1.7 z odesłaniem do 5.5–5.7.
- **Decision**: SKIPPED

### F8 — Skrypt shrink: `bitmap.close()` pomijane przy wyjątku, canvas nie zwalniany, przycisk po przeładowaniu

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: static/js/photo-shrink.js:57-75, :101-109
- **Detail**:
  - Gdy `getContext`/`drawImage` rzuci wyjątek (na iOS przy braku pamięci kontekst bywa null), `bitmap.close()` się nie wykona.
  - Canvas nie jest zerowany po `toBlob`, więc kolejne wybory na iOS Safari mogą uderzyć w limit pamięci canvasa. Kończy się to bezpiecznym powrotem do oryginału, ale bez zmniejszenia zdjęcia.
  - Niesprawdzone: Firefox pamięta dynamiczne `disabled` po przeładowaniu, więc przeładowanie w trakcie „Preparing photo…” może zostawić wyłączony *Save*.
- **Fix**: `bitmap.close()` w `finally`, `canvas.width = canvas.height = 0` po eksporcie, `autocomplete="off"` na przycisku submit.
- **Decision**: FIXED — `static/js/photo-shrink.js`: rysowanie w `try/finally` z `bitmap.close()`, zerowanie canvasa po `toBlob`; `templates/garments/add.html`: `autocomplete="off"` na *Save garment*. Sprawdzone: `node --check`, render szablonu, pytest, `collectstatic`. Nie sprawdzone w przeglądarce.

### F9 — Admin: select `photo` listuje zdjęcia wszystkich użytkowników po oryginalnych nazwach plików

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: garments/admin.py
- **Detail**: Formularz admina renderuje każdy `PrivateImage` jako opcję selecta. To nie skaluje się i pokazuje staffowi nazwy plików wszystkich użytkowników. `full_clean` i tak blokuje niezgodnego właściciela.
- **Fix**: `raw_id_fields = ('photo',)` i `list_select_related = ('owner',)`.
- **Decision**: FIXED — oba atrybuty dodane w `GarmentAdmin`; `manage.py check` i pytest zielone.

### F10 — Higiena testów: zduplikowane fixture'y i test kolejności zależny od zegara

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: garments/tests/test_views.py:74-80, garments/tests/*.py, privatemedia/tests/*.py
- **Detail**: `temp_media_root`, `owner` i `stranger` są skopiowane w czterech plikach testów, co zgadza się z dotychczasowym wzorcem, ale przy trzeciej aplikacji warto je wynieść do `conftest.py`. Test „newest first” opiera się na tym, że dwa `auto_now_add` różnią się czasem, co przy zgrubnym zegarze może dać flaky wynik. Przy okazji: check constraint jest testowany tylko na SQLite, nie ma CI z PostgreSQL.
- **Fix**: Wspólne fixture'y do głównego `conftest.py`; w teście kolejności ustawić `created_at` jawnie przez `update()`.
- **Decision**: FIXED — `temp_media_root`, `owner`, `stranger` w nowym `conftest.py` (bez `autouse`, bo `test_storage_config` sprawdza prawdziwy `MEDIA_ROOT`); `garments/tests/test_model.py`, `garments/tests/test_views.py`, `privatemedia/tests/test_gate.py`, `privatemedia/tests/test_processing.py` włączają go przez `pytest.mark.usefixtures`. Test kolejności ustawia `created_at` przez `update()`. Brak CI z PostgreSQL pozostaje poza zakresem.

## Triage Summary (2026-09-13)

| Decision | Findings |
|----------|----------|
| FIXED | F2, F3, F4, F5, F6, F8, F9, F10 |
| SKIPPED | F1, F7 |

Po triage: `uv run pytest` 101 passed, `ruff check` i `ruff format --check` czysto, `manage.py check` (settings_test) bez problemów, `collectstatic` OK. Zmiany nie są zacommitowane ani wdrożone.
