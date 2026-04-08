"""
資料庫初始化模組

提供以下功能：
1. 建立 .accdb 資料庫檔案（透過 VBScript + ADOX，無需額外 Python 套件）
2. 建立 13 張資料表
3. 透過 DAO 設定欄位預設值（Access ODBC DDL 不支援 DEFAULT 子句）
4. 建立唯一索引與效能索引
5. 建立外鍵約束
6. 寫入科目種子資料
7. 建立管理員帳號
"""

import logging
import os
import subprocess
import tempfile

import pyodbc

from app.config import Settings, settings as _default_settings
from app.utils.security import hash_password

logger = logging.getLogger("app.init_db")

# ──────────────────────────────────────────────
# 資料表 DDL
# Access ODBC 的 CREATE TABLE 不支援 DEFAULT 子句，
# 預設值改由 set_column_defaults() 透過 DAO COM 設定。
# ──────────────────────────────────────────────

TABLE_DDL: list[tuple[str, str]] = [
    (
        "Users",
        """
        CREATE TABLE Users (
            user_id AUTOINCREMENT PRIMARY KEY,
            username VARCHAR(50) NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            role VARCHAR(10) NOT NULL,
            display_name VARCHAR(50) NOT NULL,
            phone VARCHAR(20),
            email VARCHAR(100),
            created_at DATETIME NOT NULL
        )
        """,
    ),
    (
        "Tutors",
        """
        CREATE TABLE Tutors (
            tutor_id AUTOINCREMENT PRIMARY KEY,
            user_id LONG NOT NULL,
            university VARCHAR(50),
            department VARCHAR(50),
            grade_year SHORT,
            self_intro MEMO,
            teaching_experience MEMO,
            max_students SHORT,
            show_university BIT,
            show_department BIT,
            show_grade_year BIT,
            show_hourly_rate BIT,
            show_subjects BIT
        )
        """,
    ),
    (
        "Students",
        """
        CREATE TABLE Students (
            student_id AUTOINCREMENT PRIMARY KEY,
            parent_user_id LONG NOT NULL,
            name VARCHAR(50) NOT NULL,
            school VARCHAR(50),
            grade VARCHAR(20),
            target_school VARCHAR(50),
            parent_phone VARCHAR(20),
            notes MEMO
        )
        """,
    ),
    (
        "Subjects",
        """
        CREATE TABLE Subjects (
            subject_id AUTOINCREMENT PRIMARY KEY,
            subject_name VARCHAR(30) NOT NULL,
            category VARCHAR(20) NOT NULL
        )
        """,
    ),
    (
        "Tutor_Subjects",
        """
        CREATE TABLE Tutor_Subjects (
            tutor_id LONG NOT NULL,
            subject_id LONG NOT NULL,
            hourly_rate CURRENCY NOT NULL,
            CONSTRAINT pk_tutor_subjects PRIMARY KEY (tutor_id, subject_id)
        )
        """,
    ),
    (
        "Tutor_Availability",
        """
        CREATE TABLE Tutor_Availability (
            availability_id AUTOINCREMENT PRIMARY KEY,
            tutor_id LONG NOT NULL,
            day_of_week SHORT NOT NULL,
            CONSTRAINT ck_avail_dow CHECK (day_of_week >= 0 AND day_of_week <= 6),
            start_time DATETIME NOT NULL,
            end_time DATETIME NOT NULL
        )
        """,
    ),
    (
        "Conversations",
        """
        CREATE TABLE Conversations (
            conversation_id AUTOINCREMENT PRIMARY KEY,
            user_a_id LONG NOT NULL,
            user_b_id LONG NOT NULL,
            created_at DATETIME NOT NULL,
            last_message_at DATETIME
        )
        """,
    ),
    (
        "Messages",
        """
        CREATE TABLE Messages (
            message_id AUTOINCREMENT PRIMARY KEY,
            conversation_id LONG NOT NULL,
            sender_user_id LONG NOT NULL,
            content MEMO NOT NULL,
            sent_at DATETIME NOT NULL
        )
        """,
    ),
    (
        "Matches",
        """
        CREATE TABLE Matches (
            match_id AUTOINCREMENT PRIMARY KEY,
            tutor_id LONG NOT NULL,
            student_id LONG NOT NULL,
            subject_id LONG NOT NULL,
            status VARCHAR(15) NOT NULL,
            invite_message MEMO,
            want_trial BIT,
            hourly_rate CURRENCY,
            sessions_per_week SHORT,
            start_date DATETIME,
            end_date DATETIME,
            penalty_amount CURRENCY,
            trial_price CURRENCY,
            trial_count SHORT,
            contract_notes MEMO,
            terminated_by LONG,
            termination_reason MEMO,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        )
        """,
    ),
    (
        "Sessions",
        """
        CREATE TABLE Sessions (
            session_id AUTOINCREMENT PRIMARY KEY,
            match_id LONG NOT NULL,
            session_date DATETIME NOT NULL,
            hours DOUBLE NOT NULL,
            content_summary MEMO NOT NULL,
            homework MEMO,
            student_performance MEMO,
            next_plan MEMO,
            visible_to_parent BIT,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        )
        """,
    ),
    (
        "Session_Edit_Logs",
        """
        CREATE TABLE Session_Edit_Logs (
            log_id AUTOINCREMENT PRIMARY KEY,
            session_id LONG NOT NULL,
            field_name VARCHAR(50) NOT NULL,
            old_value MEMO,
            new_value MEMO,
            edited_at DATETIME NOT NULL
        )
        """,
    ),
    (
        "Exams",
        """
        CREATE TABLE Exams (
            exam_id AUTOINCREMENT PRIMARY KEY,
            student_id LONG NOT NULL,
            subject_id LONG NOT NULL,
            added_by_user_id LONG NOT NULL,
            exam_date DATETIME NOT NULL,
            exam_type VARCHAR(20) NOT NULL,
            score DOUBLE NOT NULL,
            visible_to_parent BIT,
            created_at DATETIME NOT NULL
        )
        """,
    ),
    (
        "Reviews",
        """
        CREATE TABLE Reviews (
            review_id AUTOINCREMENT PRIMARY KEY,
            match_id LONG NOT NULL,
            reviewer_user_id LONG NOT NULL,
            review_type VARCHAR(20) NOT NULL,
            rating_1 SHORT NOT NULL,
            rating_2 SHORT NOT NULL,
            rating_3 SHORT,
            rating_4 SHORT,
            personality_comment MEMO,
            comment MEMO,
            created_at DATETIME NOT NULL,
            updated_at DATETIME,
            is_locked BIT
        )
        """,
    ),
]

