"""
Seed data generator.

Call `run_seed(conn)` to populate demo fixtures. If the database already
contains non-admin users, the seed is skipped to avoid duplicates.

The function stages every INSERT inside the caller's transaction and returns
without committing; the caller (see `app.tasks.seed_tasks.generate_seed_data`)
is responsible for committing on success or rolling back on failure so a
mid-run error cannot leave the database in a half-seeded state.

WARNING — seed-only patterns:
  This module uses individual INSERT-per-row loops and _insert_and_get_id()
  helpers that issue one round-trip per row. These patterns are acceptable
  for small, one-off seed datasets but MUST NOT be copied into production
  code paths. Application code should use executemany() or a bulk
  INSERT ... VALUES statement when inserting multiple rows.
"""

import logging
import random
import secrets
import string
from datetime import datetime, time, timedelta, timezone

from app.shared.infrastructure.security import hash_password

logger = logging.getLogger("seed.generator")

_SEED_CHARS = string.ascii_letters + string.digits

# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────


def _insert_and_get_id(cursor, sql: str, params: tuple) -> int:
    """Execute an INSERT ... RETURNING statement and return the generated id."""
    cursor.execute(sql, params)
    return int(cursor.fetchone()[0])


def _dt(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    """Shorthand for constructing a datetime."""
    return datetime(year, month, day, hour, minute)


# ──────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────


def run_seed(conn) -> dict:
    """Populate demo fixture data and return a count dict keyed by table name.

    Parameters
    ----------
    conn
        An open psycopg2 connection to the PostgreSQL database.

    Returns
    -------
    dict
        Row counts inserted per table, e.g. {"users": 6, "students": 5, ...}.
    """
    # B8: the caller owns the transaction. Fail fast if `conn` is in
    # autocommit mode — otherwise every INSERT below would commit
    # individually and a mid-run error would leave the DB half-seeded,
    # defeating the whole point of the rollback path in seed_tasks /
    # admin router.
    if getattr(conn, "autocommit", False):
        raise RuntimeError(
            "run_seed requires conn.autocommit=False so the caller owns the "
            "transaction boundary (commit on success, rollback on failure)."
        )

    cursor = conn.cursor()

    # ── Idempotency guard ──────────────────────
    cursor.execute("SELECT COUNT(*) FROM users WHERE role <> 'admin'")
    if cursor.fetchone()[0] > 0:
        logger.info("Non-admin users already exist; skipping seed")
        return {"skipped": True, "message": "Seed data already present; skipped"}

    now = datetime.now(timezone.utc)
    counts = {}

    # ══════════════════════════════════════════
    # 1. Users (3 parents + 3 tutors)
    # ══════════════════════════════════════════
    parent_data = [
        ("parent_wang", "parent", "王美玲", "0912-345-678", "wang.meiling@example.com"),
        ("parent_chen", "parent", "陳志明", "0923-456-789", "chen.zhiming@example.com"),
        ("parent_lin", "parent", "林淑芬", "0934-567-890", "lin.shufen@example.com"),
    ]
    tutor_data = [
        ("tutor_zhang", "tutor", "張家豪", "0911-111-222", "zhang.jiahao@example.com"),
        ("tutor_li", "tutor", "李佳穎", "0922-222-333", "li.jiaying@example.com"),
        ("tutor_huang", "tutor", "黃柏翰", "0933-333-444", "huang.bohan@example.com"),
    ]

    parent_user_ids = []
    tutor_user_ids = []
    credentials: list[tuple[str, str]] = []  # (username, plain_password) — logged once below

    for username, role, display_name, phone, email in parent_data:
        pw = "".join(secrets.choice(_SEED_CHARS) for _ in range(16))
        credentials.append((username, pw))
        uid = _insert_and_get_id(
            cursor,
            "INSERT INTO users (username, password_hash, role, display_name, phone, email, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING user_id",
            (username, hash_password(pw), role, display_name, phone, email, now - timedelta(days=random.randint(30, 90))),
        )
        parent_user_ids.append(uid)

    for username, role, display_name, phone, email in tutor_data:
        pw = "".join(secrets.choice(_SEED_CHARS) for _ in range(16))
        credentials.append((username, pw))
        uid = _insert_and_get_id(
            cursor,
            "INSERT INTO users (username, password_hash, role, display_name, phone, email, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING user_id",
            (username, hash_password(pw), role, display_name, phone, email, now - timedelta(days=random.randint(30, 90))),
        )
        tutor_user_ids.append(uid)

    counts["users"] = 6
    logger.warning(
        "SEED CREDENTIALS (local dev only — never apply seed data to any internet-reachable host):\n%s",
        "\n".join(f"  {u}: {p}" for u, p in credentials),
    )
    logger.info("  6 users staged")

    # ══════════════════════════════════════════
    # 2. Tutors
    # ══════════════════════════════════════════
    tutor_profiles = [
        {
            "user_id": tutor_user_ids[0],
            "university": "國立臺灣大學",
            "department": "數學系",
            "grade_year": 3,
            "self_intro": "大家好，我是家豪！目前就讀臺大數學系三年級，擅長以生活化的例子講解抽象的數學觀念，讓同學真正理解而非死背公式。",
            "teaching_experience": "家教經驗兩年，曾帶過三位高中生，其中兩位成功考上第一志願。",
            "max_students": 4,
        },
        {
            "user_id": tutor_user_ids[1],
            "university": "國立清華大學",
            "department": "外國語文學系",
            "grade_year": 4,
            "self_intro": "嗨！我是佳穎，多益 950 分，曾到英國交換一學期。教學風格活潑有趣，注重聽說讀寫均衡發展。",
            "teaching_experience": "三年英文家教經驗，輔導國中到高中各年級，平均提升學生段考成績 15 分以上。",
            "max_students": 5,
        },
        {
            "user_id": tutor_user_ids[2],
            "university": "國立成功大學",
            "department": "物理學系",
            "grade_year": 2,
            "self_intro": "我是柏翰，對物理和數學充滿熱情，喜歡用實驗和圖解幫助學生建立直覺。",
            "teaching_experience": "一年家教經驗，專攻高中物理與數學。",
            "max_students": 3,
        },
    ]

    tutor_ids = []
    for t in tutor_profiles:
        tid = _insert_and_get_id(
            cursor,
            "INSERT INTO tutors (user_id, university, department, grade_year, self_intro, "
            "teaching_experience, max_students, show_university, show_department, "
            "show_grade_year, show_hourly_rate, show_subjects) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING tutor_id",
            (
                t["user_id"], t["university"], t["department"], t["grade_year"],
                t["self_intro"], t["teaching_experience"], t["max_students"],
                True, True, True, True, True,
            ),
        )
        tutor_ids.append(tid)

    counts["tutors"] = 3
    logger.info("  3 tutor profiles staged")

    # ══════════════════════════════════════════
    # 3. Students (1-2 per parent)
    # ══════════════════════════════════════════
    student_data = [
        # (parent_user_id, name, school, grade, target_school, parent_phone, notes)
        (parent_user_ids[0], "王小明", "臺北市立建國中學", "高二", "國立臺灣大學", "0912-345-678", "數理科目需要加強"),
        (parent_user_ids[0], "王小華", "臺北市立中正國中", "國三", "臺北市立建國中學", "0912-345-678", "準備會考衝刺"),
        (parent_user_ids[1], "陳品妤", "新竹市立光華國中", "國二", "國立新竹高中", "0923-456-789", "英文底子不錯，希望更上一層"),
        (parent_user_ids[1], "陳柏宇", "新竹市立光華國中", "國一", None, "0923-456-789", None),
        (parent_user_ids[2], "林宥辰", "臺中市立臺中一中", "高一", "國立清華大學", "0934-567-890", "物理觀念需要釐清"),
    ]

    student_ids = []
    for parent_uid, name, school, grade, target, phone, notes in student_data:
        sid = _insert_and_get_id(
            cursor,
            "INSERT INTO students (parent_user_id, name, school, grade, target_school, parent_phone, notes) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING student_id",
            (parent_uid, name, school, grade, target, phone, notes),
        )
        student_ids.append(sid)

    counts["students"] = len(student_data)
    logger.info("  %d students staged", len(student_data))

    # ══════════════════════════════════════════
    # 4. Subject ID lookup
    # ══════════════════════════════════════════
    cursor.execute("SELECT subject_id, subject_name FROM subjects")
    subject_map = {row[1]: row[0] for row in cursor.fetchall()}

    # ══════════════════════════════════════════
    # 5. Tutor_Subjects
    # ══════════════════════════════════════════
    tutor_subject_assignments = [
        # (tutor_id, subject_name, hourly_rate)
        (tutor_ids[0], "數學", 800),
        (tutor_ids[0], "物理", 750),
        (tutor_ids[1], "英文", 900),
        (tutor_ids[1], "國文", 700),
        (tutor_ids[1], "日文", 1000),
        (tutor_ids[2], "物理", 700),
        (tutor_ids[2], "數學", 650),
    ]

    missing_subjects = [s for _, s, _ in tutor_subject_assignments if s not in subject_map]
    for s in missing_subjects:
        logger.warning("  subject not found: %s, skipped", s)
    ts_rows = [
        (tid, subject_map[subj_name], rate)
        for tid, subj_name, rate in tutor_subject_assignments
        if subj_name in subject_map
    ]
    cursor.executemany(
        "INSERT INTO tutor_subjects (tutor_id, subject_id, hourly_rate) VALUES (%s, %s, %s)",
        ts_rows,
    )
    ts_count = len(ts_rows)

    counts["tutor_subjects"] = ts_count
    logger.info("  %d tutor-subject rows staged", ts_count)

    # ══════════════════════════════════════════
    # 6. Tutor_Availability
    # ══════════════════════════════════════════
    availability_data = [
        # (tutor_id, day_of_week, start_hour, start_min, end_hour, end_min)
        (tutor_ids[0], 1, 18, 0, 21, 0),   # Monday evening
        (tutor_ids[0], 3, 18, 0, 21, 0),   # Wednesday evening
        (tutor_ids[0], 6, 9, 0, 12, 0),    # Saturday morning
        (tutor_ids[1], 2, 14, 0, 17, 0),   # Tuesday afternoon
        (tutor_ids[1], 4, 14, 0, 17, 0),   # Thursday afternoon
        (tutor_ids[1], 7, 10, 0, 16, 0),   # Sunday all day
        (tutor_ids[2], 5, 19, 0, 21, 0),   # Friday evening
        (tutor_ids[2], 6, 13, 0, 18, 0),   # Saturday afternoon
    ]

    avail_rows = [
        (tid, dow, time(sh, sm), time(eh, em))
        for tid, dow, sh, sm, eh, em in availability_data
    ]
    cursor.executemany(
        "INSERT INTO tutor_availability (tutor_id, day_of_week, start_time, end_time) VALUES (%s, %s, %s, %s)",
        avail_rows,
    )
    avail_count = len(avail_rows)

    counts["tutor_availability"] = avail_count
    logger.info("  %d availability slots staged", avail_count)

    # ══════════════════════════════════════════
    # 7. Conversations & Messages
    # ══════════════════════════════════════════
    conversation_specs = [
        {
            "user_a": parent_user_ids[0],
            "user_b": tutor_user_ids[0],
            "messages": [
                (parent_user_ids[0], "張老師你好！請問高二數學還有收學生嗎？"),
                (tutor_user_ids[0], "王媽媽您好！目前還有名額，請問孩子目前的程度大約如何呢？"),
                (parent_user_ids[0], "小明段考大概 60-70 分左右，主要是觀念不太清楚。"),
                (tutor_user_ids[0], "了解，我可以先安排一堂試教，幫他找出問題點，方便的話我們約這週六早上如何？"),
                (parent_user_ids[0], "好的，那就麻煩老師了！"),
            ],
        },
        {
            "user_a": parent_user_ids[1],
            "user_b": tutor_user_ids[1],
            "messages": [
                (parent_user_ids[1], "李老師好，想請問英文家教的上課方式？"),
                (tutor_user_ids[1], "陳爸爸好！我通常會根據學生程度設計教材，國中生的話以課本為基礎，搭配閱讀和聽力練習。"),
                (parent_user_ids[1], "聽起來不錯，品妤英文還可以但想要更精進，可以幫她加強閱讀和寫作嗎？"),
                (tutor_user_ids[1], "沒問題！我會特別著重閱讀技巧和英文作文的練習。"),
            ],
        },
    ]

    conv_count = 0
    msg_count = 0
    for spec in conversation_specs:
        base_time = now - timedelta(days=random.randint(7, 30))
        last_msg_time = base_time

        conv_id = _insert_and_get_id(
            cursor,
            "INSERT INTO conversations (user_a_id, user_b_id, created_at, last_message_at) "
            "VALUES (%s, %s, %s, %s) RETURNING conversation_id",
            (spec["user_a"], spec["user_b"], base_time, base_time),
        )
        conv_count += 1

        for i, (sender_id, content) in enumerate(spec["messages"]):
            msg_time = base_time + timedelta(minutes=random.randint(5, 30) * (i + 1))
            last_msg_time = msg_time
            _insert_and_get_id(
                cursor,
                "INSERT INTO messages (conversation_id, sender_user_id, content, sent_at) "
                "VALUES (%s, %s, %s, %s) RETURNING message_id",
                (conv_id, sender_id, content, msg_time),
            )
            msg_count += 1

        # update last_message_at to the timestamp of the final message
        cursor.execute(
            "UPDATE conversations SET last_message_at = %s WHERE conversation_id = %s",
            (last_msg_time, conv_id),
        )

    counts["conversations"] = conv_count
    counts["messages"] = msg_count
    logger.info("  %d conversations / %d messages staged", conv_count, msg_count)

    # ══════════════════════════════════════════
    # 8. Matches
    # ══════════════════════════════════════════
    math_id = subject_map.get("數學")
    eng_id = subject_map.get("英文")
    phys_id = subject_map.get("物理")

    match_specs = [
        {
            # Wang Xiaoming <-> Zhang Jiahao (Math) — active
            "tutor_id": tutor_ids[0], "student_id": student_ids[0],
            "subject_id": math_id, "status": "active",
            "invite_message": "希望老師能幫小明打好數學基礎", "want_trial": True,
            "hourly_rate": 800, "sessions_per_week": 2,
            "start_date": now - timedelta(days=45), "end_date": None,
            "penalty_amount": 200, "trial_price": 400, "trial_count": 1,
            "contract_notes": "每週一、三晚上 7-9 點上課",
            "terminated_by": None, "termination_reason": None,
        },
        {
            # Chen Pinyu <-> Li Jiaying (English) — active
            "tutor_id": tutor_ids[1], "student_id": student_ids[2],
            "subject_id": eng_id, "status": "active",
            "invite_message": "品妤想加強英文閱讀和寫作", "want_trial": False,
            "hourly_rate": 900, "sessions_per_week": 1,
            "start_date": now - timedelta(days=30), "end_date": None,
            "penalty_amount": 300, "trial_price": None, "trial_count": None,
            "contract_notes": "每週四下午上課",
            "terminated_by": None, "termination_reason": None,
        },
        {
            # Lin Youchen <-> Huang Bohan (Physics) — trial
            "tutor_id": tutor_ids[2], "student_id": student_ids[4],
            "subject_id": phys_id, "status": "trial",
            "invite_message": "宥辰物理觀念不太清楚，想試教看看", "want_trial": True,
            "hourly_rate": 700, "sessions_per_week": 1,
            "start_date": now - timedelta(days=7), "end_date": None,
            "penalty_amount": None, "trial_price": 350, "trial_count": 1,
            "contract_notes": None,
            "terminated_by": None, "termination_reason": None,
        },
        {
            # Wang Xiaohua <-> Zhang Jiahao (Math) — pending
            "tutor_id": tutor_ids[0], "student_id": student_ids[1],
            "subject_id": math_id, "status": "pending",
            "invite_message": "小華要準備會考，希望能加強數學", "want_trial": True,
            "hourly_rate": 800, "sessions_per_week": 2,
            "start_date": None, "end_date": None,
            "penalty_amount": None, "trial_price": 400, "trial_count": 1,
            "contract_notes": None,
            "terminated_by": None, "termination_reason": None,
        },
        {
            # Chen Boyu <-> Huang Bohan (Math) — ended
            "tutor_id": tutor_ids[2], "student_id": student_ids[3],
            "subject_id": math_id, "status": "ended",
            "invite_message": "柏宇國一數學需要加強", "want_trial": False,
            "hourly_rate": 650, "sessions_per_week": 1,
            "start_date": now - timedelta(days=90), "end_date": now - timedelta(days=14),
            "penalty_amount": 200, "trial_price": None, "trial_count": None,
            "contract_notes": "每週六下午上課",
            "terminated_by": parent_user_ids[1], "termination_reason": "active|學生搬家，不方便繼續上課",
        },
    ]

    match_ids = []
    for m in match_specs:
        mid = _insert_and_get_id(
            cursor,
            "INSERT INTO matches (tutor_id, student_id, subject_id, status, invite_message, "
            "want_trial, hourly_rate, sessions_per_week, start_date, end_date, penalty_amount, "
            "trial_price, trial_count, contract_notes, terminated_by, termination_reason, "
            "created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "RETURNING match_id",
            (
                m["tutor_id"], m["student_id"], m["subject_id"], m["status"],
                m["invite_message"], m["want_trial"], m["hourly_rate"],
                m["sessions_per_week"], m["start_date"], m["end_date"],
                m["penalty_amount"], m["trial_price"], m["trial_count"],
                m["contract_notes"], m["terminated_by"], m["termination_reason"],
                now - timedelta(days=random.randint(7, 60)), now,
            ),
        )
        match_ids.append(mid)

    counts["matches"] = len(match_specs)
    logger.info("  %d matches staged", len(match_specs))

    # ══════════════════════════════════════════
    # 9. Sessions (for active / trial / ended matches)
    # ══════════════════════════════════════════
    # match_ids[0] = active (Wang-Math), match_ids[1] = active (Chen-English)
    # match_ids[2] = trial (Lin-Physics), match_ids[4] = ended (Chen-Math)

    session_specs = [
        # Wang Xiaoming — Math sessions
        {
            "match_id": match_ids[0],
            "session_date": now - timedelta(days=40),
            "hours": 2.0,
            "content_summary": "複習多項式的基本運算，包含因式分解與餘式定理。",
            "homework": "課本第三章習題 1-15",
            "student_performance": "理解力不錯，但計算常粗心，需要多練習。",
            "next_plan": "進入指數與對數函數",
            "visible_to_parent": True,
        },
        {
            "match_id": match_ids[0],
            "session_date": now - timedelta(days=33),
            "hours": 2.0,
            "content_summary": "教指數函數的圖形與性質，對數的定義與基本運算。",
            "homework": "講義第 5-8 頁",
            "student_performance": "對數的概念需要多加理解，指數部分掌握得不錯。",
            "next_plan": "對數函數與應用",
            "visible_to_parent": True,
        },
        {
            "match_id": match_ids[0],
            "session_date": now - timedelta(days=26),
            "hours": 2.0,
            "content_summary": "對數的運算法則與換底公式，搭配生活應用題練習。",
            "homework": "段考複習卷一份",
            "student_performance": "進步明顯，換底公式已能靈活運用。",
            "next_plan": "段考複習總整理",
            "visible_to_parent": True,
        },
        # Chen Pinyu — English sessions
        {
            "match_id": match_ids[1],
            "session_date": now - timedelta(days=25),
            "hours": 2.0,
            "content_summary": "閱讀練習：科普文章精讀，學習找主題句和關鍵字技巧。",
            "homework": "完成兩篇閱讀測驗並標註不會的單字",
            "student_performance": "閱讀速度偏慢但正確率高，需要提升速度。",
            "next_plan": "英文寫作基礎：段落結構",
            "visible_to_parent": True,
        },
        {
            "match_id": match_ids[1],
            "session_date": now - timedelta(days=18),
            "hours": 2.0,
            "content_summary": "英文段落寫作：主題句、支持句與結論句的架構。",
            "homework": "寫一篇 150 字短文，主題：My Favorite Season",
            "student_performance": "文法基礎好，但句型較單調，需要多樣化。",
            "next_plan": "進階句型與轉折詞使用",
            "visible_to_parent": True,
        },
        # Lin Youchen — Physics trial session
        {
            "match_id": match_ids[2],
            "session_date": now - timedelta(days=5),
            "hours": 1.5,
            "content_summary": "診斷測驗 + 力學基本觀念複習：牛頓三大運動定律。",
            "homework": "基礎練習題 10 題",
            "student_performance": "第三定律的作用力反作用力容易混淆，需要多用實例說明。",
            "next_plan": "力的合成與分解",
            "visible_to_parent": True,
        },
        # Chen Boyu — ended Math sessions
        {
            "match_id": match_ids[4],
            "session_date": now - timedelta(days=60),
            "hours": 1.5,
            "content_summary": "國一上冊整數的四則運算複習。",
            "homework": "課本習題第一章",
            "student_performance": "基礎運算能力可以，正負數觀念需加強。",
            "next_plan": "分數與小數的運算",
            "visible_to_parent": True,
        },
        {
            "match_id": match_ids[4],
            "session_date": now - timedelta(days=45),
            "hours": 1.5,
            "content_summary": "分數的基本運算與應用題。",
            "homework": "練習卷第 1-2 頁",
            "student_performance": "應用題的閱讀理解需要加強。",
            "next_plan": "一元一次方程式",
            "visible_to_parent": True,
        },
    ]

    session_count = 0
    for s in session_specs:
        _insert_and_get_id(
            cursor,
            "INSERT INTO sessions (match_id, session_date, hours, content_summary, homework, "
            "student_performance, next_plan, visible_to_parent, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING session_id",
            (
                s["match_id"], s["session_date"], s["hours"],
                s["content_summary"], s["homework"], s["student_performance"],
                s["next_plan"], s["visible_to_parent"],
                s["session_date"] + timedelta(hours=3), s["session_date"] + timedelta(hours=3),
            ),
        )
        session_count += 1

    counts["sessions"] = session_count
    logger.info("  %d session rows staged", session_count)

    # ══════════════════════════════════════════
    # 10. Exams
    # ══════════════════════════════════════════
    exam_specs = [
        # Wang Xiaoming — Math exams
        {
            "student_id": student_ids[0], "subject_id": math_id,
            "added_by_user_id": tutor_user_ids[0],
            "exam_date": now - timedelta(days=35),
            "exam_type": "段考", "score": 72.0, "visible_to_parent": True,
        },
        {
            "student_id": student_ids[0], "subject_id": math_id,
            "added_by_user_id": tutor_user_ids[0],
            "exam_date": now - timedelta(days=7),
            "exam_type": "段考", "score": 85.0, "visible_to_parent": True,
        },
        # Chen Pinyu — English exam
        {
            "student_id": student_ids[2], "subject_id": eng_id,
            "added_by_user_id": tutor_user_ids[1],
            "exam_date": now - timedelta(days=20),
            "exam_type": "小考", "score": 92.0, "visible_to_parent": True,
        },
        # Chen Boyu — Math exam (ended match)
        {
            "student_id": student_ids[3], "subject_id": math_id,
            "added_by_user_id": tutor_user_ids[2],
            "exam_date": now - timedelta(days=50),
            "exam_type": "段考", "score": 68.0, "visible_to_parent": True,
        },
    ]

    exam_count = 0
    for e in exam_specs:
        _insert_and_get_id(
            cursor,
            "INSERT INTO exams (student_id, subject_id, added_by_user_id, exam_date, "
            "exam_type, score, visible_to_parent, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING exam_id",
            (
                e["student_id"], e["subject_id"], e["added_by_user_id"],
                e["exam_date"], e["exam_type"], e["score"],
                e["visible_to_parent"], now,
            ),
        )
        exam_count += 1

    counts["exams"] = exam_count
    logger.info("  %d exam rows staged", exam_count)

    # ══════════════════════════════════════════
    # 11. Reviews
    # ══════════════════════════════════════════
    review_specs = [
        # Ended match (Chen Boyu / Huang Bohan) — parent rates tutor
        {
            "match_id": match_ids[4],
            "reviewer_user_id": parent_user_ids[1],
            "review_type": "parent_to_tutor",
            "rating_1": 4, "rating_2": 4, "rating_3": 5, "rating_4": 4,
            "personality_comment": "老師很有耐心，會用不同方式解釋到學生懂為止。",
            "comment": "黃老師教學認真，可惜因為搬家不能繼續上課。整體來說非常推薦！",
        },
        # Ended match — tutor rates parent
        {
            "match_id": match_ids[4],
            "reviewer_user_id": tutor_user_ids[2],
            "review_type": "tutor_to_parent",
            "rating_1": 5, "rating_2": 5, "rating_3": 4, "rating_4": 5,
            "personality_comment": None,
            "comment": "陳爸爸很配合教學安排，也會關心孩子的學習進度，是很好的家長。",
        },
        # Ended match — tutor rates student
        {
            "match_id": match_ids[4],
            "reviewer_user_id": tutor_user_ids[2],
            "review_type": "tutor_to_student",
            "rating_1": 3, "rating_2": 4, "rating_3": 3, "rating_4": 4,
            "personality_comment": None,
            "comment": "柏宇很乖巧，上課態度良好。建議可以多花時間在課後複習，會有更大的進步。",
        },
        # Active match (Wang Xiaoming / Zhang Jiahao) — mid-engagement parent review
        {
            "match_id": match_ids[0],
            "reviewer_user_id": parent_user_ids[0],
            "review_type": "parent_to_tutor",
            "rating_1": 5, "rating_2": 5, "rating_3": 5, "rating_4": 5,
            "personality_comment": "老師很會教，小明回家都說上課很有趣。",
            "comment": "張老師非常專業，小明的數學段考從 65 分進步到 85 分，非常感謝！",
        },
    ]

    review_count = 0
    for r in review_specs:
        _insert_and_get_id(
            cursor,
            "INSERT INTO reviews (match_id, reviewer_user_id, review_type, "
            "rating_1, rating_2, rating_3, rating_4, personality_comment, comment, "
            "created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING review_id",
            (
                r["match_id"], r["reviewer_user_id"], r["review_type"],
                r["rating_1"], r["rating_2"], r["rating_3"], r["rating_4"],
                r["personality_comment"], r["comment"],
                now - timedelta(days=random.randint(1, 14)), now,
            ),
        )
        review_count += 1

    counts["reviews"] = review_count
    logger.info("  %d review rows staged", review_count)

    logger.info("Seed data staged: %s", counts)
    return counts
