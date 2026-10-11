"""Catalog vocabulary, deterministic seed data, and explicit setup commands."""
import json
from pathlib import Path

import click
from werkzeug.security import generate_password_hash


CATEGORIES = {'floral': 'زهري', 'fresh': 'منعش', 'woody': 'خشبي',
              'oriental': 'شرقي', 'gourmand': 'دافئ وحلو'}
AUDIENCES = {'unisex': 'للجميع', 'women': 'نسائي', 'men': 'رجالي'}
IMAGES = {
    'rose': ('ورد ناعم', 'perfume-rose.png'),
    'ocean': ('انتعاش البحر', 'perfume-ocean.png'),
    'musk': ('أخشاب ومسك', 'perfume-musk.png'),
    'vanilla': ('دفء الفانيلا', 'perfume-vanilla.png'),
    'citrus': ('حمضيات مشرقة', 'perfume-citrus.png'),
    'campaign': ('المجموعة الطبيعية', 'hero-campaign.png'),
}
VOLUMES = (30, 50, 75, 100, 150)
FILTER_KEYS = ('q', 'brand', 'category', 'audience', 'volume', 'price',
               'min_price', 'max_price', 'availability', 'sort')


def load_catalog():
    path = Path(__file__).parent / 'data' / 'catalog.json'
    records = json.loads(path.read_text(encoding='utf-8'))
    seen_skus, seen_names = set(), set()
    for record in records:
        if record['sku'] in seen_skus or record['name'] in seen_names:
            raise ValueError('Catalog seed contains a duplicate identity.')
        if (record['category'] not in CATEGORIES or record['audience'] not in AUDIENCES
                or record['image_key'] not in IMAGES or record['volume_ml'] not in VOLUMES):
            raise ValueError('Catalog seed contains invalid metadata.')
        seen_skus.add(record['sku'])
        seen_names.add(record['name'])
    return records


def image_filename(key):
    """Resolve only allowlisted local assets, including for historical rows."""
    return 'images/' + IMAGES.get(key, IMAGES['musk'])[1]


def seed_catalog():
    """Insert missing sample products without changing any existing inventory."""
    from models import Perfume, db
    existing_skus = {row[0] for row in db.session.query(Perfume.sku)}
    existing_names = {row[0] for row in db.session.query(Perfume.name)}
    missing = [record for record in load_catalog()
               if record['sku'] not in existing_skus and record['name'] not in existing_names]
    if missing:
        from flask import current_app
        from migrations import backup_database
        if not current_app.testing:
            backup = backup_database(db.engine, 'before-seed')
            if backup:
                current_app.logger.info('Database backed up to %s', backup)
    added = 0
    for record in missing:
        db.session.add(Perfume(**record))
        existing_skus.add(record['sku'])
        existing_names.add(record['name'])
        added += 1
    db.session.commit()
    return added


def register_catalog_commands(app):
    @app.cli.command('seed-catalog')
    def seed_command():
        """Add missing illustrative sample products; preserve existing records."""
        from models import Perfume
        added = seed_catalog()
        click.echo(f'Added {added} products. Catalog total: {Perfume.query.count()}.')

    @app.cli.command('create-admin')
    @click.option('--username', prompt=True, envvar='LAMSA_ADMIN_USERNAME')
    @click.option('--password', prompt=True, hide_input=True,
                  confirmation_prompt=True, envvar='LAMSA_ADMIN_PASSWORD')
    def create_admin_command(username, password):
        """Create an administrator explicitly, without modifying existing users."""
        from models import User, db
        username = username.strip()
        if not 3 <= len(username) <= 80:
            raise click.ClickException('Username must contain 3 to 80 characters.')
        if not 12 <= len(password) <= 128:
            raise click.ClickException('Password must contain 12 to 128 characters.')
        if User.query.filter(db.func.lower(User.username) == username.lower()).first():
            raise click.ClickException('Username already exists; no account was changed.')
        db.session.add(User(username=username, password=generate_password_hash(password), is_admin=True))
        db.session.commit()
        click.echo('Administrator created.')
