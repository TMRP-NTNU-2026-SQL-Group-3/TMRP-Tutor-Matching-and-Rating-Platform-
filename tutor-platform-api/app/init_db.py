"""
資料庫初始化模組（PostgreSQL）

提供以下功能：
1. 建立 13 張資料表（含 DEFAULT 子句）
2. 建立唯一索引與效能索引
3. 寫入科目種子資料
4. 建立管理員帳號
"""

import logging

import psycopg2

from app.config import Settings, settings as _default_settings
from app.utils.security import hash_password

logger = logging.getLogger("app.init_db")

# ──────────────────────────────────────────────
# PostgreSQL Schema DDL
# 所有 DEFAULT 直接在 CREATE TABLE 中定義
# ──────────────────────────────────────────────

SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS users (
    user_id       SERIAL PRIMARY KEY,
    username      VARCHAR(50)  NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role          VARCHAR(10)  NOT NULL,
    display_name  VARCHAR(50)  NOT NULL,
    phone         VARCHAR(20),
    email         VARCHAR(100),
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS tutors (
    tutor_id            SERIAL PRIMARY KEY,
    user_id             INTEGER NOT NULL REFERENCES users(user_id),
    university          VARCHAR(50),
    department          VARCHAR(50),
    grade_year          SMALLINT,
    self_intro          TEXT,
    teaching_experience TEXT,
    max_students        SMALLINT     DEFAULT 5,
    show_university     BOOLEAN      DEFAULT TRUE,
    show_department     BOOLEAN      DEFAULT TRUE,
    show_grade_year     BOOLEAN      DEFAULT TRUE,
    show_hourly_rate    BOOLEAN      DEFAULT TRUE,
    show_subjects       BOOLEAN      DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS students (
    student_id     SERIAL PRIMARY KEY,
    parent_user_id INTEGER NOT NULL REFERENCES users(user_id),
    name           VARCHAR(50) NOT NULL,
    school         VARCHAR(50),
    grade          VARCHAR(20),
    target_school  VARCHAR(50),
    parent_phone   VARCHAR(20),
    notes          TEXT
);

CREATE TABLE IF NOT EXISTS subjects (
    subject_id   SERIAL PRIMARY KEY,
    subject_name VARCHAR(30) NOT NULL,
    category     VARCHAR(20) NOT NULL
);

CREATE TABLE IF NOT EXISTS tutor_subjects (
    tutor_id    INTEGER       NOT NULL REFERENCES tutors(tutor_id),
    subject_id  INTEGER       NOT NULL REFERENCES subjects(subject_id),
    hourly_rate NUMERIC(12,2) NOT NULL,
    PRIMARY KEY (tutor_id, subject_id)
);

CREATE TABLE IF NOT EXISTS tutor_availability (
    availability_id SERIAL PRIMARY KEY,
    tutor_id        INTEGER   NOT NULL REFERENCES tutors(tutor_id),
    day_of_week     SMALLINT  NOT NULL CHECK (day_of_week >= 0 AND day_of_week <= 6),
    start_time      TIME NOT NULL,
    end_time        TIME NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
    conversation_id SERIAL PRIMARY KEY,
    user_a_id       INTEGER     NOT NULL REFERENCES users(user_id),
    user_b_id       INTEGER     NOT NULL REFERENCES users(user_id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_message_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS messages (
    message_id      SERIAL PRIMARY KEY,
    conversation_id INTEGER     NOT NULL REFERENCES conversations(conversation_id),
    sender_user_id  INTEGER     NOT NULL REFERENCES users(user_id),
    content         TEXT        NOT NULL,
    sent_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS matches (
    match_id          SERIAL PRIMARY KEY,
    tutor_id          INTEGER       NOT NULL REFERENCES tutors(tutor_id),
    student_id        INTEGER       NOT NULL REFERENCES students(student_id),
    subject_id        INTEGER       NOT NULL REFERENCES subjects(subject_id),
    status            VARCHAR(15)   NOT NULL DEFAULT 'pending',
    invite_message    TEXT,
    want_trial        BOOLEAN       DEFAULT FALSE,
    hourly_rate       NUMERIC(12,2),
    sessions_per_week SMALLINT,
    start_date        TIMESTAMPTZ,
    end_date          TIMESTAMPTZ,
    penalty_amount    NUMERIC(12,2),
    trial_price       NUMERIC(12,2),
    trial_count       SMALLINT,
    contract_notes    TEXT,
    terminated_by     INTEGER       REFERENCES users(user_id),
    termination_reason TEXT,
    created_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id          SERIAL PRIMARY KEY,
    match_id            INTEGER          NOT NULL REFERENCES matches(match_id),
    session_date        TIMESTAMPTZ      NOT NULL,
    hours               DOUBLE PRECISION NOT NULL,
    content_summary     TEXT             NOT NULL,
    homework            TEXT,
    student_performance TEXT,
    next_plan           TEXT,
    visible_to_parent   BOOLEAN          DEFAULT FALSE,
    created_at          TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ      NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS session_edit_logs (
    log_id     SERIAL PRIMARY KEY,
    session_id INTEGER     NOT NULL REFERENCES sessions(session_id),
    field_name VARCHAR(50) NOT NULL,
    old_value  TEXT,
    new_value  TEXT,
    edited_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS exams (
    exam_id           SERIAL PRIMARY KEY,
    student_id        INTEGER          NOT NULL REFERENCES students(student_id),
    subject_id        INTEGER          NOT NULL REFERENCES subjects(subject_id),
    added_by_user_id  INTEGER          NOT NULL REFERENCES users(user_id),
    exam_date         TIMESTAMPTZ      NOT NULL,
    exam_type         VARCHAR(20)      NOT NULL,
    score             DOUBLE PRECISION NOT NULL,
    visible_to_parent BOOLEAN          DEFAULT FALSE,
    created_at        TIMESTAMPTZ      NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS reviews (
    review_id          SERIAL PRIMARY KEY,
    match_id           INTEGER     NOT NULL REFERENCES matches(match_id),
    reviewer_user_id   INTEGER     NOT NULL REFERENCES users(user_id),
    review_type        VARCHAR(20) NOT NULL,
    rating_1           SMALLINT    NOT NULL,
    rating_2           SMALLINT    NOT NULL,
    rating_3           SMALLINT,
    rating_4           SMALLINT,
    personality_comment TEXT,
    comment            TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ,
    is_locked          BOOLEAN     DEFAULT FALSE
);

-- 唯一索引
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username     ON users (username);
CREATE UNIQUE INDEX IF NOT EXISTS idx_subjects_name      ON subjects (subject_name);
CREATE UNIQUE INDEX IF NOT EXISTS idx_tutors_user_id     ON tutors (user_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_conversations_pair ON conversations (user_a_id, user_b_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_reviews_unique     ON reviews (match_id, reviewer_user_id, review_type);

-- 效能索引
CREATE INDEX IF NOT EXISTS idx_students_parent        ON students (parent_user_id);
CREATE INDEX IF NOT EXISTS idx_tutor_avail_tutor      ON tutor_availability (tutor_id);
CREATE INDEX IF NOT EXISTS idx_messages_conv          ON messages (conversation_id);
CREATE INDEX IF NOT EXISTS idx_messages_sent_at       ON messages (sent_at);
CREATE INDEX IF NOT EXISTS idx_matches_tutor          ON matches (tutor_id);
CREATE INDEX IF NOT EXISTS idx_matches_student        ON matches (student_id);
CREATE INDEX IF NOT EXISTS idx_matches_status         ON matches (status);
CREATE INDEX IF NOT EXISTS idx_sessions_match         ON sessions (match_id);
CREATE INDEX IF NOT EXISTS idx_exams_student          ON exams (student_id);
CREATE INDEX IF NOT EXISTS idx_reviews_match          ON reviews (match_id);
CREATE INDEX IF NOT EXISTS idx_conv_last_msg          ON conversations (last_message_at);
CREATE INDEX IF NOT EXISTS idx_tutor_subjects_subject ON tutor_subjects (subject_id);
CREATE INDEX IF NOT EXISTS idx_sessions_created       ON sessions (created_at);
CREATE INDEX IF NOT EXISTS idx_matches_status_updated ON matches (status, updated_at);
"""

# ──────────────────────────────────────────────
# 科目種子資料
# ──────────────────────────────────────────────

SEED_SUBJECTS: list[tuple[str, str]] = [
    ("數學", "math"),
    ("物理", "science"),
    ("化學", "science"),
    ("生物", "science"),
    ("地球科學", "science"),
    ("國文", "lang"),
    ("英文", "lang"),
    ("日文", "lang"),
    ("歷史", "other"),
    ("地理", "other"),
    ("公民", "other"),
    ("程式設計", "other"),
]


# ──────────────────────────────────────────────
# 函式
# ──────────────────────────────────────────────


def create_schema(conn) -> None:
    """建立全部 13 張資料表、索引與外鍵（IF NOT EXISTS 確保冪等性）。"""
    cursor = conn.cursor()
    cursor.execute(SCHEMA_DDL)
    conn.commit()
    logger.info("  資料表與索引建立完成")


def seed_subjects(conn) -> None:
    """寫入科目種子資料（若已有資料則跳過）。"""
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM subjects")
    if cursor.fetchone()[0] > 0:
        logger.info("  科目資料已存在，跳過種子寫入")
        return

    for name, category in SEED_SUBJECTS:
        cursor.execute(
            "INSERT INTO subjects (subject_name, category) VALUES (%s, %s)",
            (name, category),
        )
    conn.commit()
    logger.info("  寫入 %d 筆科目種子資料", len(SEED_SUBJECTS))


def ensure_admin_user(conn, settings: Settings | None = None) -> None:
    """確保管理員帳號存在，若不存在則建立。"""
    if settings is None:
        settings = _default_settings

    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) FROM users WHERE username = %s",
        (settings.admin_username,),
    )

    if cursor.fetchone()[0] > 0:
        logger.info("  管理員帳號已存在，跳過建立")
        return

    hashed = hash_password(settings.admin_password)

    cursor.execute(
        "INSERT INTO users (username, password_hash, role, display_name) "
        "VALUES (%s, %s, 'admin', %s)",
        (settings.admin_username, hashed, settings.admin_username),
    )
    conn.commit()
    logger.info("  管理員帳號建立完成: %s", settings.admin_username)


def initialize_database() -> None:
    """執行完整的資料庫初始化流程。"""
    settings = _default_settings

    logger.info("===== 資料庫初始化開始 =====")

    conn = psycopg2.connect(settings.database_url)
    try:
        logger.info("[1/3] 建立資料表與索引...")
        create_schema(conn)

        logger.info("[2/3] 寫入種子資料...")
        seed_subjects(conn)

        logger.info("[3/3] 建立管理員帳號...")
        ensure_admin_user(conn, settings)
    finally:
        conn.close()

    logger.info("===== 資料庫初始化完成 =====")
