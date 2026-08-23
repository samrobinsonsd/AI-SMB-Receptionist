import sqlite3
from pathlib import Path
from datetime import datetime, timezone


# Store the SQLite database in the project root.
#
# __file__ points to:
# app/database.py
#
# parents[1] moves up one level to the project root.
PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATABASE_PATH = PROJECT_ROOT / "messages.db"


def get_connection():
    """
    Open a connection to the SQLite database.

    SQLite stores the entire database in a single local file.
    Each function opens its own short-lived connection rather than
    keeping one global connection open.
    """

    return sqlite3.connect(DATABASE_PATH)


def initialize_database():
    """
    Create the messages table if it does not already exist.

    This function is safe to run every time the application starts.
    CREATE TABLE IF NOT EXISTS will leave an existing table unchanged.
    """

    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                reason TEXT NOT NULL,
                notes TEXT,
                callback_requested INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'new'
            )
            """
        )

        connection.commit()


def save_message(
    name,
    phone,
    reason,
    notes="",
    callback_requested=False,
):
    """
    Save a structured caller message to SQLite.

    callback_requested is stored as 1 or 0 because SQLite does not
    have a dedicated Boolean storage type.

    Returns the ID assigned to the newly created message.
    """

    created_at = datetime.now(timezone.utc).isoformat()

    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO messages (
                created_at,
                name,
                phone,
                reason,
                notes,
                callback_requested
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                created_at,
                name,
                phone,
                reason,
                notes,
                int(callback_requested),
            ),
        )

        connection.commit()

        return cursor.lastrowid


def get_messages():
    """
    Return all captured messages, newest first.

    sqlite3.Row lets us access database columns by name instead
    of only by numeric position.
    """

    with get_connection() as connection:
        connection.row_factory = sqlite3.Row

        rows = connection.execute(
            """
            SELECT
                id,
                created_at,
                name,
                phone,
                reason,
                notes,
                callback_requested,
                status
            FROM messages
            ORDER BY id DESC
            """
        ).fetchall()


    # Convert SQLite rows into API-friendly dictionaries.
    #
    # SQLite stores Boolean values as integers, so convert
    # callback_requested back to True/False before returning JSON.
    messages = []

    for row in rows:
        message = dict(row)
        message["callback_requested"] = bool(
            message["callback_requested"]
        )   

        messages.append(message)

    return messages