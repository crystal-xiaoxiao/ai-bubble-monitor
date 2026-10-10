# AI Bubble Watch / AI Bubble Monitor

Read `RUNBOOK.md`, `ROUTINE_PROMPT.md`, `INDICATORS.md`, and `automation/task.json` before a research run.
Work executes in the current cloud session; do not create a Codex Cloud/Dot worker or call another scheduled task.
The repository owns the research contract, validation, state and outputs. The scheduler and research model are replaceable adapters.

- Preserve the existing research scope, data quality gates and bilingual website/Feishu outputs.
- Use `scripts/pipeline.py prepare → score → build → check`; commit only its manifest-listed release files.
- Never turn stale observations into fresh data, weaken a gate to get a green run, or rewrite historical snapshots.
- Never use a new write route to evade a permissions or safety denial. Report the actual blocked action.
- Do not directly send Feishu messages or inspect its webhook secret. The existing Actions relay owns delivery.
- Migration, unit tests and site checks are not authorization to produce an extra research issue.
- `automation/archive/` is historical documentation, not active execution instructions.

For code changes, run `python3 -m unittest discover -s tests -v`. For research, run the release gates and verify GitHub head, Pages data and notification status separately.
