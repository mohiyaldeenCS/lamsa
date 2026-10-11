# Operations

Run commands below from `perfume_project/` with the project virtual environment active.

## Local start

```sh
python init_db.py
python -m flask --app app:create_app create-admin
python -m flask --app app:create_app run --host 127.0.0.1 --port 5000
```

Seeding is repeatable and does not overwrite existing product inventory or create known-password accounts. The administrator command rejects an existing username instead of changing that account.

## Backups

The private `instance/` directory contains the database, local session secret, and automatically created migration backups. Keep this directory outside Git. Stop the application before copying a database manually, or use SQLite's online backup API. Store backups privately and verify restore procedures before a deployment.

To restore, stop the server and preserve the current database before replacing it with a selected backup. Database restoration can change order and stock state; verify both together before resuming service.

## Release validation

- Run the complete isolated test suite.
- Verify a fresh database and an upgrade from the previous schema.
- Check catalog filters and mobile navigation.
- Review staged files and all outgoing commits for private data.
- Verify author and committer identity and the GitHub Actions result.

A release packages source code and illustrative assets. It does not deploy a production service or enable real payment, delivery, or email integrations.
