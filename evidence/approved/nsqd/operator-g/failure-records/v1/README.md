# Operator G admitted failure records v1

This directory is the default input scope for the active Operator G census. It is intentionally
empty: no failure record is currently admitted.

Record placement is not approval. A census caller must separately provide the matching trusted
approval and exact digest-, role-, and path-bound evidence registry entries. Evidence needed by a
record must also be stored beneath the census's explicitly declared input roots.

## Scope migration

The active census no longer scans the repository-wide `docs`, `src`, and `tests` roots. Generated
reports, maintained documentation, source changes, and the frozen review archive therefore do not
alter the active admitted-record inventory.

Historical reports retain their original declared scope, counts, and digests as immutable replay
fixtures under `evidence/archive/reviews/v1`. In particular, the historical 354-file census and its
`b930b81be31ebdad3e9007c6b96963939dc73915da6a896f8914ba9e3b2abbb4` snapshot are not claimed to
have been reproduced by this narrower scope.

The applicable record contracts are:

- `evidence/contracts/nsqd/operator-g/v1/failure-record-contract.yaml`
- `evidence/contracts/nsqd/operator-g/v2/failure-record-contract-v2.yaml`
