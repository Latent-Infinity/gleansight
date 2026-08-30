# Divergence operators packet

**Study:** `ALG.OP`
**Outcome:** Operators A and B are **supported**. B is non-default and enabled only by a composition allowlist; the default composition and CLI remain A-only. Operators C–G stay **deferred** and **runtime-disabled**.

## Packet 4 (2026-08-26)

| Id | Name | Activation | Runtime | Wait on |
| --- | --- | --- | --- | --- |
| A | inversion | supported | enabled | — |
| B | archive whitespace | supported | composition-gated | settings `nsqd.enabled_operators`; no CLI `--operator` switch |
| C | Swanson ABC | deferred | rejected | two named literatures after B |
| D | analogical transport | deferred | rejected | source/target `domain_policy_id` after C |
| E | atypical combination | deferred | rejected | separate operator-specific evidence and explicit human activation; executable `τ` alone is insufficient |
| F | missing dimensions | deferred | rejected | axis-policy clarity |
| G | failure resurrection | deferred | rejected | approved failed-experiment corpus; do not invent it |

Command: `uv run pytest tests/nsqd/test_operator_a.py -q --no-cov`

## Operator B supported contract

See `ALG-OP-B`. B targets the full `ALG-SEL` rule without axiom inversion. Before persistence, the candidate descriptor and at least one structured axiom must occupy the selected target; every explicitly bound axiom must match it. Production composition loads the allowlist from settings (`A` or `A,B`); deferred operators are rejected at composition.

Command: `uv run pytest tests/nsqd/test_operator_b.py tests/nsqd/test_operator_a.py -q --no-cov`

## Human validation

- **Validated:** packet 4 keep-disabled outcome accepted 2026-08-26. The `ALG-OP-B` contract was accepted 2026-08-27, followed by human approval for supported, non-default, composition-gated B with controlled durable writes.
- **Not authorized:** default or CLI exposure of B; runtime enablement of C–G.

## Freeze / activation status

- B is **supported**, non-default, and composition-gated.
- C–G remain **deferred**.
