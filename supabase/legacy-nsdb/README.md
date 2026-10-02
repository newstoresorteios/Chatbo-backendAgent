# NS-db legacy permission migration — not applied

Target: NS-db project `mgwvavsjxzwflibcjzhd`, not the NsAgent database.

This directory is deliberately outside the normal NsAgent migration path. The
SQL is prepared for review and isolated PostgreSQL tests only. Its production
application is pending explicit authorization; approval of the two NsAgent
memory migrations does not authorize this separate legacy database change.

The migration removes direct public/browser-role access and preserves server
roles. Validate current dependencies and the server role before applying it.
Do not run a migration push against this directory as part of an agent deploy.

Offline test from the sibling NSAgentForSorteios checkout:

```text
node scripts/verify_memory_security_migrations.mjs
```

The test requires the developer-only PGlite dependency documented in that script.
