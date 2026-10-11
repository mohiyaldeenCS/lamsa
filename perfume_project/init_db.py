from app import create_app
from models import db, User, Perfume
app = create_app()
app.app_context().push()

def seed():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        db.session.add(User(username='admin', password='admin', is_admin=True))
    if not User.query.filter_by(username='user1').first():
        db.session.add(User(username='user1', password='user1', is_admin=False))
    if Perfume.query.count() == 0:
        perfumes = [
            {'name':'Rose Essence','brand':'Bloom','description':'Floral and fresh','price':50.0,'stock':15},
            {'name':'Ocean Breeze','brand':'Wave','description':'Fresh aquatic scent','price':45.0,'stock':20},
            {'name':'Night Musk','brand':'Dark Night','description':'Deep musk fragrance','price':70.0,'stock':10},
            {'name':'Vanilla Sky','brand':'SweetNotes','description':'Warm vanilla aroma','price':55.0,'stock':12},
            {'name':'Citrus Spark','brand':'FreshLife','description':'Energetic citrus','price':40.0,'stock':18}
        ]
        for p in perfumes:
            db.session.add(Perfume(**p))
    db.session.commit()
    print('DB initialized and seeded.')

if __name__ == '__main__':
    seed()
