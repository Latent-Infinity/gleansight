# NSQD plan closeout

Verification date: 2026-10-02. Plan: [development-plan-ns-qd.md](development-plan-ns-qd.md).

Status: Complete for the required baseline.

## Scope and acceptance

Required scope is NSQD-N0, N0A, N1, N2/N2a/N2b, and N3 through N11.
All phase checklists are checked. The 24 plan facts are Active in the central
fact ledger, and all 22 Required evidence commands, EV-N00 through EV-N21,
passed. The retained status-window replay also passed against its 11 approved
records. Historical review artifacts were preserved.

The completed baseline keeps Operator A as the default, B as an explicitly
configured supported operator, and E experimental and off by default. C, D, F,
and G remain deferred. The activated novelty threshold is tunable at 0.45;
the approved runtime status window remains 730 days. Report-only packets do
not confer corpus, schema, operator, or runtime approval.

## Corrections found during closeout

The unified `gleansight rescore` command read decision and viability from the
job result's outer dictionary, returning null values on success. It now reads
the persisted card in the nested result. Two regression cases use the real
scratch database and job handler, including a stale card updated to the current
snapshot/version. Both failed before the correction and passed afterward.
Installed-command checks also verified successful JSON output and a nonzero
exit for an unknown card.

Rendered desktop checks found gray error panels on Synthesis, Harvest, Map,
Diverge, Ground, Gate, Acquire, Rescore, Skeleton, Archive, and Card. Their text
fields expanded inside wrapping rows. A fresh-process browser probe established
that setting `expand=False` still failed, while leaving expansion unset and
giving the fields bounded widths rendered the form. Those fields now use the
existing Project screen's 320-pixel width. Eleven regression cases require
bounded width and unset expansion; all failed before the correction and passed
afterward. Diverge's Operator field was also widened to 120 pixels after browser
QA found its label breaking across the field border. The EV-N18 surface command
passes 88 tests.

## Verification

| Check | Result |
| --- | --- |
| `uv run ruff format --check .` | Passed; 502 files |
| `uv run ruff check .` | Passed |
| `uv run ty check` | Passed |
| `uv run pytest -q` | 2,729 passed; 2 skipped; 92.35% coverage |
| Dedicated NSQD coverage command from the plan | 1,860 passed; 92.65% coverage |
| EV-N00 through EV-N21 commands | All passed; EV-N18 rerun after the layout fix: 88 passed |
| `uv run python scripts/replay_status_window_ablation.py --verify-retained-replay` | Passed; 11 records |
| Flet web rendering and interaction | All 18 screens passed at 1200x800 and 768x600; validation, dispatch, and confirmation checks passed |

The dedicated NSQD command used a separate temporary coverage file. It ran
after the rescore correction; the subsequent layout-only change touches no
`src/nsqd` code. The repository's full-suite threshold is 91.90%, and the NSQD
threshold is 90%.

Retained calibration verification opened the SQLite corpus read-only. The
approved measured snapshot contains six finance and five optimization sources.
All 180 persisted measurements, the 120 balanced labels, 15 adjudications,
source/neighbor bindings, and packet digest matched their retained evidence.
Domain re-evaluation reproduced the 0.45 threshold decision; altered evidence
was rejected. No new approval, corpus projection, source acquisition, or live
provider call was required for closeout.

Desktop QA uses the actual Flet app and screens in a web preview with inert service callbacks.
This permits navigation, rendering, validation, dispatch, and approval-confirmation
checks without approving a digest or changing a corpus. Backend behavior is
covered separately by the evidence commands, persisted-job regressions, and
read-only calibration checks.

On a fresh server, invalid Rescore input dispatched zero callbacks; valid
card/snapshot/version input dispatched exactly one and displayed the result.
Empty or unconfirmed approval dispatched zero callbacks. A confirmed approval
dispatched once, cleared confirmation, and rejected an immediate repeat. An
injected callback failure also cleared confirmation and rejected an immediate
repeat. No browser-console or preview-server errors were observed. A native
desktop window and live provider interactions were not exercised by this QA.

## Local execution artifacts

Detailed execution, acceptance, calibration, and desktop reports are retained
under `.omo/evidence/nsqd-closeout-*-2026-10-02*.md`. Browser screenshots,
semantic snapshots, isolated probes, and callback logs are retained under
`output/nsqd-plan-closeout-ui/run-20261002-qa1/`. These local artifacts are
ignored by Git; the commands and results above record the reproducible closeout
in the repository.
