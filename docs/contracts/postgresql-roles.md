# PostgreSQL role contract

THINC uses separate PostgreSQL identities for migrations and application
traffic.

## Migration identity

`THINC_MIGRATION_DATABASE_URL` (or `THINC_TEST_DATABASE_URL` in tests) must
authenticate as a role distinct from `thinc_app`. It owns the THINC tables and
functions and must be able to create and drop them. The migration does not
create cluster roles.

Alembic accepts exactly one effective URL. A URL explicitly placed in its
`Config` object cannot be replaced by environment variables. Without an
explicit URL, setting conflicting migration and test URLs is an error rather
than an implicit precedence rule.

## Application identity

`THINC_DATABASE_URL` (or `THINC_TEST_APP_DATABASE_URL` in tests) must
authenticate as the pre-provisioned LOGIN role `thinc_app`. Before creating
the schema, the migration rejects this role if it:

- is the migration identity or inherits the migration identity;
- is a superuser or has `BYPASSRLS`, `CREATEDB`, or `CREATEROLE`;
- inherits another role with any of those attributes; or
- has effective `CREATE` privilege on the database or `public` schema.

The migration fails with an explicit error if `thinc_app` has not been
provisioned.

## Runtime grants

| Table | SELECT | INSERT | UPDATE | DELETE |
| --- | --- | --- | --- | --- |
| `tenants` (current tenant row only) | yes | no | no | no |
| Evidence, assessment, decision, approval records | yes | yes | yes | yes |
| `audit_events` | yes | yes | no | no |

`thinc_app` receives no `TRUNCATE`, `REFERENCES`, or `TRIGGER` grant and owns
no THINC table. The audit mutation trigger remains the final append-only guard
even if privileges are changed later.

## Tenant session contract

Call `thinc_v5.db.set_tenant_context` inside every database transaction that
touches tenant-scoped data, including the `tenants` table. It uses
transaction-local PostgreSQL state, so the tenant value is cleared before a
pooled connection can serve another transaction. `tenants` has its own forced
RLS policy: `thinc_app` can select only the row whose `id` matches
`app.tenant_id`, and it has no tenant insert, update, or delete grant.
The table-owning migration identity has a separate management policy so
explicit provisioning and migrations still work while forced RLS is enabled;
that policy is not granted to `thinc_app`.

The identity boundary already supplies the tenant UUID used for this context.
Runtime bootstrap must not perform a global slug lookup through `thinc_app`;
slug discovery belongs to a separate, explicitly authorized identity service
outside Foundation.

Destructive migration tests additionally require both test URLs, a database
name containing `test`, and `THINC_TEST_DATABASE_DISPOSABLE=1`. Role rejection
tests additionally require a cluster-administrator connection through
`THINC_TEST_PROVISIONER_DATABASE_URL`; that identity is never used by runtime
or ordinary migration tests.

Cluster-mutating rejection tests are restricted to the ephemeral PostgreSQL
16 service in the GitHub Actions `quality` job. Before opening the provisioner
connection, their guard requires all of `GITHUB_ACTIONS=true`, `CI=true`,
`THINC_TEST_DATABASE_DISPOSABLE=1`, and the workflow-only
`THINC_DESTRUCTIVE_ROLE_TESTS=postgres16-github-actions-service-v1` token. It
also requires canonical, query-free `postgresql+psycopg` URLs for the exact
`thinc_migrator`, `thinc_app`, and `postgres` identities at the literal
`localhost:5432/thinc_test` destination. Driver aliases, implicit ports,
alternate loopback forms, encoded identities, and all query parameters are
rejected before the provisioner connection opens. A subsequent read-only
server check confirms PostgreSQL 16. Missing any condition skips the mutation
tests before the first `ALTER ROLE` or `GRANT`.

Positive live tests do not request a provisioner identity and remain runnable
against any explicitly disposable test database satisfying the migration/app
role contract.

The migration-cycle snapshot deliberately covers only THINC-owned database
objects: the seven THINC tables, their constraints/defaults/indexes/ownership,
RLS policies, the audit trigger and function, direct table grants, the direct
`thinc_app` schema ACL, and the audit function ACL. It excludes unrelated
cluster roles, databases, schemas, extensions, and objects owned by other
applications so a disposable shared PostgreSQL cluster is not treated as part
of THINC's migration surface.
