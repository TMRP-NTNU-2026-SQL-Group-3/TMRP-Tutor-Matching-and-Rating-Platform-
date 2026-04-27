from app.shared.domain.exceptions import DomainException, ConflictError


class DuplicateUsernameError(ConflictError):
    def __init__(self):
        super().__init__("帳號已存在")


class InvalidCredentialsError(DomainException):
    def __init__(self):
        super().__init__("帳號或密碼錯誤")


class InvalidRoleError(DomainException):
    def __init__(self):
        super().__init__("角色必須為 parent 或 tutor")


class UserNotFoundError(DomainException):
    def __init__(self):
        super().__init__("使用者不存在", 401)


class InvalidRefreshTokenError(DomainException):
    def __init__(self):
        super().__init__("刷新令牌無效或已過期", 401)


class PasswordReusedError(DomainException):
    def __init__(self):
        super().__init__("新密碼不能與最近使用過的密碼相同", 422)
