<!-- PLAN-REVIEW-REPORT -->
# Plan Review: Garment Lifecycle Implementation Plan

- **Plan**: `context/changes/garment-lifecycle/plan.md`
- **Mode**: Deep
- **Date**: 2026-09-14
- **Verdict**: REVISE → SOUND (po triage: wszystkie ustalenia FIXED)
- **Findings**: 1 critical, 4 warnings, 2 observations
- **Input dodatkowy**: `context/changes/outfit-lifecycle/research.md` §5 (nieścisłości w Phase 3 S-06), §6 (roadmapa) i Open Questions 3–5

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| End-State Alignment | PASS |
| Lean Execution | PASS |
| Architectural Fitness | PASS |
| Blind Spots | WARNING |
| Plan Completeness | FAIL (przed triage) |

## Grounding

20/21 paths ✓ (`privatemedia/forms.py` nie istnieje na `787aa1f` — zgodnie z planem przychodzi z S-04 i Phase 0 to weryfikuje). 14/14 symbols ✓ (`_store_outfit`, `_owned_outfit`, `_render_detail`, `_wardrobe_url`, `MIN_GARMENTS`, `tag_names`, `snapshot_of`, `OWNED_MODELS`, `_row_counts`, `post_only`, `kwargs_for`, pinowane testy liczników zapytań `:98/:204/:374/:623/:817`). brief↔plan ✓ z jedną luką (F7).

Zweryfikowane w kodzie i w zachowaniu Django:
- Key Discovery o `pre_delete` w kaskadzie konta trzyma się: `Collector.delete()` wysyła wszystkie `pre_delete` przed fast-delete, a `MissingGarment` bez receiverów i relacji odwrotnych trafia do `fast_deletes` jako leniwy queryset po `outfit__in`, więc wstawione tombstony są kasowane razem z outfitami.
- `Garment.photo` jest `OneToOneField(RESTRICT)`, więc kolejność `garment.delete()` → `discard_private_image(photo)` w Phase 2 jest jedyną poprawną.
- `_store_outfit` traktuje `cleaned_data['name'] == ''` jako auto-nazwę, a `Outfit.clean()` woła `default_name_for()` („najniższy wolny `outfit-N`”) — podstawa F2.
- Progress↔Phase: po triage 6/6 faz zgodne 1:1, brak checkboxów poza `## Progress`.

## Findings

### F1 — Tytuły 5.8 i 5.11 w Progress różnią się od Success Criteria

- **Severity**: ❌ CRITICAL
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 5 — Manual Verification vs `## Progress` 5.8, 5.11
- **Detail**: Kryterium 5.8 miało dopisek „(both outfit names listed)”, a 5.11 inne brzmienie listy stron niż wiersz w Progress. Fazy 0–4 były zgodne 1:1. Tytuły kroków są nienaruszalne po review.
- **Fix**: Skopiować pełne brzmienie kryteriów 5.8 i 5.11 do wierszy Progress.
- **Decision**: FIXED

### F2 — Puste pole nazwy w *Edit outfit* po cichu zmienia nazwę na `outfit-N`

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Blind Spots
- **Location**: Phase 3 — §1 Forms, §2 Views (research S-07 §5, pkt 3)
- **Detail**: `_store_outfit` traktuje pustą nazwę jako auto-nazwę, a `Outfit.clean()` wstawia najniższy wolny `outfit-N`. Przy edycji bieżąca nazwa zajmuje swój numer, więc `outfit-2` z wyczyszczonym polem staje się `outfit-1` albo `outfit-3`. `OutfitEditForm` dziedziczył etykietę „Name (optional)” i help text o `outfit-N`. Plan mówił tylko „name-race handling applies to edit unchanged”, bez testu.
- **Fix A ⭐ Recommended**: puste pole = „zostaw nazwę”. `OutfitEditForm.clean_name()` zwraca `self.instance.name` gdy puste; etykieta „Name”, bez help textu; test.
  - Strength: zero niespodzianek; gałąź auto-nazwy w `_store_outfit` nigdy nie odpala się dla edycji.
  - Tradeoff: nie da się zresetować nazwy do `outfit-N`.
  - Confidence: HIGH — zmiana w jednej metodzie formularza.
  - Blind spot: None significant.
- **Fix B**: zachować auto-nazwę, dopisać help text „Leave it empty to rename to outfit-N” i test.
  - Strength: zero zmian w logice.
  - Tradeoff: przypadkowe wyczyszczenie pola kasuje własną nazwę, numeracja skacze.
  - Confidence: MEDIUM.
  - Blind spot: race z drugą kartą przy edycji nietestowany.
- **Decision**: FIXED via Fix A (Phase 3 §1 kontrakt + test w §6)