# ──────────────────────────────────────────────
# 欄位預設值（透過 DAO 設定）
# 格式：(表名, 欄位名, DAO DefaultValue 字串)
#   Now()    → 插入時自動填入當前時間
#   "pending" → 文字預設值（DAO 需含引號）
#   True/False → 布林預設值
#   5        → 數值預設值
# ──────────────────────────────────────────────

COLUMN_DEFAULTS: list[tuple[str, str, str]] = [
    # Users
    ("Users", "created_at", "Now()"),
    # Tutors
    ("Tutors", "max_students", "5"),
    ("Tutors", "show_university", "True"),
    ("Tutors", "show_department", "True"),
    ("Tutors", "show_grade_year", "True"),
    ("Tutors", "show_hourly_rate", "True"),
    ("Tutors", "show_subjects", "True"),
    # Conversations
    ("Conversations", "created_at", "Now()"),
    # Messages
    ("Messages", "sent_at", "Now()"),
    # Matches
    ("Matches", "status", '"pending"'),
    ("Matches", "want_trial", "False"),
    ("Matches", "created_at", "Now()"),
    ("Matches", "updated_at", "Now()"),
    # Sessions
    ("Sessions", "visible_to_parent", "False"),
    ("Sessions", "created_at", "Now()"),
    ("Sessions", "updated_at", "Now()"),
    # Session_Edit_Logs
    ("Session_Edit_Logs", "edited_at", "Now()"),
    # Exams
    ("Exams", "visible_to_parent", "False"),
    ("Exams", "created_at", "Now()"),
    # Reviews
    ("Reviews", "created_at", "Now()"),
    ("Reviews", "is_locked", "False"),
]

# ──────────────────────────────────────────────
# 索引
# ──────────────────────────────────────────────

UNIQUE_INDEXES: list[str] = [
    "CREATE UNIQUE INDEX idx_users_username ON Users (username)",
    "CREATE UNIQUE INDEX idx_subjects_name ON Subjects (subject_name)",
    "CREATE UNIQUE INDEX idx_tutors_user_id ON Tutors (user_id)",
    "CREATE UNIQUE INDEX idx_conversations_pair ON Conversations (user_a_id, user_b_id)",
    "CREATE UNIQUE INDEX idx_reviews_unique ON Reviews (match_id, reviewer_user_id, review_type)",
]

