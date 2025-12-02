import json

import structlog
from fastapi import FastAPI
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response, StreamingResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.cors import CORSMiddleware

from kw2graph import settings
from kw2graph.usecase.analyze import AnalyzeKeywordsUseCase
from kw2graph.usecase.candidate import GetCandidateUseCase
from kw2graph.usecase.create_graph import CreateGraphUseCase
from kw2graph.usecase.input.analyze import AnalyzeKeywordsInput
from kw2graph.usecase.input.candidate import GetCandidateInput
from kw2graph.usecase.input.create_graph import CreateGraphInput
from kw2graph.usecase.output.analyze import AnalyzeKeywordsOutput
from kw2graph.usecase.output.candidate import GetCandidateOutput
from kw2graph.usecase.output.create_graph import CreateGraphOutput
from kw2graph.usecase.show_graph import ShowGraphInput, ShowGraphUseCase, ShowGraphOutput

logger = structlog.get_logger(__name__)

app = FastAPI(default_response_class=JSONResponse)

origins = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # 許可するオリジンのリスト
    allow_credentials=True,  # クッキーなどの資格情報を許可
    allow_methods=["*"],  # すべてのHTTPメソッド (POST, GET, PUT, DELETEなど) を許可
    allow_headers=["*"],  # すべてのHTTPヘッダーを許可 (Content-Typeなど)
)


@app.get("/healthz")
async def healthz():
    return {'status': 'UP'}


@app.post('/candidate', response_model=GetCandidateOutput)
async def get_candidate(request: GetCandidateInput):
    use_case = GetCandidateUseCase(settings)
    response = use_case.execute(request)
    return response


@app.post('/analyze', response_model=AnalyzeKeywordsOutput)
async def analyze(request: AnalyzeKeywordsInput):
    use_case = AnalyzeKeywordsUseCase(settings)
    response = use_case.execute(request)
    return response


@app.post('/create', response_model=CreateGraphOutput)
async def create_graph(request: CreateGraphInput):
    use_case = CreateGraphUseCase(settings)
    response = await use_case.execute(request)
    return response


@app.get('/show_graph', response_model=ShowGraphOutput)
async def show_graph(seed_keyword: str):
    """
    指定されたキーワードを起点とする関連グラフデータを取得する。
    """
    # GETリクエストのため、クエリパラメータからInputを作成
    request = ShowGraphInput(seed_keyword=seed_keyword)

    use_case = ShowGraphUseCase(settings)

    # ユースケースを実行
    response = await use_case.execute(request)

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
    logger.info(f'{req.method}: {req.url.path} query: {req.query_params} headers: {req.headers}')

    return res


if __name__ == '__main__':
    # https://fastapi.tiangolo.com/ja/tutorial/debugging/
    import uvicorn

    uvicorn.run(app, host='0.0.0.0', port=8000, log_level='debug')
