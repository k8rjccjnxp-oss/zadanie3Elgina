from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
import sqlite3, os
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "warehouse.db")
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    with get_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            full_name TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('client','manager','admin'))
        );
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );
        CREATE TABLE IF NOT EXISTS suppliers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category_id INTEGER REFERENCES categories(id),
            description TEXT DEFAULT '',
            manufacturer TEXT DEFAULT '',
            supplier_id INTEGER REFERENCES suppliers(id),
            price REAL NOT NULL CHECK(price >= 0),
            unit TEXT NOT NULL DEFAULT 'шт.',
            stock INTEGER NOT NULL DEFAULT 0 CHECK(stock >= 0),
            discount REAL NOT NULL DEFAULT 0 CHECK(discount >= 0 AND discount <= 100),
            image_path TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'Новый',
            pickup_address TEXT NOT NULL,
            order_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
            product_id INTEGER NOT NULL REFERENCES products(id),
            quantity INTEGER NOT NULL DEFAULT 1 CHECK(quantity > 0)
        );
        """)
        if db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
            db.executemany("INSERT INTO users(username,password_hash,full_name,role) VALUES(?,?,?,?)", [
                ("admin", generate_password_hash("admin123"), "Администратор", "admin"),
                ("manager", generate_password_hash("manager123"), "Менеджер склада", "manager"),
                ("client", generate_password_hash("client123"), "Авторизованный клиент", "client"),
            ])
            db.executemany("INSERT INTO categories(name) VALUES(?)", [
                ("Велосипеды",), ("Аксессуары",), ("Запчасти",)
            ])
            db.executemany("INSERT INTO suppliers(name) VALUES(?)", [
                ("ВелоТрейд",), ("СпортСнаб",), ("Мир деталей",)
            ])
            db.executemany("""INSERT INTO products(name,category_id,description,manufacturer,supplier_id,price,unit,stock,discount)
                              VALUES(?,?,?,?,?,?,?,?,?)""", [
                ("Городской велосипед",1,"Удобный велосипед для города","Velomax",1,25990,"шт.",12,10),
                ("Горный велосипед",1,"Для прогулок по пересечённой местности","TrailPro",2,38900,"шт.",5,0),
                ("Шлем защитный",2,"Регулируемый защитный шлем","SafeRide",2,3200,"шт.",0,15),
                ("Набор тормозных колодок",3,"Комплект для обслуживания тормозов","BikeParts",3,850,"компл.",24,5),
                ("Велосипедный фонарь",2,"Передний LED-фонарь","BrightWay",1,1450,"шт.",8,0),
            ])
            db.executemany("INSERT INTO orders(article,status,pickup_address,order_date) VALUES(?,?,?,?)", [
                ("ORD-1001","Новый","Пункт выдачи № 1","2026-10-01 12:30:00"),
                ("ORD-1002","В обработке","Пункт выдачи № 2","2026-10-03 15:10:00"),
            ])
            db.executemany("INSERT INTO order_items(order_id,product_id,quantity) VALUES(?,?,?)", [
                (1,1,1),(1,4,2),(2,2,1)
            ])

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            flash("Войдите в систему или продолжите как гость.", "warning")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped

def roles_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if session.get("role") not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator

@app.context_processor
def inject_user():
    return {"current_user": session.get("full_name"), "current_role": session.get("role")}

@app.route("/")
def index():
    return redirect(url_for("products"))

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username","").strip()
        password = request.form.get("password","")
        with get_db() as db:
            user = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.update(user_id=user["id"], username=user["username"], full_name=user["full_name"], role=user["role"])
            flash("Вы успешно вошли в систему.", "success")
            return redirect(url_for("products"))
        flash("Неверный логин или пароль.", "danger")
    return render_template("login.html")

@app.route("/guest")
def guest():
    session.clear()
    session["role"] = "guest"
    session["full_name"] = "Гость"
    flash("Вы вошли в режиме гостя. Доступен только просмотр товаров.", "info")
    return redirect(url_for("products"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/products")
def products():
    q = request.args.get("q","").strip()
    category = request.args.get("category","")
    discount_range = request.args.get("discount","all")
    sort = request.args.get("sort","name_asc")
    allowed_sorts = {
        "name_asc":"p.name ASC", "name_desc":"p.name DESC",
        "stock_asc":"p.stock ASC", "stock_desc":"p.stock DESC",
        "price_asc":"p.price ASC", "price_desc":"p.price DESC",
        "discount_asc":"p.discount ASC", "discount_desc":"p.discount DESC"
    }
    sql = """SELECT p.*, c.name AS category_name, s.name AS supplier_name
             FROM products p LEFT JOIN categories c ON c.id=p.category_id
             LEFT JOIN suppliers s ON s.id=p.supplier_id WHERE 1=1"""
    params=[]
    if q:
        sql += " AND (p.name LIKE ? OR p.description LIKE ? OR p.manufacturer LIKE ? OR c.name LIKE ? OR s.name LIKE ?)"
        params += [f"%{q}%"]*5
    if category.isdigit():
        sql += " AND p.category_id=?"; params.append(int(category))
    if discount_range == "0-11.99":
        sql += " AND p.discount >= 0 AND p.discount < 12"
    elif discount_range == "12-18.99":
        sql += " AND p.discount >= 12 AND p.discount < 19"
    elif discount_range == "19+":
        sql += " AND p.discount >= 19"
    sql += " ORDER BY " + allowed_sorts.get(sort, "p.name ASC")
    with get_db() as db:
        rows = db.execute(sql, params).fetchall()
        categories = db.execute("SELECT * FROM categories ORDER BY name").fetchall()
    return render_template("products.html", products=rows, categories=categories, q=q, category=category, discount=discount_range, sort=sort)

@app.route("/products/new", methods=["GET","POST"])
@login_required
@roles_required("admin")
def product_new():
    return product_form(None)

@app.route("/products/<int:product_id>/edit", methods=["GET","POST"])
@login_required
@roles_required("admin")
def product_edit(product_id):
    return product_form(product_id)

def product_form(product_id):
    with get_db() as db:
        product = db.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone() if product_id else None
        if product_id and not product:
            abort(404)
        categories = db.execute("SELECT * FROM categories ORDER BY name").fetchall()
        suppliers = db.execute("SELECT * FROM suppliers ORDER BY name").fetchall()
        if request.method == "POST":
            name = request.form.get("name","").strip()
            price = request.form.get("price","0")
            stock = request.form.get("stock","0")
            discount = request.form.get("discount","0")
            if not name:
                flash("Введите наименование товара.", "danger")
                return render_template("product_form.html", product=product, categories=categories, suppliers=suppliers)
            try:
                price, stock, discount = float(price), int(stock), float(discount)
                if price < 0 or stock < 0 or not 0 <= discount <= 100:
                    raise ValueError()
            except ValueError:
                flash("Проверьте цену, количество и скидку (0–100%).", "danger")
                return render_template("product_form.html", product=product, categories=categories, suppliers=suppliers)
            values=(name, request.form.get("category_id") or None, request.form.get("description","").strip(),
                    request.form.get("manufacturer","").strip(), request.form.get("supplier_id") or None,
                    price, request.form.get("unit","шт.").strip() or "шт.", stock, discount,
                    request.form.get("image_path","").strip())
            if product_id:
                db.execute("""UPDATE products SET name=?,category_id=?,description=?,manufacturer=?,supplier_id=?,
                              price=?,unit=?,stock=?,discount=?,image_path=? WHERE id=?""", values+(product_id,))
                flash("Товар обновлён.", "success")
            else:
                db.execute("""INSERT INTO products(name,category_id,description,manufacturer,supplier_id,price,unit,stock,discount,image_path)
                              VALUES(?,?,?,?,?,?,?,?,?,?)""", values)
                flash("Товар добавлен.", "success")
            db.commit()
            return redirect(url_for("products"))
    return render_template("product_form.html", product=product, categories=categories, suppliers=suppliers)

@app.route("/products/<int:product_id>/delete", methods=["POST"])
@login_required
@roles_required("admin")
def product_delete(product_id):
    with get_db() as db:
        if db.execute("SELECT 1 FROM order_items WHERE product_id=?", (product_id,)).fetchone():
            flash("Нельзя удалить товар, который присутствует в заказе.", "danger")
        else:
            db.execute("DELETE FROM products WHERE id=?", (product_id,))
            flash("Товар удалён.", "success")
    return redirect(url_for("products"))

@app.route("/orders")
@login_required
@roles_required("manager","admin")
def orders():
    with get_db() as db:
        rows=db.execute("""SELECT o.*, GROUP_CONCAT(p.name || ' × ' || oi.quantity, ', ') AS items
                           FROM orders o LEFT JOIN order_items oi ON oi.order_id=o.id
                           LEFT JOIN products p ON p.id=oi.product_id GROUP BY o.id ORDER BY o.order_date DESC""").fetchall()
    return render_template("orders.html", orders=rows)

@app.route("/orders/new", methods=["GET","POST"])
@login_required
@roles_required("admin")
def order_new():
    with get_db() as db:
        products = db.execute("SELECT id,name,stock FROM products ORDER BY name").fetchall()
        if request.method=="POST":
            article=request.form.get("article","").strip()
            status=request.form.get("status","Новый")
            address=request.form.get("pickup_address","").strip()
            product_id=request.form.get("product_id","")
            try: quantity=int(request.form.get("quantity","1"))
            except ValueError: quantity=0
            if not article or not address or not product_id or quantity < 1:
                flash("Заполните все поля корректно.", "danger")
            else:
                try:
                    cur=db.execute("INSERT INTO orders(article,status,pickup_address) VALUES(?,?,?)",(article,status,address))
                    db.execute("INSERT INTO order_items(order_id,product_id,quantity) VALUES(?,?,?)",(cur.lastrowid,int(product_id),quantity))
                    db.commit()
                    flash("Заказ добавлен.", "success")
                    return redirect(url_for("orders"))
                except sqlite3.IntegrityError:
                    flash("Артикул заказа должен быть уникальным.", "danger")
    return render_template("order_form.html", order=None, products=products)

@app.route("/orders/<int:order_id>/edit", methods=["GET","POST"])
@login_required
@roles_required("admin")
def order_edit(order_id):
    with get_db() as db:
        order=db.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        if not order: abort(404)
        products=db.execute("SELECT id,name,stock FROM products ORDER BY name").fetchall()
        item=db.execute("SELECT * FROM order_items WHERE order_id=? LIMIT 1",(order_id,)).fetchone()
        if request.method=="POST":
            article=request.form.get("article","").strip()
            status=request.form.get("status","Новый")
            address=request.form.get("pickup_address","").strip()
            product_id=request.form.get("product_id","")
            try: quantity=int(request.form.get("quantity","1"))
            except ValueError: quantity=0
            if not article or not address or not product_id or quantity<1:
                flash("Заполните все поля корректно.", "danger")
            else:
                try:
                    db.execute("UPDATE orders SET article=?,status=?,pickup_address=? WHERE id=?",(article,status,address,order_id))
                    if item:
                        db.execute("UPDATE order_items SET product_id=?,quantity=? WHERE id=?",(int(product_id),quantity,item["id"]))
                    else:
                        db.execute("INSERT INTO order_items(order_id,product_id,quantity) VALUES(?,?,?)",(order_id,int(product_id),quantity))
                    db.commit()
                    flash("Заказ обновлён.", "success")
                    return redirect(url_for("orders"))
                except sqlite3.IntegrityError:
                    flash("Артикул заказа должен быть уникальным.", "danger")
    return render_template("order_form.html", order=order, products=products, item=item)

@app.route("/orders/<int:order_id>/delete", methods=["POST"])
@login_required
@roles_required("admin")
def order_delete(order_id):
    with get_db() as db:
        db.execute("DELETE FROM orders WHERE id=?", (order_id,))
    flash("Заказ удалён.", "success")
    return redirect(url_for("orders"))

@app.errorhandler(403)
def forbidden(_):
    return render_template("error.html", code=403, message="Недостаточно прав для выполнения действия."),403

@app.errorhandler(404)
def not_found(_):
    return render_template("error.html", code=404, message="Запрашиваемая страница не найдена."),404

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
