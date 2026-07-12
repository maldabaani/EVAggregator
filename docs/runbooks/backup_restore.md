# Backup & restore — PostgreSQL

Postgres is the system of record for billing, sessions, and OCPI reconciliation
data (once the persistence layer in `docs/production_readiness.md`'s item 1 is
built — today the in-memory stores hold this instead, and none of this
runbook applies to them). This runbook covers the database once that's true.

## Backup

Nightly full logical backup via `pg_dump`, retained 30 days, plus continuous
WAL archiving for point-in-time recovery within that window:

```bash
# Nightly full dump (custom format — supports parallel restore)
pg_dump -h $PGHOST -U evagg_superadmin -Fc evagg > "evagg-$(date +%F).dump"

# WAL archiving (set in postgresql.conf on the real server, not local dev)
# archive_mode = on
# archive_command = 'aws s3 cp %p s3://evagg-wal-archive/%f'
```

Store dumps and WAL segments in object storage (S3 or equivalent) with a
30-day lifecycle policy. Encrypt at rest; these dumps contain the full
tenant table, tariffs, and wallet ledger.

## Restore

Full restore from the nightly dump:

```bash
createdb -h $PGHOST -U evagg evagg_restored
pg_restore -h $PGHOST -U evagg -d evagg_restored --jobs=4 evagg-2026-07-12.dump
```

Point-in-time restore (using the base dump + archived WAL) is the same
`pg_basebackup`/`recovery_target_time` procedure documented at
<https://www.postgresql.org/docs/current/continuous-archiving.html> — not
reproduced here since it depends on the final hosting choice (self-managed
vs. RDS/Cloud SQL, which each wrap this differently).

## Targets

Not yet formally agreed with the business — placeholders to replace once
they are:

- **RPO** (acceptable data loss): proposed 5 minutes, via WAL archiving
  frequency — tighter than the 24h a nightly-dump-only strategy would give.
- **RTO** (acceptable downtime during a restore): proposed 1 hour for a full
  restore of the expected data volume; untested against real production
  data size.

## What this doesn't cover

- Redis and NATS JetStream hold no data that isn't reconstructable from
  Postgres + live charge-point state (rate-limit counters, the carbon cache,
  presence, the event stream) — no backup strategy needed for either beyond
  their own optional persistence settings.
- RLS policies and DB roles are recreated by `alembic upgrade head`, not by
  a data restore — a restored database still needs migrations applied if
  restoring onto a schema-less instance.
