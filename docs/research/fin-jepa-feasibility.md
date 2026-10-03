# Fin-JEPA feasibility audit

Exact replication is deferred. The [versioned record](fin-jepa-feasibility-v1.json) separates
reported, proposed, unknown and verified prerequisites. No baseline smoke or reduced study
has run, and paper equivalence has not been established.

The author repository was inspected at commit
`58506d6e31ecb2c65f9c69ea1f1bc146ef08f8b9`; relevant file hashes are retained in the record.
The [paper source's reproducibility statement](https://github.com/cedricwyh/fin-jepa/blob/58506d6e31ecb2c65f9c69ea1f1bc146ef08f8b9/docs/jepa_paper.tex#L589)
identifies the full feature dataset and checkpoint as private. Its full study uses 22 features
and a chronological year split; the abstract and selected architecture describe different
predictor depths. Exact configuration and access remain unresolved.

The [public preparation script](https://github.com/cedricwyh/fin-jepa/blob/58506d6e31ecb2c65f9c69ea1f1bc146ef08f8b9/hf/prepare_dataset.py)
uses a smaller universe, 11 features and different windows. It normalizes the combined data
before splitting. The [training script](https://github.com/cedricwyh/fin-jepa/blob/58506d6e31ecb2c65f9c69ea1f1bc146ef08f8b9/hf/train_jepa.py)
splits concatenated sequences by row position. These scripts cannot establish a leakage-safe,
paper-equivalent baseline by themselves.

Unauthenticated dataset probes returned 401 for `cedwyh/fin-jepa-data` and 200 for
`perctrix/Stock-China-daily`. The latter declares Apache-2.0 at revision
`1cdaed826ecb77f1ce0412cae16c049a46701750`; data bytes and underlying permission scope were not
audited. The [repository README](https://github.com/cedricwyh/fin-jepa/blob/58506d6e31ecb2c65f9c69ea1f1bc146ef08f8b9/README.md)
declares MIT, but no tracked LICENSE file was found. This records evidence, not legal approval.

To reopen the study, obtain the missing data/checkpoint and exact configuration, or register a
distinct substitute protocol. Resolve data permissions and timestamp alignment, freeze
leakage-safe membership and train-only preprocessing, then measure a bounded smoke before a
reduced study. The JSON record lists the release gates. Existing Treasury YieldJEPA diagnostics
remain an independent prototype. The original investigation plan's `not_started` baseline
entry remains historical evidence; this audit does not grant its experiment handoff.
