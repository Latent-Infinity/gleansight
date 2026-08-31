# Deferred operator activation review

**State:** report-only; no runtime authorization
**Contract:** `docs/ablations/alg-operators.md`
**Approved-input manifests:** `docs/reviews/nsqd-projection-review-2026-08-28/final/manifest.toml` for N11 records; `tests/fixtures/approved/nsqd/manifest.toml` for DATA-NSQD-03/04
**Packet plans recorded at:** `2026-08-31T09:09:18Z`

These packets inventory the smallest evidence currently available for Operators C–G. They do not make candidates corpus facts, change `settings.nsqd.enabled_operators`, expose C–G through the CLI, or authorize generation. Operator E remains independent of executable `τ = 0.45`.

| Operator | Packet | Current conclusion | Next gate |
| --- | --- | --- | --- |
| C | `operator-c.yaml` | `N11-OPT-02 → N11-FIN-04` selected; evidence incomplete | pair/method ablation, bibliographic noninteraction, and full-text A→B/B→C extraction |
| D | `operator-d.yaml` | `optimization/1 → finance/1` selected; blocked on C | structure-mapping ablation after completed C packet |
| E | `operator-e.yaml` | same-policy and cross-policy tracks approved for separate scoring; no combination is justified | method/A-B baseline ablations plus prior-art and bridge review |
| F | `operator-f.yaml` | one-axis report policy selected; no candidate axis is admissible | candidate-versus-current-and-shuffled ablation |
| G | `operator-g.yaml` | no approved failure corpus exists; collection contract defined | collect records under `failure-record-contract.yaml`, then ablate memory/trigger policies |

No packet is activation-ready. Every future recommendation requires an explicit baseline and negative-control ablation. C and E may proceed independently after their evidence gaps close; D follows C. F and G remain blocked by separate data contracts.
