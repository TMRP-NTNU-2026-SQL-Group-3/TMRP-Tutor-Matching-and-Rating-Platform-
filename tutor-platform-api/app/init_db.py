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

from app.shared.infrastructure.config import Settings, settings as _default_settings
from app.shared.infrastructure.security import hash_password

logger = logging.getLogger("app.init_db")

# ──────────────────────────────────────────────
# PostgreSQL Schema DDL
# All DEFAULTs are declared inline on each CREATE TABLE.
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
    -- 1:1 對應 users 表，刪除 user 時連同 tutor 設定一併移除
    user_id             INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
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
    -- 子女屬於家長帳號；家長若被刪則子女資料一併清除
    parent_user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
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
    -- tutor 被刪 → 教授科目連帶刪除；subject 受 RESTRICT 保護
    -- （要刪一個科目前，須先確認沒有家教仍掛著該科目）。
    tutor_id    INTEGER       NOT NULL REFERENCES tutors(tutor_id) ON DELETE CASCADE,
    subject_id  INTEGER       NOT NULL REFERENCES subjects(subject_id) ON DELETE RESTRICT,
    hourly_rate NUMERIC(12,2) NOT NULL,
    PRIMARY KEY (tutor_id, subject_id)
);

CREATE TABLE IF NOT EXISTS tutor_availability (
    availability_id SERIAL PRIMARY KEY,
    tutor_id        INTEGER   NOT NULL REFERENCES tutors(tutor_id) ON DELETE CASCADE,
    day_of_week     SMALLINT  NOT NULL CHECK (day_of_week >= 0 AND day_of_week <= 6),
    start_time      TIME NOT NULL,
    end_time        TIME NOT NULL,
    CONSTRAINT chk_tutor_availability_time_order CHECK (start_time < end_time)
);

CREATE TABLE IF NOT EXISTS conversations (
    conversation_id SERIAL PRIMARY KEY,
    -- 使用者刪除 → 對話一併移除（含 messages，靠 messages.conversation_id 的 CASCADE）
    user_a_id       INTEGER     NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    user_b_id       INTEGER     NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_message_at TIMESTAMPTZ,
    CONSTRAINT chk_conversations_pair_order CHECK (user_a_id < user_b_id)
);

