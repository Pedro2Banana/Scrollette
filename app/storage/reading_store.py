import sqlite3

from app.config import DB_PATH


class ReadingStore:
    """SQLite storage for reading metadata: which book, which pages, when read.

    Pure data layer — Qt-free, no business logic, no agent query tools. Used
    from the main thread only (writes are fast, local, no network).
    """

    def __init__(self, path=DB_PATH):
        path.parent.mkdir(parents=True, exist_ok=True)  # 确保 data/ 存在
        self._conn = sqlite3.connect(str(path))
        self._create_tables()

    def _create_tables(self):
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id             TEXT PRIMARY KEY,   -- = file_hash
                file_name      TEXT,
                page_count     INTEGER,
                last_page      INTEGER,            -- 上次停留页（续读用）
                two_page       INTEGER,            -- 上次单/双页（0/1）
                last_opened_at TEXT
            );
            CREATE TABLE IF NOT EXISTS page_reads (
                document_id   TEXT,
                page_number   INTEGER,
                first_read_at TEXT,
                last_read_at  TEXT,
                read_count    INTEGER,
                PRIMARY KEY (document_id, page_number)
            );
            """
        )
        self._migrate()
        self._conn.commit()

    def _migrate(self):
        """给已存在的旧库补列（幂等）。"""
        existing = {row[1] for row in self._conn.execute("PRAGMA table_info(documents)")}
        for column, decl in (("last_page", "INTEGER"), ("two_page", "INTEGER")):
            if column not in existing:
                self._conn.execute(f"ALTER TABLE documents ADD COLUMN {column} {decl}")

    def upsert_document(self, document_id, file_name, page_count):
        """Register/refresh a book when it's opened."""
        self._conn.execute(
            """
            INSERT INTO documents (id, file_name, page_count, last_opened_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(id) DO UPDATE SET
                file_name = excluded.file_name,
                page_count = excluded.page_count,
                last_opened_at = datetime('now')
            """,
            (document_id, file_name, page_count),
        )
        self._conn.commit()

    def mark_read(self, document_id, page_number):
        """Record that a page was read (dwelled on). One row per page."""
        self._conn.execute(
            """
            INSERT INTO page_reads
                (document_id, page_number, first_read_at, last_read_at, read_count)
            VALUES (?, ?, datetime('now'), datetime('now'), 1)
            ON CONFLICT(document_id, page_number) DO UPDATE SET
                last_read_at = datetime('now'),
                read_count = read_count + 1
            """,
            (document_id, page_number),
        )
        self._conn.commit()

    def max_read_page(self, document_id):
        """Highest page ever read for this book (0 if none) — restores the
        companion-mode read range after a restart."""
        row = self._conn.execute(
            "SELECT MAX(page_number) FROM page_reads WHERE document_id = ?",
            (document_id,),
        ).fetchone()
        return row[0] or 0

    def save_view_state(self, document_id, last_page, two_page):
        """Remember where/how the user was reading, for resume-on-reopen."""
        self._conn.execute(
            "UPDATE documents SET last_page = ?, two_page = ? WHERE id = ?",
            (last_page, 1 if two_page else 0, document_id),
        )
        self._conn.commit()

    def view_state(self, document_id):
        """(last_page, two_page) to resume; defaults (1, False) if unknown."""
        row = self._conn.execute(
            "SELECT last_page, two_page FROM documents WHERE id = ?",
            (document_id,),
        ).fetchone()
        if not row or row[0] is None:
            return 1, False
        return row[0], bool(row[1])

    def close(self):
        self._conn.close()
