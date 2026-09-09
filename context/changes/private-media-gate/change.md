---
change_id: private-media-gate
title: Prywatna brama dostępu do zdjęć użytkownika
status: impl_reviewed
created: 2026-09-05
updated: 2026-09-09
archived_at: null
---

## Notes

Roadmap F-01 (`context/foundation/roadmap.md`, milestone M-1, stream A) — fundament, brak prerequisites, status `ready`, równolegle z S-01.

**Outcome:** pliki wgrywane przez użytkownika lądują poza publicznie serwowanym katalogiem, a każde ich pobranie przechodzi przez widok, który wymaga zalogowania i sprawdza własność pliku; próba pobrania cudzego pliku kończy się odmową.

**PRD refs:** Prywatność (NFR), Access Control, FR-003, FR-007.

**Unlocks:** S-02 (`add-garment`) i S-04 (`outfit-photo`) — oba wgrywają zdjęcia. Ścieżka weryfikacji: test z dwoma kontami, w którym drugie konto nie pobiera pliku pierwszego.

**Rozstrzygnięcie (faza 3):** pliki leżą na wolumenie Railway przypiętym do usługi `outfits-garderobe`, nie w zewnętrznym magazynie obiektowym. Wolumen `outfits-garderobe-volume` zamontowany pod `/data`; `MEDIA_ROOT=/data/media` (katalog pod punktem montowania, korzeń wolumenu zostaje wolny). To zajmuje jedyny slot wolumenu tej usługi.

**Faktyczny sufit: 5000 MB**, nie 10 GB, które zakładał `infrastructure.md` — to limit planu na wolumen, nie wybrany rozmiar. Przy 3–5 MB na zdjęcie z telefonu daje to ok. 1000–1500 zdjęć: wystarczy na MVP, ale to jest próg, przy którym wraca rozmowa o magazynie obiektowym. Postgres zużywa osobny wolumen (217 MB / 5000 MB).

**Zależność wdrożeniowa:** S-02 (`add-garment`) i S-04 (`outfit-photo`) wymagają żywego wolumenu — bez niego pierwsze wgrane zdjęcie zostałoby zapisane na efemeryczny filesystem i utracone przy najbliższym deployu. Wolumen jest podpięty (faza 3), więc ta blokada jest zdjęta; zostaje wymóg, żeby `MEDIA_ROOT` w środowisku produkcyjnym nadal wskazywał na ścieżkę pod montowaniem.

**Kontrakt dostępu do URL-a (impl-review, 2026-09-09):** S-02 i S-04 renderują zdjęcia przez
`PrivateImage.get_absolute_url()` (albo `reverse('privatemedia:image', args=[pk])`) — **nigdy**
przez `image.url`. `image.url` to `MEDIA_URL` + nazwa pliku w storage
(`/media/private/<hex>.png`) i nie pasuje do żadnego routingu, więc zawsze zwraca 404. Kuszącą
"naprawą" tego 404 jest `django.conf.urls.static.static()`, czyli dokładnie ten helper, przed
którym broni cała ta zmiana. Pinuje to test `test_get_absolute_url_is_the_gate_and_image_url_is_dead`.

Jira: OG-1.
