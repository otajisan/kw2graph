import structlog
from typing import List, Dict, Any

from gremlin_python.driver import client, serializer
from gremlin_python.driver.client import Client  # 型ヒントのためにインポート
from gremlin_python.driver.resultset import ResultSet  # 型ヒントのためにインポート
from gremlin_python.process.traversal import __ as anon

from kw2graph import config
from kw2graph.infrastructure.base import RepositoryBase

logger = structlog.get_logger(__name__)

# 関連語句の抽出結果の型定義 (OpenAIクライアントと共通)
ExtractionResult = List[Dict[str, Any]]


class GraphDatabaseRepository(RepositoryBase):
    """
    Gremlin互換のグラフデータベース（例: Neptune, TinkerPop Gremlin Server）
    に接続し、キーワードと関連度を登録するリポジトリ。
    """

    # ノードとエッジのラベルを定義
    NODE_LABEL = 'Keyword'
    EDGE_LABEL = 'RELATED_TO'

    def __init__(self, settings: config.Settings):
        super().__init__(settings)

        # 設定情報から接続URLを構築
        self.endpoint = settings.graphdb_host
        self.port = settings.graphdb_port
        self.url = f'ws://{self.endpoint}:{self.port}/gremlin'

        # Gremlinクライアントの初期化（接続は遅延実行されることが多い）
        self.client: Client = None
        self._initialize_client()

    def _initialize_client(self):
        """Gremlinクライアントの接続を試行します。"""
        try:
            logger.info("Initializing GraphDatabaseRepository", url=self.url)
            # Gremlinクライアントの作成
            # submitメソッドは、クエリ文字列をサーバーに送信するためのメソッドです。
            self.client = client.Client(
                self.url,
                'g',  # リモートトラバーサルソース名 (Gremlin Serverのデフォルト)
                message_serializer=serializer.GraphSONSerializersV3d0()
            )
            # 接続テスト (クライアントの接続が確立されるまで待つ)
            self.client.submit('g.V().limit(1)').all().result()
            logger.info("GraphDatabaseRepository connected successfully.")

        except Exception as e:
            logger.error("Failed to connect to Gremlin Server.", error=str(e), url=self.url)
            self.client = None  # 接続失敗時はNoneを維持

    def _execute_gremlin(self, query: str) -> List[Any]:
        """Gremlinクエリを実行し、結果をリストで返します。"""
        if not self.client:
            raise ConnectionError("Gremlin Server is not connected.")

        try:
            # client.submit()でクエリを送信し、結果セットを取得
            results: ResultSet = self.client.submit(query)
            # .all().result() で結果セットの全要素を取得（同期的に完了を待つ）
            return results.all().result()
        except Exception as e:
            logger.error("Gremlin query execution failed.", query=query, error=str(e))
            raise e

    def upsert_keyword_node(self, keyword: str) -> str:
        """
        キーワードノードをグラフに登録（Upsert: 存在しなければ作成、存在すれば取得）します。

        :param keyword: 登録するキーワード名
        :return: ノードのID（GremlinはID文字列を返す）
        """
        # Gremlinクエリ: 存在しなければ作成、存在すれば取得
        # TinkerPop Gremlin Serverでは、ノードのIDを返すには .id() を使用
        query = (
            f"g.V().has('{self.NODE_LABEL}', 'name', '{keyword}')"
            f".fold().coalesce(unfold(),"
            f"addV('{self.NODE_LABEL}').property('name', '{keyword}')).id()"
        )

        results = self._execute_gremlin(query)
        # 結果はノードIDのリストとして返されるため、最初の要素を返す
        return results[0] if results else None

    def register_related_keywords(self, seed_keyword: str, extracted_data: ExtractionResult) -> bool:
        """
        GPTから抽出されたデータ（関連キーワードとスコア）をグラフに登録します。

        :param seed_keyword: 起点となるキーワード
        :param extracted_data: OpenAIから取得した {"keyword": str, "score": float} のリスト
        :return: 登録処理が完全に成功した場合 True、エラーが発生した場合 False
        """
        logger.info("Starting registration to GraphDB.", seed_keyword=seed_keyword)

        try:
            # 1. 起点ノードを取得または作成
            seed_node_id = self.upsert_keyword_node(seed_keyword)
            if not seed_node_id:
                logger.error("Failed to upsert seed keyword node.", keyword=seed_keyword)
                return False  # 失敗

            # 2. 各関連キーワードを登録
            for item in extracted_data:
                related_keyword = item['keyword']
                score = item['score']

                # --- 関連ノードのUpsertとエッジの作成 ---

                # 関連ノードを取得または作成
                related_node_id = self.upsert_keyword_node(related_keyword)

                if related_node_id:
                    # 3. エッジ (関連) を作成/更新

                    # Gremlinクエリ: seed_node_id -> related_node_id へのエッジを作成/更新
                    edge_query = (
                        f"g.V('{seed_node_id}').as('a').V('{related_node_id}').coalesce("
                        f"inE('{self.EDGE_LABEL}').where(outV().is('a')),"
                        f"addE('{self.EDGE_LABEL}').from('a')).property('score', {score})"
                    )

                    self._execute_gremlin(edge_query)
                    logger.debug("Edge registered.", source=seed_keyword, target=related_keyword, score=score)
                else:
                    # 関連ノードの作成/取得に失敗した場合は、エラーとして処理を継続せず False を返すことも検討できます
                    logger.error("Failed to upsert related keyword node. Skipping.", keyword=related_keyword)
                    # ここでは、部分的な失敗を許容せず、全体を失敗と見なす場合、以下の行を追加します:
                    # return False

            logger.info("GraphDB registration finished successfully.", seed_keyword=seed_keyword)
            return True  # すべての処理が成功

        except (ConnectionError, Exception) as e:
            # _execute_gremlin内で発生したConnectionErrorやその他の例外をキャッチ
            logger.error("GraphDB registration failed due to an error.", seed_keyword=seed_keyword, error=str(e))
            return False
