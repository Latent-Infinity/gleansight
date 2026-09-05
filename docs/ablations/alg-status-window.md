# ALG.STATUS recency window

**Study:** `ALG.STATUS.WINDOW`
**Freeze: no.** v1 runtime semantics remain **730 inclusive UTC days** (`STATUS_WINDOW_DAYS = 730`). The calendar-month comparison stays report-only and non-activating.

## Runtime semantics

| Choice | v1 runtime |
| --- | --- |
| Unit | 730 days (`timedelta(days=730)`), inclusive cutoff `harvested_at >= as_of − window` |
| Override | positive int `window_days` on map jobs / `gleansight map --window-days` |
| Runtime status | unchanged |
| Not chosen for runtime | calendar-month subtraction |

## Packet 1c portable replay

Human review reopened calendar-month semantics for evidence only. The portable replay is sealed in `docs/reviews/nsqd-status-window-calendar-replay-2026-09-02/` and is rebuilt by `scripts/replay_status_window_ablation.py`.

### Provenance boundary

- Historical source: receipt-bound scratch SQLite recorded in `docs/reviews/nsqd-jepa-ideas-gaps-2026-09-01/baseline-evidence.json`
- Approved snapshot: `bb63826c4c648027fdae12c92b714e2be12b434c5530af211718c491a1afe8a5`
- Corpus version: `11`
- Snapshot membership: exactly `11` records
- Real persisted `harvested_at` observed for all 11 rows: `2026-09-02T06:45:00+00:00`
- Caveat: these timestamps are real persisted values from the receipt-bound report-only scratch replay, **not** proven original 2026-08-29 production-harvest timestamps because snapshot ids do not bind `harvested_at`

### Calendar candidate semantics

The report-only comparison candidate is **24 calendar months in UTC** with invalid destination days clamped to the destination month end while preserving the exact time of day.

| Rule | Total on valid UTC datetimes | Preserves time-of-day | Month-end behavior | Decision |
| --- | --- | --- | --- | --- |
| reject ambiguous dates | no | yes | fails on common month ends and leap day | rejected |
| preserve end-of-month identity | yes | yes | any source month-end maps to destination month-end | rejected; changes valid dates beyond necessity |
| clamp only invalid destination days | yes | yes | preserves source day when possible, otherwise destination month-end | **selected for report-only comparison** |

## Executed scenarios

### Scenario A — observed current-as-of replay

- `as_of = 2026-09-02T06:45:00+00:00`
- fixed cutoff = `2024-09-02T06:45:00+00:00`
- calendar cutoff = `2024-09-02T06:45:00+00:00`
- finance/1: zero lifecycle deltas, zero cell-status deltas
- optimization/1: zero lifecycle deltas, zero cell-status deltas

This is the required explicit zero-delta case.

### Scenario B — boundary sensitivity

- `as_of = 2028-09-02T06:45:00+00:00`
- fixed cutoff = `2026-09-03T06:45:00+00:00`
- calendar cutoff = `2026-09-02T06:45:00+00:00`
- finance/1 lifecycle counts: fixed `stale=6`, calendar `current=6`
- optimization/1 lifecycle counts: fixed `stale=5`, calendar `current=5`
- finance/1 cell-status deltas: `0`
- optimization/1 cell-status deltas: `0`

This is **sensitivity evidence only**, derived from the real receipt-bound `harvested_at` rows. It is not observed future production state.

## Decision

Keep **730 days** as the runtime default. The sealed portable artifact satisfied the calendar-month review prerequisite, and the human explicitly retained fixed 730-day semantics on 2026-09-03. Calendar-month subtraction remains rejected for runtime; no historical map is reinterpreted.

## Human validation

- **Validated:** packet 1a accepted 2026-08-25 (730-day default, overridable).
- **1b:** 12/36 synthetic day-length probe filed; length stays 730 and **not frozen**.
- **Calendar semantics:** fixed-day UTC semantics retained and calendar-month subtraction rejected for v1 on 2026-08-27.
- **Calendar packet 1c:** report-only comparison and month-end clamp rule approved 2026-08-30; portable approved-snapshot replay sealed and reviewed; human retained 730-day runtime semantics on 2026-09-03.

## Freeze status

- Window unit is recorded (730 days) and remains **tunable**.
- `ALG-ABL` stays **not frozen**.
