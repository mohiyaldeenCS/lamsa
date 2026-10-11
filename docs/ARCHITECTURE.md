# Architecture

## Request flow

Flask's application factory configures SQLAlchemy, CSRF protection, session secrets, additive schema upgrades, routes, and explicit catalog-management commands. Jinja templates render the Arabic storefront; small local JavaScript modules enhance navigation, quick-view dialogs, and quantity controls.

Core flows remain conventional server-rendered forms. Catalog filters use query parameters so results can be bookmarked and pagination retains the selected criteria. Product images resolve through an allowlist of local assets.

## Data

- `User`: account identity, password hash, and administrator flag.
- `Perfume`: inventory, price, SKU, scent category, audience, bottle size, local image key, and featured state.
- `Order`: owner, contact/address snapshot, totals, unique checkout token, and status.
- `OrderItem`: product name, brand, unit price, quantity, line total, image, bottle size, category, and audience captured at checkout.

Orders retain their item snapshots if products are edited or removed. Money used for order totals is rounded with decimal arithmetic. Product stock decrements use conditional database updates inside the same transaction as the order.

## Checkout

1. An authenticated customer reviews an available cart.
2. The checkout form includes CSRF and a session-bound one-use order token.
3. The server validates the form and checks current stock.
4. Conditional stock updates and order snapshots commit together.
5. Replaying the same token returns the existing order without a second deduction.
6. Only the owner or an administrator can view the order.

Order progression is `pending → confirmed → preparing → completed`. Eligible orders can become `cancelled`; stock is restored once. Completed and cancelled orders are terminal.

## Catalog setup

Catalog migration adds columns without replacing existing inventory. The seed command matches existing identities before inserting missing sample records. Schema and seed operations are tested for repeat execution. Administrator creation is an explicit CLI action, not a side effect of seeding.
