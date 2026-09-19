from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import re
from datetime import date, datetime
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
from pathlib import Path

app = Flask(__name__)
app.secret_key = "one-star-library-demo-secret"
app.config["UPLOAD_FOLDER"] = Path(__file__).with_name("static").joinpath("uploads")
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

app.config["UPLOAD_FOLDER"].mkdir(parents=True, exist_ok=True)


def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )
DB = Path(__file__).with_name("library.db")

def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    con = db()
    con.executescript("""
    CREATE TABLE IF NOT EXISTS books (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        author TEXT NOT NULL,
        genre TEXT,
        year INTEGER,
        copies INTEGER NOT NULL DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fio TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        phone TEXT,
        birthdate TEXT,
        gender TEXT,
        password_hash TEXT
    );
    CREATE TABLE IF NOT EXISTS bookings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_name TEXT NOT NULL,
        computer TEXT NOT NULL,
        booking_date TEXT NOT NULL,
        booking_time TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS news (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    text TEXT NOT NULL,
    date TEXT NOT NULL,
    image TEXT
    );
    CREATE TABLE IF NOT EXISTS book_reservations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        book_id INTEGER NOT NULL,
        reserved_at TEXT NOT NULL,
        UNIQUE(user_id, book_id),
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(book_id) REFERENCES books(id)
    );
    """)

    news_columns = {
        row[1]
        for row in con.execute("PRAGMA table_info(news)").fetchall()
    }

    if "image" not in news_columns:
        con.execute("ALTER TABLE news ADD COLUMN image TEXT")
    # Migration for databases created by older project versions.
    user_columns = {row[1] for row in con.execute("PRAGMA table_info(users)").fetchall()}
    if "password_hash" not in user_columns:
        con.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")

    if con.execute("SELECT COUNT(*) FROM books").fetchone()[0] == 0:
        con.executemany("INSERT INTO books(title,author,genre,year,copies) VALUES(?,?,?,?,?)", [
            ("Мастер и Маргарита", "М. Булгаков", "Роман", 1967, 4),
            ("Преступление и наказание", "Ф. Достоевский", "Роман", 1866, 3),
            ("1984", "Дж. Оруэлл", "Антиутопия", 1949, 5),
        ])
    if con.execute("SELECT COUNT(*) FROM news").fetchone()[0] == 0:
        con.executemany("INSERT INTO news(title,text,date) VALUES(?,?,?)", [
            ("110 лет теории относительности — выставка",
             "25 ноября 1915 года Альберт Эйнштейн объявил полные математические подробности общей теории относительности.",
             "25.11.2025"),
            ("«Краеведческие библиографические ресурсы региональных библиотек как основа исторического краеведения»",
             "3 декабря и 4 декабря состоится научно-образовательный вебинар.",
             "24.11.2025"),
            ("К 200-летию книгоиздателя и книготорговца Маврикия Вольфа — выставка «Искусство издавать»",
             "24 ноября в Главном здании Российской национальной библиотеки открылась выставка.",
             "24.11.2025"),
        ])
    con.commit()
    con.close()

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper

@app.context_processor
def common():
    return {"admin": session.get("admin", False), "today": date.today().isoformat()}

@app.route("/")
def index():
    con = db()
    news = con.execute("SELECT * FROM news ORDER BY id DESC").fetchall()
    con.close()
    return render_template("index.html", news=news)

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/services")
def services():
    con = db()
    news = con.execute("SELECT * FROM news ORDER BY id DESC").fetchall()
    con.close()
    return render_template("services.html", news=news)

