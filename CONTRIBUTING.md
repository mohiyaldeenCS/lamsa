# Contributing

## Local workflow

1. Branch from `main` using `feature/<topic>`, `fix/<topic>`, or `docs/<topic>`.
2. Keep changes focused and preserve existing customer data.
3. Add meaningful regression tests for behavior changes.
4. Run `python -m unittest discover -s tests -v` from `perfume_project/`.
5. Describe the problem, resulting behavior, and validation in the pull request.

Use English commit messages and documentation. Keep storefront copy in Arabic, preserve RTL layout, and check narrow-screen keyboard navigation.

## Commit conventions

Use concise subjects such as `feat(catalog): add volume filtering`, `fix(cart): reject unavailable quantities`, or `test(orders): cover duplicate cancellation`.

Do not commit generated databases, backups, environment files, credentials, virtual environments, or local preview output. Keep changes to schema additive and test upgrades from the prior schema. Preserve required font and dependency notices.

Feature branches are merged with their individual commits intact rather than squashed. Historical import branches document recovered development stages; new work should branch from the current `main`.
