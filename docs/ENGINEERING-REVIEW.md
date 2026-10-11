# Engineering Review: Catalog release

**Review Type:** Quick Review

**Verdict:** The expanded local demonstration store passes its 24-test regression suite. This is not a production-security certification or a live commerce deployment.

## Context & Assumptions

Flask, Jinja, SQLAlchemy, and SQLite serve an Arabic perfume catalog. The intended release is a source-code demonstration (assumed from the local checkout implementation); real payment and fulfillment are not implemented.

## Bugs

No release-blocking failures were observed in the executed suite. Python emits an inherited `datetime.utcnow()` deprecation warning; timestamps still work in the tested environment.

## Security

Tests exercise CSRF, order ownership, administrator access, local redirect validation, password migration, and rejection of unsafe image keys. Private databases, secrets, and backups are excluded from Git. Existing accounts retain their credentials during migration; historical demo passwords must be changed before public hosting. Login throttling and a production hosting configuration are not supplied. Dependency CVEs and infrastructure security were not audited.

## Risk Assessment

Public deployment with inherited weak credentials would put administrator access at risk. Treat credential rotation, HTTPS, secure cookies, login throttling, and host hardening as deployment prerequisites. The current local release does not claim to satisfy them.

## Architecture

The application factory separates data models, catalog vocabulary, and additive migrations. Route handlers remain in one module; split them into blueprints when subsequent features justify the additional structure.

## Performance

Catalog pagination limits result pages to 12 items. No load test was performed, and no throughput claim is made. SQLite remains a single-writer database.

## Reliability

Tests cover concurrent purchases, duplicate checkout, partial-transaction rollback, cancellation replay, repeat-safe seeding, and preserved order snapshots. Schema upgrades create private backups. Backup restoration and multi-host operation were not exercised.

## Observability

Migration backups are logged, but centralized logs, metrics, tracing, and alerting are not configured. Production incident diagnosis would require additional instrumentation.

## Dependency Analysis

Direct runtime dependencies are pinned. CI checks Python 3.11 and 3.13. The bundled font retains its license; no dependency-vulnerability scan was performed.

## Improvements

Before a public launch, add the operational controls described in [Security](../SECURITY.md), then integrate and test payment, fulfillment, and customer notifications.

## Refactoring Opportunities

Consolidate timestamp creation into one UTC helper when modernizing the inherited models. No broad rewrite is needed for the catalog release.

## Testing

Run `python -m unittest discover -s tests -v` from `perfume_project/`. The release check passed all 24 tests using disposable databases. Coverage includes legacy migration, metadata validation, filter combinations, page links, account setup, and complete rendered customer/admin flows. This is scenario coverage, not a measured line-coverage percentage.

## Change Impact

Schema changes are additive; existing products, users, and order fields are preserved. New installations no longer receive automatic demo accounts. Catalog listing now paginates. Rolling back code alone after later orders is not a substitute for a coordinated data restore.

## Maintainability

**Maintainability Score: 80/100 (qualitative).** Focused catalog modules and regression tests aid maintenance; the large route module and lightweight migration system remain constraints.

## Security Maturity

**Intermediate for local development.** Validation and authorization tests are present; operational hardening remains outside this release.

## Production Readiness

- Present: validation, regression tests, source documentation, private backup creation.
- Partial: security, error handling, logging, rollback procedures.
- Unverified or absent: load testing, monitoring, production deployment, real commerce integrations.

## Confidence

**Overall confidence: 85% for the local demonstration scope (qualitative).** Unknowns include public hosting, external integrations, operational load, and dependency vulnerabilities.

## Engineering Lessons

Keep historical data intact through additive migrations, test checkout as a transaction rather than a sequence of independent writes, and distinguish a polished local store from an operational commerce service.

## Summary

| Area | Status |
| --- | --- |
| Bugs | No failures in the executed suite |
| Security | Application checks tested; public-hosting controls pending |
| Architecture | Appropriate for a small local store |
| Performance | Paginated; not load-tested |
| Testing | 24 tests passed |
| Reliability | Stock, replay, and migration scenarios tested |
| Production Readiness | Local demonstration only |
| **Overall Score** | Suitable for the documented local scope |
