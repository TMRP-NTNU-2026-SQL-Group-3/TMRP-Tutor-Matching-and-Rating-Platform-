from pydantic import BaseModel, Field


class TutorProfileUpdate(BaseModel):
    self_intro: str | None = Field(default=None, description="自我介紹", examples=["台大數學系大三，有三年家教經驗"])
    teaching_experience: str | None = Field(default=None, description="教學經驗", examples=["曾輔導五位學生考上第一志願"])
    university: str | None = Field(default=None, description="就讀大學", examples=["國立台灣大學"])
    department: str | None = Field(default=None, description="就讀科系", examples=["數學系"])
    grade_year: int | None = Field(default=None, description="年級", examples=[3])
    max_students: int | None = Field(default=None, description="最大收學生數", examples=[5])
    show_university: bool = Field(default=True, description="是否公開大學資訊", examples=[True])
    show_department: bool = Field(default=True, description="是否公開科系資訊", examples=[True])
    show_grade_year: bool = Field(default=True, description="是否公開年級資訊", examples=[True])
    show_hourly_rate: bool = Field(default=True, description="是否公開時薪資訊", examples=[True])
    show_subjects: bool = Field(default=True, description="是否公開教學科目", examples=[True])


class SubjectItem(BaseModel):
    subject_id: int = Field(..., description="科目 ID", examples=[1])
    hourly_rate: float = Field(gt=0, description="該科目每小時費率（新台幣）", examples=[600.0])


class SubjectUpdate(BaseModel):
    subjects: list[SubjectItem] = Field(..., description="科目列表")


class AvailabilitySlot(BaseModel):
    day_of_week: int = Field(ge=0, le=6, description="星期幾（0=週日，6=週六）", examples=[1])
    start_time: str = Field(..., description="開始時間（HH:MM）", examples=["14:00"], pattern=r'^\d{2}:\d{2}(:\d{2})?$')
    end_time: str = Field(..., description="結束時間（HH:MM）", examples=["16:00"], pattern=r'^\d{2}:\d{2}(:\d{2})?$')


class AvailabilityUpdate(BaseModel):
    slots: list[AvailabilitySlot] = Field(..., description="可用時段列表")


class VisibilityUpdate(BaseModel):
    show_university: bool | None = Field(default=None, description="是否公開大學資訊", examples=[True])
    show_department: bool | None = Field(default=None, description="是否公開科系資訊", examples=[True])
    show_grade_year: bool | None = Field(default=None, description="是否公開年級資訊", examples=[False])
    show_hourly_rate: bool | None = Field(default=None, description="是否公開時薪資訊", examples=[True])
    show_subjects: bool | None = Field(default=None, description="是否公開教學科目", examples=[True])
