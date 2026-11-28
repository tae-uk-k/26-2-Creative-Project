"""인증 요청·응답(04 4장, 14 1.2)."""

from typing import Annotated, Literal

from pydantic import AfterValidator, EmailStr, Field, model_validator
from pydantic_core import PydanticCustomError

from seelo.schemas.common import CamelModel, LoginProvider
from seelo.security.passwords import is_valid_password


def _check_pw(v: str) -> str:
    if not is_valid_password(v):
        raise PydanticCustomError("weak_password", "8자 이상, 영문과 숫자를 함께 써 주세요")
    return v


PasswordStr = Annotated[str, Field(max_length=128), AfterValidator(_check_pw)]


class SignupRequest(CamelModel):
    email: EmailStr
    password: PasswordStr
    password_confirm: str = Field(max_length=128)
    agree_terms: bool
    agree_privacy: bool

    @model_validator(mode="after")
    def _rules(self) -> "SignupRequest":
        if self.password != self.password_confirm:
            raise PydanticCustomError("password_mismatch", "비밀번호가 서로 달라요")
        if not (self.agree_terms and self.agree_privacy):
            raise PydanticCustomError("terms_required", "필수 약관에 동의해 주세요")
        return self


class SignupResponse(CamelModel):
    email: str
    mail_ticket: str


class MailStatusResponse(CamelModel):
    status: Literal["queued", "sent", "failed"]


class TokenRequest(CamelModel):
    token: str = Field(min_length=10, max_length=200)


class EmailRequest(CamelModel):
    email: EmailStr


class MailTicketResponse(CamelModel):
    mail_ticket: str


class LoginRequest(CamelModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class Me(CamelModel):
    id: int
    email: str
    role: Literal["owner", "admin"]
    provider: LoginProvider
    has_store: bool


class UserResponse(CamelModel):
    user: Me


class ResetRequest(CamelModel):
    token: str = Field(min_length=10, max_length=200)
    password: PasswordStr
    password_confirm: str = Field(max_length=128)

    @model_validator(mode="after")
    def _same(self) -> "ResetRequest":
        if self.password != self.password_confirm:
            raise PydanticCustomError("password_mismatch", "비밀번호가 서로 달라요")
        return self


class PendingSignupResponse(CamelModel):
    provider: Literal["google", "kakao"]
    email: str | None
    needs_email: bool


class PendingCompleteRequest(CamelModel):
    agree_terms: bool
    agree_privacy: bool
    email: EmailStr | None = None

    @model_validator(mode="after")
    def _terms(self) -> "PendingCompleteRequest":
        if not (self.agree_terms and self.agree_privacy):
            raise PydanticCustomError("terms_required", "필수 약관에 동의해 주세요")
        return self


class PendingCompleteResponse(CamelModel):
    next: str
    user: Me | None = None
    mail_ticket: str | None = None
