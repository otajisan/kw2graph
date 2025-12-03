import re
from typing import List


class TextFormatter:
    """
    OpenAIにリクエストする前に、コンテンツタイトルを正規化するためのユーティリティクラス。
    ハッシュタグ、絵文字、括弧などのノイズを除去する機能を提供します。
    """

    # --- 正規表現パターン定義 ---

    # 1. 全角・半角の括弧とその中身 (例: 【新型ランクル70】 や (カスタム紹介) )
    # 注意: これを適用すると、重要な情報（例: 【ポケモン名】）も消える可能性があるので注意深く使う必要があります。
    BRACKET_CONTENT_PATTERN = re.compile(r"[【\[（](.*?)[】\]）]")

    # 2. ハッシュタグ (例: #料理 #飯テロ)
    HASHTAG_PATTERN = re.compile(r"#[^\s]+")

    # 3. 絵文字、記号、顔文字 (一般的なユニコードの絵文字ブロックと記号)
    # これは完全ではありませんが、一般的な絵文字を除去します。
    EMOJI_PATTERN = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # Emoticons
        "\U0001F300-\U0001F5FF"  # Symbols & Pictographs
        "\U0001F680-\U0001F6FF"  # Transport & Map Symbols
        "\U0001F1E0-\U0001F1FF"  # Flags (iOS)
        "\U00002702-\U000027B0"
        "]+",
        flags=re.UNICODE
    )

    # 4. 連続する空白文字を一つにまとめる
    WHITESPACE_PATTERN = re.compile(r"\s+")

    def __init__(self):
        """インスタンス化時に特に必要な処理はありません。"""
        pass

    def remove_hashtags(self, text: str) -> str:
        """ハッシュタグとその後の空白を除去します。"""
        return self.HASHTAG_PATTERN.sub(" ", text).strip()

    def remove_emojis_and_symbols(self, text: str) -> str:
        """絵文字や一部の記号を除去します。"""
        # 絵文字除去後に残る不要な空白は、後続の normalize_whitespace で処理
        return self.EMOJI_PATTERN.sub("", text)

    def remove_bracketed_content(self, text: str) -> str:
        """全角・半角の括弧とその中身を削除します。（例: 【タイトル】）"""
        # 注意: 重要な情報（例: 商品名など）を誤って除去しないか確認が必要です。
        return self.BRACKET_CONTENT_PATTERN.sub(" ", text)

    def normalize_whitespace(self, text: str) -> str:
        """複数の空白文字や改行を一つの半角スペースにまとめます。"""
        return self.WHITESPACE_PATTERN.sub(" ", text).strip()

    def normalize_title(self, title: str) -> str:
        """
        OpenAIに渡す前の最終的な正規化処理を実行します。
        """
        # 処理順序は重要です: 除去してから空白を正規化するのがベスト

        # 1. 括弧内のコンテンツを除去
        text = self.remove_bracketed_content(title)

        # 2. ハッシュタグを除去
        text = self.remove_hashtags(text)

        # 3. 絵文字や記号を除去
        text = self.remove_emojis_and_symbols(text)

        # 4. 最後に、連続する空白を整理 (この段階で空文字列になる)
        text = self.normalize_whitespace(text)

        return text

    def normalize_titles_list(self, titles: List[str]) -> List[str]:
        """
        タイトルのリスト全体に対して正規化処理を実行し、空文字列を除外します。

        :param titles: 処理対象のタイトル文字列のリスト
        :return: 正規化され、空でない文字列のみを含むリスト
        """
        # ★ 修正ポイント: リスト内包表記に if normalized_title: の条件を追加
        normalized_list = [self.normalize_title(title) for title in titles]

        # Pythonでは、空文字列 ("") はブール値として False と評価されます。
        # したがって、if normalized_title で空文字列を効率的に除外できます。
        return [
            normalized_title
            for normalized_title in normalized_list
            if normalized_title
        ]
