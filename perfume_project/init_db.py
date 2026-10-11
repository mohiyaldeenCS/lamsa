from app import create_app
from models import db, User, Perfume
from werkzeug.security import generate_password_hash

app = create_app()
app.app_context().push()

def seed():
    db.create_all()
    # Create admin and sample user
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', password=generate_password_hash('admin'), is_admin=True)
        db.session.add(admin)
    if not User.query.filter_by(username='user1').first():
        u = User(username='user1', password=generate_password_hash('user1'), is_admin=False)
        db.session.add(u)
    
    # Seed perfumes
    if Perfume.query.count() == 0:
        perfumes = [
            {'name':'جوهر الورد','brand':'لَمْسَة','description':'ورد طائفي، زعفران، مسك أبيض','price':189.0, 'stock':15},
            {'name':'نسيم البحر','brand':'أمواج','description':'برغموت، ملح البحر، أخشاب طافية','price':165.0, 'stock':20},
            {'name':'مسك الليل','brand':'سُرى','description':'مسك داكن، عنبر، عود معتّق','price':245.0, 'stock':10},
            {'name':'سماء الفانيلا','brand':'نغم','description':'فانيلا مدغشقر، تونكا، صندل','price':210.0, 'stock':12},
            {'name':'وهج الحمضيات','brand':'رَونق','description':'برغموت، ليمون، زهر البرتقال','price':149.0, 'stock':18}
        ]
        for p in perfumes:
            db.session.add(Perfume(**p))
    db.session.commit()
    print('DB initialized and seeded.')

if __name__ == '__main__':
    seed()
