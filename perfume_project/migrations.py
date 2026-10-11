"""Add catalog metadata to existing SQLite stores without rebuilding tables."""
from datetime import datetime
from contextlib import closing
from pathlib import Path
import sqlite3

from sqlalchemy import inspect, text

from catalog import load_catalog
from models import db


PRODUCT_COLUMNS = {
    'sku': 'VARCHAR(40)',
    'category': "VARCHAR(24) NOT NULL DEFAULT 'woody'",
    'audience': "VARCHAR(16) NOT NULL DEFAULT 'unisex'",
    'volume_ml': 'INTEGER NOT NULL DEFAULT 100',
    'image_key': "VARCHAR(24) NOT NULL DEFAULT 'musk'",
    'featured': 'BOOLEAN NOT NULL DEFAULT 0',
}
ITEM_COLUMNS = {name: definition for name, definition in PRODUCT_COLUMNS.items()
                if name not in ('sku', 'featured')}


def backup_database(engine, label='before-catalog'):
    """Use SQLite's consistent backup API, including any WAL contents."""
    filename = engine.url.database
    if engine.dialect.name != 'sqlite' or not filename or filename == ':memory:':
        return None
    path = Path(filename)
    if not path.is_file():
        return None
    backup_path = path.with_name(path.name + '.' + label + '-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.bak')
    with closing(sqlite3.connect(str(path))) as source, closing(sqlite3.connect(str(backup_path))) as target:
        source.backup(target)
    return backup_path


def ensure_schema(app):
    """Create missing tables and add only missing columns, safely on repeat runs."""
    engine = db.engine
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    missing = {}
    for table, desired in (('perfume', PRODUCT_COLUMNS), ('order_item', ITEM_COLUMNS)):
        present = {column['name'] for column in inspector.get_columns(table)} if table in tables else set()
        missing[table] = set(desired) - present if table in tables else set()
    needs_change = not {'perfume', 'user', 'order', 'order_item'}.issubset(tables) or any(missing.values())
    if needs_change and not app.testing:
        backup = backup_database(engine)
        if backup:
            app.logger.info('Database backed up to %s', backup)
    db.create_all()
    if not any(missing.values()):
        return
    if engine.dialect.name != 'sqlite':
        raise RuntimeError('Existing non-SQLite stores require an explicit catalog migration.')
    records = {record['name']: record for record in load_catalog()}
    with engine.connect() as connection:
        connection.exec_driver_sql('BEGIN IMMEDIATE')
        try:
            # Reinspect inside the write lock so concurrent startup is harmless.
            actual_missing = {}
            for table, desired in (('perfume', PRODUCT_COLUMNS), ('order_item', ITEM_COLUMNS)):
                present = {column['name'] for column in inspect(connection).get_columns(table)}
                actual_missing[table] = set(desired) - present
                for name in actual_missing[table]:
                    connection.exec_driver_sql(f'ALTER TABLE {table} ADD COLUMN {name} {desired[name]}')
            if actual_missing['perfume']:
                allocated_skus = {row[0] for row in connection.execute(text('SELECT sku FROM perfume WHERE sku IS NOT NULL'))}
                for row in connection.execute(text('SELECT id, name FROM perfume ORDER BY id')).mappings().all():
                    known = records.get(row['name'], {})
                    values = {name: known.get(name, {'sku': f"LM-LEGACY-{row['id']}",
                              'category': 'woody', 'audience': 'unisex', 'volume_ml': 100,
                              'image_key': 'musk', 'featured': False}[name])
                              for name in actual_missing['perfume']}
                    if 'sku' in values:
                        candidate = values['sku']
                        if candidate in allocated_skus:
                            candidate = f"LM-LEGACY-{row['id']}"
                        while candidate in allocated_skus:
                            candidate += '-X'
                        values['sku'] = candidate
                        allocated_skus.add(candidate)
                    assignments = ', '.join(f'{name} = :{name}' for name in values)
                    connection.execute(text(f'UPDATE perfume SET {assignments} WHERE id = :pid'),
                                       {**values, 'pid': row['id']})
                connection.exec_driver_sql('CREATE UNIQUE INDEX IF NOT EXISTS ix_perfume_sku ON perfume(sku)')
                connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_perfume_category ON perfume(category)')
                connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_perfume_audience ON perfume(audience)')
            for name in actual_missing['order_item']:
                connection.exec_driver_sql(f'''UPDATE order_item SET {name} = COALESCE(
                    (SELECT {name} FROM perfume WHERE perfume.id = order_item.perfume_id), {name})''')
            connection.commit()
        except Exception:
            connection.rollback()
            raise
