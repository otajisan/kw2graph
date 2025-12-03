import json
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Depends
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response, StreamingResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.cors import CORSMiddleware

from kw2graph import settings
from kw2graph.infrastructure.graphdb import GraphDatabaseRepository
from kw2graph.infrastructure.gremlin_manager import GLOBAL_GREMLIN_MANAGER
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPIの新しいライフサイクルイベントハンドラ。
    リソースの初期化とクリーンアップを一箇所で行う。
    """
    logger.info("Application startup: Initializing resources.")

    # 起動処理 (yield の前)
    GLOBAL_GREMLIN_MANAGER.initialize(settings)  # Gremlinクライアントの作成

    yield  # ここでアプリケーションがリクエストの処理を開始する

    # シャットダウン処理 (yield の後)
    logger.info("Application shutdown: Cleaning up resources.")
    GLOBAL_GREMLIN_MANAGER.close()  # Gremlinクライアントのクローズ


app = FastAPI(
    title="KW2Graph API",
    version="0.1.0",
    lifespan=lifespan,
    default_response_class=JSONResponse
)

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


def get_graphdb_repository():
    """DIのための関数: マネージャーからClientを取得し、リポジトリに渡す"""
    # ★ 修正: マネージャーからClientインスタンスを取得
    client_instance = GLOBAL_GREMLIN_MANAGER.get_client()
    return GraphDatabaseRepository(settings, client_instance=client_instance)


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
async def create_graph(
        request: CreateGraphInput,
        repo: GraphDatabaseRepository = Depends(get_graphdb_repository)
):
    use_case = CreateGraphUseCase(settings, graph_repo=repo)
    response = await use_case.execute(request)
    return response


@app.get('/show_graph', response_model=ShowGraphOutput)
async def show_graph(
        seed_keyword: str,
        max_depth: int = 2,
        repo: GraphDatabaseRepository = Depends(get_graphdb_repository)
):  # ★ パラメータを追加
    """
    指定されたキーワードを起点とする関連グラフデータを、指定された深さまで取得する。
    """
    # GETリクエストのため、クエリパラメータからInputを作成
    request = ShowGraphInput(
        seed_keyword=seed_keyword,
        max_depth=max_depth  # ★ パラメータを追加
    )

    use_case = ShowGraphUseCase(settings, graph_repo=repo)
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
