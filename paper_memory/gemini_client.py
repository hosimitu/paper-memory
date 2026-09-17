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

def is_retryable_error(e: Exception) -> tuple[bool, str]:
    """429（レート制限）や 503（過負荷・高需要）、504（タイムアウト）等の一時的エラーを判定する。
    
    Returns:
        (is_retryable, reason_label)
    """
    code = getattr(e, "code", None)
    status = getattr(e, "status", None)
    err_str = str(e).lower()

    # 429: Rate Limit / Quota Exceeded
    if code == 429 or status == "RESOURCE_EXHAUSTED" or "429" in err_str or "quota" in err_str or "rate limit" in err_str:
        return True, "レート制限 (429)"

    # 503: Service Unavailable / High demand / Overloaded
    if (
        code == 503
        or status == "UNAVAILABLE"
        or "503" in err_str
        or "unavailable" in err_str
        or "high demand" in err_str
        or "overloaded" in err_str
    ):
        return True, "サーバー高需要・過負荷 (503)"

    # 504: Gateway Timeout / Deadline Exceeded
    if code == 504 or status == "DEADLINE_EXCEEDED" or "504" in err_str or "deadline exceeded" in err_str:
        return True, "タイムアウト (504)"

    # 500: Internal Server Error (一時的な障害の場合がある)
    if code == 500 or status == "INTERNAL" or "500 internal" in err_str:
        return True, "サーバー一時エラー (500)"

    return False, ""


def _calculate_backoff(attempt: int, reason: str, base_sec: float = 5.0, factor: float = 2.0, max_sec: float = 60.0) -> float:
    """指数バックオフの待機時間を計算する（ジッター付き）"""
    import random
    if "429" in reason:
        # レート制限の場合は10秒単位
        return min(10.0 * (attempt + 1), max_sec)
    # 503 / 504 等の過負荷は指数バックオフ
    delay = min(base_sec * (factor ** attempt), max_sec)
    jitter = random.uniform(0.5, 1.5)
    return delay + jitter


def generate_content_with_retry(model: str, contents, config=None, max_retries: int = 4):
    """テキスト生成のラッパー（リトライ・過負荷・レート制限対応）"""
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
            retryable, reason = is_retryable_error(e)
            if retryable:
                if attempt < max_retries - 1:
                    wait_sec = _calculate_backoff(attempt, reason)
                    print(f"⚠️ LLM生成: {reason}発生。{wait_sec:.1f}秒待機してリトライします (試行 {attempt + 1}/{max_retries})...", file=sys.stderr)
                    time.sleep(wait_sec)
                    continue
            raise e
    return None

def embed_content_with_retry(model: str, contents: list[str], task_type: str = "RETRIEVAL_DOCUMENT", max_retries: int = 4) -> list[list[float]]:
    """埋め込みベクトル生成のラッパー（リトライ・過負荷・レート制限対応）"""
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
            retryable, reason = is_retryable_error(e)
            if retryable:
                if attempt < max_retries - 1:
                    wait_sec = _calculate_backoff(attempt, reason)
                    print(f"⚠️ Embedding: {reason}発生。{wait_sec:.1f}秒待機してリトライします (試行 {attempt + 1}/{max_retries})...", file=sys.stderr)
                    time.sleep(wait_sec)
                    continue
            raise e
    return []
