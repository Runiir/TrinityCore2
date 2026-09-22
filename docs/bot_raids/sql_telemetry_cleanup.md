# SQL telemetry cleanup

Experiment SQL is temporary storage. `run_live_bot_validation` and
`capture_phase1_raid_foundation` call the same lifecycle at their live entrypoints:

1. Before a run, sweep leftovers whose SQL archive was already remotely verified.
2. After normal finalization (including a failed experiment result), stream all
   stopped, ended SQL runs to one compressed archive per run.
3. DVC add, status, push, then read and validate the actual remote object.
4. Lock and compare the current SQL rows against that archive, delete matching
   rows in a transaction, and evict the exact local archive/cache object.

Commands for manual recovery:

```sh
pixi run python -m tools.bot_ml.sql_telemetry_lifecycle sweep --config trinity-worldserver-test.conf
pixi run python -m tools.bot_ml.sql_telemetry_lifecycle publish --config trinity-worldserver-test.conf
```

`sweep` never exports or deletes unverified runs. `publish` also resumes unfinished
uploads before exporting other closed runs. Commit the resulting `.dvc` pointers,
`.gitignore`, and small receipts in `artifacts/cata_raid_program/sql_telemetry/`.
An uncaught controller exception preserves SQL for explicit recovery. Running
labels, including abandoned runs still labelled running, are never auto-expired.

Exports contain the original eight experiment tables and table DDL. Frames are
selected through their owning clips; segments use `parent_run_id`. Shared bot
memory, models, accounts, characters and world tables are not touched. Failed
runs remain useful diagnostic evidence, but archiving does not admit them for
training or satisfy a performance/raid gate.

Upload/verification failures preserve rows. Changed rows fail comparison and
roll back deletion. Another database's receipts cannot authorize cleanup. Two
cleanup workers serialize through a database advisory lock; native writers are
protected by stopped-run checks and transactional row/range locks during compare
and delete. No table truncation, schema migration, or broad DVC garbage collection
is used. InnoDB can reuse freed pages without reducing the file's displayed size.

The other filesystem logs and diagnostic reports retain their existing evidence
lifecycle. SQL publication neither proves those files uploaded nor replaces them.

Validation uses real MariaDB connection-local temporary tables and a disposable
DVC repository/remote, with no gameplay or production-row mutation:

```sh
TC_SQL_TELEMETRY_TEST_CONFIG=trinity-worldserver-test.conf pixi run python -m pytest -q tests/test_sql_telemetry_lifecycle.py
```

Without the environment variable, database integration tests explicitly skip;
the offline-mode and controller-wiring tests still run.