CREATE TABLE IF NOT EXISTS messages (
    message_id      SERIAL PRIMARY KEY,
    conversation_id INTEGER     NOT NULL REFERENCES conversations(conversation_id) ON DELETE CASCADE,
    -- 使用者一旦刪除，留下的 message 與其對話多半同步消失，這裡也設 CASCADE
    sender_user_id  INTEGER     NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    content         TEXT        NOT NULL,
    sent_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS matches (
    match_id          SERIAL PRIMARY KEY,
    -- matches 是法律與計費相關的紀錄，禁止因刪除 tutor/student 而靜默消失。
    -- 若有清除需求，必須先處置 matches（例如顯式刪除或 anonymize）。
    tutor_id          INTEGER       NOT NULL REFERENCES tutors(tutor_id) ON DELETE RESTRICT,
    student_id        INTEGER       NOT NULL REFERENCES students(student_id) ON DELETE RESTRICT,
    subject_id        INTEGER       NOT NULL REFERENCES subjects(subject_id) ON DELETE RESTRICT,
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
    -- terminated_by 只是稽核欄位，使用者刪除時設回 NULL 即可，不需牽動 match
    terminated_by     INTEGER       REFERENCES users(user_id) ON DELETE SET NULL,
    termination_reason TEXT,
    created_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id          SERIAL PRIMARY KEY,
    -- 上課紀錄屬於 match：match 被刪 → sessions 一同清除
    match_id            INTEGER          NOT NULL REFERENCES matches(match_id) ON DELETE CASCADE,
    session_date        TIMESTAMPTZ      NOT NULL,
    -- 既往使用 DOUBLE PRECISION 會把 0.1 + 0.2 變成 0.30000000000000004，
    -- 而 hours 直接乘上 hourly_rate 影響家教收入；改為定點小數。
    hours               NUMERIC(10,2)    NOT NULL CHECK (hours > 0),
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
    session_id INTEGER     NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    field_name VARCHAR(50) NOT NULL,
    old_value  TEXT,
    new_value  TEXT,
    edited_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS exams (
    exam_id           SERIAL PRIMARY KEY,
    -- 學生被刪 → 考試紀錄一同移除
    student_id        INTEGER          NOT NULL REFERENCES students(student_id) ON DELETE CASCADE,
    -- 科目刪除受 RESTRICT 保護（與 tutor_subjects 一致）
    subject_id        INTEGER          NOT NULL REFERENCES subjects(subject_id) ON DELETE RESTRICT,
    -- 「誰加的」是稽核欄位 + update 權限判斷依據，必須非空。
    -- 用 RESTRICT 防止直接刪除作者；若真要刪 user，先把該人寫的 exam 處理掉。
    -- （SET NULL 會讓 list/list-by-tutor 的 INNER JOIN 漏掉匿名化的紀錄，不採用。）
    added_by_user_id  INTEGER          NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT,
    exam_date         TIMESTAMPTZ      NOT NULL,
    -- exam_type 來自前端固定列舉（src/views/tutor/MatchDetailView.vue 的 <select>），
    -- 以 CHECK 取代 ENUM 以維持 schema 簡單、可遷移；保持與 UI 顯示文字一致
    -- 才不會在 INSERT 階段違反 constraint。
    exam_type         VARCHAR(20)      NOT NULL
        CHECK (exam_type IN ('段考','小考','模擬考','其他')),
    -- score 仍接受小數但不涉及金流，保留 DOUBLE PRECISION
    score             DOUBLE PRECISION NOT NULL,
    visible_to_parent BOOLEAN          DEFAULT FALSE,
    created_at        TIMESTAMPTZ      NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS reviews (
    review_id          SERIAL PRIMARY KEY,
    -- match 一旦消失，所有與之相關的評價都失去依據
    match_id           INTEGER     NOT NULL REFERENCES matches(match_id) ON DELETE CASCADE,
    -- 評論者必須非空：list_by_match / list_by_tutor 以 INNER JOIN reviewer
    -- 取顯示名稱，欄位若 NULL 該筆評價會在前端列表整列消失。
    -- 用 RESTRICT 強制刪除使用者前必須先處置其評價。
    reviewer_user_id   INTEGER     NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT,
    review_type        VARCHAR(20) NOT NULL
        CHECK (review_type IN ('parent_to_tutor','tutor_to_parent','tutor_to_student')),
    -- 評分維度 1..5，避免應用層忘了驗證寫入越界值
    rating_1           SMALLINT    NOT NULL CHECK (rating_1 BETWEEN 1 AND 5),
    rating_2           SMALLINT    NOT NULL CHECK (rating_2 BETWEEN 1 AND 5),
    rating_3           SMALLINT             CHECK (rating_3 IS NULL OR rating_3 BETWEEN 1 AND 5),
    rating_4           SMALLINT             CHECK (rating_4 IS NULL OR rating_4 BETWEEN 1 AND 5),
    personality_comment TEXT,
    comment            TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ,
    is_locked          BOOLEAN     DEFAULT FALSE
);

-- 認證 / 限流支援表（多 worker 部署下需共享狀態，避免 in-memory 漂移）
CREATE TABLE IF NOT EXISTS refresh_token_blacklist (
    jti        VARCHAR(64)  PRIMARY KEY,
    expires_at TIMESTAMPTZ  NOT NULL,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS rate_limit_hits (
    id         BIGSERIAL    PRIMARY KEY,
    bucket_key VARCHAR(255) NOT NULL,
    hit_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
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
CREATE INDEX IF NOT EXISTS idx_rl_bucket_hit_at       ON rate_limit_hits (bucket_key, hit_at);
CREATE INDEX IF NOT EXISTS idx_rt_blacklist_exp       ON refresh_token_blacklist (expires_at);

-- FK 補強索引：CASCADE/SET NULL 會在父表刪列時掃這些 FK 欄位，沒索引時會 seq scan
CREATE INDEX IF NOT EXISTS idx_messages_sender        ON messages (sender_user_id);
CREATE INDEX IF NOT EXISTS idx_exams_added_by         ON exams (added_by_user_id);
CREATE INDEX IF NOT EXISTS idx_exams_subject          ON exams (subject_id);
CREATE INDEX IF NOT EXISTS idx_reviews_reviewer       ON reviews (reviewer_user_id);
-- session_date 常用於日期區間查詢；放在 match_id 後面同時支援單表掃與「該 match 的歷次上課」
CREATE INDEX IF NOT EXISTS idx_sessions_match_date    ON sessions (match_id, session_date);
CREATE INDEX IF NOT EXISTS idx_session_edit_logs_sess ON session_edit_logs (session_id);
CREATE INDEX IF NOT EXISTS idx_matches_terminated_by  ON matches (terminated_by);

-- Derived views: centralise tutor-aggregate SQL that was inlined across
-- several repositories (catalog, analytics, search). CREATE OR REPLACE so
-- schema re-runs keep the view in sync.
CREATE OR REPLACE VIEW v_tutor_ratings AS
SELECT m.tutor_id,
       AVG(r.rating_1) AS avg_r1,
       AVG(r.rating_2) AS avg_r2,
       AVG(r.rating_3) AS avg_r3,
       AVG(r.rating_4) AS avg_r4,
       COUNT(*)        AS review_count,
       -- Overall rating = mean of whichever dimensions were rated.
       COALESCE(
         (COALESCE(AVG(r.rating_1),0)+COALESCE(AVG(r.rating_2),0)
         +COALESCE(AVG(r.rating_3),0)+COALESCE(AVG(r.rating_4),0))
         / NULLIF(
           (CASE WHEN AVG(r.rating_1) IS NOT NULL THEN 1 ELSE 0 END
           +CASE WHEN AVG(r.rating_2) IS NOT NULL THEN 1 ELSE 0 END
           +CASE WHEN AVG(r.rating_3) IS NOT NULL THEN 1 ELSE 0 END
           +CASE WHEN AVG(r.rating_4) IS NOT NULL THEN 1 ELSE 0 END), 0)
       , 0) AS avg_rating
FROM reviews r
INNER JOIN matches m ON r.match_id = m.match_id
WHERE r.review_type = 'parent_to_tutor'
GROUP BY m.tutor_id;

CREATE OR REPLACE VIEW v_tutor_active_students AS
SELECT tutor_id, COUNT(*) AS active_count
FROM matches
WHERE status IN ('active', 'trial')
GROUP BY tutor_id;
"""

# ──────────────────────────────────────────────
# Subject seed data (display names stay in Chinese — user-facing)
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
# Functions
# ──────────────────────────────────────────────


def create_schema(conn) -> None:
    """Create all 13 tables, indexes and foreign keys (idempotent via IF NOT EXISTS)."""
    cursor = conn.cursor()
    cursor.execute(SCHEMA_DDL)
    conn.commit()
    logger.info("  Tables and indexes created")


def seed_subjects(conn) -> None:
    """Seed the subjects table; skip if rows already exist."""
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM subjects")
    if cursor.fetchone()[0] > 0:
        logger.info("  Subjects already present; skipping seed")
        return

    for name, category in SEED_SUBJECTS:
        cursor.execute(
            "INSERT INTO subjects (subject_name, category) VALUES (%s, %s)",
            (name, category),
        )
    conn.commit()
    logger.info("  Seeded %d subject rows", len(SEED_SUBJECTS))


def ensure_admin_user(conn, settings: Settings | None = None) -> None:
    """Ensure the admin account exists; create it on first boot."""
    if settings is None:
        settings = _default_settings

    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) FROM users WHERE username = %s",
        (settings.admin_username,),
    )

    if cursor.fetchone()[0] > 0:
        logger.info("  Admin account already exists; skipping creation")
        return

    hashed = hash_password(settings.admin_password)

    cursor.execute(
        "INSERT INTO users (username, password_hash, role, display_name) "
        "VALUES (%s, %s, 'admin', %s)",
        (settings.admin_username, hashed, settings.admin_username),
    )
    conn.commit()
    logger.info("  Admin account created: %s", settings.admin_username)


def verify_bootstrap(conn, settings: Settings | None = None) -> None:
    """Smoke-test that the database came up in the expected shape.

    Cheaper to fail loud at boot than to discover a missing admin account or an
    empty subjects table on the first user request. Raises RuntimeError so the
    lifespan handler in `app.main` aborts startup, matching the existing
    "refuse to serve in a half-initialized state" policy.
    """
    if settings is None:
        settings = _default_settings

    cursor = conn.cursor()

    # Admin must exist and have role=admin (defends against an operator running
    # ensure_admin_user with an unprivileged role inserted via raw SQL).
    cursor.execute(
        "SELECT role FROM users WHERE username = %s",
        (settings.admin_username,),
    )
    row = cursor.fetchone()
    if row is None:
        raise RuntimeError(f"bootstrap check failed: admin user '{settings.admin_username}' missing")
    if row[0] != "admin":
        raise RuntimeError(
            f"bootstrap check failed: user '{settings.admin_username}' has role={row[0]!r}, expected 'admin'"
        )

    cursor.execute("SELECT COUNT(*) FROM subjects")
    subject_count = cursor.fetchone()[0]
    if subject_count < len(SEED_SUBJECTS):
        raise RuntimeError(
            f"bootstrap check failed: only {subject_count} subjects seeded "
            f"(expected at least {len(SEED_SUBJECTS)})"
        )

    logger.info("  Bootstrap verification passed (admin ok, %d subjects)", subject_count)


def initialize_database() -> None:
    """Run the full database-initialization flow end-to-end."""
    settings = _default_settings

    logger.info("===== Database initialization start =====")

    conn = psycopg2.connect(settings.database_url)
    try:
        logger.info("[1/4] Creating tables and indexes...")
        create_schema(conn)

        logger.info("[2/4] Seeding reference data...")
        seed_subjects(conn)

        logger.info("[3/4] Creating admin account...")
        ensure_admin_user(conn, settings)

        logger.info("[4/4] Verifying bootstrap state...")
        verify_bootstrap(conn, settings)
    finally:
        conn.close()

    logger.info("===== Database initialization complete =====")
