# Detection events, incidents and alerts

This note defines the four concepts the persistence layer keeps apart, the
incident lifecycle, and the guarantees the database provides.

> **Safety framing.** A model output is a *potential* fire or smoke indication.
> Nothing in this system confirms an emergency, and nothing here controls fire
> suppression or life-safety equipment.

## The four concepts

| Concept | Lifetime | Stored where | Visible to operators |
|---|---|---|---|
| **Raw detection** | one frame | nowhere | no |
| **Confirmed detection event** | permanent | `detection_events` (+ evidence JPEG) | yes, as history |
| **Incident** | until explicitly closed | `incidents` + `incident_transitions` | yes, as the work item |
| **Alert** | permanent | `alerts` | yes, as notification/acknowledgement state |

* A **raw detection** is one model output above threshold on one frame. The
  temporal confirmation engine drops most of them; they are never persisted on
  their own.
* A **confirmed detection event** is a detection that survived
  `CONFIRMATION_FRAMES` consecutive frames. One row per occurrence, with the
  confidence, class, camera, timestamp and an evidence frame
  (`detection_events.snapshot_path`).
* An **incident** groups every confirmed event of the same class on the same
  camera while it is active. It is the thing an operator acknowledges and
  closes. Each event points at its incident through
  `detection_events.incident_id`.
* An **alert** is the notification record created for one confirmed event
  (audible cue and its acknowledgement flag). Alerts stay per event; they are
  not incidents, and acknowledging an alert does not acknowledge the incident.

## Lifecycle

```
                   acknowledge                 close
   open ──────────────────────────► acknowledged ──────────► closed
     │                                   │                     ▲
     └───────────────────────────────────┴─────── close ───────┘
```

Only these transitions are accepted; every other request is a 409.

| From | Action | To | Side effects |
|---|---|---|---|
| `open` | acknowledge | `acknowledged` | `acknowledged_at`, `acknowledged_by`, transition row, linked alerts acknowledged |
| `open` | close | `closed` | `closed_at`, `closed_by`, `close_reason`, transition row |
| `acknowledged` | acknowledge | *unchanged* | idempotent: `changed: false` |
| `acknowledged` | close | `closed` | as above |
| `closed` | acknowledge | — | rejected (409) |
| `closed` | close | *unchanged* | idempotent: `changed: false` |
| any | — | `open` | never; a new detection after closure starts a **new** incident |

Rules:

1. **At most one active incident per (camera, class).** A confirmed detection
   either updates that incident (`event_count += 1`, `last_event_id`,
   `last_confidence`, `peak_confidence`, `updated_at`, evidence if newer) or, when
   none is active, opens a new one.
2. **Acknowledgement is not resolution.** An acknowledged incident keeps
   receiving detections and stays acknowledged. Only an explicit close ends it.
3. **No automatic closure.** There is no timer that clears incidents, because a
   silent auto-close would misrepresent an active hazard.
4. **Closure reasons** are `resolved`, `false_positive`, `duplicate`, `other`.
5. `camera_id = 0` means "camera not identified" (callers that predate the
   registry).

### Concurrency

* Incident creation and updates run inside `BEGIN IMMEDIATE` transactions
  (`database.db.transaction`), which serialises the read-check-write sequence.
* `ux_incidents_active` — a partial unique index on `(camera_id, class_name)
  WHERE status IN ('open','acknowledged')` — makes duplicate active incidents
  impossible even if two workers race. The loser of the race attaches its event
  to the winner instead of failing.
* The event row, the incident update and the alert row commit together, so a
  crash cannot leave an incident without its event or an event without its
  alert.

The test `test_concurrent_writers_neither_lose_nor_duplicate_records` runs eight
threads writing simultaneously and asserts exactly one incident, the exact event
count, no duplicate ids and no lost alerts.

## Evidence

* Evidence is written to `EVIDENCE_DIR` before the database transaction, then
  referenced by path in `detection_events.snapshot_path` and, per incident, by
  `incidents.evidence_event_id` (the newest event with a frame).
* API responses never contain filesystem paths: events and incidents expose
  `has_evidence` and `evidence_url` (`/evidence/<event_id>`), and that route
  applies the existing `resolve_evidence_path` traversal guard.
* A deleted evidence file never breaks a page: the detail view renders "the
  evidence file is missing on disk" and the image endpoint returns 404.

## Schema versioning and migrations

* Numbered SQL files live in `database/migrations/NNNN_name.sql`.
* Applied versions are recorded in `schema_migrations(version, name, applied_at)`.
* Each migration runs in one transaction: either all of its statements and the
  version row commit, or nothing does.
* Re-running the migration set is a no-op. A database created by a **newer**
  release raises `UnsupportedSchemaVersion` and refuses to start rather than
  corrupting data.
* Migration `0001` also contains the baseline tables, so a fresh database and a
  pre-migration database converge on the same schema. Existing rows and
  identifiers are preserved; `detection_events` only gains a nullable
  `incident_id`, and historical rows keep `NULL` (they are not retro-assigned).

## Video replay

A video **file** is not a live camera. The worker reports
`source_kind: "file"` and `is_live: false` in `/api/workers`, incidents record
the `source_kind` that produced them, and every EOF re-open increments
`replay_wraps`. Replay is therefore visible rather than silently presented as
live monitoring, and because active incidents coalesce, looping the same clip
does not inflate the incident count.

## Out of scope in this milestone

* Automatic closure, retention deletion or evidence pruning.
* Multi-operator accounts, roles and audit identity beyond the `actor` string.
* Any control output — this software only records and displays observations.
