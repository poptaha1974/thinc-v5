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
| `tenants` | yes | no | no | no |
| Evidence, assessment, decision, approval records | yes | yes | yes | yes |
| `audit_events` | yes | yes | no | no |

`thinc_app` receives no `TRUNCATE`, `REFERENCES`, or `TRIGGER` grant and owns
no THINC table. The audit mutation trigger remains the final append-only guard
even if privileges are changed later.

## Tenant session contract

Call `thinc_v5.db.set_tenant_context` inside every database transaction that
touches a tenant-owned table. It uses transaction-local PostgreSQL state, so
the tenant value is cleared before a pooled connection can serve another
transaction.

Destructive migration tests additionally require both test URLs, a database
name containing `test`, and `THINC_TEST_DATABASE_DISPOSABLE=1`. Role rejection
tests additionally require a cluster-administrator connection through
`THINC_TEST_PROVISIONER_DATABASE_URL`; that identity is never used by runtime
or ordinary migration tests.

The migration-cycle snapshot deliberately covers only THINC-owned database
objects: the six THINC tables, their constraints/defaults/indexes/ownership,
RLS policies, the audit trigger and function, direct table grants, the direct
`thinc_app` schema ACL, and the audit function ACL. It excludes unrelated
cluster roles, databases, schemas, extensions, and objects owned by other
applications so a disposable shared PostgreSQL cluster is not treated as part
of THINC's migration surface.
