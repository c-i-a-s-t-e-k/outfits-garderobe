---
change_id: add-garment
title: Dodawanie ubrania ze zdjęciem i prywatna lista ubrań
status: implementing
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
