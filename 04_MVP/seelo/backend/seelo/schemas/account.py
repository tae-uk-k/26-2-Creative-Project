"""계정 설정 요청·응답(04 4장, 14 1.2)."""

from datetime import datetime

from pydantic import Field

from seelo.schemas.auth import PasswordStr
from seelo.schemas.common import CamelModel, LoginProvider


class AccountResponse(CamelModel):
    email: str
    provider: LoginProvider
    created_at: datetime
    can_change_password: bool


class ChangePasswordRequest(CamelModel):
    current_password: str = Field(max_length=128)
    new_password: PasswordStr
    new_password_confirm: str = Field(max_length=128)


class DeleteAccountRequest(CamelModel):
    confirm_text: str = Field(max_length=50)
