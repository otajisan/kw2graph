import json

import structlog
from fastapi import FastAPI
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response, StreamingResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from kw2graph import settings
from kw2graph.usecase.candidate import GetCandidateUseCase
from kw2graph.usecase.input.candidate import GetCandidateInput
from kw2graph.usecase.output.candidate import GetCandidateOutput

logger = structlog.get_logger(__name__)

app = FastAPI(default_response_class=JSONResponse)


@app.get("/healthz")
async def healthz():
    return {'status': 'UP'}


@app.get("/candidate", response_model=GetCandidateOutput)
async def get_candidate(request: GetCandidateInput):
    use_case = GetCandidateUseCase(settings)
    response = use_case.execute(request)
    return response


@app.exception_handler(RequestValidationError)
async def handle_request_validation_error(request, exc) -> JSONResponse:
    logger.error(f'Bad Request. invalid parameters specified. {exc.raw_errors}')
    return JSONResponse(
        status_code=400,
        content=json.loads(exc.json()),
    )


@app.exception_handler(StarletteHTTPException)
async def handle_http_exception(request, exc):
    logger.error(f'HTTP Exception occurred. code: {exc.status_code} detail: {exc.detail}')
    return await http_exception_handler(request, exc)


@app.middleware("http")
async def intercept_http_requests(req, call_next):
    res = await call_next(req)

    logger.info(f'{res.status_code} {req.method}: {req.url.path} query: {req.query_params}')

    return res


if __name__ == '__main__':
    # https://fastapi.tiangolo.com/ja/tutorial/debugging/
    import uvicorn

    uvicorn.run(app, host='0.0.0.0', port=8000, log_level='debug')
