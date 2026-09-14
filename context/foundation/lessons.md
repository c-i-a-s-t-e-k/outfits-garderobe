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

## Done means all checks pass on the PR deploy, not on production after merge

- **Context**: The final verification phase of any plan in context/changes/<change-id>/plan.md: the manual/smoke checks that currently run against Railway production after merging to master.
- **Problem**: If checks only run on production after merge, a failure needs a second fix PR, and the plan/roadmap close-out needs yet another docs PR (compose-outfit went p4 production checks → separate close-out PR #3). Production ends up being the first real deploy the paths run on.
- **Rule**: Done means every plan check passes on the Railway PR environment. Before merging, run the verification paths against the PR deploy. Put any fixes in the same PR, and once everything passes, put the plan Progress and roadmap close-out there too. Production checks after merge are only a confirmation.
- **Applies to**: plan, plan-review, implement

## Run manual checks yourself; hand the developer a ready environment, never a to-do list

- **Context**: The `#### Manual` verification items at the end of a phase in /10x-implement and /10x-tdd, and any other step that needs the running app.
- **Problem**: The phase-end gate listed manual steps and waited for the developer, who then had to work out how to start the app (the dev settings need `DEBUG=True` locally or they demand `MEDIA_ROOT`), create accounts and data, and find the URLs. Most of those checks can be run by the agent (outfit-photo Phase 1: admin ownership refusal and the garment photo shrink both verified in headless Chromium).
- **Rule**: Run the manual checks yourself first: start the worktree's dev server on the plan's port (`DEBUG=True uv run --env-file <absolute .env path> python manage.py runserver <port>`), seed local accounts with verified emails and the data the check needs, and drive the flow in headless Chromium (the cached Playwright Chromium via `uv run --no-project --with playwright`). Assert on the page and re-read the database, and look at screenshots. Report the results with the evidence. When a check genuinely needs the developer (a real phone, a judgement call, credentials only they hold), prepare everything before asking: server running, accounts and data seeded, and give them the clickable links, logins and the exact steps.
- **Applies to**: implement, tdd, impl-review
