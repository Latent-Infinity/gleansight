# Evidence layout

This tree separates immutable historical golden inputs from canonical approved inputs and contracts. It is not a destination for active workflow output.

## Frozen archive

`archive/reviews/v1/` is the byte-for-byte relocation of the former `docs/reviews/` tree. It is
historical evidence, not a writer destination. Do not edit, regenerate, reseal, or correct files in
place, and do not add correction packets. Historical paths and payload strings inside archived files intentionally remain unchanged.

Persisted logical paths beginning with `docs/reviews/` remain valid read identities. The public
`nsqd.domain.artifact_paths.resolve_artifact_path(repo_root, logical_path)` API maps only that prefix
to `evidence/archive/reviews/v1/`. Other repository-relative paths map directly beneath `repo_root`.
The resolver rejects absolute paths and `..` traversal, performs no search or fallback, and never
chooses a resurrected `docs/reviews/` file. Trusted readers still enforce descriptor-relative
`O_NOFOLLOW` checks at the physical read boundary.

## Authoritative inputs

`approved/` contains canonical explicitly approved, immutable inputs promoted from the archive. The N11 v1
projection bundle includes its approved projections, excerpts, and manifest without byte changes.

`contracts/` contains canonical versioned authoritative contracts. Operator G v1 and v2 are independent,
byte-identical promotions of their archived contract YAML files. Promotion does not grant runtime
authority or alter scoring schemas.

`tests/fixtures/approved/` remains the intentional stable test-input location and is not part of this
evidence tree. Tests must not write newly generated workflow output there.

## Ignored output

Generated workflow reports and metadata belong under ignored `output/<workflow>/<UTC-run-id>/` run
directories. Runtime application state remains under ignored `data/`, including the SQLite database,
LanceDB index, and blobs. Neither belongs under `evidence/`, and writers must not modify the frozen
archive or create `docs/archive/` as an alternate destination.

Operator G's default census scope is the explicit admitted-input root
`evidence/approved/nsqd/operator-g/failure-records/v1/`. Generated reports under `output/` do not
enter that scope and therefore do not change the census. A complete census with zero eligible records
proves zero only within the admitted scope at that snapshot; it is not a global absence claim.