@app.route("/books")
def books():
    q = request.args.get("q", "").strip()
    con = db()
    if q:
        rows = con.execute(
            "SELECT * FROM books WHERE title LIKE ? OR author LIKE ? OR genre LIKE ? ORDER BY title",
            (f"%{q}%", f"%{q}%", f"%{q}%")).fetchall()
    else:
        rows = con.execute("SELECT * FROM books ORDER BY title").fetchall()
    reserved_counts = {r["book_id"]: r["cnt"] for r in con.execute("SELECT book_id, COUNT(*) AS cnt FROM book_reservations GROUP BY book_id").fetchall()}
    con.close()
    return render_template("books.html", books=rows, q=q, reserved_counts=reserved_counts)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        surname = request.form.get("surname", "").strip()
        first_name = request.form.get("first_name", "").strip()
        patronymic = request.form.get("patronymic", "").strip()
        fio = " ".join(x for x in (surname, first_name, patronymic) if x)
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        birthdate = request.form.get("birthdate", "")
        gender = request.form.get("gender", "")
        consent = request.form.get("consent")
        email_ok = re.fullmatch(r"[^\s@]+@[^\s@]+\.[A-Za-zА-Яа-яЁё]{2,}", email or "") is not None
        phone_ok = re.fullmatch(r"\+7\d{10}", phone or "") is not None
        password_ok = len(password) >= 8 and re.search(r"[!@#]", password) is not None
        birth_ok = True
        if birthdate:
            try:
                birth_ok = datetime.strptime(birthdate, "%Y-%m-%d").date() <= date.today()
            except ValueError:
                birth_ok = False
        if not surname or not first_name or not patronymic:
            flash("Заполните фамилию, имя и отчество.", "error")
        elif not email_ok:
            flash("Введите корректный email.", "error")
        elif not phone_ok:
            flash("Телефон должен быть в формате +79991234567.", "error")
        elif not password_ok:
            flash("Пароль должен содержать минимум 8 символов и !, @ или #.", "error")
        elif not birth_ok:
            flash("Дата рождения не может быть будущей.", "error")
        elif not consent:
            flash("Необходимо согласиться на обработку персональных данных.", "error")
        else:
            con = db()
            try:
                con.execute("INSERT INTO users(fio,email,phone,birthdate,gender,password_hash) VALUES(?,?,?,?,?,?)",
                            (fio, email, phone, birthdate, gender, generate_password_hash(password)))
                con.commit()
                flash("Регистрация прошла успешно. Теперь войдите в аккаунт.", "ok")
                return redirect(url_for("login"))
            except sqlite3.IntegrityError:
                flash("Пользователь с таким email уже существует.", "error")
            finally:
                con.close()
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        login_value = request.form.get("login", "").strip().lower()
        password = request.form.get("password", "")
        if login_value == "admin" and password == "admin":
            session.clear()
            session["admin"] = True
            return redirect(url_for("admin"))

        con = db()
        user = con.execute("SELECT * FROM users WHERE lower(email)=?", (login_value,)).fetchone()
        con.close()
        if user and user["password_hash"] and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user"] = user["id"]
            session["user_name"] = user["fio"]
            flash("Вы успешно вошли в аккаунт.", "ok")
            return redirect(url_for("index"))
        flash("Неверный email или пароль.", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/admin")
@admin_required
def admin():
    con = db()
    users = con.execute("SELECT * FROM users ORDER BY id DESC").fetchall()
    books = con.execute("SELECT * FROM books ORDER BY id DESC").fetchall()
    bookings = con.execute("SELECT * FROM bookings ORDER BY booking_date, booking_time").fetchall()
    book_reservations = con.execute("SELECT br.*, b.title AS book_title, u.fio AS user_fio FROM book_reservations br JOIN books b ON b.id=br.book_id JOIN users u ON u.id=br.user_id ORDER BY br.id DESC").fetchall()
    news = con.execute("SELECT * FROM news ORDER BY id DESC").fetchall()
    con.close()
    return render_template("admin.html", users=users, books=books, bookings=bookings, book_reservations=book_reservations, news=news)

@app.post("/admin/books/add")
@admin_required
def add_book():
    con = db()
    con.execute("INSERT INTO books(title,author,genre,year,copies) VALUES(?,?,?,?,?)",
                (request.form["title"],request.form["author"],request.form.get("genre",""),
                 request.form.get("year") or None,request.form.get("copies",1)))
    con.commit(); con.close()
    return redirect(url_for("admin"))

@app.post("/admin/books/<int:id>/delete")
@admin_required
def delete_book(id):
    con=db(); con.execute("DELETE FROM books WHERE id=?", (id,)); con.commit(); con.close()
    return redirect(url_for("admin"))

@app.post("/admin/users/<int:id>/delete")
@admin_required
def delete_user(id):
    con=db(); con.execute("DELETE FROM users WHERE id=?", (id,)); con.commit(); con.close()
    return redirect(url_for("admin"))

@app.post("/admin/news/add")
@admin_required
def add_news():
    news_date = request.form.get("date", "")

    try:
        formatted_date = datetime.strptime(
            news_date, "%Y-%m-%d"
        ).strftime("%d.%m.%Y")
    except ValueError:
        flash("Укажите корректную дату.", "error")
        return redirect(url_for("admin"))

    image_name = None
    image = request.files.get("image")

    if image and image.filename:
        if not allowed_file(image.filename):
            flash("Можно загружать только PNG, JPG, JPEG или WEBP.", "error")
            return redirect(url_for("admin"))

        image_name = secure_filename(image.filename)

        # Чтобы файлы с одинаковыми именами не перезаписывали друг друга
        stem = Path(image_name).stem
        suffix = Path(image_name).suffix
        counter = 1

        final_name = image_name

        while (app.config["UPLOAD_FOLDER"] / final_name).exists():
            final_name = f"{stem}_{counter}{suffix}"
            counter += 1

        image_name = final_name
        image.save(app.config["UPLOAD_FOLDER"] / image_name)

    con = db()
    con.execute(
        "INSERT INTO news(title, text, date, image) VALUES(?,?,?,?)",
        (
            request.form["title"],
            request.form["text"],
            formatted_date,
            image_name
        )
    )
    con.commit()
    con.close()

    return redirect(url_for("admin"))

@app.post("/admin/news/<int:id>/delete")
@admin_required
def delete_news(id):
    con=db(); con.execute("DELETE FROM news WHERE id=?", (id,)); con.commit(); con.close()
    return redirect(url_for("admin"))

@app.post("/books/<int:book_id>/reserve")
def reserve_book(book_id):
    if not session.get("user"):
        return redirect(url_for("login"))
    con=db()
    book=con.execute("SELECT * FROM books WHERE id=?", (book_id,)).fetchone()
    if not book:
        con.close(); flash("Книга не найдена.", "error"); return redirect(url_for("books"))
    count=con.execute("SELECT COUNT(*) FROM book_reservations WHERE book_id=?", (book_id,)).fetchone()[0]
    if count >= book["copies"]:
        flash("Свободных экземпляров этой книги нет.", "error")
    else:
        try:
            con.execute("INSERT INTO book_reservations(user_id,book_id,reserved_at) VALUES(?,?,?)", (session["user"], book_id, datetime.now().isoformat(timespec="seconds")))
            con.commit(); flash("Книга забронирована.", "ok")
        except sqlite3.IntegrityError:
            flash("Вы уже бронировали эту книгу.", "error")
    con.close(); return redirect(url_for("books"))

@app.route("/bookings", methods=["GET","POST"])
def bookings():
    if not session.get("user"):
        return redirect(url_for("login"))
    con=db()
    if request.method == "POST":
        con.execute("INSERT INTO bookings(user_name,computer,booking_date,booking_time) VALUES(?,?,?,?)",
                    (session.get("user_name", ""),request.form["computer"],
                     request.form["booking_date"],request.form["booking_time"]))
        con.commit()
        flash("Компьютер забронирован.", "ok")
    rows=con.execute("SELECT * FROM bookings ORDER BY booking_date, booking_time").fetchall()
    con.close()
    return render_template("bookings.html", bookings=rows)

@app.post("/admin/bookings/<int:id>/delete")
@admin_required
def delete_booking(id):
    con=db(); con.execute("DELETE FROM bookings WHERE id=?", (id,)); con.commit(); con.close()
    return redirect(url_for("admin"))

init_db()
if __name__ == "__main__":
    app.run(debug=True)
