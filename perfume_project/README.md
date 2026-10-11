# LAMSA application

See the [repository README](../README.md) for setup, feature descriptions, screenshots, and project documentation.

From this directory with the virtual environment active:

```sh
python -m pip install -r requirements.txt
python init_db.py
python -m flask --app app:create_app create-admin
python -m flask --app app:create_app run
```

Run tests with `python -m unittest discover -s tests -v`. Test databases are isolated from the local store.

The `instance/` directory is private local state and must never be committed. Catalog seeding preserves existing data and never creates default-password users. Checkout creates local demonstration orders only; no payment or shipping provider is connected.
