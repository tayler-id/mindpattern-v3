# harness/tickets.py

> Ticket lifecycle management. Pick, mark, decay, archive.

## Key Functions

- `list_tickets(status)` — list tickets by status
- `pick()` — select next ticket to process (priority + age ordering)
- `mark_in_progress(ticket_path)` — set status to in_progress
- `mark_done(ticket_path, pr_url)` — set status to done with PR link
- `mark_failed(ticket_path, reason)` — set status to failed with reason
- `mark_held(ticket_path)` — set status to held
- `decay()` — archive tickets older than ticket_decay_days (7 days)
- `bump(ticket_path)` — increase priority

## Missing

- No `mark_open()` — can't reset tickets via CLI. Must edit JSON manually.

## Ticket Schema

```json
{
  "id": "YYYY-MM-DD-NNN",
  "title": "...",
  "type": "bug|improvement|feature|research",
  "source": "scout|research",
  "priority": "P1|P2|P3",
  "status": "open|in_progress|done|failed|held",
  "tdd_spec": {"test_file": "...", "tests_to_write": [...]},
  "files_to_modify": ["..."],
  "created_at": "ISO-8601",
  "expires_at": "ISO-8601"
}
```

## Connected To

Called by [[harness/run]]. Tickets created by scout and research agents.

## Last Modified By Harness

Never — created 2026-04-01.
