# -*- coding: utf-8 -*-
"""
Gemini Client — google-genai API の共通クライアントモジュール
"""
import os
import sys
import time

from google import genai
from google.genai import types
from google.genai import errors as genai_errors

_client = None

def get_client() -> genai.Client:
    """GEMINI_API_KEY を使った共通クライアントを返す"""
    global _client
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            print("⚠️ GEMINI_API_KEY 環境変数が設定されていません。", file=sys.stderr)
            # api_key が None の場合でも Client 初期化は試みる（環境変数 GOOGLE_API_KEY などをフォールバックとして見る可能性があるため）
            # 明示的に指定する場合は以下の通り
        _client = genai.Client(api_key=api_key)
    return _client

def generate_content_with_retry(model: str, contents, config=None, max_retries: int = 3):
    """テキスト生成のラッパー（リトライ・レート制限対応）"""
    client = get_client()
    
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=model,
                contents=contents,
                config=config
            )
            return response
        except Exception as e:
            # 429 判定
            if isinstance(e, genai_errors.APIError) and getattr(e, "code", None) == 429 or "429" in str(e) or "quota" in str(e).lower():
                if attempt < max_retries - 1:
                    wait_sec = 10 * (attempt + 1)
                    print(f"⚠️ LLM生成: レート制限発生。{wait_sec}秒待機してリトライします (試行 {attempt + 1}/{max_retries})...", file=sys.stderr)
                    time.sleep(wait_sec)
                    continue
            raise e
    return None

def embed_content_with_retry(model: str, contents: list[str], task_type: str = "RETRIEVAL_DOCUMENT", max_retries: int = 3) -> list[list[float]]:
    """埋め込みベクトル生成のラッパー"""
    client = get_client()
    
    for attempt in range(max_retries):
        try:
            result = client.models.embed_content(
                model=model,
                contents=contents,
                config=types.EmbedContentConfig(task_type=task_type)
            )
            # embeddings はリストのオブジェクトとして返される
            return [e.values for e in result.embeddings]
        except Exception as e:
            if isinstance(e, genai_errors.APIError) and getattr(e, "code", None) == 429 or "429" in str(e) or "quota" in str(e).lower():
                if attempt < max_retries - 1:
                    wait_sec = 10 * (attempt + 1)
                    print(f"⚠️ Embedding: レート制限発生。{wait_sec}秒待機してリトライします (試行 {attempt + 1}/{max_retries})...", file=sys.stderr)
                    time.sleep(wait_sec)
                    continue
            raise e
    return []
