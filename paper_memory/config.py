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
Config — プロジェクト設定の一元管理
"""

import os
from dotenv import load_dotenv

# .env の読み込み
load_dotenv(override=True)

# デフォルト言語設定 ('en' or 'ja')
DEFAULT_LANGUAGE = os.environ.get("PAPER_MEMORY_LANGUAGE", "ja")

# AIモデル設定（ai_models.py から継承または統合も検討可能だが、一旦インポートしておく）
from .ai_models import QA_MODEL, EMBEDDING_MODEL, TABLE_IMAGE_MODEL, FORMULA_IMAGE_MODEL, AUTOLINK_MODEL
