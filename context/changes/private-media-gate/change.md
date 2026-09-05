---
change_id: private-media-gate
title: Prywatna brama dostępu do zdjęć użytkownika
status: implementing
created: 2026-09-05
updated: 2026-09-06
archived_at: null
---

## Notes

Roadmap F-01 (`context/foundation/roadmap.md`, milestone M-1, stream A) — fundament, brak prerequisites, status `ready`, równolegle z S-01.

**Outcome:** pliki wgrywane przez użytkownika lądują poza publicznie serwowanym katalogiem, a każde ich pobranie przechodzi przez widok, który wymaga zalogowania i sprawdza własność pliku; próba pobrania cudzego pliku kończy się odmową.

**PRD refs:** Prywatność (NFR), Access Control, FR-003, FR-007.

**Unlocks:** S-02 (`add-garment`) i S-04 (`outfit-photo`) — oba wgrywają zdjęcia. Ścieżka weryfikacji: test z dwoma kontami, w którym drugie konto nie pobiera pliku pierwszego.

**Otwarte pytanie (nie blokuje):** gdzie fizycznie leżą pliki na platformie wdrożeniowej — wolumen przypięty do usługi czy zewnętrzny magazyn obiektowy? Materiał o infrastrukturze wskazuje limit jednego wolumenu na usługę i przyjmuje wolumen za wystarczający poniżej 10 GB. Owner: user.

**Zależność wdrożeniowa (zapisana przy zamknięciu fazy 2):** brama działa, ale produkcja pisze na efemeryczny filesystem do czasu ukończenia fazy 3 (wolumen Railway + `MEDIA_ROOT`). S-02 (`add-garment`) i S-04 (`outfit-photo`) nie mogą trafić na produkcję przed fazą 3 — pierwsze wgrane zdjęcie zostałoby utracone przy najbliższym deployu.

Jira: OG-1.
