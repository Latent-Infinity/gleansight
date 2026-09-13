# Operator C evidence audit

**State:** complete negative evidence report; report-only; runtime unauthorized
**Cutoff:** `2026-08-31T00:00:00Z`
**Decision:** insufficient evidence; no Swanson bridge and no candidate output

This packet executes the evidence checks planned in
`../nsqd-operator-activation-2026-08-30/operator-c.yaml`. It binds canonical external
bibliography, records citation/co-citation/author/direct-mention queries, extracts each
proposed bridge against a versioned arXiv source or commit-pinned full text with polarity and direction, searches direct
`A → C` prior art under the fixed cutoff, and compares both pairs across two extraction
methods and a deterministic shuffled negative control.

Every proposed bridge is rejected because at least one side lacks direct support. Zero
search results are recorded only as absence of evidence; Semantic Scholar was rate-limited,
so bibliographic noninteraction remains unverified. The broad backup prior-art query also
returned 207 works, showing that generic gradient-clipping/financial-time-series overlap is
not specific enough to support a bridge.

The packet does not write corpus facts, request human acceptance, alter
`settings.nsqd.enabled_operators`, expose C through the CLI, or authorize runtime use.

## Artifacts

- `evidence-ledger.json` — canonical records and interaction-query results.
- `claim-extractions.jsonl` — seven proposed bridge concepts with explicit `A → B` and
  `B → C` support, polarity, direction, and rejection reasons.
- `direct-a-to-c-prior-art.jsonl` — fixed-cutoff exact-pair and concept searches.
- `ablation-results.json` — preferred/backup pair and extraction/control comparisons.
- `review-summary.json` — digest manifest and independent-agent recommendation; its
  `packet_digest` is SHA-256 over canonical JSON of the sorted `artifact_sha256` map, and it
  is not human acceptance.

## Reproduce

The exact query or source URLs for every interaction check are stored in the ledger, and
the prior-art query URLs are stored in their result rows. Verify packet integrity
and the runtime boundary with:

```bash
uv run pytest tests/nsqd/test_operator_c.py tests/nsqd/test_operator_c_evidence_packet.py tests/nsqd/test_operator_activation_packets.py tests/nsqd/test_cli.py -q --no-cov
```
