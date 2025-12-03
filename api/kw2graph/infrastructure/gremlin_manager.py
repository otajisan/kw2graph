import structlog
from gremlin_python.driver import client as gremlin_client, serializer
from gremlin_python.driver.client import Client

from kw2graph import config

logger = structlog.get_logger(__name__)


# グローバルなクライアントインスタンス（シングルトンとして振る舞う）
class GremlinClientManager:
    """
    Gremlin Clientの接続と切断を管理し、Clientインスタンスを提供するクラス。
    FastAPIのライフサイクルイベント（startup/shutdown）からのみ利用される。
    """

    def __init__(self):
        self._client: Client | None = None
        self._url: str | None = None

    def initialize(self, settings: config.Settings):
        """Gremlinクライアントを初期化し、接続します。"""
        if self._client:
            logger.warning("GremlinClientManager is already initialized.")
            return

        self._url = f'ws://{settings.graphdb_host}:{settings.graphdb_port}/gremlin'
        logger.info("Initializing Gremlin Client.", url=self._url)

        self._client = gremlin_client.Client(
            self._url,
            'g',
            message_serializer=serializer.GraphSONSerializersV3d0()
        )
        # Note: 接続テストは初回クエリ実行時に任せ、__init__ では行わない。

    def close(self):
        """Gremlinクライアントを明示的にクローズします。"""
        if self._client:
            logger.info("Closing Gremlin Client.")
            try:
                # 警告を無視するため、明示的なtry-exceptは行わないが、クローズを試みる
                self._client.close()
                self._client = None
            except Exception as e:
                logger.error("Error during Gremlin client close.", error=str(e))

    def get_client(self) -> Client:
        """初期化済みのGremlin Clientインスタンスを返します。"""
        if not self._client:
            # 起動イベントで初期化されることを前提としているため、通常は発生しない
            raise RuntimeError("Gremlin Client is not initialized. Check startup event configuration.")
        return self._client


# 💡 アプリケーション全体で共有するマネージャーインスタンス
GLOBAL_GREMLIN_MANAGER = GremlinClientManager()
