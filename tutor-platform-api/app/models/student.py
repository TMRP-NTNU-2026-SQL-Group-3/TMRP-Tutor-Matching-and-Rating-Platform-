from pydantic import BaseModel, Field


class StudentCreate(BaseModel):
    name: str = Field(..., description="學生姓名", examples=["王小明"])
    school: str | None = Field(default=None, description="就讀學校", examples=["台北市立建國中學"])
    grade: str | None = Field(default=None, description="年級", examples=["高二"])


class StudentUpdate(BaseModel):
    name: str | None = Field(default=None, description="學生姓名", examples=["王小明"])
    school: str | None = Field(default=None, description="就讀學校", examples=["台北市立建國中學"])
    grade: str | None = Field(default=None, description="年級", examples=["高二"])
    target_school: str | None = Field(default=None, description="目標學校", examples=["國立台灣大學"])
