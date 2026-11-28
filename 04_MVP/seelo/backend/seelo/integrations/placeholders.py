"""아직 만들지 않은 외부 연동 자리(4단계부터 채운다). 부르면 바로 알 수 있게 예외를 낸다."""

from typing import Any


class NotYetImplemented:
    def __init__(self, name: str, step: str) -> None:
        self._name = name
        self._step = step

    def __getattr__(self, attr: str) -> Any:
        raise NotImplementedError(f"{self._name}.{attr}: 12 작업순서 {self._step}에서 구현한다")

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError(f"{self._name}: 12 작업순서 {self._step}에서 구현한다")
