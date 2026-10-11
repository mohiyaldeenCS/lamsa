from functools import wraps
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import os
import secrets
from urllib.parse import urlsplit

from flask import (Flask, abort, flash, redirect, render_template, request,
                   session, url_for)
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import or_, update
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from config import Config, local_secret_key
from catalog import AUDIENCES, CATEGORIES, FILTER_KEYS, IMAGES, VOLUMES, register_catalog_commands
from forms import (CheckoutForm, EmptyForm, FragranceFinderForm, LoginForm,
                   ORDER_STATUS_LABELS, OrderStatusForm, PerfumeForm, RegisterForm)
from models import Order, OrderItem, Perfume, User, db
from migrations import ensure_schema


def create_app(test_config=None):
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)
    if not app.config.get('SECRET_KEY'):
        app.config['SECRET_KEY'] = local_secret_key()
    db.init_app(app)
    CSRFProtect(app)
    os.makedirs(os.path.join(app.root_path, "instance"), exist_ok=True)

    # Startup migrates metadata but never seeds inventory or creates accounts.
    with app.app_context():
        ensure_schema(app)
    register_catalog_commands(app)

    def current_user():
        user_id = session.get("user_id")
        return db.session.get(User, user_id) if user_id else None

    def admin_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = current_user()
            if not user or not user.is_admin:
                flash("هذه الصفحة مخصصة لإدارة المتجر.", "danger")
                return redirect(url_for("login", next=request.path))
            return view(*args, **kwargs)
        return wrapped

    def clean_cart():
        cart = session.get("cart", {})
        if isinstance(cart, list):
            cart = {str(pid): 1 for pid in cart}
        if not isinstance(cart, dict):
            return {}
        cleaned = {}
        for key, value in cart.items():
            try:
                pid, quantity = int(key), int(value)
            except (ValueError, TypeError, OverflowError):
                continue
            if pid > 0 and quantity > 0:
                cleaned[str(pid)] = min(quantity, 1000000)
        return cleaned

    def login_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user():
                flash("سجّل الدخول لإكمال طلبك ومتابعته.", "info")
                return redirect(url_for('login', next=request.path))
            return view(*args, **kwargs)
        return wrapped

    def local_target(target, default):
        if not target or any(ord(char) < 32 for char in target) or '\\' in target:
            return url_for(default)
        try:
            parsed = urlsplit(target)
        except ValueError:
            return url_for(default)
        if parsed.scheme or parsed.netloc:
            origin = urlsplit(request.host_url)
            if parsed.scheme != origin.scheme or parsed.netloc != origin.netloc:
                return url_for(default)
        path = parsed.path or '/'
        if not path.startswith('/') or path.startswith('//'):
            return url_for(default)
        return path + ('?' + parsed.query if parsed.query else '')

    def money(value):
        return Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def cart_summary(normalize=False):
        items, subtotal, corrected, unavailable = [], Decimal('0.00'), {}, False
        for pid, requested in clean_cart().items():
            perfume = db.session.get(Perfume, int(pid))
            if not perfume or perfume.stock < 1:
                unavailable = True
                continue
            quantity = min(requested, perfume.stock)
            unavailable = unavailable or quantity != requested
            corrected[pid] = quantity
            line_total = money(perfume.price) * quantity
            items.append({'perfume': perfume, 'quantity': quantity, 'line_total': line_total})
            subtotal += line_total
        if normalize and session.get('cart', {}) != corrected:
            session['cart'] = corrected
        return {'items': items, 'subtotal': subtotal, 'shipping': Decimal('0.00'), 'total': subtotal}, unavailable

    @app.template_filter("sar")
    def sar(value):
        amount = money(value)
        return f"{amount:,.0f} ر.س" if amount == amount.to_integral_value() else f"{amount:,.2f} ر.س"

    @app.route("/")
    def home():
        featured = Perfume.query.order_by(Perfume.featured.desc(), Perfume.id.asc()).limit(5).all()
        return render_template("home.html", perfumes=featured)

    @app.route("/about")
    def about():
        return render_template("about.html")

    @app.route("/register", methods=["GET", "POST"])
    def register():
        form = RegisterForm()
        if form.validate_on_submit():
            username = form.username.data.strip()
            if User.query.filter(db.func.lower(User.username) == username.lower()).first():
                flash("اسم المستخدم مستخدم بالفعل، جرّب اسمًا آخر.", "danger")
            else:
                user = User(username=username, password=generate_password_hash(form.password.data), is_admin=False)
                db.session.add(user)
                try:
                    db.session.commit()
                except IntegrityError:
                    db.session.rollback()
                    flash("اسم المستخدم مستخدم بالفعل، جرّب اسمًا آخر.", "danger")
                    return render_template("register.html", form=form)
                flash("أهلًا بك في لَمْسَة، تم إنشاء حسابك بنجاح.", "success")
                return redirect(url_for("login"))
        return render_template("register.html", form=form)

    @app.route("/login", methods=["GET", "POST"])
    def login():
        form = LoginForm()
        if form.validate_on_submit():
            user = User.query.filter_by(username=form.username.data.strip()).first()
            valid = False
            if user:
                try:
                    valid = check_password_hash(user.password, form.password.data)
                except (ValueError, TypeError):
                    valid = False
                # Only migrate genuinely legacy plaintext. Never accept an
                # encoded password hash itself as a login credential.
                legacy_plaintext = '$' not in user.password and not user.password.startswith(('scrypt:', 'pbkdf2:'))
                if not valid and legacy_plaintext and secrets.compare_digest(user.password.encode(), form.password.data.encode()):
                    valid = True
                    user.password = generate_password_hash(form.password.data)
                    db.session.commit()
            if valid:
                session["user_id"] = user.id
                session["username"] = user.username
                session["is_admin"] = bool(user.is_admin)
                session.pop('checkout_token', None)
                flash(f"مرحبًا بعودتك، {user.username}.", "success")
                target = request.args.get("next")
                return redirect(local_target(target, 'profile'))
            flash("اسم المستخدم أو كلمة المرور غير صحيحة.", "danger")
        return render_template("login.html", form=form)

    @app.post("/logout")
    def logout():
        form = EmptyForm()
        if not form.validate_on_submit():
            abort(400)
        cart, wishlist = session.get("cart"), session.get("wishlist")
        session.clear()
        if cart:
            session["cart"] = cart
        if wishlist:
            session["wishlist"] = wishlist
        flash("تم تسجيل خروجك بأمان.", "info")
        return redirect(url_for("home"))

    @app.route("/profile")
    def profile():
        user = current_user()
        if not user:
            flash("سجّل الدخول للوصول إلى حسابك.", "warning")
            return redirect(url_for("login", next=request.path))
        orders = Order.query.filter_by(user_id=user.id).order_by(Order.created_at.desc()).all()
        return render_template("profile.html", user=user, orders=orders)

    @app.route("/perfumes")
    def perfumes():
        query = Perfume.query
        search = request.args.get("q", "").strip()
        brand = request.args.get("brand", "").strip()
        price = request.args.get("price", "")
        availability = request.args.get("availability", "")
        sort = request.args.get("sort", "newest")
        category = request.args.get('category', '')
        audience = request.args.get('audience', '')
        volume = request.args.get('volume', '')
        if search:
            pattern = f"%{search}%"
            query = query.filter(or_(Perfume.name.ilike(pattern), Perfume.brand.ilike(pattern), Perfume.description.ilike(pattern), Perfume.sku.ilike(pattern)))
        if brand:
            query = query.filter(Perfume.brand == brand)
        if category:
            query = query.filter(Perfume.category == category)
        if audience:
            query = query.filter(Perfume.audience == audience)
        if volume:
            try:
                query = query.filter(Perfume.volume_ml == int(volume))
            except ValueError:
                abort(400)
        if price == "under175": query = query.filter(Perfume.price < 175)
        elif price == "175-225": query = query.filter(Perfume.price >= 175, Perfume.price <= 225)
        elif price == "over225": query = query.filter(Perfume.price > 225)
        price_bounds = {}
        for key in ('min_price', 'max_price'):
            raw = request.args.get(key, '').strip()
            if raw:
                try:
                    value = Decimal(raw)
                    if not value.is_finite() or not 0 <= value <= 1000000:
                        abort(400)
                except InvalidOperation:
                    abort(400)
                price_bounds[key] = value
        if len(price_bounds) == 2 and price_bounds['min_price'] > price_bounds['max_price']:
            abort(400)
        if 'min_price' in price_bounds:
            query = query.filter(Perfume.price >= price_bounds['min_price'])
        if 'max_price' in price_bounds:
            query = query.filter(Perfume.price <= price_bounds['max_price'])
        if availability == "available": query = query.filter(Perfume.stock > 0)
        order_map = {"price_asc": Perfume.price.asc(), "price_desc": Perfume.price.desc(), "name": Perfume.name.asc(), "newest": Perfume.created_at.desc()}
        page = max(1, min(request.args.get('page', 1, type=int) or 1, 1000000))
        pagination = query.order_by(order_map.get(sort, Perfume.created_at.desc()), Perfume.id.asc()).paginate(page=page, per_page=12, error_out=False)
        filters = {key: request.args.get(key) for key in FILTER_KEYS if request.args.get(key)}
        def page_url(number):
            return url_for('perfumes', **filters, page=number)
        brands = [row[0] for row in db.session.query(Perfume.brand).filter(Perfume.brand.isnot(None)).distinct().order_by(Perfume.brand)]
        return render_template("perfumes.html", perfumes=pagination.items, brands=brands,
                               pagination=pagination, page_url=page_url, filters=filters)

    @app.route("/perfumes/<int:pid>")
    def perfume_detail(pid):
        perfume = db.session.get(Perfume, pid)
        if not perfume: abort(404)
        similar = Perfume.query.filter(Perfume.id != pid).order_by((Perfume.category == perfume.category).desc(), Perfume.id.asc()).limit(3).all()
        notes = [part.strip() for part in (perfume.description or "عنبر، مسك، أخشاب دافئة").replace("،", ",").split(",") if part.strip()][:4]
        return render_template("perfume_detail.html", perfume=perfume, similar=similar, notes=notes, wished=pid in session.get("wishlist", []))

    @app.post("/cart/add/<int:pid>")
    def add_to_cart(pid):
        form = EmptyForm()
        perfume = db.session.get(Perfume, pid)
        if not form.validate_on_submit(): abort(400)
        if not perfume: abort(404)
        if perfume.stock < 1:
            flash("هذا العطر غير متوفر حاليًا.", "warning")
            return redirect(local_target(request.referrer, 'perfumes'))
        try: quantity = max(1, int(request.form.get("quantity", 1)))
        except ValueError: quantity = 1
        cart = clean_cart()
        cart[str(pid)] = min(perfume.stock, cart.get(str(pid), 0) + quantity)
        session["cart"] = cart
        flash(f"أُضيف «{perfume.name}» إلى حقيبتك.", "success")
        return redirect(local_target(request.referrer, 'cart'))

    @app.route("/cart")
    def cart():
        summary, changed = cart_summary(normalize=True)
        if changed:
            flash('حُدّثت الحقيبة حسب المخزون المتاح. راجع الكميات قبل المتابعة.', 'warning')
        return render_template("cart.html", **summary)

    @app.post("/cart/update")
    def update_cart():
        form = EmptyForm()
        if not form.validate_on_submit(): abort(400)
        cart_data = clean_cart()
        for pid in list(cart_data):
            perfume = db.session.get(Perfume, int(pid))
            try: quantity = int(request.form.get(f"quantity_{pid}", cart_data[pid]))
            except ValueError: quantity = cart_data[pid]
            if quantity <= 0 or not perfume or perfume.stock < 1: cart_data.pop(pid, None)
            else: cart_data[pid] = min(quantity, perfume.stock)
        session["cart"] = cart_data
        flash("تم تحديث حقيبة التسوق.", "success")
        return redirect(url_for("cart"))

    @app.post("/cart/remove/<int:pid>")
    def remove_from_cart(pid):
        form = EmptyForm()
        if not form.validate_on_submit(): abort(400)
        cart_data = clean_cart(); cart_data.pop(str(pid), None); session["cart"] = cart_data
        flash("تمت إزالة العطر من الحقيبة.", "info")
        return redirect(url_for("cart"))

    @app.post("/cart/clear")
    def clear_cart():
        form = EmptyForm()
        if not form.validate_on_submit(): abort(400)
        session.pop("cart", None); flash("تم إفراغ حقيبة التسوق.", "info")
        return redirect(url_for("cart"))

    @app.post("/wishlist/<int:pid>")
    def toggle_wishlist(pid):
        form = EmptyForm()
        if not form.validate_on_submit(): abort(400)
        if not db.session.get(Perfume, pid): abort(404)
        wishlist = session.get("wishlist", [])
        if pid in wishlist: wishlist.remove(pid); flash("أزيل العطر من المفضلة.", "info")
        else: wishlist.append(pid); flash("حُفظ العطر في المفضلة.", "success")
        session["wishlist"] = wishlist
        return redirect(local_target(request.referrer, 'wishlist'))

    @app.get('/wishlist')
    def wishlist():
        ids = [pid for pid in session.get('wishlist', []) if isinstance(pid, int)]
        products = Perfume.query.filter(Perfume.id.in_(ids)).all() if ids else []
        session['wishlist'] = [product.id for product in products]
        return render_template('wishlist.html', perfumes=products)

    @app.route('/fragrance-finder', methods=['GET', 'POST'])
    def fragrance_finder():
        form = FragranceFinderForm()
        recommendations, submitted = [], False
        if form.validate_on_submit():
            submitted = True
            keywords = {
                'floral': ('ورد', 'زهر', 'ياسمين', 'rose', 'floral'),
                'fresh': ('بحر', 'برغموت', 'ليمون', 'حمض', 'نعناع', 'citrus', 'fresh'),
                'woody': ('عود', 'أخشاب', 'مسك', 'عنبر', 'صندل', 'wood', 'musk'),
                'gourmand': ('فانيلا', 'تونكا', 'كراميل', 'vanilla', 'amber'),
                'oriental': ('عود', 'عنبر', 'زعفران', 'بخور', 'oud', 'amber'),
                'any': (),
            }
            def relevance(perfume):
                text = f'{perfume.name} {perfume.description or ""}'.lower()
                score = sum(5 for word in keywords[form.family.data] if word in text)
                if perfume.category == form.family.data:
                    score += 30
                bright = any(word in text for word in keywords['fresh'] + keywords['floral'])
                rich = any(word in text for word in ('عود', 'عنبر', 'داكن', 'فانيلا', 'tonka', 'amber'))
                if form.occasion.data == 'everyday' and bright: score += 2
                if form.occasion.data == 'evening' and rich: score += 2
                if form.occasion.data == 'gift' and perfume.price <= 225: score += 1
                if form.intensity.data == 'soft' and bright: score += 2
                if form.intensity.data == 'bold' and rich: score += 2
                if form.intensity.data == 'balanced' and bright and rich: score += 2
                return (-score, perfume.price, perfume.id)
            recommendations = sorted(Perfume.query.filter(Perfume.stock > 0).all(), key=relevance)[:3]
        return render_template('fragrance_finder.html', form=form, recommendations=recommendations, submitted=submitted)

    @app.route('/checkout', methods=['GET', 'POST'])
    @login_required
    def checkout():
        form = CheckoutForm()
        user = current_user()
        if form.validate_on_submit():
            existing = Order.query.filter_by(checkout_token=form.checkout_token.data, user_id=user.id).first()
            if existing:
                return redirect(url_for('order_detail', order_id=existing.id))
            expected_token = session.get('checkout_token', '')
            if not expected_token or not secrets.compare_digest(expected_token, form.checkout_token.data):
                flash('انتهت صلاحية نموذج الطلب. راجع الحقيبة وحاول مجددًا.', 'warning')
                return redirect(url_for('checkout'))
            summary, changed = cart_summary()
            if changed or not summary['items']:
                flash('تغيّر المخزون. راجع حقيبتك قبل تأكيد الطلب.', 'warning')
                return redirect(url_for('cart'))
            order = Order(user_id=user.id, checkout_token=form.checkout_token.data,
                          full_name=form.full_name.data.strip(), phone=form.phone.data.strip(),
                          city=form.city.data.strip(), address=form.address.data.strip(),
                          note=(form.note.data or '').strip(), subtotal=summary['subtotal'],
                          shipping=summary['shipping'], total=summary['total'])
            try:
                db.session.add(order)
                # A conditional database update, rather than a read-and-write,
                # prevents overlapping checkouts from overselling a product.
                for item in summary['items']:
                    perfume, quantity = item['perfume'], item['quantity']
                    result = db.session.execute(update(Perfume).where(
                        Perfume.id == perfume.id, Perfume.stock >= quantity,
                        Perfume.price == perfume.price
                    ).values(stock=Perfume.stock - quantity).execution_options(synchronize_session=False))
                    if result.rowcount != 1:
                        db.session.rollback()
                        flash('تغيّر مخزون أحد العطور أو سعره. راجع حقيبتك ثم حاول مجددًا.', 'warning')
                        return redirect(url_for('cart'))
                    order.items.append(OrderItem(perfume_id=perfume.id, name=perfume.name,
                        brand=perfume.brand or '', unit_price=money(perfume.price),
                        quantity=quantity, line_total=item['line_total'], image_key=perfume.image_key,
                        volume_ml=perfume.volume_ml, category=perfume.category, audience=perfume.audience))
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                existing = Order.query.filter_by(checkout_token=form.checkout_token.data, user_id=user.id).first()
                if not existing:
                    raise
                return redirect(url_for('order_detail', order_id=existing.id))
            session.pop('cart', None)
            session.pop('checkout_token', None)
            flash('سُجّل طلبك التجريبي. لم يتم تحصيل أي مبلغ أو إنشاء شحنة.', 'success')
            return redirect(url_for('order_detail', order_id=order.id))
        summary, changed = cart_summary()
        if changed or not summary['items']:
            flash('راجع حقيبتك والكميات المتاحة قبل إكمال الطلب.', 'info')
            return redirect(url_for('cart'))
        if 'checkout_token' not in session:
            session['checkout_token'] = secrets.token_urlsafe(32)
        form.checkout_token.data = session['checkout_token']
        return render_template('checkout.html', form=form, **summary)

    @app.get('/orders/<int:order_id>')
    @login_required
    def order_detail(order_id):
        order = db.session.get(Order, order_id) or abort(404)
        user = current_user()
        if order.user_id != user.id and not user.is_admin:
            abort(404)
        return render_template('order_detail.html', order=order)

    @app.get('/admin/orders')
    @admin_required
    def admin_orders():
        orders = Order.query.order_by(Order.created_at.desc()).all()
        return render_template('admin_orders.html', orders=orders, status_form=OrderStatusForm())

    @app.post('/admin/orders/<int:order_id>/status')
    @admin_required
    def update_order_status(order_id):
        form = OrderStatusForm()
        if not form.validate_on_submit(): abort(400)
        order = db.session.get(Order, order_id) or abort(404)
        previous, desired = order.status, form.status.data
        allowed = {
            'pending': {'confirmed', 'cancelled'},
            'confirmed': {'preparing', 'cancelled'},
            'preparing': {'completed', 'cancelled'},
            'completed': set(), 'cancelled': set(),
        }
        if desired == previous:
            return redirect(url_for('admin_orders'))
        if desired not in allowed.get(previous, set()):
            flash('هذا الانتقال غير متاح. الطلب المكتمل أو الملغي نهائي.', 'warning')
            return redirect(url_for('admin_orders'))
        result = db.session.execute(update(Order).where(Order.id == order.id, Order.status == previous)
            .values(status=desired).execution_options(synchronize_session=False))
        if result.rowcount != 1:
            db.session.rollback()
            flash('تغيّرت حالة الطلب بالفعل. حدّث الصفحة.', 'warning')
            return redirect(url_for('admin_orders'))
        if desired == 'cancelled':
            for item in order.items:
                db.session.execute(update(Perfume).where(Perfume.id == item.perfume_id)
                    .values(stock=Perfume.stock + item.quantity).execution_options(synchronize_session=False))
        db.session.commit()
        flash('تم تحديث حالة الطلب التجريبي.', 'success')
        return redirect(url_for('admin_orders'))

    @app.route("/admin")
    @admin_required
    def admin():
        products = Perfume.query.order_by(Perfume.created_at.desc()).all()
        return render_template("admin.html", products=products, user_count=User.query.count(), stock_total=sum(p.stock for p in products), low_stock=[p for p in products if p.stock <= 5])

    @app.route("/admin/perfumes/add", methods=["GET", "POST"])
    @app.route("/add_perfume", methods=["GET", "POST"])
    @admin_required
    def add_perfume():
        form = PerfumeForm()
        if form.validate_on_submit():
            perfume = Perfume()
            form.populate_obj(perfume)
            perfume.price = float(money(form.price.data))
            db.session.add(perfume); db.session.commit(); flash("تمت إضافة العطر إلى المجموعة.", "success")
            return redirect(url_for("admin"))
        return render_template("perfume_form.html", form=form, title="إضافة عطر جديد", editing=False)

    @app.route("/admin/perfumes/<int:pid>/edit", methods=["GET", "POST"])
    @admin_required
    def edit_perfume(pid):
        perfume = db.session.get(Perfume, pid) or abort(404)
        form = PerfumeForm(obj=perfume)
        if form.validate_on_submit():
            form.populate_obj(perfume)
            perfume.price = float(money(form.price.data))
            db.session.commit(); flash("تم حفظ تعديلات العطر.", "success")
            return redirect(url_for("admin"))
        return render_template("perfume_form.html", form=form, title="تعديل العطر", editing=True, perfume=perfume)

    @app.post("/admin/perfumes/<int:pid>/delete")
    @admin_required
    def delete_perfume(pid):
        form = EmptyForm(); perfume = db.session.get(Perfume, pid) or abort(404)
        if not form.validate_on_submit(): abort(400)
        # SQLite can reuse a deleted product's numeric ID. Unlink historical
        # items so cancelling an old order cannot restock an unrelated product.
        db.session.execute(update(OrderItem).where(OrderItem.perfume_id == pid).values(perfume_id=0))
        db.session.delete(perfume); db.session.commit(); flash("تم حذف العطر من المجموعة.", "info")
        return redirect(url_for("admin"))

    @app.context_processor
    def inject_globals():
        cart_data = clean_cart()
        return {"logged_in": bool(session.get("user_id")), "current_username": session.get("username"), "cart_count": sum(cart_data.values()), "wishlist_count": len(session.get("wishlist", [])), "wishlist_ids": session.get('wishlist', []), "empty_form": EmptyForm(), "current_year": datetime.now().year, 'status_labels': ORDER_STATUS_LABELS,
                'category_labels': CATEGORIES, 'audience_labels': AUDIENCES, 'catalog_volumes': VOLUMES,
                'catalog_images': IMAGES, 'catalog_filter_keys': FILTER_KEYS}

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("error.html", code=404, message="يبدو أن الصفحة التي تبحث عنها غير موجودة."), 404

    @app.errorhandler(400)
    def bad_request(_error):
        return render_template("error.html", code=400, message="تعذر التحقق من الطلب. حدّث الصفحة وحاول مرة أخرى."), 400

    @app.errorhandler(500)
    def server_error(_error):
        db.session.rollback()
        return render_template("error.html", code=500, message="تعذر إكمال الطلب الآن. جرّب مرة أخرى بعد قليل."), 500

    return app


if __name__ == "__main__":
    create_app().run()
