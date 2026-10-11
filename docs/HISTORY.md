# Repository history

The project originally existed as local files without a Git repository. The initial history was reconstructed from the original source inspection and retained development snapshots when version control was introduced.

Commits describe coherent feature stages. Their timestamps record the import, not the original day each line was written. Original files reconstructed from the inspection have normalized formatting; the history is not represented as an untouched recording of earlier commits.

## Stages

| Stage | Branch | Scope |
| --- | --- | --- |
| Foundation | feature/legacy-foundation | Hello-world entry point, original models, forms, routes, templates, and seed data |
| Functional store | feature/storefront-core | Arabic views, cart actions, favorites, catalog filters, and product administration |
| Commerce and visual redesign | feature/checkout-discovery | Local orders, stock transactions, security, photographic UI, fonts, and tests |
| Expanded catalog | feature/catalog-expansion | Product metadata, safe migrations, larger catalog, filtering, pagination, and explicit admin setup |
| Repository delivery | chore/repository-delivery | English documentation, CI, issue templates, release notes, and launch instructions |

All imported commits use the repository owner's configured Git author and committer identity. No co-author trailers are added.

## Ongoing workflow

`main` is the integrated branch. Keep focused feature/fix branches and merge without squash to preserve meaningful commits. Annotated tags identify milestones. Do not force-push published history or backdate imported commits.

Historical branches and tags intentionally preserve superseded implementations. The current `main` branch is the supported version.
