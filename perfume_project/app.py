from functools import wraps
from datetime import datetime
import os

from flask import (Flask, abort, flash, redirect, render_template, request,
                   session, url_for)
from sqlalchemy import or_
from werkzeug.security import check_password_hash, generate_password_hash

from config import Config
from forms import EmptyForm, LoginForm, PerfumeForm, RegisterForm
from models import Perfume, User, db


def create_app(test_config=None):
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)
    db.init_app(app)
    os.makedirs(os.path.join(app.root_path, "instance"), exist_ok=True)

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
        return {str(k): max(1, int(v)) for k, v in cart.items()}

    @app.template_filter("sar")
    def sar(value):
        return f"{float(value):,.0f} ر.س"

    @app.route("/")
    def home():
        featured = Perfume.query.order_by(Perfume.created_at.desc()).limit(3).all()
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
                db.session.commit()
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
                if not valid and user.password == form.password.data:
                    valid = True
                    user.password = generate_password_hash(form.password.data)
                    db.session.commit()
            if valid:
                session["user_id"] = user.id
                session["username"] = user.username
                session["is_admin"] = bool(user.is_admin)
                flash(f"مرحبًا بعودتك، {user.username}.", "success")
                target = request.args.get("next")
                return redirect(target if target and target.startswith("/") else url_for("profile"))
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
        return render_template("profile.html", user=user)

    @app.route("/perfumes")
    def perfumes():
        query = Perfume.query
        search = request.args.get("q", "").strip()
        brand = request.args.get("brand", "").strip()
        price = request.args.get("price", "")
        availability = request.args.get("availability", "")
        sort = request.args.get("sort", "newest")
        if search:
            pattern = f"%{search}%"
            query = query.filter(or_(Perfume.name.ilike(pattern), Perfume.brand.ilike(pattern), Perfume.description.ilike(pattern)))
        if brand:
            query = query.filter(Perfume.brand == brand)
        if price == "under175": query = query.filter(Perfume.price < 175)
        elif price == "175-225": query = query.filter(Perfume.price >= 175, Perfume.price <= 225)
        elif price == "over225": query = query.filter(Perfume.price > 225)
        if availability == "available": query = query.filter(Perfume.stock > 0)
        order_map = {"price_asc": Perfume.price.asc(), "price_desc": Perfume.price.desc(), "name": Perfume.name.asc(), "newest": Perfume.created_at.desc()}
        products = query.order_by(order_map.get(sort, Perfume.created_at.desc())).all()
        brands = [row[0] for row in db.session.query(Perfume.brand).filter(Perfume.brand.isnot(None)).distinct().order_by(Perfume.brand)]
        return render_template("perfumes.html", perfumes=products, brands=brands)

    @app.route("/perfumes/<int:pid>")
    def perfume_detail(pid):
        perfume = db.session.get(Perfume, pid)
        if not perfume: abort(404)
        similar = Perfume.query.filter(Perfume.id != pid).order_by(Perfume.created_at.desc()).limit(3).all()
        notes = [part.strip() for part in (perfume.description or "عنبر، مسك، أخشاب دافئة").replace("،", ",").split(",") if part.strip()][:4]
        return render_template("perfume_detail.html", perfume=perfume, similar=similar, notes=notes, wished=pid in session.get("wishlist", []))

    @app.post("/cart/add/<int:pid>")
    def add_to_cart(pid):
        form = EmptyForm()
        perfume = db.session.get(Perfume, pid)
        if not form.validate_on_submit() or not perfume: abort(404)
        if perfume.stock < 1:
            flash("هذا العطر غير متوفر حاليًا.", "warning")
            return redirect(request.referrer or url_for("perfumes"))
        try: quantity = max(1, int(request.form.get("quantity", 1)))
        except ValueError: quantity = 1
        cart = clean_cart()
        cart[str(pid)] = min(perfume.stock, cart.get(str(pid), 0) + quantity)
        session["cart"] = cart
        flash(f"أُضيف «{perfume.name}» إلى حقيبتك.", "success")
        return redirect(request.referrer or url_for("cart"))

    @app.route("/cart")
    def cart():
        cart_data = clean_cart()
        items, subtotal = [], 0
        for pid, quantity in cart_data.items():
            perfume = db.session.get(Perfume, int(pid))
            if perfume:
                quantity = min(quantity, max(perfume.stock, 1))
                line_total = perfume.price * quantity
                items.append({"perfume": perfume, "quantity": quantity, "line_total": line_total})
                subtotal += line_total
        shipping = 0 if subtotal >= 250 or not items else 25
        return render_template("cart.html", items=items, subtotal=subtotal, shipping=shipping, total=subtotal + shipping)

    @app.post("/cart/update")
    def update_cart():
        form = EmptyForm()
        if not form.validate_on_submit(): abort(400)
        cart_data = clean_cart()
        for pid in list(cart_data):
            perfume = db.session.get(Perfume, int(pid))
            try: quantity = int(request.form.get(f"quantity_{pid}", cart_data[pid]))
            except ValueError: quantity = cart_data[pid]
            if quantity <= 0 or not perfume: cart_data.pop(pid, None)
            else: cart_data[pid] = min(quantity, perfume.stock)
        session["cart"] = cart_data
        flash("تم تحديث حقيبة التسوق.", "success")
        return redirect(url_for("cart"))

    @app.post("/cart/remove/<int:pid>")
    def remove_from_cart(pid):
        form = EmptyForm()
        if form.validate_on_submit():
            cart_data = clean_cart(); cart_data.pop(str(pid), None); session["cart"] = cart_data
            flash("تمت إزالة العطر من الحقيبة.", "info")
        return redirect(url_for("cart"))

    @app.post("/cart/clear")
    def clear_cart():
        form = EmptyForm()
        if form.validate_on_submit(): session.pop("cart", None); flash("تم إفراغ حقيبة التسوق.", "info")
        return redirect(url_for("cart"))

    @app.post("/wishlist/<int:pid>")
    def toggle_wishlist(pid):
        form = EmptyForm()
        if not form.validate_on_submit() or not db.session.get(Perfume, pid): abort(404)
        wishlist = session.get("wishlist", [])
        if pid in wishlist: wishlist.remove(pid); flash("أزيل العطر من المفضلة.", "info")
        else: wishlist.append(pid); flash("حُفظ العطر في المفضلة.", "success")
        session["wishlist"] = wishlist
        return redirect(request.referrer or url_for("perfume_detail", pid=pid))

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
            perfume = Perfume(name=form.name.data.strip(), brand=form.brand.data.strip(), description=form.description.data.strip(), price=form.price.data, stock=form.stock.data)
            db.session.add(perfume); db.session.commit(); flash("تمت إضافة العطر إلى المجموعة.", "success")
            return redirect(url_for("admin"))
        return render_template("perfume_form.html", form=form, title="إضافة عطر جديد", editing=False)

    @app.route("/admin/perfumes/<int:pid>/edit", methods=["GET", "POST"])
    @admin_required
    def edit_perfume(pid):
        perfume = db.session.get(Perfume, pid) or abort(404)
        form = PerfumeForm(obj=perfume)
        if form.validate_on_submit():
            form.populate_obj(perfume); db.session.commit(); flash("تم حفظ تعديلات العطر.", "success")
            return redirect(url_for("admin"))
        return render_template("perfume_form.html", form=form, title="تعديل العطر", editing=True, perfume=perfume)

    @app.post("/admin/perfumes/<int:pid>/delete")
    @admin_required
    def delete_perfume(pid):
        form = EmptyForm(); perfume = db.session.get(Perfume, pid) or abort(404)
        if form.validate_on_submit(): db.session.delete(perfume); db.session.commit(); flash("تم حذف العطر من المجموعة.", "info")
        return redirect(url_for("admin"))

    @app.context_processor
    def inject_globals():
        cart_data = clean_cart()
        return {"logged_in": bool(session.get("user_id")), "current_username": session.get("username"), "cart_count": sum(cart_data.values()), "wishlist_count": len(session.get("wishlist", [])), "empty_form": EmptyForm(), "current_year": datetime.now().year}

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
