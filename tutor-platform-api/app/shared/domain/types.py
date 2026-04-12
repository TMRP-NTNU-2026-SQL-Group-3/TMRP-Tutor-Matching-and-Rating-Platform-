"""
型別別名，讓程式碼語義更清楚。
使用 NewType 而非裸 int，IDE 可以提示型別錯用。
"""
from typing import NewType

UserId = NewType("UserId", int)
TutorId = NewType("TutorId", int)
StudentId = NewType("StudentId", int)
MatchId = NewType("MatchId", int)
SubjectId = NewType("SubjectId", int)
SessionId = NewType("SessionId", int)
ReviewId = NewType("ReviewId", int)
ConversationId = NewType("ConversationId", int)
