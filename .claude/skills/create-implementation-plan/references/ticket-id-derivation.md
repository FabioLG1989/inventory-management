# TICKET_ID Derivation

`<TICKET_ID>` keys the artifact path `<workspace-root>/<temp>/tickets/<TICKET_ID>/artifacts/`. Producer (`/create-implementation-plan`) and consumer (`/implement-ticket`) MUST derive it identically or the artifact handoff breaks. Derive from the single input source:

- `--from-jira` → the Jira key (e.g., `PROJ-123`).
- `--from-linear` → the Linear issue identifier (e.g., `ENG-123`).
- `--from-markdown` → the tracker ticket key the H1 is titled with (e.g., `# PROJ-123: Title` → `PROJ-123`), slugified if it holds `/`, `#` or another character unsafe in a path or branch name; else the slugified H1; fallback `adhoc-<YYYY-MM-DD>`.
- `--from-input` → the same rule, applied to a short title of the description.
- `--from-plan` → the ticket id found inside the plan (e.g., in its `## Summary`); else the slugified plan title; else `adhoc-<YYYY-MM-DD>`.
