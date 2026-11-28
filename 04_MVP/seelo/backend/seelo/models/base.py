"""ORM 공통(02 5장, 13 10장). DB의 정답은 migrations/sql/0001_initial.sql이다."""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, MappedColumn, mapped_column


class Base(DeclarativeBase):
    type_annotation_map = {
        int: BigInteger,
        str: Text,
        datetime: DateTime(timezone=True),
        dict[str, Any]: JSONB,
        list[Any]: JSONB,
    }


def pk() -> MappedColumn[int]:
    return mapped_column(BigInteger, Identity(always=True), primary_key=True)


def fk(
    target: str,
    ondelete: str,
    *,
    nullable: bool = False,
    name: str | None = None,
    use_alter: bool = False,
) -> MappedColumn[Any]:
    return mapped_column(
        BigInteger,
        ForeignKey(target, ondelete=ondelete, name=name, use_alter=use_alter),
        nullable=nullable,
    )


def created_col() -> MappedColumn[datetime]:
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


def ts(*, nullable: bool = True) -> MappedColumn[Any]:
    return mapped_column(DateTime(timezone=True), nullable=nullable)


def txt(*, nullable: bool = False, default: str | None = None) -> MappedColumn[Any]:
    return mapped_column(
        Text, nullable=nullable, server_default=text(f"'{default}'") if default is not None else None
    )


def jsonb(*, nullable: bool = True, default: str | None = None) -> MappedColumn[Any]:
    """default는 SQL 리터럴 문자열: "'{}'" 또는 "'[]'"."""
    return mapped_column(JSONB, nullable=nullable, server_default=text(default) if default else None)
