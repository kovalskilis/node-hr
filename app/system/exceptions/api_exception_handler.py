from fastapi import Request, status
from fastapi.responses import JSONResponse

from app.system.exceptions.base_exception import BaseHTTPException


async def common_exception_handler(request: Request, exc: BaseHTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "path": str(request.url)}
    )
