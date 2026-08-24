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


# GPT-Realtime-2.1-mini pricing per 1 million tokens.
# These values are centralized here so pricing can be updated
# without changing the call-processing logic.
TEXT_INPUT_COST_PER_MILLION = 0.60
TEXT_OUTPUT_COST_PER_MILLION = 2.40
AUDIO_INPUT_COST_PER_MILLION = 10.00
AUDIO_OUTPUT_COST_PER_MILLION = 20.00
CACHED_TEXT_INPUT_COST_PER_MILLION = 0.06
CACHED_AUDIO_INPUT_COST_PER_MILLION = 0.30
# Twilio US local inbound voice pricing per minute.
TWILIO_INBOUND_COST_PER_MINUTE = 0.0085


def calculate_call_cost(call):
    """
    Estimate OpenAI and Twilio cost for one completed call.

    Realtime input usage can include cached tokens, which are billed
    at a lower rate than uncached input tokens.

    Audio tokens are tracked separately from text tokens so each usage
    type can be priced correctly.
    """

    input_tokens = call["input_tokens"] or 0
    output_tokens = call["output_tokens"] or 0
    input_audio_tokens = call["input_audio_tokens"] or 0
    output_audio_tokens = call["output_audio_tokens"] or 0
    cached_input_tokens = call["cached_input_tokens"] or 0

    # Total input includes both text and audio.
    text_input_tokens = max(
        input_tokens - input_audio_tokens,
        0,
    )

    # Output is handled the same way.
    text_output_tokens = max(
        output_tokens - output_audio_tokens,
        0,
    )

    # Cached tokens are part of the input total, so subtract them
    # from the normal text-input bucket before applying standard pricing.
    cached_text_input_tokens = (
        call["cached_text_input_tokens"] or 0
    )

    cached_audio_input_tokens = (
        call["cached_audio_input_tokens"] or 0
    )

    uncached_text_input_tokens = max(
        text_input_tokens - cached_text_input_tokens,
        0,
    )

    uncached_audio_input_tokens = max(
        input_audio_tokens - cached_audio_input_tokens,
        0,
    )

    openai_cost = (
        uncached_text_input_tokens
        / 1_000_000
        * TEXT_INPUT_COST_PER_MILLION
        +
        cached_text_input_tokens
        / 1_000_000
        * CACHED_TEXT_INPUT_COST_PER_MILLION
        +
        uncached_audio_input_tokens
        / 1_000_000
        * AUDIO_INPUT_COST_PER_MILLION
        +
        cached_audio_input_tokens
        / 1_000_000
        * CACHED_AUDIO_INPUT_COST_PER_MILLION
        +
        text_output_tokens
        / 1_000_000
        * TEXT_OUTPUT_COST_PER_MILLION
        +
        output_audio_tokens
        / 1_000_000
        * AUDIO_OUTPUT_COST_PER_MILLION
    )

    duration_seconds = call["duration_seconds"] or 0

    billed_minutes = max(
        1,
        (duration_seconds + 59) // 60,
    )

    twilio_cost = (
        billed_minutes
        * TWILIO_INBOUND_COST_PER_MINUTE
    )

    return {
        "openai_cost_usd": round(openai_cost, 6),
        "twilio_cost_usd": round(twilio_cost, 6),
        "estimated_total_cost_usd": round(
            openai_cost + twilio_cost,
            6,
        ),
    }


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

        
        # Store basic information about every receptionist call.
        #
        # This gives us the foundation for usage reporting,
        # cost tracking, and operational analytics.
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                call_sid TEXT NOT NULL UNIQUE,
                stream_sid TEXT,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                duration_seconds INTEGER,
                outcome TEXT NOT NULL DEFAULT 'completed'
            )
            """
        )
        # Add usage columns to older databases without deleting
        # any existing call records.
        #
        # SQLite does not support IF NOT EXISTS for ADD COLUMN,
        # so we inspect the current schema first.
        call_columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(calls)"
            ).fetchall()
        }

        if "input_tokens" not in call_columns:
            connection.execute(
                """
                ALTER TABLE calls
                ADD COLUMN input_tokens INTEGER NOT NULL DEFAULT 0
                """
            )

        if "output_tokens" not in call_columns:
            connection.execute(
                """
                ALTER TABLE calls
                ADD COLUMN output_tokens INTEGER NOT NULL DEFAULT 0
                """
            )

        if "input_audio_tokens" not in call_columns:
            connection.execute(
                """
                ALTER TABLE calls
                ADD COLUMN input_audio_tokens INTEGER NOT NULL DEFAULT 0
                """
            )

        if "output_audio_tokens" not in call_columns:
            connection.execute(
                """
                ALTER TABLE calls
                ADD COLUMN output_audio_tokens INTEGER NOT NULL DEFAULT 0
                """
            )
            
        if "cached_input_tokens" not in call_columns:
            connection.execute(
                """
                ALTER TABLE calls
                ADD COLUMN cached_input_tokens INTEGER NOT NULL DEFAULT 0
                """
            )
            
        if "cached_text_input_tokens" not in call_columns:
            connection.execute(
                """
                ALTER TABLE calls
                ADD COLUMN cached_text_input_tokens INTEGER NOT NULL DEFAULT 0
                """
            )

        if "cached_audio_input_tokens" not in call_columns:
            connection.execute(
                """
                ALTER TABLE calls
                ADD COLUMN cached_audio_input_tokens INTEGER NOT NULL DEFAULT 0
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


