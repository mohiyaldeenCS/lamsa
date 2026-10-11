"""Initialize the schema and add missing sample products without creating users."""
from app import create_app
from catalog import seed_catalog
from models import Perfume


def seed():
    app = create_app()
    with app.app_context():
        added = seed_catalog()
        print(f'Added {added} sample products. Catalog total: {Perfume.query.count()}.')
        print('No accounts were created or changed. Use flask --app app:create_app create-admin explicitly.')


if __name__ == '__main__':
    seed()
