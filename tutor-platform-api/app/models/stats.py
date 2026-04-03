from pydantic import BaseModel


class IncomeStats(BaseModel):
    total_income: float = 0.0
    total_hours: float = 0.0
    monthly_breakdown: list[dict] = []


class ExpenseStats(BaseModel):
    total_expense: float = 0.0
    monthly_breakdown: list[dict] = []
