# Paper research operations

Inspect each operation with `gleansight api describe NAME` immediately before calling it. Its JSON schema determines required fields, limits, and accepted values. Paths and identifiers below refer to existing local records unless the operation creates them.

| Goal | Operations |
| --- | --- |
| Discover, screen, and import | `papers.candidates.discover`, `papers.candidates.list`, `papers.candidates.get`, `papers.candidates.import`, `papers.candidates.reject` |
| Read or manage papers and analysis runs | `papers.papers.list`, `papers.papers.get`, `papers.papers.get-markdown`, `papers.papers.reset-stage`, `papers.papers.delete`, `papers.runs.list`, `papers.runs.get`, `papers.runs.extractions` |
| Queue pipeline work | `papers.pipeline.download`, `papers.pipeline.convert`, `papers.pipeline.embed`, `papers.pipeline.analyze`, `papers.pipeline.analyze-project`, `papers.pipeline.reanalyze` |
| Manage and execute queued work | `papers.jobs.enqueue`, `papers.jobs.list`, `papers.jobs.get`, `papers.jobs.status`, `papers.jobs.run-next`, `papers.jobs.run-bounded`, `papers.jobs.retry`, `papers.jobs.recover`, `papers.jobs.cancel`, `papers.jobs.bulk-cancel`, `papers.jobs.delete`, `papers.jobs.bulk-delete` |
| Configure analysis prompts and profiles | `papers.prompts.create`, `papers.prompts.create-version`, `papers.prompts.list`, `papers.prompts.get`, `papers.prompts.versions`, `papers.prompts.get-version`, `papers.profiles.list`, `papers.profiles.get` |
| Organize corpus | `papers.projects.create`, `papers.projects.list`, `papers.projects.get`, `papers.projects.members`, `papers.projects.for-paper`, `papers.projects.attach`, `papers.tags.create`, `papers.tags.list`, `papers.tags.get`, `papers.tags.members`, `papers.tags.for-paper`, `papers.tags.attach` |
| Query extractions and search | `papers.query.search`, `papers.query.filter`, `papers.query.count`, `papers.query.average` |
| Synthesize and investigate | `papers.synthesis.ask`, `papers.research.ideate-project`, `papers.research.plan-idea` |
| Repair search indexes | `papers.indexes.rebuild-fts`, `papers.indexes.rebuild-vector` |

Discovery calls a live scholarly provider and retains candidates. Importing a candidate attaches requested project/tag memberships and queues a download; it does not finish conversion or analysis. A pipeline operation queues work or reuses a matching analysis run. Run jobs explicitly, then inspect job and run status before using outputs. Analysis requires a suitable prompt version, profile, and model as shown by its schema.

`papers.synthesis.ask` answers from readable corpus evidence. `investigation_plan=true` requests a plan, not execution or approval. Project ideation writes an evidence-grounded report bundle; `plan-idea` uses a selected idea from a verified bundle. Use returned paths and identifiers instead of predicting a report directory. Model-backed calls need the configured provider and may be costly.

Query and taxonomy operations expose supported application use cases. They do not authorize arbitrary database updates. Before deleting records, resetting stages, or rebuilding indexes, inspect current state and confirm the user's requested scope.
