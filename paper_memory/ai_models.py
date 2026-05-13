# Copyright 2026 hosimitu
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# -*- coding: utf-8 -*-
"""
AI Models — プロジェクトで使用するAIモデル名の一元管理
"""

# PDFからのテキストおよび表の抽出に使用するモデル
# 処理速度と構造化データ抽出の精度のバランスから選択
# [使用箇所] scripts/extract_pdf.py
EXTRACTION_MODEL = "gemini-3-flash-preview"

# セマンティック検索用のベクトル（埋め込み）生成に使用するモデル
# [使用箇所] paper_memory/store.py
EMBEDDING_MODEL = "models/gemini-embedding-2"

# ダッシュボードのQA機能で回答を生成するために使用するモデル
# [使用箇所] paper_memory/server.py
QA_MODEL = "gemini-3.1-flash-lite"

# ノート間の意味的な関連性を評価し、自動リンクを構築するために使用するモデル
# [使用箇所] paper_memory/autolinker.py
AUTOLINK_MODEL = "gemini-3.1-flash-lite"