### F3 — Dodanie ubrania przez *Edit outfit* nie zdejmuje plakietki *Incomplete*

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Blind Spots
- **Location**: What We're NOT Doing (pkt 3), Phase 3 §4 `edit.html`, Phase 4 §4 (research S-07 §5, pkt 1)
- **Detail**: Reguła „tylko *Replace* i *Keep without it* zamykają brak” jest świadoma i spójna, ale UI jej nie komunikował. Użytkownik, który „naprawił” outfit przez edycję, dalej widzi „Incomplete · 1 missing”, a *Replace* dodaje kolejne ubranie. Brak komunikatu i testu.
- **Fix A ⭐ Recommended**: gdy outfit ma tombstony, `edit.html` pokazuje `<p class="notice">` „This outfit has N missing garment(s). Adding garments here does not close them — use Replace or Keep without it on the outfit page” z linkiem; test.
  - Strength: template + jeden test, bez logiki; reguła zostaje jednoznaczna.
  - Tradeoff: jeden krok więcej dla użytkownika, który poszedł przez edycję.
  - Confidence: HIGH.
  - Blind spot: mieszczenie notki w 360 px (pokrywa check 3.10).
- **Fix B**: automatycznie zamykać brak przy dodaniu ubrania tego samego typu w edycji.
  - Strength: naprawa przez edycję „po prostu działa”.
  - Tradeoff: niejawne dopasowanie (dwa braki tego typu, *Other*), łamie decyzję z NOT Doing, logika w `_store_outfit`.
  - Confidence: LOW.
  - Blind spot: interakcja z `select_for_update` na tombstonie.
- **Decision**: FIXED via Fix A (Phase 3 §4 kontrakt `edit.html` + test w §6)

### F4 — Check 0.3 i warunek „czysty working tree” nie uwzględniają niezacommitowanych edycji planu

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 0 — §2 Merge, Success Criteria 0.3
- **Detail**: `git status` pokazywał zmodyfikowane `plan.md` i `plan-brief.md` (Phase 0, merge zamiast rebase, decyzja S-07), a review dołożył kolejne edycje. Phase 0 §2 kazał zatrzymać się przy nieczystym drzewie, a 0.3 mówił dosłownie „only the planning commit”.
- **Fix**: W Phase 0 §2 pierwszy krok „commit pending docs edits in `context/changes/garment-lifecycle/`” i przeformułowane 0.3 (SC + Progress): „only docs commits touching `context/` are ahead of master”.
- **Decision**: FIXED

### F5 — Close-out w Phase 5 zostawia nieaktualny graf roadmapy i folder `outfit-lifecycle`

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 5 — §3 close-out (research S-07 §6 i Open Q4)
- **Detail**: Plan mówił „Nothing else in the dependency graph changes”, a po close-oucie nieprawdziwe zostawały: (a) S-06 Prerequisites „S-03” przy faktycznej zależności od S-04 i S-05; (b) S-06 PRD refs bez FR-006, choć slice go dostarcza, a S-07 staje się done-by-reference; (c) `outfit-lifecycle/change.md` (status `preparing`) nigdy nie stampowany ani archiwizowany; (d) pliki-sieroty po usunięciu z admina/ORM/konta bez wpisu w *Parked*.
- **Fix**: Kontrakt Phase 5 §3 rozszerzony o: Prerequisites S-06 → `S-03, S-04, S-05`; PRD refs → `FR-004, FR-006, US-01`; wpis *Parked* o plikach-sierotach z progiem powrotu; stamp `outfit-lifecycle/change.md` i `/10x-archive outfit-lifecycle` po merge.
- **Decision**: FIXED

### F6 — Asymetria minimum ubrań: edycja ≥ 1, kompozycja ≥ 2

- **Severity**: 💬 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Blind Spots
- **Location**: Phase 3 §1 Forms (research S-07 §5, pkt 2)
- **Detail**: Decyzja była zapisana w `plan-brief.md` i spójna z regułą dismiss (ukryte przy 0 ubrań). Ryzyko produktowe małe: outfit z jednym ubraniem i tak powstaje przez *Keep without it*. Brakowało uzasadnienia w `plan.md`.
- **Fix**: Jedno zdanie w Phase 3 §1 Intent z powodem asymetrii.
- **Decision**: FIXED

### F7 — Decyzja „bez podglądu outfitu na stronie usuwania” i 360 px w checku 5.10 zapisane tylko poza planem

- **Severity**: 💬 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: What We're NOT Doing (pkt 5), Phase 5 check 5.10 (research S-07 §5, pkt 4–5)
- **Detail**: Brief mówił „świadomie bez checkboxa i podglądu outfitu”, `plan.md` wymieniał tylko checkbox. Check 5.10 jako jedyny z 5.8–5.11 nie wymagał 360 px, choć dotyczy stron formularzy.
- **Fix**: Dopisek „or an outfit preview (photo or collage)” w pkt 5 What We're NOT Doing z odwołaniem do decyzji developera; „at 360 px” w 5.10 (SC + Progress).
- **Decision**: FIXED

## Poza ustaleniami — sprawdzone i bez uwag

- Research S-07 §5 pkt 4 (podgląd outfitu na stronie usuwania): decyzja developera z 2026-09-14 „no change” — zapisana teraz w planie (F7), nie jest osobnym ustaleniem.
- Research Open Q3 (czy edycja zamyka braki): rozstrzygnięte przez F3 — nie zamyka, UI to mówi.
- Research Open Q5 (rozmiar plików-sierot): niemierzony; wpis *Parked* z F5 nosi próg powrotu, pomiar nie jest potrzebny do S-06.
