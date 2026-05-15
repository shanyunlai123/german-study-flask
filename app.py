import csv
from datetime import date, timedelta
from io import StringIO
import os
import re
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
    add_column_if_missing("words", "part_of_speech", "TEXT DEFAULT ''")
    add_column_if_missing("words", "plural_form", "TEXT DEFAULT ''")
    add_column_if_missing("words", "collocations", "TEXT DEFAULT ''")
    add_column_if_missing("words", "examples", "TEXT DEFAULT ''")
    add_column_if_missing("words", "synonyms", "TEXT DEFAULT ''")
    add_column_if_missing("words", "grammar_notes", "TEXT DEFAULT ''")
    add_column_if_missing("words", "level_text", "TEXT DEFAULT ''")

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


def normalize_lines(value):
    lines = []
    for line in (value or "").replace("\r\n", "\n").split("\n"):
        line = line.strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def add_word(
    german,
    chinese,
    example="",
    level=1,
    tag="",
    part_of_speech="",
    plural_form="",
    collocations="",
    examples="",
    synonyms="",
    grammar_notes="",
    level_text="",
):
    german = (german or "").strip()
    chinese = (chinese or "").strip()
    example = (example or "").strip()
    tag = (tag or "").strip()
    level = clean_level(level)
    part_of_speech = (part_of_speech or "").strip()
    plural_form = (plural_form or "").strip()
    collocations = normalize_lines(collocations)
    examples = normalize_lines(examples or example)
    synonyms = normalize_lines(synonyms)
    grammar_notes = normalize_lines(grammar_notes)
    level_text = normalize_lines(level_text or tag)

    if not german or not chinese:
        return False

    get_db().execute(
        """
        INSERT INTO words
        (
            german, chinese, example, level, tag, created_at, next_review,
            part_of_speech, plural_form, collocations, examples, synonyms,
            grammar_notes, level_text
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            german,
            chinese,
            example,
            level,
            tag,
            today_text(),
            today_text(),
            part_of_speech,
            plural_form,
            collocations,
            examples,
            synonyms,
            grammar_notes,
            level_text,
        ),
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


def get_csv_value(row, *names):
    for name in names:
        value = row.get(name)
        if value:
            return value
    return ""


def parse_structured_words(text):
    blocks = re.split(r"\n\s*\n(?=\s*(?:单词|german|word)\s*[:：])", text.strip())
    words = []

    for block in blocks:
        if not block.strip():
            continue

        data = {
            "german": "",
            "part_of_speech": "",
            "plural_form": "",
            "chinese": "",
            "collocations": [],
            "examples": [],
            "synonyms": [],
            "grammar_notes": [],
            "level_text": [],
        }
        section = None
        last_example_index = None

        for raw_line in block.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            field_match = re.match(r"^(单词|词性|复数|中文|搭配|例句|近义词|语法|等级|german|word|chinese)\s*[:：]\s*(.*)$", line, re.IGNORECASE)
            if field_match:
                field = field_match.group(1).lower()
                value = field_match.group(2).strip()

                if field in ("单词", "german", "word"):
                    data["german"] = value
                    section = None
                elif field == "词性":
                    data["part_of_speech"] = value
                    section = None
                elif field == "复数":
                    data["plural_form"] = value
                    section = None
                elif field in ("中文", "chinese"):
                    data["chinese"] = value
                    section = None
                elif field == "搭配":
                    section = "collocations"
                    if value:
                        data[section].append(value)
                elif field == "例句":
                    section = "examples"
                    last_example_index = None
                    if value:
                        data[section].append(value)
                        last_example_index = len(data[section]) - 1
                elif field == "近义词":
                    section = "synonyms"
                    if value:
                        data[section].append(value)
                elif field == "语法":
                    section = "grammar_notes"
                    if value:
                        data[section].append(value)
                elif field == "等级":
                    section = "level_text"
                    if value:
                        data[section].append(value)
                continue

            if line.startswith("-"):
                item = line[1:].strip()
                if section:
                    data[section].append(item)
                    if section == "examples":
                        last_example_index = len(data[section]) - 1
                continue

            if section == "examples" and last_example_index is not None:
                data["examples"][last_example_index] += "\n" + line
                continue

            if section:
                data[section].append(line)

        if data["german"] and data["chinese"]:
            words.append(
                {
                    "german": data["german"],
                    "chinese": data["chinese"],
                    "part_of_speech": data["part_of_speech"],
                    "plural_form": data["plural_form"],
                    "collocations": "\n".join(data["collocations"]),
                    "examples": "\n\n".join(data["examples"]),
                    "synonyms": "\n".join(data["synonyms"]),
                    "grammar_notes": "\n".join(data["grammar_notes"]),
                    "level_text": "\n".join(data["level_text"]),
                }
            )

    return words


def parse_bulk_line(line):
    line = re.sub(r"^\s*\d+[\.\)、)]\s*", "", line.strip())
    if not line:
        return "", ""

    for separator in ("=", "＝", ":", "："):
        if separator in line:
            german, chinese = line.split(separator, 1)
            return german.strip(), chinese.strip()

    for separator in ("\t", ",", "，", ";", "；", " - ", " – ", " — "):
        if separator in line:
            german, chinese = line.split(separator, 1)
            return german.strip(), chinese.strip()

    wide_space_match = re.split(r"\s{2,}", line, maxsplit=1)
    if len(wide_space_match) == 2:
        return wide_space_match[0].strip(), wide_space_match[1].strip()

    chinese_match = re.search(r"[\u3400-\u9fff]", line)
    if chinese_match:
        index = chinese_match.start()
        german = line[:index].strip(" \t,;:：=＝-–—")
        chinese = line[index:].strip(" \t,;:：=＝-–—")
        return german, chinese

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
        part_of_speech = request.form.get("part_of_speech", "").strip()
        plural_form = request.form.get("plural_form", "").strip()
        collocations = request.form.get("collocations", "").strip()
        examples = request.form.get("examples", "").strip()
        synonyms = request.form.get("synonyms", "").strip()
        grammar_notes = request.form.get("grammar_notes", "").strip()
        level_text = request.form.get("level_text", "").strip()

        if add_word(
            german,
            chinese,
            part_of_speech=part_of_speech,
            plural_form=plural_form,
            collocations=collocations,
            examples=examples,
            synonyms=synonyms,
            grammar_notes=grammar_notes,
            level_text=level_text,
        ):
            get_db().commit()

        return redirect(url_for("words"))

    rows = get_db().execute(
        "SELECT * FROM words ORDER BY next_review ASC, id DESC"
    ).fetchall()
    return render_template("words.html", words=rows)


@app.route("/words/<int:word_id>")
def word_detail(word_id):
    word = get_db().execute(
        "SELECT * FROM words WHERE id = ?", (word_id,)
    ).fetchone()
    if word is None:
        return redirect(url_for("words"))
    return render_template("word_detail.html", word=word)


@app.route("/words/import", methods=["GET", "POST"])
def import_words():
    imported = 0
    skipped = 0
    skipped_lines = []
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
                    error = "CSV 表头至少需要包含 german 和 chinese。可选字段：part_of_speech,plural_form,collocations,examples,synonyms,grammar_notes,level_text。"
                else:
                    for row in reader:
                        row = normalize_csv_row(row)
                        if add_word(
                            row.get("german"),
                            row.get("chinese"),
                            example=get_csv_value(row, "example"),
                            level=get_csv_value(row, "level", "review_level"),
                            tag=get_csv_value(row, "tag"),
                            part_of_speech=get_csv_value(row, "part_of_speech", "pos", "词性"),
                            plural_form=get_csv_value(row, "plural_form", "plural", "复数"),
                            collocations=get_csv_value(row, "collocations", "搭配"),
                            examples=get_csv_value(row, "examples", "例句"),
                            synonyms=get_csv_value(row, "synonyms", "近义词"),
                            grammar_notes=get_csv_value(row, "grammar_notes", "grammar", "语法"),
                            level_text=get_csv_value(row, "level_text", "等级"),
                        ):
                            imported += 1
                        else:
                            skipped += 1
                            if len(skipped_lines) < 5:
                                skipped_lines.append(str(dict(row)))
                    get_db().commit()

        if import_type == "text":
            bulk_text = request.form.get("bulk_text", "")
            structured_words = parse_structured_words(bulk_text)

            if structured_words:
                for word_data in structured_words:
                    if add_word(**word_data):
                        imported += 1
                    else:
                        skipped += 1
                        if len(skipped_lines) < 5:
                            skipped_lines.append(str(word_data))
            else:
                for line in bulk_text.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    german, chinese = parse_bulk_line(line)
                    if add_word(german, chinese, tag="批量导入"):
                        imported += 1
                    else:
                        skipped += 1
                        if len(skipped_lines) < 5:
                            skipped_lines.append(line[:120])
            get_db().commit()

        if not error:
            return render_template(
                "import_words.html",
                imported=imported,
                skipped=skipped,
                skipped_lines=skipped_lines,
                error=error,
            )

    imported = request.args.get("imported", imported)
    skipped = request.args.get("skipped", skipped)
    return render_template(
        "import_words.html",
        imported=imported,
        skipped=skipped,
        skipped_lines=skipped_lines,
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
