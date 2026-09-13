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
