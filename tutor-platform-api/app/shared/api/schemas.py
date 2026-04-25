from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    success: bool = Field(..., description="請求是否成功", examples=[True])
    data: Optional[T] = Field(default=None, description="回應資料")
    message: Optional[str] = Field(default=None, description="回應訊息", examples=["操作成功"])


class PaginatedData(BaseModel, Generic[T]):
    items: List[T] = Field(..., description="資料列表")
    total: int = Field(..., description="總筆數", examples=[100])
    page: int = Field(..., description="目前頁碼", examples=[1])
    page_size: int = Field(..., description="每頁筆數", examples=[20])
    total_pages: int = Field(..., description="總頁數", examples=[5])
    has_next: bool = Field(..., description="是否有下一頁", examples=[True])
    has_prev: bool = Field(..., description="是否有上一頁", examples=[False])
