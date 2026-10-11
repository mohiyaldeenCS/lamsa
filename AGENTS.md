# Repository Guidelines

## Project Structure & Module Organization

The Flask application factory lives in `perfume_project/app.py`. It initializes CSRF, SQLAlchemy, additive migrations, routes, and catalog commands. `models.py` owns persistence; `catalog.py` defines shared metadata vocabularies and loads `data/catalog.json`. Keep catalog imports independent of model initialization; command functions import models locally to avoid circular imports.

`migrations.py` upgrades existing SQLite databases without replacing tables. Preserve product identities and order-item snapshots when changing catalog behavior. Jinja templates render Arabic RTL pages, with local CSS, JavaScript, fonts, and allowlisted images. The root `app.py` only launches the actual application.

## Build, Test, and Development Commands

Install dependencies with `python -m pip install -r perfume_project/requirements.txt`. Run these commands from `perfume_project/`:

- `python init_db.py`: create or upgrade the schema and add missing sample products.
- `python -m flask --app app:create_app create-admin`: explicitly create an administrator.
- `python -m flask --app app:create_app run`: start the local server.
- `python -m unittest discover -s tests -v`: run the complete suite.
- `python -m unittest discover -s tests -p test_catalog.py -v`: run catalog tests only.

## Coding Style & Naming Conventions

Follow `.editorconfig`: UTF-8, LF endings, four-space Python indentation, and two-space YAML/JSON indentation. User-facing storefront copy is Arabic; repository documentation, commit messages, and source comments are English. No formatter or linter is currently configured.

## Testing Guidelines

The `unittest` suite uses disposable databases. Never point tests at `instance/perfumes.db`. Preserve coverage of stock transactions, duplicate checkout, authorization, CSRF, legacy migrations, repeat-safe seeding, and rendered templates. CI exercises Python 3.11 and 3.13.

## Commit & Pull Request Guidelines

Use focused commits such as `feat(catalog): ...`, `test(commerce): ...`, and `docs: ...`. Keep feature branches and non-squash merges so individual changes remain visible. Complete the pull-request template's validation and compatibility sections. Do not commit database files, backups, session secrets, virtual environments, or generated test output.