PERFORMANCE_INDEXES: list[str] = [
    "CREATE INDEX idx_students_parent ON Students (parent_user_id)",
    "CREATE INDEX idx_tutor_avail_tutor ON Tutor_Availability (tutor_id)",
    "CREATE INDEX idx_messages_conv ON Messages (conversation_id)",
    "CREATE INDEX idx_messages_sent_at ON Messages (sent_at)",
    "CREATE INDEX idx_matches_tutor ON Matches (tutor_id)",
    "CREATE INDEX idx_matches_student ON Matches (student_id)",
    "CREATE INDEX idx_matches_status ON Matches (status)",
    "CREATE INDEX idx_sessions_match ON Sessions (match_id)",
    "CREATE INDEX idx_exams_student ON Exams (student_id)",
    "CREATE INDEX idx_reviews_match ON Reviews (match_id)",
    "CREATE INDEX idx_conv_last_msg ON Conversations (last_message_at)",
    "CREATE INDEX idx_tutor_subjects_subject ON Tutor_Subjects (subject_id)",
    "CREATE INDEX idx_sessions_created ON Sessions (created_at)",
    "CREATE INDEX idx_matches_status_updated ON Matches (status, updated_at)",
]

# ──────────────────────────────────────────────
# 外鍵約束
# ──────────────────────────────────────────────

FOREIGN_KEYS: list[str] = [
    # Tutors
    "ALTER TABLE Tutors ADD CONSTRAINT fk_tutors_user FOREIGN KEY (user_id) REFERENCES Users (user_id)",
    # Students
    "ALTER TABLE Students ADD CONSTRAINT fk_students_parent FOREIGN KEY (parent_user_id) REFERENCES Users (user_id)",
    # Tutor_Subjects
    "ALTER TABLE Tutor_Subjects ADD CONSTRAINT fk_ts_tutor FOREIGN KEY (tutor_id) REFERENCES Tutors (tutor_id)",
    "ALTER TABLE Tutor_Subjects ADD CONSTRAINT fk_ts_subject FOREIGN KEY (subject_id) REFERENCES Subjects (subject_id)",
    # Tutor_Availability
    "ALTER TABLE Tutor_Availability ADD CONSTRAINT fk_avail_tutor FOREIGN KEY (tutor_id) REFERENCES Tutors (tutor_id)",
    # Conversations
    "ALTER TABLE Conversations ADD CONSTRAINT fk_conv_user_a FOREIGN KEY (user_a_id) REFERENCES Users (user_id)",
    "ALTER TABLE Conversations ADD CONSTRAINT fk_conv_user_b FOREIGN KEY (user_b_id) REFERENCES Users (user_id)",
    # Messages
    "ALTER TABLE Messages ADD CONSTRAINT fk_msg_conv FOREIGN KEY (conversation_id) REFERENCES Conversations (conversation_id)",
    "ALTER TABLE Messages ADD CONSTRAINT fk_msg_sender FOREIGN KEY (sender_user_id) REFERENCES Users (user_id)",
    # Matches
    "ALTER TABLE Matches ADD CONSTRAINT fk_match_tutor FOREIGN KEY (tutor_id) REFERENCES Tutors (tutor_id)",
    "ALTER TABLE Matches ADD CONSTRAINT fk_match_student FOREIGN KEY (student_id) REFERENCES Students (student_id)",
    "ALTER TABLE Matches ADD CONSTRAINT fk_match_subject FOREIGN KEY (subject_id) REFERENCES Subjects (subject_id)",
    "ALTER TABLE Matches ADD CONSTRAINT fk_match_terminated FOREIGN KEY (terminated_by) REFERENCES Users (user_id)",
    # Sessions
    "ALTER TABLE Sessions ADD CONSTRAINT fk_session_match FOREIGN KEY (match_id) REFERENCES Matches (match_id)",
    # Session_Edit_Logs
    "ALTER TABLE Session_Edit_Logs ADD CONSTRAINT fk_editlog_session FOREIGN KEY (session_id) REFERENCES Sessions (session_id)",
    # Exams
    "ALTER TABLE Exams ADD CONSTRAINT fk_exam_student FOREIGN KEY (student_id) REFERENCES Students (student_id)",
    "ALTER TABLE Exams ADD CONSTRAINT fk_exam_subject FOREIGN KEY (subject_id) REFERENCES Subjects (subject_id)",
    "ALTER TABLE Exams ADD CONSTRAINT fk_exam_addedby FOREIGN KEY (added_by_user_id) REFERENCES Users (user_id)",
    # Reviews
    "ALTER TABLE Reviews ADD CONSTRAINT fk_review_match FOREIGN KEY (match_id) REFERENCES Matches (match_id)",
    "ALTER TABLE Reviews ADD CONSTRAINT fk_review_reviewer FOREIGN KEY (reviewer_user_id) REFERENCES Users (user_id)",
]

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


