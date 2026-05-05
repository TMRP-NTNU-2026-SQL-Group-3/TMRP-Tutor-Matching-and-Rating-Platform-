from pydantic import BaseModel, Field, model_validator

from app.shared.api.validators import OptionalStr, TrimmedStr


class TutorProfileUpdate(BaseModel):
    self_intro: str | None = Field(default=None, max_length=4000, description="自我介紹")
    teaching_experience: str | None = Field(default=None, max_length=4000, description="教學經驗")
    university: str | None = Field(default=None, max_length=200, description="就讀大學")
    department: str | None = Field(default=None, max_length=200, description="就讀科系")
    grade_year: int | None = Field(default=None, description="年級")
    max_students: int | None = Field(default=None, ge=1, le=100, description="最大收學生數")
    show_university: bool | None = Field(default=None, description="是否公開大學資訊")
    show_department: bool | None = Field(default=None, description="是否公開科系資訊")
    show_grade_year: bool | None = Field(default=None, description="是否公開年級資訊")
    show_hourly_rate: bool | None = Field(default=None, description="是否公開時薪資訊")
    show_subjects: bool | None = Field(default=None, description="是否公開教學科目")


class SubjectItem(BaseModel):
    subject_id: int = Field(..., description="科目 ID")
    hourly_rate: float = Field(ge=1, le=9999, description="該科目每小時費率")


class SubjectUpdate(BaseModel):
    subjects: list[SubjectItem] = Field(..., description="科目列表")


class AvailabilitySlot(BaseModel):
    day_of_week: int = Field(ge=0, le=6, description="星期幾（0=週日，6=週六）")
    start_time: str = Field(..., description="開始時間（HH:MM）", pattern=r'^\d{2}:\d{2}(:\d{2})?$')
    end_time: str = Field(..., description="結束時間（HH:MM）", pattern=r'^\d{2}:\d{2}(:\d{2})?$')

    @model_validator(mode="after")
    def validate_times(self):
        from datetime import time as dt_time
        def _parse(s: str) -> dt_time:
            parts = s.split(":")
            return dt_time(int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) == 3 else 0)
        try:
            st = _parse(self.start_time)
            et = _parse(self.end_time)
        except (ValueError, IndexError):
            raise ValueError("時間格式不合法，請使用 HH:MM 或 HH:MM:SS")
        if st >= et:
            raise ValueError("開始時間必須早於結束時間")
        return self


class AvailabilityUpdate(BaseModel):
    slots: list[AvailabilitySlot] = Field(..., description="可用時段列表")


class VisibilityUpdate(BaseModel):
    show_university: bool | None = Field(default=None)
    show_department: bool | None = Field(default=None)
    show_grade_year: bool | None = Field(default=None)
    show_hourly_rate: bool | None = Field(default=None)
    show_subjects: bool | None = Field(default=None)


class StudentCreate(BaseModel):
    name: TrimmedStr = Field(..., max_length=50, description="學生姓名")
    school: OptionalStr = Field(default=None, max_length=50, description="就讀學校")
    grade: OptionalStr = Field(default=None, max_length=20, description="年級")


class StudentUpdate(BaseModel):
    name: OptionalStr = Field(default=None, max_length=50, description="學生姓名")
    school: OptionalStr = Field(default=None, max_length=50, description="就讀學校")
    grade: OptionalStr = Field(default=None, max_length=20, description="年級")
    target_school: OptionalStr = Field(default=None, max_length=50, description="目標學校")
