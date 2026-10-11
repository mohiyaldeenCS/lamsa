# Security

Report vulnerabilities privately to the repository owner through GitHub's private vulnerability reporting feature when available. Do not include passwords, live customer information, session keys, or database copies in public issues.

The current application is a local demonstration store. Its checkout does not process payments or arrange delivery. Before operating a public shop, configure an appropriate production server, HTTPS, private secrets, backup retention, login throttling, payment and shipping providers, and a privacy policy.

Historical baseline tags preserve earlier project behavior, including demo credentials and security limitations that were removed in later versions. Use the current main branch rather than historical tags for development.

Upgrades preserve existing accounts and do not reset their passwords. If an installation was initialized with historical demo credentials, change those credentials before exposing it outside local development. Fresh installations create no accounts automatically.

Required security properties include CSRF validation on state changes, hashed passwords, order-owner access checks, idempotent checkout, conditional stock updates, and a separate test database.
