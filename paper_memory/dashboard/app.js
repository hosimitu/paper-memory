/**
 * Paper Memory Dashboard - Main Application
 */

const API_BASE = '/api';

const TYPE_LABELS = {
    background: '背景・先行研究',
    method: '手法・アプローチ',
    result: '結果・データ',
    discussion: '考察・解釈',
    conclusion: '結論',
    insight: '著者の洞察',
    limitation: '限界・課題',
    future_work: '今後の展望',
    definition: '定義'
};

const TYPE_COLORS = {
    background: 'var(--color-background)',
    method: 'var(--color-method)',
    result: 'var(--color-result)',
    discussion: 'var(--color-discussion)',
    insight: 'var(--color-insight)',
    limitation: 'var(--color-limitation)',
    future_work: 'var(--color-future)',
    definition: 'var(--color-definition)'
};

class App {
    constructor() {
        this.contentArea = document.getElementById('content-area');
        this.viewTitle = document.getElementById('view-title');
        this.navItems = document.querySelectorAll('.nav-item');
        this.themeToggle = document.getElementById('theme-toggle');
        this.noteModal = document.getElementById('note-modal');

        this.currentView = 'overview';
        this.cache = {};
        this.qaHistoryOffset = 0;
        this.init();
    }

    init() {
        // Navigation setup
        this.navItems.forEach(item => {
            item.addEventListener('click', (e) => {
                e.preventDefault();
                const view = item.getAttribute('data-view');
                this.switchView(view);
            });
        });

        // Theme toggle
        this.themeToggle.addEventListener('click', () => {
            document.body.classList.toggle('light-mode');
            const isLight = document.body.classList.contains('light-mode');
            localStorage.setItem('theme', isLight ? 'light' : 'dark');
        });

        // Modal close
        const closeBtn = this.noteModal.querySelector('.modal-close');
        closeBtn.onclick = () => this.noteModal.classList.remove('active');
        this.noteModal.onclick = (e) => {
            if (e.target === this.noteModal) this.noteModal.classList.remove('active');
        };

        // History API (Back/Forward support)
        window.onpopstate = (e) => {
            if (e.state) {
                this.switchView(e.state.view, e.state.params, false);
            } else {
                this.switchView('overview', {}, false);
            }
        };

        // Load saved theme
        const savedTheme = localStorage.getItem('theme');
        if (savedTheme === 'dark') {
            document.body.classList.remove('light-mode');
            document.body.classList.add('dark-mode');
        } else {
            document.body.classList.add('light-mode');
        }

        // Initial view
        this.switchView('overview', {}, false);

        lucide.createIcons();
    }

    async switchView(view, params = {}, saveHistory = true) {
        this.currentView = view;
        this.currentParams = params;

        // Save history state
        if (saveHistory) {
            history.pushState({ view, params }, '', `#${view}`);
        }

        // Update active nav
        this.navItems.forEach(item => {
            item.classList.toggle('active', item.getAttribute('data-view') === view);
        });

        // Show loader
        this.contentArea.innerHTML = '<div class="loader-container"><div class="loader"></div></div>';

        // Set title
        const titles = {
            overview: '概要',
            notes: '知識ノート',
            papers: '登録論文',
            references: '参考文献',
            search: 'セマンティック検索',
            qa: 'AIアシスタント'
        };
        this.viewTitle.innerText = titles[view] || 'Paper Memory';

        // Load data and render
        try {
            switch (view) {
                case 'overview': await this.renderOverview(); break;
                case 'notes': await this.renderNotes(params); break;
                case 'papers': await this.renderPapers(); break;
                case 'references': await this.renderReferences(); break;
                case 'search': await this.renderSearch(params); break;
                case 'qa': await this.renderQA(params); break;
            }
        } catch (err) {
            console.error(err);
            this.contentArea.innerHTML = `<div class="error-msg">データの取得に失敗しました: ${err.message}</div>`;
        }

        lucide.createIcons();
    }

