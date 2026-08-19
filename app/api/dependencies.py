from typing import Annotated

from fastapi import Depends


def noop_dependency() -> None:
    """临时占位依赖：后续接入数据库 Session、当前用户、Repository 等。"""
    return None


NoopDep = Annotated[None, Depends(noop_dependency)]
