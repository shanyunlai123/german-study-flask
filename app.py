import csv
from datetime import date, timedelta
from io import StringIO
import os
import sqlite3

from flask import Flask, g, redirect, render_template, request, send_from_directory, url_for


app = Flask(__name__)
DATABASE = "words.db"

INTERVAL_DAYS = {
    1: 1,
    2: 2,
    3: 4,
    4: 7,
    5: 15,
    6: 30,
}


def today_text():
    return date.today().isoformat()


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(error):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def column_exists(table, column):
    rows = get_db().execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in rows)


def add_column_if_missing(table, column, definition):
    if not column_exists(table, column):
        get_db().execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db():
    db = get_db()
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS words (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            german TEXT NOT NULL,
            chinese TEXT NOT NULL,
            created_at TEXT NOT NULL,
            reviewed_at TEXT
        )
        """
    )
    add_column_if_missing("words", "example", "TEXT DEFAULT ''")
    add_column_if_missing("words", "level", "INTEGER DEFAULT 1")
    add_column_if_missing("words", "review_count", "INTEGER DEFAULT 0")
    add_column_if_missing("words", "next_review", "TEXT")
    add_column_if_missing("words", "tag", "TEXT DEFAULT ''")

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS reading_mistakes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            question TEXT NOT NULL,
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS listening_mistakes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            detail TEXT NOT NULL,
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS writing_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    db.execute(
        "UPDATE words SET next_review = created_at WHERE next_review IS NULL"
    )
    db.commit()


def clean_level(value):
    try:
        level = int(value)
    except (TypeError, ValueError):
        level = 1
    return min(max(level, 1), max(INTERVAL_DAYS))


def add_word(german, chinese, example="", level=1, tag=""):
    german = (german or "").strip()
    chinese = (chinese or "").strip()
    example = (example or "").strip()
    tag = (tag or "").strip()
    level = clean_level(level)

    if not german or not chinese:
        return False

    get_db().execute(
        """
        INSERT INTO words
        (german, chinese, example, level, tag, created_at, next_review)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (german, chinese, example, level, tag, today_text(), today_text()),
    )
    return True


def decode_upload(raw_content):
    for encoding in ("utf-8-sig", "utf-16", "gbk"):
        try:
            return raw_content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw_content.decode("utf-8", errors="ignore")


def normalize_csv_row(row):
    return {
        (key or "").strip().lower(): (value or "").strip()
        for key, value in row.items()
    }


def parse_bulk_line(line):
    for separator in ("=", "＝", ":", "："):
        if separator in line:
            german, chinese = line.split(separator, 1)
            return german.strip(), chinese.strip()
    return "", ""


@app.before_request
def before_request():
    init_db()


@app.route("/")
def home():
    db = get_db()
    today = today_text()
    stats = {
        "words": db.execute("SELECT COUNT(*) FROM words").fetchone()[0],
        "today_words": db.execute(
            "SELECT COUNT(*) FROM words WHERE next_review <= ?", (today,)
        ).fetchone()[0],
        "reading": db.execute("SELECT COUNT(*) FROM reading_mistakes").fetchone()[0],
        "listening": db.execute("SELECT COUNT(*) FROM listening_mistakes").fetchone()[0],
        "templates": db.execute("SELECT COUNT(*) FROM writing_templates").fetchone()[0],
    }
    return render_template("home.html", stats=stats)


@app.route("/service-worker.js")
def service_worker():
    response = send_from_directory("static", "service-worker.js")
    response.headers["Service-Worker-Allowed"] = "/"
    return response


@app.route("/words", methods=["GET", "POST"])
def words():
    if request.method == "POST":
        german = request.form.get("german", "").strip()
        chinese = request.form.get("chinese", "").strip()
        example = request.form.get("example", "").strip()
        tag = request.form.get("tag", "").strip()

        if add_word(german, chinese, example, tag=tag):
            get_db().commit()

        return redirect(url_for("words"))

    rows = get_db().execute(
        "SELECT * FROM words ORDER BY next_review ASC, id DESC"
    ).fetchall()
    return render_template("words.html", words=rows)


