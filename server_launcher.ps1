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

# 1. 文字コードの設定（日本語表示用）
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
[System.Console]::InputEncoding = [System.Text.Encoding]::UTF8

# 2. 環境変数の設定
$env:TERM = "xterm-256color"             # 256色カラー警告対策
$env:COLORTERM = "truecolor"             # True color (24-bit) 警告対策

# 3. スクリプトがある場所にカレントディレクトリを変更
Set-Location $PSScriptRoot

Write-Host "FastAPIサーバーを起動します..." -ForegroundColor Cyan
Write-Host "作業ディレクトリ: $PSScriptRoot" -ForegroundColor Gray

# 4. FastAPIサーバーをバックグラウンドで起動
pwsh -NoExit -Command "python -m paper_memory serve"