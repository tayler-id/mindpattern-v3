# Checkpoint record

Use one record per independently reviewable behavior change. Fill it with task facts and link the evidence. Keep generated response bodies and private runtime data outside committed documentation.

| Field | Record |
| --- | --- |
| User outcome | Action and observable end state. |
| Scope | Feature-map IDs and changed files. |
| Acceptance | Concrete expected result and relevant failure paths. |
| Verification | Exact commands, outcomes, evidence location, source identity. |
| Runtime limits | ASGI, HTTP, browser, external-provider, and data limits that apply. |
| Review 1 | Findings, fixes, dismissals, and remaining issues. |
| Review 2 | Independent findings, fixes, dismissals, and remaining issues. |
| Next step | Next reversible checkpoint or a specifically authorized commit or release action. |