def _run_vbscript(vbs_content: str, args: list[str] | None = None) -> None:
    """將 VBScript 內容寫入暫存檔並透過 cscript 執行。"""
    fd, vbs_path = tempfile.mkstemp(suffix=".vbs")
    try:
        with os.fdopen(fd, "w", encoding="ascii") as f:
            f.write(vbs_content)

        cmd = ["cscript", "//NoLogo", vbs_path] + (args or [])
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            raise RuntimeError(
                f"VBScript 執行失敗。\n"
                f"stderr: {result.stderr.strip()}\n"
                f"stdout: {result.stdout.strip()}"
            )
    finally:
        os.unlink(vbs_path)


def create_accdb_file(db_path: str) -> None:
    """使用 VBScript + ADOX 建立空白 .accdb 資料庫檔案。"""
    abs_path = os.path.abspath(db_path)

    if os.path.exists(abs_path):
        logger.info("資料庫檔案已存在，跳過建立: %s", abs_path)
        return

    os.makedirs(os.path.dirname(abs_path), exist_ok=True)

    vbs_content = (
        'Set cat = CreateObject("ADOX.Catalog")\n'
        "cat.Create "
        '"Provider=Microsoft.ACE.OLEDB.12.0;'
        'Data Source=" & WScript.Arguments(0) & ";"\n'
        "Set cat = Nothing\n"
    )

    try:
        _run_vbscript(vbs_content, [abs_path])
    except RuntimeError as e:
        raise RuntimeError(
            f"建立 .accdb 檔案失敗。\n{e}\n"
            f"請確認已安裝 Microsoft Access Database Engine "
            f"(https://www.microsoft.com/en-us/download/details.aspx?id=54920)"
        ) from e

    logger.info("資料庫檔案建立完成: %s", abs_path)


def _table_exists(cursor, table_name: str) -> bool:
    """檢查資料表是否已存在。"""
    for _ in cursor.tables(table=table_name, tableType="TABLE"):
        return True
    return False


def create_tables(conn: pyodbc.Connection) -> None:
    """建立全部 13 張資料表（跳過已存在的表）。"""
    cursor = conn.cursor()
    for table_name, ddl in TABLE_DDL:
        if _table_exists(cursor, table_name):
            logger.info("  資料表已存在，跳過: %s", table_name)
            continue
        cursor.execute(ddl)
        conn.commit()
        logger.info("  建立資料表: %s", table_name)


def set_column_defaults(db_path: str) -> None:
    """透過 DAO COM 設定欄位預設值。

    Access ODBC 的 CREATE TABLE 不支援 DEFAULT 子句，
    因此改用 DAO.DBEngine 直接操作資料庫檔案的欄位屬性。
    """
    abs_path = os.path.abspath(db_path)

    # 產生 VBScript 逐一設定各欄位的 DefaultValue 屬性
    lines = [
        'Set engine = CreateObject("DAO.DBEngine.120")',
        'Set db = engine.OpenDatabase(WScript.Arguments(0))',
        "",
    ]
    for table, field, default_value in COLUMN_DEFAULTS:
        # 在 VBScript 中，字串需用雙引號包裹；若 default_value 本身含引號則需轉義
        # DAO 的 DefaultValue 直接接受 Access 運算式字串，如 Now()、"pending"、True
        escaped = default_value.replace('"', '""')
        lines.append(f'db.TableDefs("{table}").Fields("{field}").DefaultValue = "{escaped}"')

    lines += [
        "",
        "db.Close",
        "Set db = Nothing",
        "Set engine = Nothing",
    ]

    _run_vbscript("\n".join(lines), [abs_path])
    logger.info("  已設定 %d 個欄位預設值", len(COLUMN_DEFAULTS))


