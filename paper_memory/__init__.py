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
Paper Memory — 論文要素蓄積システム

A-Memの設計思想（Zettelkasten原則：原子性・リンキング・進化）に基づき、
研究論文PDFから知識要素を抽出・蓄積・組織化するPythonヘルパーパッケージ。
Gemini CLIのバックエンドとして動作する。
"""

__version__ = "0.2.0"

from .reference import Reference, ReferenceStore  # noqa: F401
