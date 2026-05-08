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
from app.teaching.domain.constants import EXAM_TYPES

# Render the exam_type CHECK-constraint IN-list from the single-source tuple
# in app.teaching.domain.constants. Values are SQL-escaped by doubling single
# quotes — they are short hand-curated labels, never user-supplied.
_EXAM_TYPES_SQL = ", ".join(
    "'" + t.replace("'", "''") + "'" for t in EXAM_TYPES
)

logger = logging.getLogger("app.init_db")

# ──────────────────────────────────────────────
# PostgreSQL Schema DDL
# All DEFAULTs are declared inline on each CREATE TABLE.
# ──────────────────────────────────────────────

SCHEMA_DDL = f"""
CREATE TABLE IF NOT EXISTS users (
    user_id       SERIAL PRIMARY KEY,
    username      VARCHAR(100) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role          VARCHAR(10)  NOT NULL,
    display_name  VARCHAR(100) NOT NULL,
    phone         VARCHAR(30),
    email         VARCHAR(100),
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_users_role         CHECK (role IN ('parent', 'tutor', 'admin')),
    CONSTRAINT chk_users_email_format CHECK (email IS NULL OR email LIKE '%@%')
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
    category     VARCHAR(30) NOT NULL,
    CONSTRAINT chk_subject_category CHECK (category IN ('math', 'science', 'lang', 'other'))
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
    -- D3: terminated_by is an audit field. Previously ON DELETE SET NULL,
    -- which silently erased who terminated the match when the acting user
    -- was deleted. RESTRICT forces the admin to explicitly reassign or
    -- anonymize the audit trail before removing such a user.
    terminated_by     INTEGER       REFERENCES users(user_id) ON DELETE RESTRICT,
    termination_reason TEXT,
    -- D4: Denormalized parent owner to avoid JOIN through students on every
    -- parent-scoped query. Maintained by trg_matches_set_parent (BEFORE
    -- INSERT/UPDATE OF student_id) and trg_students_propagate_parent
    -- (AFTER UPDATE OF students.parent_user_id).
    parent_user_id    INTEGER       REFERENCES users(user_id) ON DELETE RESTRICT,
    created_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_matches_status CHECK (status IN ('pending','trial','active','paused',
                                                    'terminating','ended','cancelled','rejected'))
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
        CHECK (exam_type IN ({_EXAM_TYPES_SQL})),
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

-- SEC-06: password reuse prevention; stores the last 5 hashes per user.
CREATE TABLE IF NOT EXISTS password_history (
    history_id    SERIAL       PRIMARY KEY,
    user_id       INTEGER      NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    password_hash VARCHAR(255) NOT NULL,
    changed_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- SEC-12: DB-backed idempotency for match creation. An in-process dict is not
-- shared across workers, so the same Idempotency-Key landing on a different
-- worker sees an empty cache. Storing the key here makes the check consistent
-- regardless of which worker handles the retry.
CREATE TABLE IF NOT EXISTS idempotency_keys (
    idem_key   VARCHAR(128) NOT NULL,
    user_id    INTEGER      NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    match_id   INTEGER      NOT NULL,
    expires_at TIMESTAMPTZ  NOT NULL,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, idem_key)
);
CREATE INDEX IF NOT EXISTS idx_idempotency_expires ON idempotency_keys (expires_at);

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

-- B10: Admin actions (currently just match state transitions) write here so
-- privileged state changes remain reconstructable even after the underlying
-- row has moved on. actor_user_id uses ON DELETE SET NULL to keep the audit
-- trail intact if the admin account is later removed; resource_id is a soft
-- reference only (no FK) because the referenced row may itself be deleted.
CREATE TABLE IF NOT EXISTS audit_log (
    audit_id       BIGSERIAL   PRIMARY KEY,
    actor_user_id  INTEGER     REFERENCES users(user_id) ON DELETE SET NULL,
    action         VARCHAR(50) NOT NULL,
    resource_type  VARCHAR(50) NOT NULL,
    resource_id    INTEGER,
    old_value      TEXT,
    new_value      TEXT,
    reason         TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 唯一索引
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username     ON users (username);
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email        ON users (email) WHERE email IS NOT NULL;
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
CREATE INDEX IF NOT EXISTS idx_pw_history_user        ON password_history (user_id, changed_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_resource     ON audit_log (resource_type, resource_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_actor        ON audit_log (actor_user_id, created_at);

-- FK 補強索引：CASCADE/SET NULL 會在父表刪列時掃這些 FK 欄位，沒索引時會 seq scan
-- DB-C01/C02: single-column indexes on conversations.user_a_id / user_b_id.
-- The composite unique idx_conversations_pair (user_a_id, user_b_id) requires
-- both columns (AND), so the OR query in postgres_message_repo forces a full
-- table scan without these. They also support ON DELETE CASCADE scans from users.
CREATE INDEX IF NOT EXISTS idx_conversations_user_a   ON conversations (user_a_id);
CREATE INDEX IF NOT EXISTS idx_conversations_user_b   ON conversations (user_b_id);
CREATE INDEX IF NOT EXISTS idx_messages_sender        ON messages (sender_user_id);
CREATE INDEX IF NOT EXISTS idx_exams_added_by         ON exams (added_by_user_id);
CREATE INDEX IF NOT EXISTS idx_exams_subject          ON exams (subject_id);
CREATE INDEX IF NOT EXISTS idx_reviews_reviewer       ON reviews (reviewer_user_id);
-- session_date 常用於日期區間查詢；放在 match_id 後面同時支援單表掃與「該 match 的歷次上課」
CREATE INDEX IF NOT EXISTS idx_sessions_match_date    ON sessions (match_id, session_date);
CREATE INDEX IF NOT EXISTS idx_session_edit_logs_sess ON session_edit_logs (session_id);
CREATE INDEX IF NOT EXISTS idx_matches_terminated_by  ON matches (terminated_by);

-- D1: analytics group exams by student and sort chronologically; DESC on
-- exam_date lets "most recent N exams per student" use an index-only path
-- instead of scanning and sorting the full table.
CREATE INDEX IF NOT EXISTS idx_exams_student_date    ON exams (student_id, exam_date DESC);
-- D2: parent-scoped session lists filter on match_id and visible_to_parent
-- together; INCLUDE (session_date) enables index-only scans for the common
-- "session list with dates" response shape without widening the key.
CREATE INDEX IF NOT EXISTS idx_sessions_match_visible ON sessions (match_id, visible_to_parent) INCLUDE (session_date);
-- D4: supports parent-scoped match lookups via the denormalized column.
CREATE INDEX IF NOT EXISTS idx_matches_parent         ON matches (parent_user_id);
-- DB-M02: composite index for the common "list my active matches" query pattern.
CREATE INDEX IF NOT EXISTS idx_matches_parent_status   ON matches (parent_user_id, status);

-- B11: v_tutor_ratings used to be a regular VIEW, so every tutor page
-- re-scanned the full reviews table. Materialising it turns reads into a
-- single-row lookup; the refresh trigger below keeps it current on
-- review write. If an older deployment still has the non-materialised
-- VIEW, drop it before recreating as a materialised view.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_views
        WHERE schemaname = current_schema() AND viewname = 'v_tutor_ratings'
    ) THEN
        DROP VIEW v_tutor_ratings;
    END IF;
END $$;

CREATE MATERIALIZED VIEW IF NOT EXISTS v_tutor_ratings AS
SELECT m.tutor_id,
       AVG(r.rating_1) AS avg_r1,
       AVG(r.rating_2) AS avg_r2,
       AVG(r.rating_3) AS avg_r3,
       AVG(r.rating_4) AS avg_r4,
       COUNT(*)        AS review_count,
       -- Overall rating = mean of whichever dimensions were actually rated.
       -- Only non-NULL dimensions contribute to both numerator and denominator.
       -- Returns NULL (not 0) when no rated reviews exist, so unreviewed tutors
       -- are not ranked below tutors with genuine low scores.
       CASE WHEN COUNT(r.review_id) = 0 THEN NULL ELSE
         (COALESCE(AVG(r.rating_1), 0) + COALESCE(AVG(r.rating_2), 0)
        + COALESCE(AVG(r.rating_3), 0) + COALESCE(AVG(r.rating_4), 0))
        / NULLIF(
            (CASE WHEN AVG(r.rating_1) IS NOT NULL THEN 1 ELSE 0 END)
          + (CASE WHEN AVG(r.rating_2) IS NOT NULL THEN 1 ELSE 0 END)
          + (CASE WHEN AVG(r.rating_3) IS NOT NULL THEN 1 ELSE 0 END)
          + (CASE WHEN AVG(r.rating_4) IS NOT NULL THEN 1 ELSE 0 END)
        , 0)
       END AS avg_rating
FROM reviews r
INNER JOIN matches m ON r.match_id = m.match_id
WHERE r.review_type = 'parent_to_tutor'
GROUP BY m.tutor_id;

-- Unique index required so REFRESH MATERIALIZED VIEW CONCURRENTLY can run
-- without blocking concurrent readers.
CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_tutor_ratings_tutor
    ON v_tutor_ratings (tutor_id);

-- Previously a plain VIEW, scanned by the tutor search / detail hot paths.
-- Converted to a MATERIALIZED VIEW so the group-by over `matches` is not
-- re-executed on every listing request. Refreshed CONCURRENTLY by the
-- trigger below after any write that can change a tutor's active-student
-- count. A unique index on `tutor_id` is required for CONCURRENTLY.
--
-- Migration block: older deployments may still have the plain VIEW. The
-- DO block drops it only if `relkind = 'v'`; if relkind is already 'm'
-- (materialized) we leave it alone and let the CREATE … IF NOT EXISTS
-- below be a no-op. A bare `DROP VIEW IF EXISTS` would error on the
-- second init run because that syntax rejects materialized views.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_class
         WHERE relname = 'v_tutor_active_students'
           AND relkind = 'v'
    ) THEN
        DROP VIEW v_tutor_active_students;
    END IF;
END $$;

CREATE MATERIALIZED VIEW IF NOT EXISTS v_tutor_active_students AS
SELECT tutor_id, COUNT(*) AS active_count
FROM matches
WHERE status IN ('active', 'trial')
GROUP BY tutor_id;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_tutor_active_tutor
    ON v_tutor_active_students (tutor_id);

CREATE OR REPLACE FUNCTION fn_refresh_tutor_active_students() RETURNS TRIGGER AS $fn$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY v_tutor_active_students;
    RETURN NULL;
END;
$fn$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_matches_refresh_active_students ON matches;
CREATE TRIGGER trg_matches_refresh_active_students
    AFTER INSERT OR UPDATE OF status OR DELETE ON matches
    FOR EACH STATEMENT
    EXECUTE FUNCTION fn_refresh_tutor_active_students();

-- B11: Statement-level trigger refreshes the materialised view after any
-- write to reviews. CONCURRENTLY keeps reads unblocked; statement scope
-- means a multi-row batch refreshes once, not per row.
CREATE OR REPLACE FUNCTION fn_refresh_tutor_ratings() RETURNS TRIGGER AS $fn$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY v_tutor_ratings;
    RETURN NULL;
END;
$fn$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_reviews_refresh_ratings ON reviews;
CREATE TRIGGER trg_reviews_refresh_ratings
    AFTER INSERT OR UPDATE OR DELETE ON reviews
    FOR EACH STATEMENT
    EXECUTE FUNCTION fn_refresh_tutor_ratings();

-- D4: keep matches.parent_user_id in sync with the owning student. The
-- BEFORE trigger populates it on INSERT or whenever student_id moves;
-- the AFTER trigger on students fans a parent-ownership change out to
-- every existing match for that student.
CREATE OR REPLACE FUNCTION fn_match_set_parent_user() RETURNS TRIGGER AS $fn$
BEGIN
    SELECT s.parent_user_id
      INTO NEW.parent_user_id
      FROM students s
     WHERE s.student_id = NEW.student_id;
    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_matches_set_parent ON matches;
CREATE TRIGGER trg_matches_set_parent
    BEFORE INSERT OR UPDATE OF student_id ON matches
    FOR EACH ROW
    EXECUTE FUNCTION fn_match_set_parent_user();

CREATE OR REPLACE FUNCTION fn_students_propagate_parent() RETURNS TRIGGER AS $fn$
BEGIN
    IF OLD.parent_user_id IS DISTINCT FROM NEW.parent_user_id THEN
        UPDATE matches
           SET parent_user_id = NEW.parent_user_id
         WHERE student_id = NEW.student_id;
    END IF;
    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_students_propagate_parent ON students;
CREATE TRIGGER trg_students_propagate_parent
    AFTER UPDATE OF parent_user_id ON students
    FOR EACH ROW
    EXECUTE FUNCTION fn_students_propagate_parent();

-- Normalize conversation participant order at the DB layer instead of
-- trusting each caller (repo, admin CSV import, seed script) to sort
-- user_a_id < user_b_id themselves. The CHECK constraint catches the bug,
-- but raising a constraint violation on a non-app insert path is worse
-- UX than transparently swapping the columns before the row reaches the
-- check. Self-conversations (a == b) still fall to the existing CHECK.
CREATE OR REPLACE FUNCTION fn_conversations_order_pair() RETURNS TRIGGER AS $fn$
DECLARE
    tmp INTEGER;
BEGIN
    IF NEW.user_a_id > NEW.user_b_id THEN
        tmp := NEW.user_a_id;
        NEW.user_a_id := NEW.user_b_id;
        NEW.user_b_id := tmp;
    END IF;
    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_conversations_order_pair ON conversations;
CREATE TRIGGER trg_conversations_order_pair
    BEFORE INSERT OR UPDATE OF user_a_id, user_b_id ON conversations
    FOR EACH ROW
    EXECUTE FUNCTION fn_conversations_order_pair();

-- Migration block for databases created before these fixes shipped.
-- CREATE TABLE IF NOT EXISTS does not rewrite existing tables, so any
-- schema change on `matches` needs an explicit ALTER guarded with
-- information_schema / pg_constraint lookups to stay idempotent.
DO $$
DECLARE
    con_action CHAR;
BEGIN
    -- D3: tighten terminated_by from SET NULL to RESTRICT if an older
    -- deployment still has the permissive FK.
    SELECT confdeltype INTO con_action
      FROM pg_constraint
     WHERE conrelid = 'matches'::regclass
       AND conname  = 'matches_terminated_by_fkey';
    IF con_action IS NOT NULL AND con_action <> 'r' THEN
        ALTER TABLE matches DROP CONSTRAINT matches_terminated_by_fkey;
        ALTER TABLE matches
            ADD CONSTRAINT matches_terminated_by_fkey
            FOREIGN KEY (terminated_by) REFERENCES users(user_id)
            ON DELETE RESTRICT;
    END IF;
END $$;

-- D4: add the denormalised column for older databases, then backfill
-- from the owning student. The BEFORE trigger uses UPDATE OF student_id,
-- so this direct UPDATE will not recurse through it.
ALTER TABLE matches
    ADD COLUMN IF NOT EXISTS parent_user_id INTEGER
    REFERENCES users(user_id) ON DELETE RESTRICT;

UPDATE matches m
   SET parent_user_id = s.parent_user_id
  FROM students s
 WHERE s.student_id = m.student_id
   AND m.parent_user_id IS NULL;

-- DB-L01: widen tight VARCHAR columns for existing databases.
-- CREATE TABLE IF NOT EXISTS does not alter existing columns, so
-- explicit ALTERs are needed for deployments created before the widening.
ALTER TABLE users ALTER COLUMN username      TYPE VARCHAR(100);
ALTER TABLE users ALTER COLUMN display_name  TYPE VARCHAR(100);
ALTER TABLE users ALTER COLUMN phone         TYPE VARCHAR(30);
ALTER TABLE subjects ALTER COLUMN category   TYPE VARCHAR(30);

-- I-07 / I-14: backfill CHECK constraints for databases created before these
-- were added to the CREATE TABLE statements. The DO block is idempotent.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conrelid = 'users'::regclass AND conname = 'chk_users_role'
    ) THEN
        ALTER TABLE users ADD CONSTRAINT chk_users_role
            CHECK (role IN ('parent', 'tutor', 'admin'));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conrelid = 'users'::regclass AND conname = 'chk_users_email_format'
    ) THEN
        ALTER TABLE users ADD CONSTRAINT chk_users_email_format
            CHECK (email IS NULL OR email LIKE '%@%');
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conrelid = 'matches'::regclass AND conname = 'chk_matches_status'
    ) THEN
        ALTER TABLE matches ADD CONSTRAINT chk_matches_status
            CHECK (status IN ('pending','trial','active','paused',
                              'terminating','ended','cancelled','rejected'));
    END IF;
END $$;
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


# Stable 64-bit key for the bootstrap advisory lock. Used by run_bootstrap()
# below to serialise schema creation + seed + admin-user creation across
# concurrent uvicorn workers. Any constant works.
_BOOTSTRAP_LOCK_KEY = 0x544D5250_424F4F54  # "TMRP" "BOOT"


def create_schema(conn) -> None:
    """Create all 13 tables, indexes and foreign keys (idempotent via IF NOT EXISTS)."""
    cursor = conn.cursor()
    cursor.execute(SCHEMA_DDL)
    conn.commit()
    logger.info("  Tables and indexes created")


def run_bootstrap(conn, settings: Settings | None = None) -> None:
    """Run create_schema + seed_subjects + ensure_admin_user + verify_bootstrap
    under a Postgres advisory lock.

    Why the lock: with `uvicorn --workers N`, every worker runs lifespan
    startup and would otherwise execute the full DDL bundle concurrently.
    `CREATE TABLE IF NOT EXISTS`, `ALTER TABLE ... ADD CONSTRAINT` and the
    seed/admin SELECT-then-INSERT pairs are not atomic across sessions, so
    concurrent runs can deadlock, raise duplicate_object / "tuple
    concurrently updated", or insert duplicate rows — killing one worker
    and triggering a supervisor restart. The advisory lock serialises all
    workers; second-and-later runs find the schema already in place and
    no-op via the existing IF NOT EXISTS / SELECT-COUNT guards.
    """
    cursor = conn.cursor()
    cursor.execute("SELECT pg_advisory_lock(%s)", (_BOOTSTRAP_LOCK_KEY,))
    try:
        create_schema(conn)
        seed_subjects(conn)
        ensure_admin_user(conn, settings)
        verify_bootstrap(conn, settings)
    finally:
        cursor.execute("SELECT pg_advisory_unlock(%s)", (_BOOTSTRAP_LOCK_KEY,))
        conn.commit()


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
