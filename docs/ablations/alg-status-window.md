# ALG.STATUS recency window

**Study:** `ALG.STATUS.WINDOW`
**Freeze: no.** v1 “24 months” means **730 days**. Callers may override with `window_days`. This probe does not freeze 12/24/36 and does not adopt calendar-month subtraction.

## Semantics (packet 1a)

| Choice | v1 default |
| --- | --- |
| Unit | 730 days (`timedelta(days=730)`), inclusive cutoff `harvested_at >= as_of − window` |
| Override | positive int `window_days` on map jobs / `gleansight map --window-days` |
| Not chosen | calendar-month subtraction |

## Dataset

Fixed `as_of=2024-01-01T00:00:00Z`. Synthetic harvest ages only. Not DATA-NSQD-03.

Lengths: 365 / 730 / 1095 days (12 / 24 / 36 under 365-day years).

Command: `uv run pytest tests/nsqd/test_status_window_ablation.py -q --no-cov`

## Result

| Age (days) | 365 | 730 | 1095 |
| --- | --- | --- | --- |
| 364–365 | current | current | current |
| 400 | stale | current | current |
| 729–730 | stale | current | current |
| 731–800 | stale | stale | current |
| 1095 | stale | stale | current |
| 1096 | stale | stale | stale |

Three papers + one code, not Mature, no evaluation claim:

| Harvest age | 365 | 730 | 1095 |
| --- | --- | --- | --- |
| 400d | Unknown (stale leftover) | Active | Active |
| 800d | Unknown | Unknown | Active |

ALG-SEL with a remaining Missing cell still selects that Missing cell at every length (preferred statuses beat Active).

## Decision

Keep **730 days** as the current default. File 12/36 as constructed sensitivity, not a freeze. Users may approximate alternate day lengths through `window_days`. Calendar-month subtraction is rejected for v1; it would require a separately approved, versioned semantics packet.

## Packet 1c — report-only calendar comparison (2026-08-30)

Human review reopened calendar-month semantics for evidence only. Runtime map/status behavior remains the inclusive, overridable 730-day UTC window. The comparison candidate is 24 calendar months with these proposed rules:

- compute entirely in UTC and preserve the exact time of day;
- subtract whole calendar months;
- when the source day does not exist in the destination month, clamp to that month's final day (`2024-03-31 → 2024-02-29`, `2023-03-31 → 2023-02-28`, `2024-02-29 → 2023-02-28`);
- do not reuse `window_days=730` to label calendar semantics;
- do not change runtime defaults or historical map interpretation from this packet.

Constructed boundary evidence is executable through `calendar_month_cutoff` / `calendar_month_window` in the ablation module and `tests/nsqd/test_status_window_ablation.py`. At `as_of=2024-03-31T00:00:00Z`, the fixed cutoff is `2022-04-01T00:00:00Z`, while 24 calendar months yields `2022-03-31T00:00:00Z`; a record at the latter boundary is stale under 730 days and current under calendar semantics. The packet also checks leap-day and month-end clamping, UTC enforcement, positive month counts, and preservation of the 730-day runtime default.

Activation remains pending a separate human decision after an approved-snapshot replay records changed lifecycle and cell-status rows with explicit semantics metadata.

### Calendar rule ablation

| Rule | Total on valid UTC datetimes | Preserves time-of-day | Month-end behavior | Decision |
| --- | --- | --- | --- | --- |
| reject ambiguous dates | no | yes | fails on common month ends and leap day | rejected |
| preserve end-of-month identity | yes | yes | any source month-end maps to destination month-end | rejected; changes valid dates beyond necessity |
| clamp only invalid destination days | yes | yes | preserves source day when possible, otherwise destination month-end | **selected for report-only comparison** |

The runtime comparison remains 730 fixed UTC days versus 24 calendar months under the selected clamp rule. No result from another rule may be pooled into that packet.

## Human validation

- **Validated:** packet 1a accepted 2026-08-25 (730-day default, overridable).
- **1b:** 12/36 table filed; length stays 730 and **not frozen**.
- **Calendar semantics:** fixed-day UTC semantics retained and calendar-month subtraction rejected for v1 on 2026-08-27.
- **Calendar packet 1c:** report-only comparison and month-end clamp rule approved 2026-08-30; no runtime activation.

## Freeze status

- Window unit is recorded (730 days) and remains **tunable**.
- `ALG-ABL` stays **not frozen**.