def update_message_status(message_id, status):
    """
    Update the workflow status of a stored caller message.

    Allowed statuses:
    - new
    - contacted
    - closed

    Returns True if a message was updated, otherwise False.
    """

    allowed_statuses = {
        "new",
        "contacted",
        "closed",
    }

    if status not in allowed_statuses:
        raise ValueError(
            f"Invalid status: {status}"
        )

    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE messages
            SET status = ?
            WHERE id = ?
            """,
            (
                status,
                message_id,
            ),
        )

        connection.commit()

        return cursor.rowcount > 0
    
    
def start_call(call_sid, stream_sid=None):
    """
    Create a database record when a Twilio call begins.

    Twilio's Call SID uniquely identifies the telephone call.
    The Stream SID identifies the Media Stream carrying the
    real-time audio for that call.
    """

    started_at = datetime.now(timezone.utc).isoformat()

    with get_connection() as connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO calls (
                call_sid,
                stream_sid,
                started_at
            )
            VALUES (?, ?, ?)
            """,
            (
                call_sid,
                stream_sid,
                started_at,
            ),
        )

        connection.commit()


def end_call(call_sid, outcome="completed"):
    """
    Mark a call as finished and calculate its duration.

    Duration is calculated locally from our recorded start and end
    timestamps. Later we can compare this with Twilio's own billing
    duration if needed.
    """

    ended_at = datetime.now(timezone.utc)

    with get_connection() as connection:
        connection.row_factory = sqlite3.Row

        call = connection.execute(
            """
            SELECT started_at
            FROM calls
            WHERE call_sid = ?
            """,
            (call_sid,),
        ).fetchone()

        if not call:
            return False

        started_at = datetime.fromisoformat(
            call["started_at"]
        )

        duration_seconds = int(
            (ended_at - started_at).total_seconds()
        )

        connection.execute(
            """
            UPDATE calls
            SET
                ended_at = ?,
                duration_seconds = ?,
                outcome = ?
            WHERE call_sid = ?
            """,
            (
                ended_at.isoformat(),
                duration_seconds,
                outcome,
                call_sid,
            ),
        )

        connection.commit()

        return True


def get_calls():
    """
    Return recorded calls, newest first.

    This will eventually power cost and usage reporting.
    """

    with get_connection() as connection:
        connection.row_factory = sqlite3.Row

        rows = connection.execute(
            """
            SELECT
                id,
                call_sid,
                stream_sid,
                started_at,
                ended_at,
                duration_seconds,
                outcome,
                input_tokens,
                output_tokens,
                input_audio_tokens,
                output_audio_tokens,
                cached_input_tokens,
                cached_text_input_tokens,
                cached_audio_input_tokens
            FROM calls
            ORDER BY id DESC
            """
        ).fetchall()

        calls = []

        for row in rows:
            call = dict(row)

            # Add calculated cost information to the API response.
            call.update(
                calculate_call_cost(call)
            )

            calls.append(call)

        return calls
    

def add_call_usage(
    call_sid,
    input_tokens=0,
    output_tokens=0,
    input_audio_tokens=0,
    output_audio_tokens=0,
    cached_input_tokens=0,
    cached_text_input_tokens=0,
    cached_audio_input_tokens=0,
):
    """
    Add OpenAI usage from one completed model response to a call.

    A single telephone call can contain many AI responses, so usage
    must be accumulated rather than overwritten.
    """

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE calls
            SET
                input_tokens = input_tokens + ?,
                output_tokens = output_tokens + ?,
                input_audio_tokens = input_audio_tokens + ?,
                output_audio_tokens = output_audio_tokens + ?,
                cached_input_tokens = cached_input_tokens + ?,
                cached_text_input_tokens = cached_text_input_tokens + ?,
                cached_audio_input_tokens = cached_audio_input_tokens + ?
            WHERE call_sid = ?
            """,
            (
                input_tokens,
                output_tokens,
                input_audio_tokens,
                output_audio_tokens,
                cached_input_tokens,
                cached_text_input_tokens,
                cached_audio_input_tokens,
                call_sid,
            ),
        )

        connection.commit()