@app.route("/words/import", methods=["GET", "POST"])
def import_words():
    imported = 0
    skipped = 0
    error = ""

    if request.method == "POST":
        import_type = request.form.get("import_type")

        if import_type == "csv":
            file = request.files.get("csv_file")
            if not file or file.filename == "":
                error = "请选择一个 CSV 文件。"
            else:
                raw_content = file.read()
                content = decode_upload(raw_content)
                sample = content[:2048]
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
                except csv.Error:
                    dialect = csv.excel

                reader = csv.DictReader(StringIO(content), dialect=dialect)
                fieldnames = {
                    (field or "").strip().lower()
                    for field in (reader.fieldnames or [])
                }

                if not {"german", "chinese"}.issubset(fieldnames):
                    error = "CSV 表头至少需要包含 german 和 chinese。可选字段：example,level,tag。"
                else:
                    for row in reader:
                        row = normalize_csv_row(row)
                        if add_word(
                            row.get("german"),
                            row.get("chinese"),
                            row.get("example"),
                            row.get("level"),
                            row.get("tag"),
                        ):
                            imported += 1
                        else:
                            skipped += 1
                    get_db().commit()

        if import_type == "text":
            bulk_text = request.form.get("bulk_text", "")
            for line in bulk_text.splitlines():
                line = line.strip()
                if not line:
                    continue
                german, chinese = parse_bulk_line(line)
                if add_word(german, chinese, tag="批量导入"):
                    imported += 1
                else:
                    skipped += 1
            get_db().commit()

        if not error:
            return redirect(url_for("import_words", imported=imported, skipped=skipped))

    imported = request.args.get("imported", imported)
    skipped = request.args.get("skipped", skipped)
    return render_template(
        "import_words.html",
        imported=imported,
        skipped=skipped,
        error=error,
    )


@app.route("/words/<int:word_id>/delete", methods=["POST"])
def delete_word(word_id):
    get_db().execute("DELETE FROM words WHERE id = ?", (word_id,))
    get_db().commit()
    return redirect(url_for("words"))


@app.route("/review")
def review():
    rows = get_db().execute(
        """
        SELECT * FROM words
        WHERE next_review <= ?
        ORDER BY next_review ASC, id DESC
        """,
        (today_text(),),
    ).fetchall()
    return render_template("review.html", words=rows)


@app.route("/review/<int:word_id>/<result>", methods=["POST"])
def review_word(word_id, result):
    word = get_db().execute(
        "SELECT * FROM words WHERE id = ?", (word_id,)
    ).fetchone()
    if word is None:
        return redirect(url_for("review"))

    if result == "forgot":
        level = 1
    else:
        level = min((word["level"] or 1) + 1, max(INTERVAL_DAYS))

    next_review = date.today() + timedelta(days=INTERVAL_DAYS[level])
    get_db().execute(
        """
        UPDATE words
        SET level = ?, review_count = ?, reviewed_at = ?, next_review = ?
        WHERE id = ?
        """,
        (
            level,
            (word["review_count"] or 0) + 1,
            today_text(),
            next_review.isoformat(),
            word_id,
        ),
    )
    get_db().commit()
    return redirect(url_for("review"))


@app.route("/reading", methods=["GET", "POST"])
def reading():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        question = request.form.get("question", "").strip()
        reason = request.form.get("reason", "").strip()

        if title and question and reason:
            get_db().execute(
                """
                INSERT INTO reading_mistakes
                (title, question, reason, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (title, question, reason, today_text()),
            )
            get_db().commit()

        return redirect(url_for("reading"))

    rows = get_db().execute(
        "SELECT * FROM reading_mistakes ORDER BY id DESC"
    ).fetchall()
    return render_template("reading.html", mistakes=rows)


@app.route("/listening", methods=["GET", "POST"])
def listening():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        detail = request.form.get("detail", "").strip()
        reason = request.form.get("reason", "").strip()

        if title and detail and reason:
            get_db().execute(
                """
                INSERT INTO listening_mistakes
                (title, detail, reason, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (title, detail, reason, today_text()),
            )
            get_db().commit()

        return redirect(url_for("listening"))

    rows = get_db().execute(
        "SELECT * FROM listening_mistakes ORDER BY id DESC"
    ).fetchall()
    return render_template("listening.html", mistakes=rows)


@app.route("/writing", methods=["GET", "POST"])
def writing():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        category = request.form.get("category", "").strip()
        content = request.form.get("content", "").strip()

        if title and category and content:
            get_db().execute(
                """
                INSERT INTO writing_templates
                (title, category, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (title, category, content, today_text()),
            )
            get_db().commit()

        return redirect(url_for("writing"))

    rows = get_db().execute(
        "SELECT * FROM writing_templates ORDER BY id DESC"
    ).fetchall()
    return render_template("writing.html", templates=rows)


if __name__ == "__main__":
    with app.app_context():
        init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
