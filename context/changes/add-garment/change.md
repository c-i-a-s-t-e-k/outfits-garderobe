---
change_id: add-garment
title: Dodawanie ubrania ze zdjęciem i prywatna lista ubrań
status: implemented
created: 2026-09-13
updated: 2026-09-13
archived_at: null
---

## Notes

jest to S-02 z @context/foundation/roadmap.md — Jira: OG-3 (In progress)

- **Cel:** użytkownik może dodać ubranie ze zdjęciem, typem i opisem, a potem zobaczyć swoją prywatną listę ubrań ze zdjęciami.
- **PRD:** FR-003, US-01.
- **Zależności:** S-01 (konto), F-01 (prywatna brama zdjęć) — obie done (2026-09-12).
- **Pytanie otwarte:** typ ubrania — zamknięta lista wyboru czy dowolny tekst? Wpływa na późniejsze filtrowanie po typie. Nie blokuje planowania.
- **Ryzyko:** pierwszy realny test wgrywania zdjęcia z telefonu — duże pliki prosto z aparatu bez zmniejszania łamią wymaganie odpowiedzi < 5 s.

### Faza 4 — weryfikacja ręczna (2026-09-13)

Sprawdzone automatycznie w headless Chromium (Playwright) na lokalnym `runserver` z osobną bazą. Zdjęcia testowe były wygenerowane: JPEG 6 MB 4000×3000 z orientacją EXIF 6 i HEIC 2,4 MB.

- **3.11:** pole *Other* pokazuje się i chowa zgodnie z wyborem typu.
- **3.14:** przy 360 px strona miała 410 px szerokości, bo nie zawijało się menu w nagłówku (Pico `nav ul` bez `flex-wrap`). Naprawione w `static/css/app.css`, teraz 360 px na liście, formularzu (również z błędem), zmianie hasła i `/wardrobe/`.
- **4.5:** POST 240 KB zamiast 6 MB; zapis 1200×1600, prosto, bez EXIF.
- **4.6:** *Fast 4G* (upload 1,35 Mb/s, opóźnienie 165 ms): *Save* → lista w 2,2 s. Ten sam plik bez JS: 36,8 s.
- **4.9:** Chrome nie dekoduje HEIC, skrypt zostawia oryginał (2,46 MB), serwer zapisuje go poprawnie.
- **4.10:** bez JS POST 6 MB, zapis poprawny.
- **4.7, 4.8 — pominięte decyzją developera, w planie celowo nieodhaczone.** Nie udało się podłączyć telefonu (Samsung bez opcji debugowania USB), a projekt jest hobbystyczny i przed MVP. Ryzyko przyjęte świadomie: zachowanie na prawdziwych telefonach sprawdzą testy 5.5 i 5.6 na produkcji.

### Production deploy (Faza 5) — 2026-09-13

- **Deploy:** `57fcfa7` jako deployment `cc352903` (fast-forward `feat/user-accounts` → `master`, razem z p1–p4 i poprawkami z review S-01). Logi: pillow-heif zainstalowany, `collectstatic` (136 plików), `garments.0001_initial` na Postgresie, dwa workery gunicorna (`--workers 2`), `/health/` 200. Produkcja serwuje `photo-shrink.js` i CSS z poprawką nagłówka.
- **Odstępstwo od planu, wydajność:** aplikacja działa w `europe-west4`, a Postgres w `sfo`. Na produkcji `SELECT 1` trwał 150 ms, a otwarcie połączenia 1,06–1,22 s i przy `CONN_MAX_AGE=0` powtarzało się przy każdym żądaniu. Każde żądanie z sesją i każdy kafelek zdjęcia trwał ~1,5 s, a telefon mierzył 4–7 s od *Save* do listy. Poprawka: `conn_max_age=300` i `conn_health_checks=True` (`9922fce`, deployment `adc50b4b`), przypięte testem w `test_deploy_config.py`. Po poprawce ponowne użycie połączenia trwa ~300 ms (health check i zapytanie).
- **Pomiary na Androidzie po poprawce (dane komórkowe, logi HTTP Railway):** POST dodania 2,67–2,80 s (wcześniej 3,5–4,4 s), lista 0,61 s (1,5 s), strona dodawania 0,46 s (1,36–1,55 s), kafelek 0,61 s, a w kolejce przy 2 workerach 1,2–1,8 s (wcześniej 1,5/3,0 s). *Save* → lista ~3,4 s, zgodnie z odczuciem developera („zauważalnie szybciej”).
- **Zdjęcia na produkcji (5.7, sprawdzone przez `railway ssh` i Pillow):** JPEG 735×1049 (45 KB) i 1200×1600 (188 KB, źródłowo HEIC ~900 KB), bez EXIF i GPS; developer potwierdził, że kafelki stoją prosto. Pamięć usługi przy uploadach maksymalnie 198 MB z 8 GB.
- **5.8:** drugie konto na produkcji widzi pustą listę.
- **Nieodhaczone celowo:**
  - **4.7, 5.5:** brak dostępu do iPhone'a.
  - **4.8:** Android (Chrome 152) przy `accept="image/*"` proponuje tylko galerię i kolekcje, bez aparatu. Developer akceptuje samą galerię na MVP. Poprawka UX odłożona do sekcji Parked w roadmapie.
  - **5.9:** mniej niż 10 ubrań na koncie.
- **Follow-upy:**
  - **Przeniesienie Postgresa do `europe-west4`:** usunęłoby 150 ms na zapytanie. Odłożone świadomie do czasu po MVP.
  - **`manage.py` przez `railway ssh` nie startuje:** pillow-heif nie znajduje `libstdc++.so.6`, bo sesja ssh nie ma `LD_LIBRARY_PATH` z Nixpacks; działający proces aplikacji ma. Obejście: `export $(tr '\0' '\n' < /proc/1/environ | grep '^LD_LIBRARY_PATH=')`.
  - **Przestarzały `railway.toml`:** Railway ostrzega, że konfiguracja przez ten plik działa do 2026-12-01 (`railway config migrate`).
