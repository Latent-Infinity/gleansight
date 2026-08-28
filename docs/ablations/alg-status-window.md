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

## Human validation

- **Validated:** packet 1a accepted 2026-08-25 (730-day default, overridable).
- **1b:** 12/36 table filed; length stays 730 and **not frozen**.
- **Calendar semantics:** fixed-day UTC semantics retained and calendar-month subtraction rejected for v1 on 2026-08-27.

## Freeze status

- Window unit is recorded (730 days) and remains **tunable**.
- `ALG-ABL` stays **not frozen**.
