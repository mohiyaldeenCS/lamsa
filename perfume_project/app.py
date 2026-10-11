from flask import Flask, render_template, redirect, url_for, flash, request, session
from config import Config
from models import db, User, Perfume
from forms import RegisterForm, LoginForm, PerfumeForm
import os

def create_app():
    app = Flask(__name__, static_folder='static', template_folder='templates')
    app.config.from_object(Config)
    db.init_app(app)
    os.makedirs(os.path.join(app.root_path, 'instance'), exist_ok=True)
    def current_user():
        if 'user_id' in session:
            return User.query.get(session['user_id'])
        return None
    @app.route('/')
    def home():
        recent_perfumes = Perfume.query.order_by(Perfume.created_at.desc()).limit(3).all()
        return render_template('home.html', perfumes=recent_perfumes)
    @app.route('/about')
    def about():
        info = {'author':'Student','purpose':'Perfume e-commerce mini project'}
        return render_template('about.html', info=info)
    @app.route('/register', methods=['GET','POST'])
    def register():
        form = RegisterForm()
        if form.validate_on_submit():
            if User.query.filter_by(username=form.username.data).first():
                flash('Username exists','danger')
                return redirect(url_for('register'))
            u = User(username=form.username.data, password=form.password.data, is_admin=False)
            db.session.add(u)
            db.session.commit()
            flash('Registered successfully','success')
            return redirect(url_for('login'))
        return render_template('register.html', form=form)
    @app.route('/login', methods=['GET','POST'])
    def login():
        form = LoginForm()
        if form.validate_on_submit():
            user = User.query.filter_by(username=form.username.data, password=form.password.data).first()
            if user:
                session['user_id'] = user.id
                session['username'] = user.username
                session['is_admin'] = user.is_admin
                flash('Logged in','success')
                return redirect(url_for('profile'))
            flash('Invalid credentials','danger')
        return render_template('login.html', form=form)
    @app.route('/logout')
    def logout():
        session.clear()
        flash('Logged out','info')
        return redirect(url_for('home'))
    @app.route('/profile')
    def profile():
        user = current_user()
        if not user:
            flash('Please login','warning')
            return redirect(url_for('login'))
        return render_template('profile.html', user=user)
    @app.route('/perfumes')
    def perfumes():
        perfumes = Perfume.query.all()
        return render_template('perfumes.html', perfumes=perfumes)
    @app.route('/perfumes/<int:pid>')
    def perfume_detail(pid):
        perfume = Perfume.query.get(pid)
        if not perfume:
            return render_template('error.html', message='Perfume not found')
        return render_template('perfume_detail.html', perfume=perfume)
    @app.route('/add_perfume', methods=['GET','POST'])
    def add_perfume():
        user = current_user()
        if not user or not user.is_admin:
            flash('Admin only','danger')
            return redirect(url_for('home'))
        form = PerfumeForm()
        if form.validate_on_submit():
            p = Perfume(name=form.name.data, brand=form.brand.data,
                        description=form.description.data, price=form.price.data,
                        stock=form.stock.data)
            db.session.add(p)
            db.session.commit()
            flash('Perfume added','success')
            return redirect(url_for('perfumes'))
        return render_template('add_perfume.html', form=form)
    @app.route('/cart')
    def cart():
        cart_ids = session.get('cart', [])
        items = Perfume.query.filter(Perfume.id.in_(cart_ids)).all() if cart_ids else []
        total = sum(p.price for p in items)
        return render_template('cart.html', items=items, total=total)
    @app.context_processor
    def inject_user():
        return dict(logged_in = 'user_id' in session, current_username = session.get('username'))
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)
