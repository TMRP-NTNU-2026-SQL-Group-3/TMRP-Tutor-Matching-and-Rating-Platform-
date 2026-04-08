"""
假資料產生器

呼叫 run_seed(conn) 即可填入完整的展示用假資料。
若偵測到資料庫已有非管理員的使用者，會跳過以避免重複寫入。
"""

import logging
import random
from datetime import datetime, timedelta

import pyodbc

from app.utils.access_bits import to_access_bit
from app.utils.security import hash_password

logger = logging.getLogger("seed.generator")

TRUE = to_access_bit(True)
FALSE = to_access_bit(False)

# ──────────────────────────────────────────────
# 輔助函式
# ──────────────────────────────────────────────


def _insert_and_get_id(cursor: pyodbc.Cursor, sql: str, params: tuple) -> int:
    """執行 INSERT 並回傳自動產生的 ID。"""
    cursor.execute(sql, params)
    cursor.execute("SELECT @@IDENTITY")
    return int(cursor.fetchone()[0])


def _dt(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    """建立 datetime 的簡寫。"""
    return datetime(year, month, day, hour, minute)


# ──────────────────────────────────────────────
# 主函式
# ──────────────────────────────────────────────


def run_seed(conn: pyodbc.Connection) -> dict:
    """
    填入展示用假資料。回傳各表新增筆數。

    Parameters
    ----------
    conn : pyodbc.Connection
        已連線的 MS Access pyodbc 連線物件。

    Returns
    -------
    dict
        各資料表新增的筆數，例如 {"users": 6, "students": 5, ...}。
    """
    cursor = conn.cursor()

    # ── 防重複 ─────────────────────────────────
    cursor.execute("SELECT COUNT(*) FROM Users WHERE role <> 'admin'")
    if cursor.fetchone()[0] > 0:
        logger.info("已有非管理員使用者，跳過假資料寫入")
        return {"skipped": True, "message": "資料庫已有種子資料，跳過寫入"}

    now = datetime.now()
    hashed = hash_password("password123")

    counts = {}

    # ══════════════════════════════════════════
    # 1. Users（3 parents + 3 tutors）
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

    for username, role, display_name, phone, email in parent_data:
        uid = _insert_and_get_id(
            cursor,
            "INSERT INTO Users (username, password_hash, role, display_name, phone, email, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (username, hashed, role, display_name, phone, email, now - timedelta(days=random.randint(30, 90))),
        )
        parent_user_ids.append(uid)

    for username, role, display_name, phone, email in tutor_data:
        uid = _insert_and_get_id(
            cursor,
            "INSERT INTO Users (username, password_hash, role, display_name, phone, email, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (username, hashed, role, display_name, phone, email, now - timedelta(days=random.randint(30, 90))),
        )
        tutor_user_ids.append(uid)

    conn.commit()
    counts["users"] = 6
    logger.info("  建立 6 位使用者")

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
            "INSERT INTO Tutors (user_id, university, department, grade_year, self_intro, "
            "teaching_experience, max_students, show_university, show_department, "
            "show_grade_year, show_hourly_rate, show_subjects) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                t["user_id"], t["university"], t["department"], t["grade_year"],
                t["self_intro"], t["teaching_experience"], t["max_students"],
                TRUE, TRUE, TRUE, TRUE, TRUE,
            ),
        )
        tutor_ids.append(tid)

    conn.commit()
    counts["tutors"] = 3
    logger.info("  建立 3 位家教檔案")

    # ══════════════════════════════════════════
    # 3. Students（每位家長 1-2 位學生）
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
            "INSERT INTO Students (parent_user_id, name, school, grade, target_school, parent_phone, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (parent_uid, name, school, grade, target, phone, notes),
        )
        student_ids.append(sid)

    conn.commit()
    counts["students"] = len(student_data)
    logger.info("  建立 %d 位學生", len(student_data))

    # ══════════════════════════════════════════
    # 4. 查詢科目 ID
    # ══════════════════════════════════════════
    cursor.execute("SELECT subject_id, subject_name FROM Subjects")
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

    ts_count = 0
    for tid, subj_name, rate in tutor_subject_assignments:
        subj_id = subject_map.get(subj_name)
        if subj_id is None:
            logger.warning("  找不到科目 %s，跳過", subj_name)
            continue
        cursor.execute(
            "INSERT INTO Tutor_Subjects (tutor_id, subject_id, hourly_rate) VALUES (?, ?, ?)",
            (tid, subj_id, rate),
        )
        ts_count += 1

    conn.commit()
    counts["tutor_subjects"] = ts_count
    logger.info("  建立 %d 筆家教科目", ts_count)

    # ══════════════════════════════════════════
    # 6. Tutor_Availability
    # ══════════════════════════════════════════
    availability_data = [
        # (tutor_id, day_of_week, start_hour, start_min, end_hour, end_min)
        (tutor_ids[0], 1, 18, 0, 21, 0),   # 週一晚上
        (tutor_ids[0], 3, 18, 0, 21, 0),   # 週三晚上
        (tutor_ids[0], 6, 9, 0, 12, 0),    # 週六早上
        (tutor_ids[1], 2, 14, 0, 17, 0),   # 週二下午
        (tutor_ids[1], 4, 14, 0, 17, 0),   # 週四下午
        (tutor_ids[1], 0, 10, 0, 16, 0),   # 週日整天
        (tutor_ids[2], 5, 19, 0, 21, 0),   # 週五晚上
        (tutor_ids[2], 6, 13, 0, 18, 0),   # 週六下午
    ]

    avail_count = 0
    # 使用固定日期作為基準，只取時間部分
    base_date = datetime(1899, 12, 30)  # Access 日期基準（Access 以此日期儲存時間部分）
    for tid, dow, sh, sm, eh, em in availability_data:
        start_time = base_date.replace(hour=sh, minute=sm)
        end_time = base_date.replace(hour=eh, minute=em)
        _insert_and_get_id(
            cursor,
            "INSERT INTO Tutor_Availability (tutor_id, day_of_week, start_time, end_time) "
            "VALUES (?, ?, ?, ?)",
            (tid, dow, start_time, end_time),
        )
        avail_count += 1

    conn.commit()
    counts["tutor_availability"] = avail_count
    logger.info("  建立 %d 筆可用時段", avail_count)

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
            "INSERT INTO Conversations (user_a_id, user_b_id, created_at, last_message_at) "
            "VALUES (?, ?, ?, ?)",
            (spec["user_a"], spec["user_b"], base_time, base_time),
        )
        conv_count += 1

        for i, (sender_id, content) in enumerate(spec["messages"]):
            msg_time = base_time + timedelta(minutes=random.randint(5, 30) * (i + 1))
            last_msg_time = msg_time
            _insert_and_get_id(
                cursor,
                "INSERT INTO Messages (conversation_id, sender_user_id, content, sent_at) "
                "VALUES (?, ?, ?, ?)",
                (conv_id, sender_id, content, msg_time),
            )
            msg_count += 1

        # 更新最後訊息時間
        cursor.execute(
            "UPDATE Conversations SET last_message_at = ? WHERE conversation_id = ?",
            (last_msg_time, conv_id),
        )

    conn.commit()
    counts["conversations"] = conv_count
    counts["messages"] = msg_count
    logger.info("  建立 %d 個對話、%d 則訊息", conv_count, msg_count)

    # ══════════════════════════════════════════
    # 8. Matches
    # ══════════════════════════════════════════
    math_id = subject_map.get("數學")
    eng_id = subject_map.get("英文")
    phys_id = subject_map.get("物理")

    match_specs = [
        {
            # 王小明 <-> 張家豪 (數學) — active
            "tutor_id": tutor_ids[0], "student_id": student_ids[0],
            "subject_id": math_id, "status": "active",
            "invite_message": "希望老師能幫小明打好數學基礎", "want_trial": TRUE,
            "hourly_rate": 800, "sessions_per_week": 2,
            "start_date": now - timedelta(days=45), "end_date": None,
            "penalty_amount": 200, "trial_price": 400, "trial_count": 1,
            "contract_notes": "每週一、三晚上 7-9 點上課",
            "terminated_by": None, "termination_reason": None,
        },
        {
            # 陳品妤 <-> 李佳穎 (英文) — active
            "tutor_id": tutor_ids[1], "student_id": student_ids[2],
            "subject_id": eng_id, "status": "active",
            "invite_message": "品妤想加強英文閱讀和寫作", "want_trial": FALSE,
            "hourly_rate": 900, "sessions_per_week": 1,
            "start_date": now - timedelta(days=30), "end_date": None,
            "penalty_amount": 300, "trial_price": None, "trial_count": None,
            "contract_notes": "每週四下午上課",
            "terminated_by": None, "termination_reason": None,
        },
        {
            # 林宥辰 <-> 黃柏翰 (物理) — trial
            "tutor_id": tutor_ids[2], "student_id": student_ids[4],
            "subject_id": phys_id, "status": "trial",
            "invite_message": "宥辰物理觀念不太清楚，想試教看看", "want_trial": TRUE,
            "hourly_rate": 700, "sessions_per_week": 1,
            "start_date": now - timedelta(days=7), "end_date": None,
            "penalty_amount": None, "trial_price": 350, "trial_count": 1,
            "contract_notes": None,
            "terminated_by": None, "termination_reason": None,
        },
        {
            # 王小華 <-> 張家豪 (數學) — pending
            "tutor_id": tutor_ids[0], "student_id": student_ids[1],
            "subject_id": math_id, "status": "pending",
            "invite_message": "小華要準備會考，希望能加強數學", "want_trial": TRUE,
            "hourly_rate": 800, "sessions_per_week": 2,
            "start_date": None, "end_date": None,
            "penalty_amount": None, "trial_price": 400, "trial_count": 1,
            "contract_notes": None,
            "terminated_by": None, "termination_reason": None,
        },
        {
            # 陳柏宇 <-> 黃柏翰 (數學) — ended
            "tutor_id": tutor_ids[2], "student_id": student_ids[3],
            "subject_id": math_id, "status": "ended",
            "invite_message": "柏宇國一數學需要加強", "want_trial": FALSE,
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
            "INSERT INTO Matches (tutor_id, student_id, subject_id, status, invite_message, "
            "want_trial, hourly_rate, sessions_per_week, start_date, end_date, penalty_amount, "
            "trial_price, trial_count, contract_notes, terminated_by, termination_reason, "
            "created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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

    conn.commit()
    counts["matches"] = len(match_specs)
    logger.info("  建立 %d 筆配對", len(match_specs))

    # ══════════════════════════════════════════
    # 9. Sessions（為 active / trial / ended 的配對建立上課紀錄）
    # ══════════════════════════════════════════
    # match_ids[0] = active (王小明-數學), match_ids[1] = active (陳品妤-英文)
    # match_ids[2] = trial (林宥辰-物理), match_ids[4] = ended (陳柏宇-數學)

    session_specs = [
        # 王小明的數學課
        {
            "match_id": match_ids[0],
            "session_date": now - timedelta(days=40),
            "hours": 2.0,
            "content_summary": "複習多項式的基本運算，包含因式分解與餘式定理。",
            "homework": "課本第三章習題 1-15",
            "student_performance": "理解力不錯，但計算常粗心，需要多練習。",
            "next_plan": "進入指數與對數函數",
            "visible_to_parent": TRUE,
        },
        {
            "match_id": match_ids[0],
            "session_date": now - timedelta(days=33),
            "hours": 2.0,
            "content_summary": "教指數函數的圖形與性質，對數的定義與基本運算。",
            "homework": "講義第 5-8 頁",
            "student_performance": "對數的概念需要多加理解，指數部分掌握得不錯。",
            "next_plan": "對數函數與應用",
            "visible_to_parent": TRUE,
        },
        {
            "match_id": match_ids[0],
            "session_date": now - timedelta(days=26),
            "hours": 2.0,
            "content_summary": "對數的運算法則與換底公式，搭配生活應用題練習。",
            "homework": "段考複習卷一份",
            "student_performance": "進步明顯，換底公式已能靈活運用。",
            "next_plan": "段考複習總整理",
            "visible_to_parent": TRUE,
        },
        # 陳品妤的英文課
        {
            "match_id": match_ids[1],
            "session_date": now - timedelta(days=25),
            "hours": 2.0,
            "content_summary": "閱讀練習：科普文章精讀，學習找主題句和關鍵字技巧。",
            "homework": "完成兩篇閱讀測驗並標註不會的單字",
            "student_performance": "閱讀速度偏慢但正確率高，需要提升速度。",
            "next_plan": "英文寫作基礎：段落結構",
            "visible_to_parent": TRUE,
        },
        {
            "match_id": match_ids[1],
            "session_date": now - timedelta(days=18),
            "hours": 2.0,
            "content_summary": "英文段落寫作：主題句、支持句與結論句的架構。",
            "homework": "寫一篇 150 字短文，主題：My Favorite Season",
            "student_performance": "文法基礎好，但句型較單調，需要多樣化。",
            "next_plan": "進階句型與轉折詞使用",
            "visible_to_parent": TRUE,
        },
        # 林宥辰的物理試教課
        {
            "match_id": match_ids[2],
            "session_date": now - timedelta(days=5),
            "hours": 1.5,
            "content_summary": "診斷測驗 + 力學基本觀念複習：牛頓三大運動定律。",
            "homework": "基礎練習題 10 題",
            "student_performance": "第三定律的作用力反作用力容易混淆，需要多用實例說明。",
            "next_plan": "力的合成與分解",
            "visible_to_parent": TRUE,
        },
        # 陳柏宇的已結束數學課
        {
            "match_id": match_ids[4],
            "session_date": now - timedelta(days=60),
            "hours": 1.5,
            "content_summary": "國一上冊整數的四則運算複習。",
            "homework": "課本習題第一章",
            "student_performance": "基礎運算能力可以，正負數觀念需加強。",
            "next_plan": "分數與小數的運算",
            "visible_to_parent": TRUE,
        },
        {
            "match_id": match_ids[4],
            "session_date": now - timedelta(days=45),
            "hours": 1.5,
            "content_summary": "分數的基本運算與應用題。",
            "homework": "練習卷第 1-2 頁",
            "student_performance": "應用題的閱讀理解需要加強。",
            "next_plan": "一元一次方程式",
            "visible_to_parent": TRUE,
        },
    ]

    session_count = 0
    for s in session_specs:
        _insert_and_get_id(
            cursor,
            "INSERT INTO Sessions (match_id, session_date, hours, content_summary, homework, "
            "student_performance, next_plan, visible_to_parent, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                s["match_id"], s["session_date"], s["hours"],
                s["content_summary"], s["homework"], s["student_performance"],
                s["next_plan"], s["visible_to_parent"],
                s["session_date"] + timedelta(hours=3), s["session_date"] + timedelta(hours=3),
            ),
        )
        session_count += 1

    conn.commit()
    counts["sessions"] = session_count
    logger.info("  建立 %d 筆上課紀錄", session_count)

    # ══════════════════════════════════════════
    # 10. Exams
    # ══════════════════════════════════════════
    exam_specs = [
        # 王小明的數學考試
        {
            "student_id": student_ids[0], "subject_id": math_id,
            "added_by_user_id": tutor_user_ids[0],
            "exam_date": now - timedelta(days=35),
            "exam_type": "段考", "score": 72.0, "visible_to_parent": TRUE,
        },
        {
            "student_id": student_ids[0], "subject_id": math_id,
            "added_by_user_id": tutor_user_ids[0],
            "exam_date": now - timedelta(days=7),
            "exam_type": "段考", "score": 85.0, "visible_to_parent": TRUE,
        },
        # 陳品妤的英文考試
        {
            "student_id": student_ids[2], "subject_id": eng_id,
            "added_by_user_id": tutor_user_ids[1],
            "exam_date": now - timedelta(days=20),
            "exam_type": "小考", "score": 92.0, "visible_to_parent": TRUE,
        },
        # 陳柏宇的數學考試（已結束的配對）
        {
            "student_id": student_ids[3], "subject_id": math_id,
            "added_by_user_id": tutor_user_ids[2],
            "exam_date": now - timedelta(days=50),
            "exam_type": "段考", "score": 68.0, "visible_to_parent": TRUE,
        },
    ]

    exam_count = 0
    for e in exam_specs:
        _insert_and_get_id(
            cursor,
            "INSERT INTO Exams (student_id, subject_id, added_by_user_id, exam_date, "
            "exam_type, score, visible_to_parent, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                e["student_id"], e["subject_id"], e["added_by_user_id"],
                e["exam_date"], e["exam_type"], e["score"],
                e["visible_to_parent"], now,
            ),
        )
        exam_count += 1

    conn.commit()
    counts["exams"] = exam_count
    logger.info("  建立 %d 筆考試紀錄", exam_count)

    # ══════════════════════════════════════════
    # 11. Reviews
    # ══════════════════════════════════════════
    review_specs = [
        # 已結束的配對 (陳柏宇-黃柏翰) — 家長評價老師
        {
            "match_id": match_ids[4],
            "reviewer_user_id": parent_user_ids[1],
            "review_type": "parent_to_tutor",
            "rating_1": 4, "rating_2": 4, "rating_3": 5, "rating_4": 4,
            "personality_comment": "老師很有耐心，會用不同方式解釋到學生懂為止。",
            "comment": "黃老師教學認真，可惜因為搬家不能繼續上課。整體來說非常推薦！",
        },
        # 已結束的配對 — 老師評價家長
        {
            "match_id": match_ids[4],
            "reviewer_user_id": tutor_user_ids[2],
            "review_type": "tutor_to_parent",
            "rating_1": 5, "rating_2": 5, "rating_3": 4, "rating_4": 5,
            "personality_comment": None,
            "comment": "陳爸爸很配合教學安排，也會關心孩子的學習進度，是很好的家長。",
        },
        # 已結束的配對 — 老師評價學生
        {
            "match_id": match_ids[4],
            "reviewer_user_id": tutor_user_ids[2],
            "review_type": "tutor_to_student",
            "rating_1": 3, "rating_2": 4, "rating_3": 3, "rating_4": 4,
            "personality_comment": None,
            "comment": "柏宇很乖巧，上課態度良好。建議可以多花時間在課後複習，會有更大的進步。",
        },
        # active 配對 (王小明-張家豪) — 家長期中評價
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
            "INSERT INTO Reviews (match_id, reviewer_user_id, review_type, "
            "rating_1, rating_2, rating_3, rating_4, personality_comment, comment, "
            "created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                r["match_id"], r["reviewer_user_id"], r["review_type"],
                r["rating_1"], r["rating_2"], r["rating_3"], r["rating_4"],
                r["personality_comment"], r["comment"],
                now - timedelta(days=random.randint(1, 14)), now,
            ),
        )
        review_count += 1

    conn.commit()
    counts["reviews"] = review_count
    logger.info("  建立 %d 筆評價", review_count)

    logger.info("假資料寫入完成：%s", counts)
    return counts