def create_indexes(conn: pyodbc.Connection) -> None:
    """建立唯一索引與效能索引（跳過已存在的索引）。"""
    cursor = conn.cursor()
    for sql in UNIQUE_INDEXES + PERFORMANCE_INDEXES:
        try:
            cursor.execute(sql)
            conn.commit()
        except pyodbc.Error:
            pass  # 索引已存在，靜默跳過


def create_foreign_keys(conn: pyodbc.Connection) -> None:
    """建立外鍵約束（跳過已存在的約束）。"""
    cursor = conn.cursor()
    for sql in FOREIGN_KEYS:
        try:
            cursor.execute(sql)
            conn.commit()
        except pyodbc.Error:
            pass  # 約束已存在，靜默跳過


def seed_subjects(conn: pyodbc.Connection) -> None:
    """寫入科目種子資料（若已有資料則跳過）。"""
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM Subjects")
    if cursor.fetchone()[0] > 0:
        logger.info("  科目資料已存在，跳過種子寫入")
        return

    for name, category in SEED_SUBJECTS:
        cursor.execute(
            "INSERT INTO Subjects (subject_name, category) VALUES (?, ?)",
            (name, category),
        )
    conn.commit()
    logger.info("  寫入 %d 筆科目種子資料", len(SEED_SUBJECTS))


def ensure_admin_user(conn: pyodbc.Connection, settings: Settings | None = None) -> None:
    """確保管理員帳號存在，若不存在則建立。"""
    if settings is None:
        settings = _default_settings

    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) FROM Users WHERE username = ?",
        (settings.admin_username,),
    )
    if cursor.fetchone()[0] > 0:
        logger.info("  管理員帳號已存在，跳過")
        return

    hashed = hash_password(settings.admin_password)
    cursor.execute(
        "INSERT INTO Users (username, password_hash, role, display_name, created_at) "
        "VALUES (?, ?, 'admin', ?, Now())",
        (settings.admin_username, hashed, settings.admin_username),
    )
    conn.commit()
    logger.info("  管理員帳號建立完成: %s", settings.admin_username)


def initialize_database() -> None:
    """執行完整的資料庫初始化流程。"""
    settings = _default_settings
    db_path = settings.access_db_path

    # 檢查 ODBC 驅動程式
    access_driver = "Microsoft Access Driver (*.mdb, *.accdb)"
    if access_driver not in pyodbc.drivers():
        raise RuntimeError(
            f"未找到 ODBC 驅動程式: {access_driver}\n"
            f"可用的驅動程式: {pyodbc.drivers()}\n"
            f"請安裝 Microsoft Access Database Engine。"
        )

    logger.info("===== 資料庫初始化開始 =====")

    # 步驟 1：建立 .accdb 檔案
    create_accdb_file(db_path)

    # 步驟 2：建立資料表
    abs_path = os.path.abspath(db_path)
    conn_str = (
        r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};"
        rf"DBQ={abs_path};"
    )
    conn = pyodbc.connect(conn_str)

    try:
        logger.info("[1/6] 建立資料表...")
        create_tables(conn)

        # 遷移：確保 Reviews 資料表包含 is_locked 欄位
        cursor = conn.cursor()
        existing_cols = [c.column_name for c in cursor.columns(table="Reviews")]
        if "is_locked" not in existing_cols:
            cursor.execute("ALTER TABLE Reviews ADD COLUMN is_locked BIT")
            cursor.execute("UPDATE Reviews SET is_locked = False")
            conn.commit()
            logger.info("  已補建 Reviews.is_locked 欄位")
    finally:
        conn.close()

    # 步驟 3：設定欄位預設值（需先關閉 ODBC 連線，DAO 才能開啟資料庫）
    logger.info("[2/6] 設定欄位預設值...")
    set_column_defaults(db_path)

    # 步驟 4~6：重新建立 ODBC 連線，完成索引、外鍵、種子資料
    conn = pyodbc.connect(conn_str)
    try:
        logger.info("[3/6] 建立索引...")
        create_indexes(conn)

        logger.info("[4/6] 建立外鍵約束...")
        create_foreign_keys(conn)

        logger.info("[5/6] 寫入種子資料...")
        seed_subjects(conn)

        logger.info("[6/6] 建立管理員帳號...")
        ensure_admin_user(conn, settings)
    finally:
        conn.close()

    logger.info("===== 資料庫初始化完成 =====")
