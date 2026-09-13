# Lessons Learned

> Append-only register of recurring rules and patterns. Re-read at start by /10x-frame, /10x-research, /10x-plan, /10x-plan-review, /10x-implement, /10x-impl-review.

## Plan in English, brief and impl-review in Polish — identifiers stay English

- **Context**: Artifacts written by /10x-plan (plan.md, plan-brief.md) and /10x-impl-review (reviews/impl-review.md) in any context/changes/<change-id>/ folder.
- **Problem**: The developer reads and decides much faster in Polish, but English is far cheaper in tokens. An all-English flow slows the human; an all-Polish flow costs more, and translated headers, phase/step titles or Progress keys break the 10x-workflow parsers (## Progress, <!-- IMPL-REVIEW-REPORT -->, Decision: PENDING).
- **Rule**: Write plan.md in English — it is the source of truth. Write plan-brief.md in Polish, copying verbatim from plan.md every English identifier: phase and step titles, function/setting/file names, required headers and property keys. In /10x-impl-review, investigate and reason in English, then write reviews/impl-review.md prose in Polish, keeping the report marker, section headers, field labels (Severity, Impact, Dimension, Location, Detail, Fix, Decision) and enum values (CRITICAL/WARNING/OBSERVATION, PENDING/FIXED/SKIPPED…) in English.
- **Applies to**: plan, plan-review, impl-review

## Propagate roadmap state changes to Jira

- **Context**: Any edit to context/foundation/roadmap.md, especially at the end of /10x-implement once every phase of a slice is complete.
- **Problem**: After a whole slice is implemented, Jira doesn't show that the work is done or what to pick up next. The roadmap and Jira drift apart.
- **Rule**: Whenever you touch roadmap.md, including when /10x-implement finishes the last phase, check whether the state change belongs in Jira too. If it does, update the linked issue (transition its status and note what's next). Don't leave that to the developer.
- **Applies to**: implement