    async renderOverview() {
        const stats = await this.fetchJson('/stats');
        if (this.currentView !== 'overview') return;

        const template = document.getElementById('tpl-overview');
        const content = template.content.cloneNode(true);

        // Fill stats
        content.getElementById('stat-total-notes').innerText = stats.notes.total_notes;
        content.getElementById('stat-total-papers').innerText = stats.notes.total_papers;
        content.getElementById('stat-total-links').innerText = stats.notes.total_links;
        content.getElementById('stat-total-refs').innerText = stats.references.total_unread;

        // Click handlers for stat cards
        content.querySelectorAll('.stat-card').forEach(card => {
            const view = card.getAttribute('data-goto');
            if (view) {
                card.addEventListener('click', () => this.switchView(view));
            }
        });

        // Type distribution
        const distArea = content.getElementById('type-distribution');
        for (const [type, count] of Object.entries(stats.notes.type_distribution)) {
            const tag = document.createElement('div');
            tag.className = 'type-tag';
            tag.style.borderLeft = `4px solid ${TYPE_COLORS[type] || '#ccc'}`;
            tag.innerHTML = `<span>${TYPE_LABELS[type] || type}</span> <strong>${count}</strong>`;

            tag.addEventListener('click', () => {
                this.switchView('notes', { type: type });
            });

            distArea.appendChild(tag);
        }

        // Recent notes
        const recentArea = content.getElementById('recent-notes');
        const notes = await this.fetchJson('/notes');
        if (this.currentView !== 'overview') return;

        notes.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))
            .slice(0, 5)
            .forEach(note => {
                const item = document.createElement('div');
                item.className = 'note-card mini';
                item.style.setProperty('--type-color', TYPE_COLORS[note.element_type] || '#ccc');
                item.innerHTML = `
                    <div class="note-header"><span class="note-type">${TYPE_LABELS[note.element_type]}</span></div>
                    <div class="note-content">${note.content}</div>
                `;
                item.onclick = () => this.showNoteDetail(note.id);
                recentArea.appendChild(item);
            });

        this.contentArea.innerHTML = '';
        this.contentArea.appendChild(content);
    }

    async renderNotes(params = {}) {
        this.contentArea.innerHTML = '';
        const filterType = params.type;
        const paperId = params.paperId;

        const filterBar = document.createElement('div');
        filterBar.className = 'filter-bar';

        if (paperId) {
            filterBar.innerHTML = `
                <div style="display:flex; align-items:center; gap:16px; width:100%">
                    <span style="font-weight:600; color:var(--accent)">論文フィルタ適用中</span>
                    <button class="type-filter-btn active" onclick="window.app.switchView('notes')">
                        <i data-lucide="x" style="width:14px;height:14px;display:inline-block;vertical-align:middle"></i> フィルタ解除
                    </button>
                </div>
            `;
        } else {
            const typeFilters = document.createElement('div');
            typeFilters.className = 'type-filters';
            const allBtn = document.createElement('button');
            allBtn.className = `type-filter-btn ${!filterType ? 'active' : ''}`;
            allBtn.innerText = 'すべて';
            allBtn.onclick = () => this.switchView('notes');
            typeFilters.appendChild(allBtn);

            Object.entries(TYPE_LABELS).forEach(([type, label]) => {
                const btn = document.createElement('button');
                btn.className = `type-filter-btn ${filterType === type ? 'active' : ''}`;
                btn.innerText = label;
                btn.onclick = () => this.switchView('notes', { type: type });
                typeFilters.appendChild(btn);
            });
            filterBar.appendChild(typeFilters);
        }

        const searchContainer = document.createElement('div');
        searchContainer.className = 'search-filter-container';
        searchContainer.innerHTML = `
            <i data-lucide="search" style="width:18px;height:18px"></i>
            <input type="text" class="search-filter-input" placeholder="現在のリストから検索...">
        `;

        filterBar.appendChild(searchContainer);
        this.contentArea.appendChild(filterBar);

        let endpoint = '/notes';
        if (paperId) {
            endpoint = `/papers/${paperId}/notes`;
            this.viewTitle.innerText = `ノート: ${params.title || '特定論文'}`;
        } else if (filterType) {
            endpoint += `?type=${encodeURIComponent(filterType)}`;
            this.viewTitle.innerText = `知識ノート: ${TYPE_LABELS[filterType]}`;
        }

        const notes = await this.fetchJson(endpoint);
        const list = document.createElement('div');
        list.className = 'note-list';

        const renderList = (data) => {
            list.innerHTML = '';
            if (data.length === 0) {
                list.innerHTML = '<div class="error-msg">ノートが見つかりませんでした</div>';
                return;
            }
            data.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp)).forEach(note => {
                const card = document.createElement('div');
                card.className = 'note-card';
                card.style.setProperty('--type-color', TYPE_COLORS[note.element_type] || '#ccc');
                card.innerHTML = `
                    <div class="note-header">
                        <span class="note-type">${TYPE_LABELS[note.element_type]}</span>
                        <span class="note-date">${new Date(note.timestamp).toLocaleDateString()}</span>
                    </div>
                    <div class="note-content">${note.content}</div>
                    <div class="note-footer">
                        <i data-lucide="book" style="width:14px;height:14px;display:inline-block;vertical-align:middle;margin-right:4px"></i>
                        ${note.source_paper.title}
                    </div>
                `;
                card.onclick = () => this.showNoteDetail(note.id);
                list.appendChild(card);
            });
            lucide.createIcons();
        };

        renderList(notes);
        this.contentArea.appendChild(list);

        const searchInput = searchContainer.querySelector('.search-filter-input');
        searchInput.addEventListener('input', (e) => {
            const q = e.target.value.toLowerCase();
            const filtered = notes.filter(n =>
                n.content.toLowerCase().includes(q) ||
                n.source_paper.title.toLowerCase().includes(q) ||
                (n.keywords && n.keywords.some(k => k.toLowerCase().includes(q)))
            );
            renderList(filtered);
        });
    }

    async showNoteDetail(noteId) {
        // Reset action buttons
        document.getElementById('modal-actions').style.display = 'none';

        const note = await this.fetchJson(`/notes/${noteId}`);

        const typeEl = document.getElementById('modal-type');
        typeEl.innerText = TYPE_LABELS[note.element_type];
        typeEl.style.color = TYPE_COLORS[note.element_type];

        document.getElementById('modal-paper-title').innerText = note.source_paper.title;

        const doi = note.source_paper.doi;
        const doiArea = document.getElementById('modal-paper-doi');
        if (doi) {
            doiArea.innerHTML = `DOI: <a href="https://doi.org/${doi}" target="_blank" rel="noopener noreferrer" class="paper-doi-link">${doi}</a>`;
        } else {
            doiArea.innerHTML = '';
        }

        document.getElementById('modal-content-full').innerText = note.content;

        const kwArea = document.getElementById('modal-keywords');
        kwArea.innerHTML = '';
        (note.keywords || []).forEach(kw => {
            const span = document.createElement('span');
            span.className = 'keyword-tag clickable';
            span.innerText = kw;
            span.onclick = () => {
                this.noteModal.classList.remove('active');
                this.switchView('search', { query: kw });
            };
            kwArea.appendChild(span);
        });

        document.getElementById('modal-context').innerText = note.context || '-';

        const linksArea = document.getElementById('modal-links');
        linksArea.innerHTML = '';
        if (note.linked_notes_info && note.linked_notes_info.length > 0) {
            note.linked_notes_info.forEach(link => {
                const card = document.createElement('div');
                card.className = 'note-card mini';
                card.style.setProperty('--type-color', TYPE_COLORS[link.element_type] || '#ccc');
                card.innerHTML = `
                    <div class="note-header"><span class="note-type">${TYPE_LABELS[link.element_type]}</span></div>
                    <div class="note-content">${link.content}</div>
                `;
                card.onclick = (e) => {
                    e.stopPropagation();
                    this.showNoteDetail(link.id);
                };
                linksArea.appendChild(card);
            });
        } else {
            linksArea.innerHTML = '<p class="modal-text-small">関連ノートはありません</p>';
        }

        this.noteModal.classList.add('active');
        lucide.createIcons();
    }

    async renderPapers() {
        const papers = await this.fetchJson('/papers');
        const list = document.createElement('div');
        list.className = 'paper-list grid';

        papers.forEach((paper, index) => {
            const doiLink = paper.doi ? `<a href="https://doi.org/${paper.doi}" target="_blank" rel="noopener noreferrer" class="paper-doi-link">${paper.doi}</a>` : '-';
            const card = document.createElement('div');
            card.className = 'dashboard-section paper-card';
            card.innerHTML = `
                <h4>[${index + 1}] ${paper.title}</h4>
                <div class="paper-meta">
                    <p>著者: ${JSON.parse(paper.authors).join(', ')}</p>
                    <p>年: ${paper.year || '不明'}</p>
                    <p>DOI: ${doiLink}</p>
                </div>
            `;
            list.appendChild(card);
        });

        this.contentArea.innerHTML = '';
        this.contentArea.appendChild(list);
    }

    async renderReferences() {
        const allRefs = await this.fetchJson('/references');
        // unread のものだけ表示
        const refs = allRefs.filter(r => r.status === 'unread');

        this.contentArea.innerHTML = '<h3>未読参考文献</h3><div class="note-list"></div>';
        const list = this.contentArea.querySelector('.note-list');

        refs.forEach(ref => {
            const card = document.createElement('div');
            card.className = 'note-card';
            card.style.setProperty('--type-color', ref.relevance === 'high' ? '#ef4444' : '#38bdf8');
            card.innerHTML = `
                <div class="note-header">
                    <span class="note-type">${ref.relevance.toUpperCase()} RELEVANCE</span>
                </div>
                <h5 style="margin: 12px 0; line-height: 1.4;">${ref.title}</h5>
                <p class="note-content">${ref.reason}</p>
                <div class="note-footer">引用元: ${ref.cited_by}</div>
            `;
            card.onclick = () => this.showReferenceDetail(ref);
            list.appendChild(card);
        });
    }

    async showReferenceDetail(ref) {
        const papers = await this.fetchJson('/papers');
        const sourcePaper = papers.find(p => p.title === ref.cited_by);

        const typeEl = document.getElementById('modal-type');
        typeEl.innerText = `${ref.relevance.toUpperCase()} RELEVANCE`;
        typeEl.style.color = ref.relevance === 'high' ? '#ef4444' : '#38bdf8';

        document.getElementById('modal-paper-title').innerText = ref.title;

        const doi = ref.doi;
        const doiArea = document.getElementById('modal-paper-doi');
        if (doi) {
            doiArea.innerHTML = `DOI: <a href="https://doi.org/${doi}" target="_blank" rel="noopener noreferrer" class="paper-doi-link">${doi}</a>`;
        } else {
            doiArea.innerHTML = 'DOI: 不明';
        }

        document.getElementById('modal-content-full').innerText = ref.reason;

        const kwArea = document.getElementById('modal-keywords');
        kwArea.innerHTML = '';
        let keywords = [];
        try { keywords = JSON.parse(ref.keywords || '[]'); } catch (e) { }
        keywords.forEach(kw => {
            const span = document.createElement('span');
            span.className = 'keyword-tag clickable';
            span.innerText = kw;
            span.onclick = () => {
                this.noteModal.classList.remove('active');
                this.switchView('search', { query: kw });
            };
            kwArea.appendChild(span);
        });

        let citedByHtml = ref.cited_by;
        if (sourcePaper) {
            const escapedTitle = sourcePaper.title.replace(/'/g, "\\'");
            citedByHtml = `<a href="#" onclick="event.preventDefault(); window.app.noteModal.classList.remove('active'); window.app.switchView('notes', {paperId: '${sourcePaper.id}', title: '${escapedTitle}'})" style="color:var(--accent); text-decoration:underline;">${ref.cited_by}</a>`;
        }

        document.getElementById('modal-context').innerHTML = `
            <strong>引用元:</strong> ${citedByHtml}<br>
            <strong>ジャーナル:</strong> ${ref.journal || '-'}<br>
            <strong>出版年:</strong> ${ref.year || '-'}
        `;

        document.getElementById('modal-links').innerHTML = '';
        document.querySelector('.modal-links-section h4').innerText = '';

        // Show and setup action buttons
        const actionArea = document.getElementById('modal-actions');
        actionArea.style.display = 'flex';

        const btnDismiss = document.getElementById('btn-dismiss-ref');

        btnDismiss.onclick = () => {
            if (confirm('この参考文献をリストから除外しますか？\n（将来、別の論文から引用された場合には自動的に再表示されます）')) {
                this.updateReferenceStatus(ref.id, 'dismissed');
            }
        };

        this.noteModal.classList.add('active');
        lucide.createIcons();
    }

    async updateReferenceStatus(refId, newStatus) {
        try {
            const res = await fetch(`${API_BASE}/references/${refId}/status`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ status: newStatus })
            });

            if (!res.ok) throw new Error('Status update failed');

            this.noteModal.classList.remove('active');
            // キャッシュをクリアして再描画
            delete this.cache['/references'];
            delete this.cache['/stats'];
            this.switchView('references');
        } catch (err) {
            alert(`エラーが発生しました: ${err.message}`);
        }
    }

    async renderSearch(params = {}) {
        this.contentArea.innerHTML = `
            <div class="search-page">
                <div class="search-guide">
                    <h3><i data-lucide="sparkles"></i> 意味で探すセマンティック検索</h3>
                    <p>キーワードの完全一致だけでなく、言葉の「意味」の近さで知識を検索します。文章のような自然なクエリでも関連するノートを見つけ出せます。</p>
                    <ul>
                        <li><strong>概念検索</strong>: 「膜の劣化メカニズム」など、特定の事象やメカニズムについて探す</li>
                        <li><strong>横断比較</strong>: 「透過係数の測定条件」など、異なる論文の共通項目を比較する</li>
                        <li><strong>キモの特定</strong>: 「著者の独創的なアイデア」などで検索し、研究の核心を突く</li>
                    </ul>
                </div>
                
                <div class="search-container-large">
                    <i data-lucide="search" class="search-icon-large"></i>
                    <input type="text" id="search-input" placeholder="知識を意味で検索（例：膜分離の性能限界）..." class="search-box-large">
                </div>
                <p class="search-hint">Enterキーで検索を実行します</p>

                <div class="search-settings">
                    <div class="threshold-control">
                        <label for="threshold-slider">関連度の閾値 (低いほど厳密):</label>
                        <input type="range" id="threshold-slider" class="threshold-slider" min="0.2" max="0.8" step="0.05" value="0.45">
                        <span id="threshold-display" class="threshold-value">0.45</span>
                    </div>
                </div>
                
                <div id="search-results-meta" style="margin-bottom: 16px; color: var(--text-secondary); font-size: 0.9rem;"></div>
                <div id="search-results" class="note-list"></div>
            </div>
        `;

        const input = document.getElementById('search-input');
        const resultsArea = document.getElementById('search-results');
        const thresholdSlider = document.getElementById('threshold-slider');
        const thresholdDisplay = document.getElementById('threshold-display');

        thresholdSlider.addEventListener('input', (e) => {
            thresholdDisplay.innerText = e.target.value;
        });

        input.addEventListener('keypress', async (e) => {
            if (e.key === 'Enter') {
                this.executeSearch(input.value, resultsArea, parseFloat(thresholdSlider.value));
            }
        });

        if (params.query) {
            input.value = params.query;
            this.executeSearch(params.query, resultsArea, 0.45);
        }

        lucide.createIcons();
    }

    async renderQA(params = {}) {
        this.contentArea.innerHTML = `
            <div class="search-page">
                <div class="qa-section dashboard-section" style="padding: 24px;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <h3><i data-lucide="bot"></i> AIアシスタント（過去の知識への質問）</h3>
                        <div id="qa-rate-limit" class="status-badge" style="background: var(--bg-secondary); color: var(--text-light); font-size: 0.8rem; padding: 4px 12px; border-radius: 20px;">
                            API使用状況: 取得中...
                        </div>
                    </div>
                    <p class="search-hint">蓄積されたノートをもとにAIが回答を生成します。推測を排除し、情報源を明示します。</p>
                    <div class="search-container-large" style="margin-top: 16px;">
                        <i data-lucide="message-circle" class="search-icon-large"></i>
                        <input type="text" id="qa-input" placeholder="AIに質問する（例：最も透過率が高い膜は何ですか？）..." class="search-box-large">
                        <button id="qa-btn" class="action-btn" style="margin-left: 12px; padding: 0 24px; height: 100%;">質問</button>
                    </div>

                    <div class="search-settings" style="margin-top: 16px; margin-bottom: 0;">
                        <div class="threshold-control">
                            <label for="qa-threshold-slider">関連度の閾値 (低いほど厳密):</label>
                            <input type="range" id="qa-threshold-slider" class="threshold-slider" min="0.2" max="0.8" step="0.05" value="0.45">
                            <span id="qa-threshold-display" class="threshold-value">0.45</span>
                        </div>
                    </div>

                    <div id="qa-results" style="margin-top: 24px;"></div>

                    <div id="qa-history-container" class="qa-history-section">
                        <div class="qa-history-header">
                            <h3><i data-lucide="history"></i> 過去の質問履歴 (最新10件)</h3>
                            <button id="clear-qa-history" class="action-btn dismiss" style="font-size: 0.8rem; padding: 4px 12px;">すべての履歴を消去</button>
                        </div>
                        <div id="qa-history-list" class="qa-history-list">
                            <div style="color: var(--text-light); font-size: 0.9rem;">履歴を読み込み中...</div>
                        </div>
                    </div>
                </div>
            </div>
        `;

        const qaInput = document.getElementById('qa-input');
        const qaBtn = document.getElementById('qa-btn');
        const qaResultsArea = document.getElementById('qa-results');
        const qaThresholdSlider = document.getElementById('qa-threshold-slider');
        const qaThresholdDisplay = document.getElementById('qa-threshold-display');

        qaThresholdSlider.addEventListener('input', (e) => {
            qaThresholdDisplay.innerText = e.target.value;
        });

        const triggerQA = () => {
            if (qaInput.value.trim()) {
                this.executeQA(qaInput.value, qaResultsArea, parseFloat(qaThresholdSlider.value));
            }
        };

        qaBtn.addEventListener('click', triggerQA);
        qaInput.addEventListener('keypress', async (e) => {
            if (e.key === 'Enter') triggerQA();
        });

        if (params.query) {
            qaInput.value = params.query;
            triggerQA();
        }

        // 履歴消去ボタン
        document.getElementById('clear-qa-history').addEventListener('click', async () => {
            if (confirm('質問履歴をすべて消去しますか？')) {
                await fetch(API_BASE + '/qa/history/clear', { method: 'POST' });
                this.loadQAHistory();
            }
        });

        // 履歴読み込み
        this.qaHistoryOffset = 0;
        this.loadQAHistory();

        // 初期レート制限表示
        fetch('/api/stats')
            .then(res => res.json())
            .then(data => {
                if (data.api_usage) {
                    const badge = document.getElementById('qa-rate-limit');
                    if (badge) badge.innerText = `API使用状況: ${data.api_usage.used} / ${data.api_usage.limit} RPM`;
                }
            });

        lucide.createIcons();
    }

    async loadQAHistory(isAppend = false) {
        const listArea = document.getElementById('qa-history-list');
        if (!listArea) return;

        if (!isAppend) {
            this.qaHistoryOffset = 0;
            listArea.innerHTML = '<div style="color: var(--text-light); font-size: 0.9rem;">履歴を読み込み中...</div>';
        }

        try {
            // limit=11 で次ページがあるか確認する
            const history = await this.fetchJson(`/qa/history?limit=11&offset=${this.qaHistoryOffset}`);

            if (!isAppend) listArea.innerHTML = '';

            // さらに表示ボタンを一旦削除
            const existingMoreBtn = document.getElementById('qa-history-more-btn');
            if (existingMoreBtn) existingMoreBtn.remove();

            if ((!history || history.length === 0) && !isAppend) {
                listArea.innerHTML = '<div style="color: var(--text-light); font-size: 0.9rem;">履歴はありません。</div>';
                return;
            }

            const hasMore = history.length > 10;
            const itemsToShow = hasMore ? history.slice(0, 10) : history;

            itemsToShow.forEach(item => {
                const date = new Date(item.timestamp).toLocaleString('ja-JP');
                const div = document.createElement('div');
                div.className = 'qa-history-item';
                div.innerHTML = `
                    <div class="qa-history-query">
                        <div class="qa-history-query-text">
                            <i data-lucide="message-circle" style="width:16px; flex-shrink: 0;"></i>
                            <span>${item.query}</span>
                        </div>
                        <button class="delete-history-btn" title="削除">
                            <i data-lucide="trash-2" style="width:16px; height:16px;"></i>
                        </button>
                    </div>
                    <div class="qa-history-answer">${item.answer}</div>
                    <div class="qa-history-meta">
                        ${date} | 閾値: ${item.threshold} | ${item.references.length}件の参照
                    </div>
                `;

                const deleteBtn = div.querySelector('.delete-history-btn');
                deleteBtn.onclick = async (e) => {
                    e.stopPropagation();
                    if (confirm('この質問履歴を削除しますか？')) {
                        await fetch(`${API_BASE}/qa/history/${item.id}/delete`, { method: 'POST' });
                        this.loadQAHistory();
                    }
                };

                div.onclick = () => {
                    // 履歴をクリックしたら結果エリアに再表示
                    const resultsArea = document.getElementById('qa-results');
                    this.displayQAResult(item.query, item.answer, item.references, resultsArea);
                    document.getElementById('qa-input').value = item.query;
                    document.getElementById('qa-threshold-slider').value = item.threshold;
                    document.getElementById('qa-threshold-display').innerText = item.threshold;
                    resultsArea.scrollIntoView({ behavior: 'smooth' });
                };
                listArea.appendChild(div);
            });

            if (hasMore) {
                this.qaHistoryOffset += 10;
                const moreBtn = document.createElement('button');
                moreBtn.id = 'qa-history-more-btn';
                moreBtn.className = 'action-btn';
                moreBtn.style = 'width: 100%; justify-content: center; margin-top: 16px; background: var(--bg-secondary); border: 1px dashed var(--border); color: var(--text-secondary); font-size: 0.85rem;';
                moreBtn.innerHTML = '<i data-lucide="chevron-down" style="width:16px;"></i> さらに過去の履歴を表示';
                moreBtn.onclick = () => this.loadQAHistory(true);
                listArea.appendChild(moreBtn);
            }

            lucide.createIcons();
        } catch (err) {
            listArea.innerHTML = `<div class="error-msg">履歴の読み込みに失敗しました: ${err.message}</div>`;
        }
    }

    displayQAResult(query, answer, references, resultsArea) {
        const dedentedAnswer = (str) => {
            const lines = str.split('\n');
            const firstNonEmptyLine = lines.find(l => l.trim().length > 0);
            if (!firstNonEmptyLine) return str.trim();
            const match = firstNonEmptyLine.match(/^(\s+)/);
            if (!match) return str.trim();
            const indent = match[1];
            return lines.map(l => l.startsWith(indent) ? l.slice(indent.length) : l).join('\n').trim();
        };

        resultsArea.innerHTML = `
            <div class="qa-result-card" style="background: var(--bg-primary); border: 1px solid var(--accent); border-radius: 16px; padding: 24px; box-shadow: 0 4px 20px rgba(56, 189, 248, 0.1);">
                <div style="font-weight: 700; color: var(--accent); margin-bottom: 12px; display: flex; align-items: center; gap: 8px;">
                    <i data-lucide="help-circle"></i> 質問: ${query}
                </div>
                <div class="modal-text-block markdown-content" style="font-size: 1.05rem; line-height: 1.8; color: var(--text-primary); margin-bottom: 24px;">
                    ${marked.parse(dedentedAnswer(answer))}
                </div>
                
                ${references.length > 0 ? `
                <div class="qa-references">
                    <h4 style="font-size: 0.9rem; color: var(--text-secondary); margin-bottom: 12px; border-top: 1px solid var(--border); padding-top: 16px;">
                        <i data-lucide="library" style="width: 16px; vertical-align: middle; margin-right: 4px;"></i> 参照された知識ノート
                    </h4>
                    <div class="mini-note-list horizontal">
                        ${references.map(ref => `
                            <div class="note-card" style="min-width: 200px; max-width: 200px; padding: 12px; font-size: 0.85rem; cursor: pointer;" onclick="app.showNoteDetail('${ref.note_id}')">
                                <div style="color: var(--accent); font-weight: 600; margin-bottom: 4px; line-height: 1.4;">[${ref.id}]<br>${ref.title}</div>
                                <div style="display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; opacity: 0.8;">
                                    ノート詳細を表示
                                </div>
                            </div>
                        `).join('')}
                    </div>
                </div>
                ` : ''}
            </div>
        `;
        lucide.createIcons();
    }

    async executeQA(query, resultsArea, threshold = 0.45) {
        if (!query || !query.trim()) return;

        resultsArea.innerHTML = `
            <div class="loader-container" style="display:flex; flex-direction:column; gap:12px; align-items:center;">
                <div class="loader"></div>
                <div style="color:var(--text-light); font-size:0.9rem;">回答生成中...（閾値 ${threshold} でノートを検索中）</div>
            </div>`;

        try {
            const res = await fetch(API_BASE + '/qa', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query, threshold, n: 15 })
            });

            const data = await res.json();
            if (!res.ok) {
                throw new Error(data.error || `HTTP error! status: ${res.status}`);
            }

            if (data.error) throw new Error(data.error);

            // レート制限表示の更新
            if (data.api_usage) {
                const badge = document.getElementById('qa-rate-limit');
                if (badge) badge.innerText = `API使用状況: ${data.api_usage.used} / ${data.api_usage.limit} RPM`;
            }

            if (data.answer) {
                this.displayQAResult(query, data.answer, data.references || [], resultsArea);
                this.loadQAHistory(); // 履歴を更新
            } else {
                resultsArea.innerHTML = `<div class="error-msg">回答の取得に失敗しました</div>`;
            }
        } catch (err) {
            resultsArea.innerHTML = `<div class="error-msg">QA処理中にエラーが発生しました: ${err.message}</div>`;
        }
        lucide.createIcons();
    }

    async executeSearch(query, resultsArea, threshold = 0.45) {
        if (!query || !query.trim()) return;

        const metaArea = document.getElementById('search-results-meta');
        if (metaArea) metaArea.innerText = '';
        resultsArea.innerHTML = '<div class="loader-container"><div class="loader"></div></div>';

        try {
            // n=50 で多めに取得し、サーバー側の閾値フィルタリングを利用
            const endpoint = `/search?q=${encodeURIComponent(query)}&threshold=${threshold}&n=50`;
            const data = await this.fetchJson(endpoint, false);
            const results = data.results || [];

            resultsArea.innerHTML = '';

            if (results.length === 0) {
                resultsArea.innerHTML = '<div class="error-msg">関連する知識は見つかりませんでした。閾値を上げて再試行してください。</div>';
                return;
            }

            if (metaArea) {
                metaArea.innerText = `${results.length} 件の関連ノートが見つかりました（閾値: ${threshold}）`;
            }

            // 要素タイプ順にソート（元々のロジックを維持）
            const typeOrder = Object.keys(TYPE_LABELS);
            results.sort((a, b) => {
                const orderA = typeOrder.indexOf(a.note.element_type);
                const orderB = typeOrder.indexOf(b.note.element_type);
                return orderA - orderB;
            });

            results.forEach(res => {
                const note = res.note;
                // Cosine Distance をスコア（パーセント）に変換 (1 - distance) * 100
                const score = res.distance !== null ? Math.round((1 - res.distance) * 100) : null;

                const card = document.createElement('div');
                card.className = 'note-card';
                card.style.setProperty('--type-color', TYPE_COLORS[note.element_type] || '#ccc');
                card.innerHTML = `
                    <div class="note-header">
                        <span class="note-type">${TYPE_LABELS[note.element_type]}</span>
                        ${score !== null ? `<span class="score-badge">適合度: ${score}%</span>` : ''}
                    </div>
                    <div class="note-content">${note.content}</div>
                    <div class="note-footer">${note.source_paper.title}</div>
                `;
                card.onclick = () => this.showNoteDetail(note.id);
                resultsArea.appendChild(card);
            });
        } catch (err) {
            resultsArea.innerHTML = `<div class="error-msg">検索中にエラーが発生しました: ${err.message}</div>`;
        }
        lucide.createIcons();
    }

    async fetchJson(endpoint, useCache = true) {
        if (useCache && this.cache[endpoint]) {
            return this.cache[endpoint];
        }

        try {
            const res = await fetch(API_BASE + endpoint);
            if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
            const data = await res.json();

            if (useCache) {
                this.cache[endpoint] = data;
            }
            this.updateConnectionStatus(true);
            return data;
        } catch (e) {
            this.updateConnectionStatus(false);
            throw e;
        }
    }

    updateConnectionStatus(isConnected) {
        const badge = document.getElementById('connection-status');
        const text = document.getElementById('server-status');
        if (isConnected) {
            badge.classList.remove('disconnected');
            text.innerText = 'Connected';
        } else {
            badge.classList.add('disconnected');
            text.innerText = 'Disconnected';
        }
    }
}

// Start the app
window.addEventListener('DOMContentLoaded', () => {
    window.app = new App();
});
