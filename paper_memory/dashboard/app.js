/**
 * Paper Memory Dashboard - Main Application
 */

const API_BASE = '/api';

const getTypeLabels = () => ({
    background: i18n.t('type.background'),
    method: i18n.t('type.method'),
    result: i18n.t('type.result'),
    discussion: i18n.t('type.discussion'),
    conclusion: i18n.t('type.conclusion'),
    insight: i18n.t('type.insight'),
    limitation: i18n.t('type.limitation'),
    future_work: i18n.t('type.future_work'),
    definition: i18n.t('type.definition')
});

const TYPE_HEX_COLORS = {
    background: '#6366f1',
    method: '#10b981',
    result: '#f59e0b',
    discussion: '#8b5cf6',
    conclusion: '#3b82f6',
    insight: '#ec4899',
    limitation: '#ef4444',
    future_work: '#06b6d4',
    definition: '#84cc16',
    other: '#94a3b8'
};

const TYPE_COLORS = {
    background: 'var(--color-background)',
    method: 'var(--color-method)',
    result: 'var(--color-result)',
    discussion: 'var(--color-discussion)',
    conclusion: '#3b82f6',
    insight: 'var(--color-insight)',
    limitation: 'var(--color-limitation)',
    future_work: 'var(--color-future)',
    definition: 'var(--color-definition)',
    other: 'var(--text-muted)'
};

// キーワードを現在の言語に合わせて平滑化した文字列配列として取得する
const getKeywordsList = (keywords) => {
    if (!keywords) return [];

    // 文字列の場合はJSONパースを試みる
    if (typeof keywords === 'string') {
        try {
            keywords = JSON.parse(keywords);
        } catch (e) {
            return [keywords];
        }
    }

    // 配列の場合は各要素を文字列または翻訳オブジェクトとして解決
    if (Array.isArray(keywords)) {
        return keywords.map(kw => {
            if (kw && typeof kw === 'object') {
                return i18n.getTranslatedString(kw);
            }
            return kw ? String(kw) : '';
        }).filter(Boolean);
    }

    // オブジェクトの場合は言語別配列、または多言語文字列オブジェクトとして解決
    if (typeof keywords === 'object') {
        const lang = i18n.currentLang();
        const kwList =
            keywords[lang] ??
            (lang !== 'en' ? (keywords['local'] ?? keywords['ja']) : undefined) ??
            keywords['en'] ??
            Object.values(keywords)[0];

        if (Array.isArray(kwList)) {
            return kwList.map(String).filter(Boolean);
        }
        if (typeof kwList === 'string') {
            return [kwList];
        }
        return [i18n.getTranslatedString(keywords)].filter(Boolean);
    }

    return [String(keywords)];
};

// 著者情報を文字列の配列として安全に取得する
const getAuthorsList = (authors) => {
    if (!authors) return [];
    if (Array.isArray(authors)) {
        return authors;
    }
    if (typeof authors === 'string') {
        try {
            const parsed = JSON.parse(authors);
            if (Array.isArray(parsed)) {
                return parsed;
            }
            return [parsed];
        } catch (e) {
            // カンマ区切りの文字列などの場合は分割する
            return authors.split(',').map(s => s.trim()).filter(Boolean);
        }
    }
    return [String(authors)];
};

class App {
    constructor() {
        this.contentArea = document.getElementById('content-area');
        this.viewTitle = document.getElementById('view-title');
        this.navItems = document.querySelectorAll('.nav-item');
        this.themeToggle = document.getElementById('theme-toggle');
        this.noteModal = document.getElementById('note-modal');
        this.langSelector = document.getElementById('lang-selector');

        this.currentView = 'overview';
        this.cache = {};
        this.qaHistoryOffset = 0;
        this.paperSortMode = ['title', 'year', 'registration'].includes(localStorage.getItem('paper-sort-mode'))
            ? localStorage.getItem('paper-sort-mode')
            : 'registration';
        this.init();
    }

    getMethodBadgeHtml(method) {
        if (method === 'vector') {
            return `
                <span class="method-badge vector" title="${i18n.t('search.method.vector')}">
                    <i data-lucide="sparkles"></i>
                    ${i18n.t('search.method.vector')}
                </span>
            `;
        } else if (method === 'hybrid') {
            return `
                <span class="method-badge hybrid" title="${i18n.t('search.method.hybrid-title')}">
                    <i data-lucide="layers"></i>
                    ${i18n.t('search.method.hybrid')}
                </span>
            `;
        } else {
            return `
                <span class="method-badge keyword" title="${i18n.t('search.method.keyword')}">
                    <i data-lucide="type"></i>
                    ${i18n.t('search.method.keyword')}
                </span>
            `;
        }
    }

    async init() {
        // Load server config first
        await i18n.loadConfig();

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

        // Language selector setup
        if (this.langSelector) {
            this.langSelector.value = i18n.currentLang();
            this.langSelector.addEventListener('change', (e) => {
                i18n.setLanguage(e.target.value);
            });
        }

        i18n.applyTranslations();

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
            overview: i18n.t('nav.overview'),
            notes: i18n.t('nav.notes'),
            upload: i18n.t('nav.upload'),
            papers: i18n.t('nav.papers'),
            references: i18n.t('nav.references'),
            search: i18n.t('nav.search'),
            graph: i18n.t('nav.graph'),
            qa: i18n.t('nav.qa')
        };
        this.viewTitle.innerText = titles[view] || 'Paper Memory';

        // Load data and render
        try {
            switch (view) {
                case 'overview': await this.renderOverview(); break;
                case 'notes': await this.renderNotes(params); break;
                case 'upload': await this.renderUpload(); break;
                case 'papers': await this.renderPapers(); break;
                case 'references': await this.renderReferences(); break;
                case 'search': await this.renderSearch(params); break;
                case 'graph': await this.renderGraph(params); break;
                case 'qa': await this.renderQA(params); break;
            }
        } catch (err) {
            console.error(err);
            this.contentArea.innerHTML = `<div class="error-msg">${i18n.t('error.fetch_failed', { message: err.message })}</div>`;
        }

        lucide.createIcons();
    }

    async renderOverview() {
        const stats = await this.fetchJson('/stats');
        if (this.currentView !== 'overview') return;

        const template = document.getElementById('tpl-overview');
        const content = template.content.cloneNode(true);

        // Fill stats
        content.querySelector('#stat-total-notes').innerText = stats.notes.total_notes;
        content.querySelector('#stat-total-papers').innerText = stats.notes.total_papers;
        content.querySelector('#stat-total-links').innerText = stats.notes.total_links;
        content.querySelector('#stat-total-refs').innerText = stats.references.total_unread;

        // Click handlers for stat cards
        content.querySelectorAll('.stat-card').forEach(card => {
            const view = card.getAttribute('data-goto');
            if (view) {
                card.addEventListener('click', () => this.switchView(view));
            }
        });

        // Type distribution
        const distArea = content.querySelector('#type-distribution');
        const typeLabels = getTypeLabels();
        for (const [type, count] of Object.entries(stats.notes.type_distribution)) {
            const tag = document.createElement('div');
            tag.className = 'type-tag';
            tag.style.borderLeft = `4px solid ${TYPE_COLORS[type] || '#ccc'}`;
            tag.innerHTML = `<span>${typeLabels[type] || type}</span> <strong>${count}</strong>`;

            tag.addEventListener('click', () => {
                this.switchView('notes', { type: type });
            });

            distArea.appendChild(tag);
        }

        // Recent notes
        const recentArea = content.querySelector('#recent-notes');
        const notes = await this.fetchJson('/notes');
        if (this.currentView !== 'overview') return;

        notes.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))
            .slice(0, 5)
            .forEach(note => {
                const item = document.createElement('div');
                item.className = 'note-card mini';
                item.style.setProperty('--type-color', TYPE_COLORS[note.element_type] || '#ccc');
                item.innerHTML = `
                    <div class="note-header"><span class="note-type">${typeLabels[note.element_type] || note.element_type}</span></div>
                    <div class="note-content">${i18n.getTranslatedString(note.content)}</div>
                `;
                item.onclick = () => this.showNoteDetail(note.id);
                recentArea.appendChild(item);
            });

        this.contentArea.innerHTML = '';
        i18n.applyTranslations(content);
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
                    <span style="font-weight:600; color:var(--accent)">${i18n.t('filter.paper_applied')}</span>
                    <button class="type-filter-btn active" onclick="window.app.switchView('notes')">
                        <i data-lucide="x" style="width:14px;height:14px;display:inline-block;vertical-align:middle"></i> ${i18n.t('filter.clear')}
                    </button>
                </div>
            `;
        } else {
            const typeFilters = document.createElement('div');
            typeFilters.className = 'type-filters';
            const allBtn = document.createElement('button');
            allBtn.className = `type-filter-btn ${!filterType ? 'active' : ''}`;
            allBtn.innerText = i18n.t('filter.all');
            allBtn.onclick = () => this.switchView('notes');
            typeFilters.appendChild(allBtn);

            Object.entries(getTypeLabels()).forEach(([type, label]) => {
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
            <input type="text" class="search-filter-input" placeholder="${i18n.t('search.placeholder')}">
        `;

        filterBar.appendChild(searchContainer);
        this.contentArea.appendChild(filterBar);

        let endpoint = '/notes';
        if (paperId) {
            endpoint = `/papers/${paperId}/notes`;
            this.viewTitle.innerText = `${i18n.t('nav.notes')}: ${params.title || ''}`;
        } else if (filterType) {
            endpoint += `?type=${encodeURIComponent(filterType)}`;
            this.viewTitle.innerText = `${i18n.t('nav.notes')}: ${getTypeLabels()[filterType]}`;
        }

        const notes = await this.fetchJson(endpoint);
        const list = document.createElement('div');
        list.className = 'note-list';

        const renderList = (data) => {
            list.innerHTML = '';
            if (data.length === 0) {
                list.innerHTML = `<div class="error-msg">${i18n.t('search.not_found')}</div>`;
                return;
            }
            const typeLabels = getTypeLabels();
            data.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp)).forEach(note => {
                const card = document.createElement('div');
                card.className = 'note-card';
                card.style.setProperty('--type-color', TYPE_COLORS[note.element_type] || '#ccc');
                card.innerHTML = `
                    <div class="note-header">
                        <span class="note-type">${typeLabels[note.element_type] || note.element_type}</span>
                        <span class="note-date">${new Date(note.timestamp).toLocaleDateString()}</span>
                    </div>
                    <div class="note-content">${i18n.getTranslatedString(note.content)}</div>
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
            const filtered = notes.filter(n => {
                const c = i18n.getTranslatedString(n.content).toLowerCase();
                const t = n.source_paper.title.toLowerCase();
                const kws = getKeywordsList(n.keywords);
                const kwMatch = kws.some(k => k.toLowerCase().includes(q));
                return c.includes(q) || t.includes(q) || kwMatch;
            });
            renderList(filtered);
        });
    }

    async showNoteDetail(noteId) {
        // Reset action buttons
        document.getElementById('modal-actions').style.display = 'none';

        const note = await this.fetchJson(`/notes/${noteId}`);

        const typeLabels = getTypeLabels();
        const typeEl = document.getElementById('modal-type');
        typeEl.innerText = typeLabels[note.element_type] || note.element_type;
        typeEl.style.color = TYPE_COLORS[note.element_type];

        document.getElementById('modal-paper-title').innerText = note.source_paper ? note.source_paper.title : 'Unknown';

        const doi = note.source_paper ? note.source_paper.doi : null;
        const doiArea = document.getElementById('modal-paper-doi');
        if (doi) {
            doiArea.innerHTML = `DOI: <a href="https://doi.org/${doi}" target="_blank" rel="noopener noreferrer" class="paper-doi-link">${doi}</a>`;
        } else {
            doiArea.innerHTML = '';
        }

        if (note.has_markdown) {
            doiArea.innerHTML += ` <span style="margin: 0 8px;">|</span> <a href="${note.markdown_url}" target="_blank" style="color:var(--accent); text-decoration:underline;">📄 Markdownを開く</a>`;
        }

        document.getElementById('modal-content-full').innerText = i18n.getTranslatedString(note.content);

        const kwArea = document.getElementById('modal-keywords');
        kwArea.innerHTML = '';
        const keywords = getKeywordsList(note.keywords);
        keywords.forEach(kwStr => {
            const span = document.createElement('span');
            span.className = 'keyword-tag clickable';
            span.innerText = kwStr;
            span.onclick = () => {
                this.noteModal.classList.remove('active');
                this.switchView('search', { query: kwStr });
            };
            kwArea.appendChild(span);
        });

        document.getElementById('modal-context').innerText = i18n.getTranslatedString(note.context) || '-';

        const linksArea = document.getElementById('modal-links');
        linksArea.innerHTML = '';
        if (note.linked_notes_info && note.linked_notes_info.length > 0) {
            const typeLabels = getTypeLabels();
            note.linked_notes_info.forEach(link => {
                const card = document.createElement('div');
                card.className = 'note-card mini';
                card.style.setProperty('--type-color', TYPE_COLORS[link.element_type] || '#ccc');

                const translatedReason = i18n.getTranslatedString(link.reason);
                const reasonHtml = translatedReason ? `<div class="note-reason" style="font-size:0.8rem; color:var(--text-secondary); margin-top:8px; font-style:italic;">"${translatedReason}"</div>` : '';

                card.innerHTML = `
                    <div class="note-header"><span class="note-type">${typeLabels[link.element_type] || link.element_type}</span></div>
                    <div class="note-content">${i18n.getTranslatedString(link.content)}</div>
                    ${reasonHtml}
                `;
                card.onclick = (e) => {
                    e.stopPropagation();
                    this.showNoteDetail(link.id);
                };
                linksArea.appendChild(card);
            });
        } else {
            linksArea.innerHTML = `<p class="modal-text-small">${i18n.t('modal.no_links')}</p>`;
        }

        this.noteModal.classList.add('active');
        lucide.createIcons();
    }

    async renderPapers() {
        const papers = await this.fetchJson('/papers');
        const sortedPapers = this.paperSortMode === 'title'
            ? [...papers].sort((a, b) => (a.title || '').localeCompare(b.title || '', undefined, { sensitivity: 'base' }))
            : this.paperSortMode === 'year'
                ? [...papers].sort((a, b) => {
                    const ay = Number(a.year) || 0;
                    const by = Number(b.year) || 0;
                    return by - ay || (a.title || '').localeCompare(b.title || '', undefined, { sensitivity: 'base' });
                })
                : papers;

        // デフォルトはリスト表示
        if (!this.paperViewMode) {
            this.paperViewMode = 'list';
        }

        const headerHtml = `
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; gap: 12px; flex-wrap: wrap;">
                <h3 style="margin: 0;">${i18n.t('nav.papers') || '登録論文'}</h3>
                <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                    <div class="view-toggle" style="display: flex; gap: 4px;">
                        <button id="btn-sort-registration" class="action-btn ${this.paperSortMode === 'registration' ? 'active' : ''}" title="${i18n.t('paper.sort.registration')}">
                            ${i18n.t('paper.sort.registration')}
                        </button>
                        <button id="btn-sort-title" class="action-btn ${this.paperSortMode === 'title' ? 'active' : ''}" title="${i18n.t('paper.sort.title')}">
                            ${i18n.t('paper.sort.title')}
                        </button>
                        <button id="btn-sort-year" class="action-btn ${this.paperSortMode === 'year' ? 'active' : ''}" title="${i18n.t('paper.sort.year')}">
                            ${i18n.t('paper.sort.year')}
                        </button>
                    </div>
                    <div class="view-toggle">
                        <button id="btn-view-list" class="action-btn ${this.paperViewMode === 'list' ? 'active' : ''}" title="リスト表示">
                            <i data-lucide="list"></i>
                        </button>
                        <button id="btn-view-grid" class="action-btn ${this.paperViewMode === 'grid' ? 'active' : ''}" title="タイル表示">
                            <i data-lucide="layout-grid"></i>
                        </button>
                    </div>
                </div>
            </div>
        `;

        const list = document.createElement('div');
        list.className = `paper-view-container ${this.paperViewMode}-view`;

        sortedPapers.forEach((paper, index) => {
            const doiLink = paper.doi ? `<a href="https://doi.org/${paper.doi}" target="_blank" rel="noopener noreferrer" class="paper-doi-link">${paper.doi}</a>` : '-';
            let mdLink = '';
            if (paper.has_markdown && paper.id) {
                mdLink = ` <span style="margin: 0 8px;">|</span> <a href="${paper.markdown_url}" target="_blank" style="color:var(--accent); text-decoration:underline;">📄 Markdownを開く</a>`;
            }
            const thumbnailHtml = paper.thumbnail_url
                ? `<div class="paper-thumbnail"><img src="${paper.thumbnail_url}" alt="Thumbnail"></div>`
                : `<div class="paper-thumbnail"><i data-lucide="image" style="width:32px;height:32px;opacity:0.3;"></i></div>`;

            const card = document.createElement('div');
            card.className = 'dashboard-section paper-card';
            card.style.position = 'relative';
            card.innerHTML = `
                ${thumbnailHtml}
                <div class="paper-content">
                    <h4>[${index + 1}] ${paper.title}</h4>
                    <div class="paper-meta">
                        <p>${i18n.t('modal.authors') || 'Authors'}: ${getAuthorsList(paper.authors).join(', ')}</p>
                        <p>${i18n.t('ref.year')}: ${paper.year || i18n.t('status.unknown')}</p>
                        <p>DOI: ${doiLink}${mdLink}</p>
                    </div>
                </div>
                <div class="paper-actions" style="position: absolute; top: 12px; right: 12px;">
                    <button class="action-btn delete-paper-btn" data-id="${paper.id}" title="Delete Paper" style="color: #ef4444;">
                        <i data-lucide="trash-2"></i>
                    </button>
                </div>
            `;
            list.appendChild(card);
        });

        this.contentArea.innerHTML = headerHtml;
        this.contentArea.appendChild(list);

        document.getElementById('btn-view-list').onclick = () => {
            this.paperViewMode = 'list';
            this.renderPapers();
        };
        document.getElementById('btn-view-grid').onclick = () => {
            this.paperViewMode = 'grid';
            this.renderPapers();
        };
        document.getElementById('btn-sort-registration').onclick = () => {
            this.paperSortMode = 'registration';
            localStorage.setItem('paper-sort-mode', this.paperSortMode);
            this.renderPapers();
        };
        document.getElementById('btn-sort-title').onclick = () => {
            this.paperSortMode = 'title';
            localStorage.setItem('paper-sort-mode', this.paperSortMode);
            this.renderPapers();
        };
        document.getElementById('btn-sort-year').onclick = () => {
            this.paperSortMode = 'year';
            localStorage.setItem('paper-sort-mode', this.paperSortMode);
            this.renderPapers();
        };

        // 削除ボタンのイベントリスナー追加
        list.querySelectorAll('.delete-paper-btn').forEach(btn => {
            btn.onclick = async (e) => {
                e.stopPropagation();
                const paperId = btn.getAttribute('data-id');
                if (confirm(i18n.t('paper.confirm_delete'))) {
                    try {
                        const res = await fetch(`/api/papers/${paperId}/delete`, { method: 'POST' });
                        const data = await res.json();
                        if (data.status === 'success') {
                            alert(i18n.t('paper.delete_success') + `\nDeleted notes: ${data.deleted_notes}`);
                            this.cache = {}; // Clear cache
                            this.renderPapers();
                        } else {
                            alert(i18n.t('error.alert', { message: data.error || 'Failed to delete' }));
                        }
                    } catch (err) {
                        alert(i18n.t('error.alert', { message: err.message }));
                    }
                }
            };
        });

        lucide.createIcons();
    }

    async renderReferences() {
        const allRefs = await this.fetchJson('/references');
        // unread のものだけ表示
        const refs = allRefs.filter(r => r.status === 'unread');

        this.contentArea.innerHTML = `<h3>${i18n.t('ref.unread_title')}</h3><div class="note-list"></div>`;
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
                <p class="note-content">${i18n.getTranslatedString(ref.reason)}</p>
                <div class="note-footer">${i18n.t('ref.source')}: ${ref.cited_by}</div>
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
            doiArea.innerHTML = `DOI: ${i18n.t('status.disconnected').includes('切断') ? '不明' : 'Unknown'}`;
        }

        document.getElementById('modal-content-full').innerText = i18n.getTranslatedString(ref.reason);

        const kwArea = document.getElementById('modal-keywords');
        kwArea.innerHTML = '';
        const keywords = getKeywordsList(ref.keywords);
        keywords.forEach(kwStr => {
            const span = document.createElement('span');
            span.className = 'keyword-tag clickable';
            span.innerText = kwStr;
            span.onclick = () => {
                this.noteModal.classList.remove('active');
                this.switchView('search', { query: kwStr });
            };
            kwArea.appendChild(span);
        });

        let citedByHtml = ref.cited_by;
        if (sourcePaper) {
            const escapedTitle = sourcePaper.title.replace(/'/g, "\\'");
            citedByHtml = `<a href="#" onclick="event.preventDefault(); window.app.noteModal.classList.remove('active'); window.app.switchView('notes', {paperId: '${sourcePaper.id}', title: '${escapedTitle}'})" style="color:var(--accent); text-decoration:underline;">${ref.cited_by}</a>`;
        }

        document.getElementById('modal-context').innerHTML = `
            <strong>${i18n.t('ref.source')}:</strong> ${citedByHtml}<br>
            <strong>${i18n.t('ref.journal')}:</strong> ${ref.journal || '-'}<br>
            <strong>${i18n.t('ref.year')}:</strong> ${ref.year || '-'}
        `;

        document.getElementById('modal-links').innerHTML = '';
        document.querySelector('.modal-links-section h4').innerText = '';

        // Show and setup action buttons
        const actionArea = document.getElementById('modal-actions');
        actionArea.style.display = 'flex';

        const btnDismiss = document.getElementById('btn-dismiss-ref');

        btnDismiss.onclick = () => {
            if (confirm(i18n.t('ref.confirm_dismiss'))) {
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
            alert(i18n.t('error.alert', { message: err.message }));
        }
    }

    async renderSearch(params = {}) {
        this.contentArea.innerHTML = `
            <div class="search-page">
                <div class="search-guide">
                    <h3><i data-lucide="sparkles"></i> ${i18n.t('search.guide.title')}</h3>
                    <p>${i18n.t('search.guide.desc')}</p>
                    <ul>
                        <li>${i18n.t('search.guide.li1')}</li>
                        <li>${i18n.t('search.guide.li2')}</li>
                        <li>${i18n.t('search.guide.li3')}</li>
                    </ul>
                </div>
                
                <div class="search-container-large">
                    <i data-lucide="search" class="search-icon-large"></i>
                    <input type="text" id="search-input" placeholder="${i18n.t('search.input_placeholder')}" class="search-box-large">
                </div>
                <p class="search-hint">${i18n.t('search.hint')}</p>

                <div class="search-settings">
                    <div class="threshold-control">
                        <label for="threshold-slider">${i18n.t('search.threshold')}</label>
                        <input type="range" id="threshold-slider" class="threshold-slider" min="0.2" max="0.8" step="0.05" value="0.45">
                        <span id="threshold-display" class="threshold-value">0.45</span>
                    </div>
                    <div class="threshold-control">
                        <label for="n-results-slider">${i18n.t('search.n_results')}</label>
                        <input type="range" id="n-results-slider" class="threshold-slider" min="5" max="50" step="5" value="10">
                        <span id="n-results-display" class="threshold-value">10</span>
                    </div>
                    <div class="threshold-control">
                        <label for="link-depth-select">${i18n.t('search.link_depth')}</label>
                        <select id="link-depth-select" class="graph-select">
                            <option value="0">${i18n.t('search.link_depth.0')}</option>
                            <option value="1" selected>${i18n.t('search.link_depth.1')}</option>
                            <option value="2">${i18n.t('search.link_depth.2')}</option>
                            <option value="3">${i18n.t('search.link_depth.3')}</option>
                        </select>
                    </div>
                    <div class="threshold-control">
                        <label class="toggle-label">
                            <input type="checkbox" id="expand-paper-toggle">
                            <span>${i18n.t('search.expand_paper')}</span>
                        </label>
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
        const nResultsSlider = document.getElementById('n-results-slider');
        const nResultsDisplay = document.getElementById('n-results-display');
        const linkDepthSelect = document.getElementById('link-depth-select');
        const expandPaperToggle = document.getElementById('expand-paper-toggle');

        thresholdSlider.addEventListener('input', (e) => {
            thresholdDisplay.innerText = e.target.value;
        });
        nResultsSlider.addEventListener('input', (e) => {
            nResultsDisplay.innerText = e.target.value;
        });

        const getSearchParams = () => ({
            threshold: parseFloat(thresholdSlider.value),
            n: parseInt(nResultsSlider.value),
            linkDepth: parseInt(linkDepthSelect.value),
            expandPaper: expandPaperToggle.checked,
        });

        input.addEventListener('keypress', async (e) => {
            if (e.key === 'Enter') {
                this.executeSearch(input.value, resultsArea, getSearchParams());
            }
        });

        if (params.query) {
            input.value = params.query;
            this.executeSearch(params.query, resultsArea, getSearchParams());
        }

        lucide.createIcons();
    }

    // ==========================================
    // アップロード画面
    // ==========================================
    async renderUpload() {
        const tpl = document.getElementById('tpl-upload');
        if (!tpl) {
            this.contentArea.innerHTML = '<div class="error-msg">テンプレートが見つかりません (tpl-upload)</div>';
            return;
        }
        this.contentArea.innerHTML = '';
        this.contentArea.appendChild(tpl.content.cloneNode(true));
        i18n.applyTranslations(this.contentArea);

        const configPanel = document.getElementById('upload-config-panel');
        const dropzone = document.getElementById('upload-dropzone');
        const fileInput = document.getElementById('upload-file-input');
        const queueList = document.getElementById('queue-list');
        const backendSelect = document.getElementById('pdf-backend-select');
        const lightCheckbox = document.getElementById('pdf-light-mode-checkbox');

        // marker-pdf がインストールされているかチェックして設定パネルの表示を制御
        try {
            const cfg = await this.fetchJson('/api/config');
            if (configPanel) {
                configPanel.style.display = cfg && cfg.marker_available ? 'flex' : 'none';
            }
        } catch (e) {
            if (configPanel) configPanel.style.display = 'none';
        }

        if (backendSelect && lightCheckbox) {
            const savedBackend = localStorage.getItem('pdf_backend') || 'auto';
            const savedLight = localStorage.getItem('pdf_light_mode') === 'true';
            backendSelect.value = savedBackend;
            lightCheckbox.checked = savedLight;

            const updateVisibility = () => {
                const isMarker = backendSelect.value === 'marker' || backendSelect.value === 'auto';
                document.getElementById('pdf-light-mode-container').style.display = isMarker ? 'flex' : 'none';
            };
            updateVisibility();

            backendSelect.addEventListener('change', (e) => {
                localStorage.setItem('pdf_backend', e.target.value);
                updateVisibility();
            });
            lightCheckbox.addEventListener('change', (e) => {
                localStorage.setItem('pdf_light_mode', e.target.checked ? 'true' : 'false');
            });
        }

        if (dropzone && fileInput) {
            dropzone.addEventListener('click', () => fileInput.click());
            fileInput.addEventListener('change', async (e) => {
                if (e.target.files.length > 0) {
                    const h3 = dropzone.querySelector('h3');
                    if (h3) h3.textContent = i18n.currentLang() === 'ja' ? 'アップロード中...' : 'Uploading...';
                    await window._handlePdfUpload(e.target.files[0]);
                    if (h3) h3.textContent = i18n.t('upload.dropzone_title');
                    fileInput.value = '';
                    // キュー再読み込み
                    this.switchView('upload', {}, false);
                }
            });

            dropzone.addEventListener('dragover', (e) => {
                e.preventDefault();
                dropzone.classList.add('dragover');
            });
            dropzone.addEventListener('dragleave', () => {
                dropzone.classList.remove('dragover');
            });
            dropzone.addEventListener('drop', async (e) => {
                e.preventDefault();
                dropzone.classList.remove('dragover');
                const files = Array.from(e.dataTransfer.files).filter(f => f.name.toLowerCase().endsWith('.pdf'));
                if (files.length > 0) {
                    const h3 = dropzone.querySelector('h3');
                    if (h3) h3.textContent = i18n.currentLang() === 'ja' ? 'アップロード中...' : 'Uploading...';
                    await window._handlePdfUpload(files[0]);
                    if (h3) h3.textContent = i18n.t('upload.dropzone_title');
                    this.switchView('upload', {}, false);
                }
            });
        }

        // キュー読み込み
        if (queueList) {
            try {
                const resp = await fetch('/api/queue');
                const items = await resp.json();
                if (items && items.length > 0) {
                    queueList.innerHTML = '';
                    items.forEach(item => {
                        const el = document.createElement('div');
                        el.className = 'queue-item';

                        // 日時データの取り出し（更新日時、なければ開始日時）
                        const rawValue = item.updated_at || item.started_at;
                        let dateObj;

                        if (rawValue) {
                            // 数値型（秒単位のタイムスタンプ）なら1000倍してミリ秒に、文字列型（ISO形式等）ならそのままDateオブジェクト化
                            dateObj = typeof rawValue === 'number' ? new Date(rawValue * 1000) : new Date(rawValue);
                        }

                        // 正しく変換できた場合はローカル日時に、データが無い、または不正な場合はハイフンを表示
                        const dt = (dateObj && !isNaN(dateObj.getTime())) ? dateObj.toLocaleString() : '-';

                        const turns = (item.completed_turns || []).length;
                        let mdLink = '';
                        if (item.has_markdown && item.markdown_url) {
                            mdLink = ` <span style="margin: 0 8px;">|</span> <a href="${item.markdown_url}" target="_blank" style="color:var(--accent); text-decoration:underline;">📄 Markdownを開く</a>`;
                        }
                        el.innerHTML = `
                            <div class="queue-item-info">
                                <div class="queue-item-title">${this._esc(item.paper_name)}</div>
                                <div class="queue-item-meta">Status : ${this._esc(item.status)} | Completed Turn : ${turns} | Last Updated : ${dt}${mdLink}</div>
                            </div>
                            <div class="queue-item-actions">
                                <button class="btn-resume" data-pdf="${this._esc(item.pdf_path)}">${i18n.t('upload.resume')}</button>
                                <button class="btn-delete" data-id="${this._esc(item.id)}">${i18n.t('upload.delete')}</button>
                            </div>
                        `;
                        queueList.appendChild(el);
                    });

                    queueList.querySelectorAll('.btn-resume').forEach(btn => {
                        btn.addEventListener('click', () => {
                            window._startAnalysis(btn.dataset.pdf, true, false, false);
                        });
                    });
                    queueList.querySelectorAll('.btn-delete').forEach(btn => {
                        btn.addEventListener('click', async () => {
                            const id = btn.dataset.id;
                            const action = await window._showConfirmDialog(i18n.t('upload.delete_confirm'), [
                                { label: i18n.currentLang() === 'ja' ? 'キャンセル' : 'Cancel', value: 'cancel' },
                                { label: i18n.t('upload.delete'), value: 'delete', primary: true }
                            ]);
                            if (action === 'delete') {
                                await fetch('/api/delete_queue_item', {
                                    method: 'POST',
                                    headers: { 'Content-Type': 'application/json' },
                                    body: JSON.stringify({ id })
                                });
                                this.switchView('upload', {}, false);
                            }
                        });
                    });
                } else {
                    queueList.innerHTML = `<p style="color: var(--text-muted);">${i18n.currentLang() === 'ja' ? 'キューは空です' : 'Queue is empty'}</p>`;
                }
            } catch (e) {
                console.error(e);
                queueList.innerHTML = '<p style="color: red;">Error loading queue</p>';
            }
        }

        lucide.createIcons();
    }

    _esc(unsafe) {
        if (!unsafe) return '';
        return String(unsafe)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    async renderQA(params = {}) {
        this.contentArea.innerHTML = `
            <div class="search-page">
                <div class="qa-section dashboard-section" style="padding: 24px;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <h3><i data-lucide="bot"></i> ${i18n.t('qa.title')}</h3>
                        <div id="qa-rate-limit" class="status-badge" style="background: var(--bg-secondary); color: var(--text-light); font-size: 0.8rem; padding: 4px 12px; border-radius: 20px;">
                            ${i18n.t('qa.rate_limit')}
                        </div>
                    </div>
                    <p class="search-hint">${i18n.t('qa.hint')}</p>
                    <div class="search-container-large" style="margin-top: 16px;">
                        <i data-lucide="message-circle" class="search-icon-large"></i>
                        <input type="text" id="qa-input" placeholder="${i18n.t('qa.input_placeholder')}" class="search-box-large">
                        <button id="qa-btn" class="action-btn" style="margin-left: 12px; padding: 0 24px; height: 100%;">${i18n.t('qa.btn')}</button>
                    </div>

                    <div class="search-settings" style="margin-top: 16px; margin-bottom: 0;">
                        <div class="threshold-control">
                            <label for="qa-threshold-slider">${i18n.t('search.threshold')}</label>
                            <input type="range" id="qa-threshold-slider" class="threshold-slider" min="0.2" max="0.8" step="0.05" value="0.45">
                            <span id="qa-threshold-display" class="threshold-value">0.45</span>
                        </div>
                        <div class="threshold-control">
                            <label for="qa-n-results-slider">${i18n.t('search.n_results')}</label>
                            <input type="range" id="qa-n-results-slider" class="threshold-slider" min="5" max="50" step="5" value="15">
                            <span id="qa-n-results-display" class="threshold-value">15</span>
                        </div>
                        <div class="threshold-control">
                            <label for="qa-link-depth-select">${i18n.t('search.link_depth')}</label>
                            <select id="qa-link-depth-select" class="graph-select">
                                <option value="0">${i18n.t('search.link_depth.0')}</option>
                                <option value="1" selected>${i18n.t('search.link_depth.1')}</option>
                                <option value="2">${i18n.t('search.link_depth.2')}</option>
                                <option value="3">${i18n.t('search.link_depth.3')}</option>
                            </select>
                        </div>
                        <div class="threshold-control">
                            <label class="toggle-label">
                                <input type="checkbox" id="qa-expand-paper-toggle">
                                <span>${i18n.t('search.expand_paper')}</span>
                            </label>
                        </div>
                        <div class="threshold-control">
                            <label for="qa-query-mode-select">${i18n.t('qa.rewrite_mode')}</label>
                            <select id="qa-query-mode-select" class="graph-select">
                                <option value="ai">${i18n.t('qa.rewrite_mode.ai')}</option>
                                <option value="raw" selected>${i18n.t('qa.rewrite_mode.raw')}</option>
                            </select>
                        </div>
                        <div class="threshold-control">
                            <label for="qa-mode-select">${i18n.t('qa.mode')}</label>
                            <select id="qa-mode-select" class="graph-select">
                                <option value="fact" selected>${i18n.t('qa.mode.fact')}</option>
                                <option value="insight">${i18n.t('qa.mode.insight')}</option>
                            </select>
                        </div>
                    </div>

                    <div id="qa-results" style="margin-top: 24px;"></div>

                    <div id="qa-history-container" class="qa-history-section">
                        <div class="qa-history-header">
                            <h3><i data-lucide="history"></i> ${i18n.t('qa.history')}</h3>
                            <button id="clear-qa-history" class="action-btn dismiss" style="font-size: 0.8rem; padding: 4px 12px;">${i18n.t('qa.clear_history')}</button>
                        </div>
                        <div id="qa-history-list" class="qa-history-list">
                            <div style="color: var(--text-light); font-size: 0.9rem;">${i18n.t('qa.loading_history')}</div>
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
        const qaNResultsSlider = document.getElementById('qa-n-results-slider');
        const qaNResultsDisplay = document.getElementById('qa-n-results-display');
        const qaLinkDepthSelect = document.getElementById('qa-link-depth-select');
        const qaExpandPaperToggle = document.getElementById('qa-expand-paper-toggle');
        const qaQueryModeSelect = document.getElementById('qa-query-mode-select');
        const qaModeSelect = document.getElementById('qa-mode-select');

        qaThresholdSlider.addEventListener('input', (e) => {
            qaThresholdDisplay.innerText = e.target.value;
        });
        qaNResultsSlider.addEventListener('input', (e) => {
            qaNResultsDisplay.innerText = e.target.value;
        });

        const getQAParams = () => ({
            threshold: parseFloat(qaThresholdSlider.value),
            n: parseInt(qaNResultsSlider.value),
            linkDepth: parseInt(qaLinkDepthSelect.value),
            expandPaper: qaExpandPaperToggle.checked,
            useAiRewrite: qaQueryModeSelect.value === 'ai',
            mode: qaModeSelect.value,
        });

        const triggerQA = () => {
            if (qaInput.value.trim()) {
                this.executeQA(qaInput.value, qaResultsArea, getQAParams());
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
            if (confirm(i18n.t('qa.confirm_clear'))) {
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
                    if (badge) badge.innerText = `${i18n.t('qa.rate_limit').split(':')[0]}: ${data.api_usage.used} / ${data.api_usage.limit} RPM`;
                }
            });

        lucide.createIcons();
    }

    async loadQAHistory(isAppend = false) {
        const listArea = document.getElementById('qa-history-list');
        if (!listArea) return;

        if (!isAppend) {
            this.qaHistoryOffset = 0;
            listArea.innerHTML = `<div style="color: var(--text-light); font-size: 0.9rem;">${i18n.t('qa.loading_history')}</div>`;
        }

        try {
            // limit=11 で次ページがあるか確認する
            const history = await this.fetchJson(`/qa/history?limit=11&offset=${this.qaHistoryOffset}`, false);

            if (!isAppend) listArea.innerHTML = '';

            // さらに表示ボタンを一旦削除
            const existingMoreBtn = document.getElementById('qa-history-more-btn');
            if (existingMoreBtn) existingMoreBtn.remove();

            if ((!history || history.length === 0) && !isAppend) {
                listArea.innerHTML = `<div style="color: var(--text-light); font-size: 0.9rem;">${i18n.t('qa.no_history')}</div>`;
                return;
            }

            const hasMore = history.length > 10;
            const itemsToShow = hasMore ? history.slice(0, 10) : history;

            itemsToShow.forEach(item => {
                const date = new Date(item.timestamp).toLocaleString('ja-JP');
                const linkDepthText = item.link_depth !== undefined ? i18n.t(`search.link_depth.${item.link_depth}`) : i18n.t('search.link_depth.1');
                const expandPaperText = item.expand_paper
                    ? i18n.t('qa.expand_paper.on')
                    : i18n.t('qa.expand_paper.off');
                const rewrittenQueries = Array.isArray(item.rewritten_queries) ? item.rewritten_queries.filter(Boolean) : [];
                const rewrittenSummary = rewrittenQueries.length > 0 ? rewrittenQueries.join(' • ') : i18n.t('qa.result.no_rewritten');

                const mdLink = item.output_file
                    ? `<a href="${item.output_file}" target="_blank" rel="noopener noreferrer"
                        onclick="event.stopPropagation()"
                        style="display: inline-flex; align-items: center; gap: 4px; color: var(--accent); font-size: 0.8rem; text-decoration: none;">
                        <i data-lucide="file-text" style="width:14px; height:14px;"></i>Markdown
                      </a>`
                    : '';

                const div = document.createElement('div');
                div.className = 'qa-history-item';
                div.innerHTML = `
                    <div class="qa-history-query">
                        <div class="qa-history-query-text">
                            <i data-lucide="message-circle" style="width:16px; flex-shrink: 0;"></i>
                            <span>${item.query}</span>
                        </div>
                        <div style="display: flex; align-items: center; gap: 8px;">
                            ${mdLink}
                            <button class="delete-history-btn" title="削除">
                                <i data-lucide="trash-2" style="width:16px; height:16px;"></i>
                            </button>
                        </div>
                    </div>
                    <div class="qa-history-answer">${item.answer}</div>
                    <div style="margin-top: 8px; display: flex; align-items: center; gap: 8px; color: var(--text-secondary); font-size: 0.9rem; flex-wrap: wrap;">
                        <i data-lucide="sparkles" style="width:16px;"></i>
                        <span>${i18n.t('qa.result.rewritten_query')}: ${rewrittenSummary}</span>
                    </div>
                    <div class="qa-history-meta" style="display: flex; align-items: center; gap: 12px; flex-wrap: wrap;">
                        <span>${date}</span>
                        <span>|</span>
                        <span>${i18n.t('search.threshold').split('(')[0].trim()}: ${item.threshold}</span>
                        <span>|</span>
                        <span>${i18n.t('search.link_depth')}: ${linkDepthText}</span>
                        <span>|</span>
                        <span>${i18n.t('search.expand_paper')}: ${expandPaperText}</span>
                        <span>|</span>
                        <span>${i18n.t('qa.history.n_results')} ${item.n !== undefined ? item.n : 15}</span>
                        <span>|</span>
                        <span>${item.references.length}${i18n.currentLang() === 'ja' ? '件の参照' : ' references'}</span>
                        ${this.getMethodBadgeHtml(item.search_method)}
                    </div>
                `;

                const deleteBtn = div.querySelector('.delete-history-btn');
                deleteBtn.onclick = async (e) => {
                    e.stopPropagation();
                    if (confirm(i18n.t('qa.confirm_delete'))) {
                        await fetch(`${API_BASE}/qa/history/${item.id}/delete`, { method: 'POST' });
                        this.loadQAHistory();
                    }
                };

                div.onclick = () => {
                    // 履歴をクリックしたら結果エリアに再表示
                    const resultsArea = document.getElementById('qa-results');
                    this.displayQAResult(item.query, item.answer, item.references, resultsArea, item.search_method, null, rewrittenQueries, item.output_file || null);
                    document.getElementById('qa-input').value = item.query;
                    document.getElementById('qa-threshold-slider').value = item.threshold;
                    document.getElementById('qa-threshold-display').innerText = item.threshold;
                    if (item.n !== undefined) {
                        document.getElementById('qa-n-results-slider').value = item.n;
                        document.getElementById('qa-n-results-display').innerText = item.n;
                    }
                    if (item.link_depth !== undefined) {
                        document.getElementById('qa-link-depth-select').value = item.link_depth;
                    }
                    if (item.expand_paper !== undefined) {
                        document.getElementById('qa-expand-paper-toggle').checked = item.expand_paper;
                    }
                    if (item.mode !== undefined) {
                        document.getElementById('qa-mode-select').value = item.mode;
                    }
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
                moreBtn.innerHTML = `<i data-lucide="chevron-down" style="width:16px;"></i> ${i18n.t('qa.more_history')}`;
                moreBtn.onclick = () => this.loadQAHistory(true);
                listArea.appendChild(moreBtn);
            }

            lucide.createIcons();
        } catch (err) {
            listArea.innerHTML = `<div class="error-msg">履歴の読み込みに失敗しました: ${err.message}</div>`;
        }
    }

    displayQAResult(query, answer, references, resultsArea, searchMethod = 'vector', graphStats = null, rewrittenQueries = [], outputFile = null) {
        const dedentedAnswer = (str) => {
            const lines = str.split('\n');
            const firstNonEmptyLine = lines.find(l => l.trim().length > 0);
            if (!firstNonEmptyLine) return str.trim();
            const match = firstNonEmptyLine.match(/^(\s+)/);
            if (!match) return str.trim();
            const indent = match[1];
            return lines.map(l => l.startsWith(indent) ? l.slice(indent.length) : l).join('\n').trim();
        };

        const rewrittenList = Array.isArray(rewrittenQueries) ? rewrittenQueries.filter(Boolean) : [];
        const rewrittenSummary = rewrittenList.length > 0 ? rewrittenList.join(' • ') : i18n.t('qa.result.no_rewritten');

        let statsHtml = '';
        if (graphStats && (graphStats.linked_notes > 0 || graphStats.paper_expanded > 0)) {
            statsHtml = `<span class="graph-stats-badge">
                ${i18n.t('search.graph_stats', {
                direct: graphStats.direct_hits,
                linked: graphStats.linked_notes,
                paper: graphStats.paper_expanded
            })}
            </span>`;
        }

        resultsArea.innerHTML = `
                <div style="font-weight: 700; color: var(--accent); margin-bottom: 12px; display: flex; flex-direction: column; gap: 8px;">
                    <div style="display: flex; align-items: center; gap: 12px; flex-wrap: wrap;">
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <i data-lucide="help-circle"></i> ${i18n.t('qa.result.query')}: ${query}
                        </div>
                        ${this.getMethodBadgeHtml(searchMethod)}
                        ${statsHtml}
                        ${outputFile ? `
                        <a href="${outputFile}" target="_blank" rel="noopener noreferrer" style="display: inline-flex; align-items: center; gap: 4px; padding: 4px 10px; background: rgba(var(--accent-rgb), 0.1); border-radius: 12px; font-size: 0.85rem; color: var(--accent); border: 1px solid rgba(var(--accent-rgb), 0.2); text-decoration: none;">
                            <i data-lucide="file-text" style="width: 14px; height: 14px;"></i> Markdownを開く
                        </a>
                        ` : ''}
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px; color: var(--text-secondary); font-size: 0.9rem; flex-wrap: wrap;">
                        <i data-lucide="sparkles" style="width: 16px;"></i>
                        <span>${i18n.t('qa.result.rewritten_query')}: ${rewrittenSummary}</span>
                    </div>
                </div>
                <div class="modal-text-block markdown-content" style="font-size: 1.05rem; line-height: 1.8; color: var(--text-primary); margin-bottom: 24px;">
                    ${marked.parse(dedentedAnswer(answer))}
                </div>
                
                ${references.length > 0 ? `
                <div class="qa-references">
                    <h4 style="font-size: 0.9rem; color: var(--text-secondary); margin-bottom: 12px; border-top: 1px solid var(--border); padding-top: 16px;">
                        <i data-lucide="library" style="width: 16px; vertical-align: middle; margin-right: 4px;"></i> ${i18n.t('qa.result.ref_notes')}
                    </h4>
                    <div class="mini-note-list horizontal">
                        ${references.map(ref => `
                            <div class="note-card" style="min-width: 200px; max-width: 200px; padding: 12px; font-size: 0.85rem; cursor: pointer;" onclick="app.showNoteDetail('${ref.note_id}')">
                                <div style="color: var(--accent); font-weight: 600; margin-bottom: 4px; line-height: 1.4;">[${ref.id}]<br>${ref.title}</div>
                                <div style="display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; opacity: 0.8;">
                                    ${i18n.t('qa.result.show_detail')}
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

    async executeQA(query, resultsArea, params = {}) {
        if (!query || !query.trim()) return;
        const threshold = params.threshold || 0.45;
        const n = params.n || 15;
        const linkDepth = params.linkDepth !== undefined ? params.linkDepth : 1;
        const expandPaper = params.expandPaper || false;
        const useAiRewrite = params.useAiRewrite !== undefined ? params.useAiRewrite : true;
        const mode = params.mode || 'fact';

        // 進捗ステップの定義（将来のフェーズ追加はここに行を追加するだけ）
        const STEPS = [
            { key: 'query_rewriting', label: () => i18n.t('qa.progress.query_rewriting'), icon: '✦', visible: useAiRewrite },
            { key: 'searching', label: () => i18n.t('qa.progress.searching', { threshold }), icon: '⊛' },
            { key: 'reranking', label: () => i18n.t('qa.progress.reranking'), icon: '⊕' },
            { key: 'graph_expansion', label: () => i18n.t('qa.progress.graph_expansion'), icon: '⊗', visible: linkDepth > 0 },
            { key: 'generating_answer', label: () => i18n.t('qa.progress.generating_answer'), icon: '★' },
            { key: 'saving', label: () => i18n.t('qa.progress.saving'), icon: '✓' },
        ].filter(s => s.visible !== false);

        // プログレスUIを描画
        const renderProgress = (activeKey) => {
            const stepsHtml = STEPS.map((s, idx) => {
                const isDone = STEPS.findIndex(x => x.key === activeKey) > idx;
                const isActive = s.key === activeKey;
                const cls = isDone ? 'done' : isActive ? 'active' : '';
                const iconContent = isDone ? '✔' : s.icon;
                return `<div class="qa-progress-step ${cls}" id="qa-step-${s.key}">
                    <div class="qa-step-icon">${iconContent}</div>
                    <div class="qa-step-label">${s.label()}</div>
                </div>`;
            }).join('');

            resultsArea.innerHTML = `
                <div class="qa-progress-container">
                    <div class="qa-progress-spinner"></div>
                    <div class="qa-progress-steps">${stepsHtml}</div>
                </div>`;
        };

        // 最初のステップでUIを初期化
        const firstStep = useAiRewrite ? 'query_rewriting' : 'searching';
        renderProgress(firstStep);

        try {
            const response = await fetch(API_BASE + '/qa', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query, threshold, n, link_depth: linkDepth, expand_paper: expandPaper, use_ai_rewrite: useAiRewrite, lang: i18n.currentLang(), mode })
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder('utf-8');
            let buffer = '';
            let currentEvent = null;
            let currentData = null;

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });

                // SSEのチャンクを行単位でパース
                const lines = buffer.split('\n');
                buffer = lines.pop(); // 末尾の未完成行はバッファに残す

                for (const line of lines) {
                    if (line.startsWith('event: ')) {
                        currentEvent = line.slice(7).trim();
                    } else if (line.startsWith('data: ')) {
                        currentData = line.slice(6).trim();
                    } else if (line === '' && currentEvent && currentData) {
                        // イベント完成
                        let payload = null;
                        try {
                            payload = JSON.parse(currentData);
                        } catch (parseErr) {
                            // JSONパース失敗は無視
                        }
                        
                        if (payload) {
                            if (currentEvent === 'progress') {
                                renderProgress(payload.step);
                            } else if (currentEvent === 'complete') {
                                // レート制限表示の更新
                                if (payload.api_usage) {
                                    const badge = document.getElementById('qa-rate-limit');
                                    if (badge) badge.innerText = `${i18n.t('qa.rate_limit').split(':')[0]}: ${payload.api_usage.used} / ${payload.api_usage.limit} RPM`;
                                }

                                if (payload.answer) {
                                    this.displayQAResult(query, payload.answer, payload.references || [], resultsArea, payload.search_method, payload.graph_stats, payload.rewritten_queries || [], payload.output_file || null);
                                    this.loadQAHistory();
                                } else {
                                    resultsArea.innerHTML = `<div class="error-msg">${i18n.t('error.alert', { message: 'No answer returned' })}</div>`;
                                }
                            } else if (currentEvent === 'error') {
                                throw new Error(payload.error || 'Unknown error');
                            }
                        }

                        currentEvent = null;
                        currentData = null;
                    }
                }
            }
        } catch (err) {
            resultsArea.innerHTML = `<div class="error-msg">${i18n.t('error.alert', { message: err.message })}</div>`;
        }
        lucide.createIcons();
    }


    async executeSearch(query, resultsArea, params = {}) {
        if (!query || !query.trim()) return;
        const threshold = params.threshold || 0.45;
        const n = params.n || 10;
        const linkDepth = params.linkDepth !== undefined ? params.linkDepth : 1;
        const expandPaper = params.expandPaper || false;

        const metaArea = document.getElementById('search-results-meta');
        if (metaArea) metaArea.innerText = '';
        resultsArea.innerHTML = '<div class="loader-container"><div class="loader"></div></div>';

        try {
            const endpoint = `/search?q=${encodeURIComponent(query)}&threshold=${threshold}&n=${n}&link_depth=${linkDepth}&expand_paper=${expandPaper}`;
            const data = await this.fetchJson(endpoint, false);
            const results = data.results || [];
            const graphStats = data.graph_stats;

            resultsArea.innerHTML = '';

            if (results.length === 0) {
                resultsArea.innerHTML = `<div class="error-msg">${i18n.t('search.not_found')}</div>`;
                return;
            }

            if (metaArea) {
                const countText = `${results.length} ${i18n.currentLang() === 'ja' ? '件の関連ノートが見つかりました' : 'notes found'}`;
                let statsHtml = '';
                if (graphStats && (graphStats.linked_notes > 0 || graphStats.paper_expanded > 0)) {
                    statsHtml = `<span class="graph-stats-badge">
                        ${i18n.t('search.graph_stats', {
                        direct: graphStats.direct_hits,
                        linked: graphStats.linked_notes,
                        paper: graphStats.paper_expanded
                    })}
                    </span>`;
                }
                metaArea.innerHTML = `
                    <div style="display: flex; align-items: center; gap: 12px; flex-wrap: wrap;">
                        <span>${countText} (${i18n.t('search.threshold').split('(')[0].trim()}: ${threshold})</span>
                        ${this.getMethodBadgeHtml(data.search_method)}
                        ${statsHtml}
                    </div>
                `;
            }

            // ソース順でソート: direct → linked → paper_expand、その中でタイプ順
            const sourceOrder = { direct: 0, linked: 1, paper_expand: 2 };
            const typeOrder = Object.keys(getTypeLabels());
            results.sort((a, b) => {
                const sA = sourceOrder[a.source] ?? 9;
                const sB = sourceOrder[b.source] ?? 9;
                if (sA !== sB) return sA - sB;
                return typeOrder.indexOf(a.note.element_type) - typeOrder.indexOf(b.note.element_type);
            });

            results.forEach(res => {
                const note = res.note;
                const typeLabels = getTypeLabels();
                const score = res.distance !== null && res.distance !== undefined
                    ? Math.round((1 - res.distance) * 100) : null;
                const source = res.source || 'direct';
                const depth = res.depth || 0;

                // ソースバッジの生成
                let sourceBadge = '';
                if (source === 'direct') {
                    sourceBadge = `<span class="source-badge source-direct"><i data-lucide="zap" style="width:11px;height:11px;"></i> ${i18n.t('search.badge.direct')}</span>`;
                } else if (source === 'linked') {
                    sourceBadge = `<span class="source-badge source-linked"><i data-lucide="git-branch" style="width:11px;height:11px;"></i> ${i18n.t('search.badge.linked', { depth })}</span>`;
                } else if (source === 'paper_expand') {
                    sourceBadge = `<span class="source-badge source-paper"><i data-lucide="book-open" style="width:11px;height:11px;"></i> ${i18n.t('search.badge.paper_expand')}</span>`;
                }

                // リンク理由の表示（linked の場合）
                let linkReasonHtml = '';
                if (source === 'linked' && res.link_reason) {
                    const reasonText = typeof res.link_reason === 'object'
                        ? i18n.getTranslatedString(res.link_reason)
                        : String(res.link_reason);
                    if (reasonText) {
                        linkReasonHtml = `<div class="link-reason-badge">
                            <i data-lucide="link" style="width:11px;height:11px;"></i>
                            ${i18n.t('search.linked_from')} ${reasonText}
                        </div>`;
                    }
                }

                const card = document.createElement('div');
                card.className = 'note-card';
                card.style.setProperty('--type-color', TYPE_COLORS[note.element_type] || '#ccc');
                card.innerHTML = `
                    <div class="note-header">
                        <span class="note-type">${typeLabels[note.element_type] || note.element_type}</span>
                        <div style="display:flex;align-items:center;gap:6px;">
                            ${sourceBadge}
                            ${score !== null ? `<span class="score-badge">${i18n.currentLang() === 'ja' ? '適合度' : 'Match'}: ${score}%</span>` : ''}
                        </div>
                    </div>
                    <div class="note-content">${i18n.getTranslatedString(note.content)}</div>
                    ${linkReasonHtml}
                    <div class="note-footer">${note.source_paper.title}</div>
                `;
                card.onclick = () => this.showNoteDetail(note.id);
                resultsArea.appendChild(card);
            });
            lucide.createIcons();
        } catch (err) {
            resultsArea.innerHTML = `<div class="error-msg">${i18n.t('error.alert', { message: err.message })}</div>`;
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
            text.innerText = i18n.t('status.connected');
        } else {
            badge.classList.add('disconnected');
            text.innerText = i18n.t('status.disconnected');
        }
    }

    async renderGraph(params = {}) {
        const graphData = await this.fetchJson('/graph');
        if (this.currentView !== 'graph') return;

        const template = document.getElementById('tpl-graph');
        const content = template.content.cloneNode(true);
        this.contentArea.innerHTML = '';
        this.contentArea.appendChild(content);

        const cyContainer = document.getElementById('cy');
        const tooltip = document.getElementById('graph-tooltip');
        const backBtn = document.getElementById('btn-graph-back-global');
        const localBadge = document.getElementById('graph-local-badge');
        const typeSelect = document.getElementById('graph-type-select');
        const paperSelect = document.getElementById('graph-paper-select');
        const searchInput = document.getElementById('graph-search-input');
        const resetBtn = document.getElementById('btn-graph-reset-view');
        const statNodes = document.getElementById('graph-stat-nodes');
        const statEdges = document.getElementById('graph-stat-edges');
        const legendItems = document.getElementById('graph-legend-items');

        const nodes = graphData.nodes || [];
        const edges = graphData.edges || [];

        if (nodes.length === 0) {
            cyContainer.innerHTML = `<div class="empty-state" style="padding: 40px; text-align: center; color: var(--text-muted);">${i18n.t('graph.no_data')}</div>`;
            return;
        }

        // 論文セレクトボックスの構築
        const papersMap = new Map();
        nodes.forEach(n => {
            if (n.paper_title && !papersMap.has(n.paper_title)) {
                papersMap.set(n.paper_title, n.paper_id);
            }
        });
        papersMap.forEach((paperId, paperTitle) => {
            const opt = document.createElement('option');
            opt.value = paperTitle;
            opt.textContent = paperTitle.length > 35 ? paperTitle.slice(0, 35) + '...' : paperTitle;
            paperSelect.appendChild(opt);
        });

        // 凡例 (Legend) の構築
        const typeLabels = getTypeLabels();
        legendItems.innerHTML = '';
        Object.keys(TYPE_HEX_COLORS).forEach(type => {
            if (type === 'other') return;
            const item = document.createElement('div');
            item.className = 'graph-legend-item';
            item.innerHTML = `<span class="graph-legend-dot" style="background-color: ${TYPE_HEX_COLORS[type]}"></span><span>${typeLabels[type] || type}</span>`;
            item.onclick = () => {
                typeSelect.value = typeSelect.value === type ? '' : type;
                applyFilters();
            };
            legendItems.appendChild(item);
        });

        // 統計の初期値
        statNodes.textContent = nodes.length;
        statEdges.textContent = edges.length;

        // Cytoscape 要素の作成
        const isDarkMode = !document.body.classList.contains('light-mode');
        const textColor = isDarkMode ? '#e2e8f0' : '#334155';
        const edgeColor = isDarkMode ? 'rgba(148, 163, 184, 0.25)' : 'rgba(148, 163, 184, 0.4)';
        const accentColor = '#6366f1';

        const elements = [
            ...nodes.map(n => {
                let contentText = '';
                if (typeof n.content === 'object' && n.content !== null) {
                    contentText = i18n.getTranslatedString(n.content);
                } else {
                    contentText = String(n.content || '');
                }
                const labelText = contentText.length > 20 ? contentText.slice(0, 20) + '...' : contentText;

                return {
                    group: 'nodes',
                    data: {
                        id: n.id,
                        label: labelText,
                        fullContent: contentText,
                        elementType: n.element_type || 'other',
                        paperTitle: n.paper_title || '',
                        paperId: n.paper_id,
                        paperYear: n.paper_year,
                        keywords: n.keywords || [],
                        tags: n.tags || [],
                        linkCount: n.link_count || 0,
                        color: TYPE_HEX_COLORS[n.element_type] || '#94a3b8',
                        size: Math.min(22 + (n.link_count || 0) * 4, 52)
                    }
                };
            }),
            ...edges.map((e, idx) => ({
                group: 'edges',
                data: {
                    id: `e_${e.source}_${e.target}_${idx}`,
                    source: e.source,
                    target: e.target,
                    reason: typeof e.reason === 'object' && e.reason !== null ? i18n.getTranslatedString(e.reason) : String(e.reason || '')
                }
            }))
        ];

// 標準内蔵の力指向 (cose) レイアウトを使用

        const cy = cytoscape({
            container: cyContainer,
            elements: elements,
            style: [
                {
                    selector: 'node',
                    style: {
                        'background-color': 'data(color)',
                        'width': 'data(size)',
                        'height': 'data(size)',
                        'label': 'data(label)',
                        'color': textColor,
                        'font-size': '10px',
                        'font-family': 'Inter, "Noto Sans JP", sans-serif',
                        'text-valign': 'bottom',
                        'text-margin-y': 4,
                        'text-max-width': '100px',
                        'text-wrap': 'ellipsis',
                        'border-width': 2,
                        'border-color': isDarkMode ? '#1e293b' : '#ffffff',
                        'transition-property': 'background-color, border-color, border-width, opacity, width, height',
                        'transition-duration': '0.2s',
                        'cursor': 'pointer'
                    }
                },
                {
                    selector: 'node:selected',
                    style: {
                        'border-color': accentColor,
                        'border-width': 4,
                        'shadow-blur': 12,
                        'shadow-color': accentColor,
                        'shadow-opacity': 0.8
                    }
                },
                {
                    selector: 'node.highlighted',
                    style: {
                        'border-color': accentColor,
                        'border-width': 3,
                        'opacity': 1,
                        'z-index': 100
                    }
                },
                {
                    selector: 'node.dimmed',
                    style: {
                        'opacity': 0.12
                    }
                },
                {
                    selector: 'node.hidden',
                    style: {
                        'display': 'none'
                    }
                },
                {
                    selector: 'edge',
                    style: {
                        'width': 1.5,
                        'line-color': edgeColor,
                        'curve-style': 'bezier',
                        'target-arrow-shape': 'triangle',
                        'target-arrow-color': edgeColor,
                        'arrow-scale': 0.8,
                        'opacity': 0.7,
                        'transition-property': 'line-color, target-arrow-color, width, opacity',
                        'transition-duration': '0.2s'
                    }
                },
                {
                    selector: 'edge.highlighted',
                    style: {
                        'line-color': accentColor,
                        'target-arrow-color': accentColor,
                        'width': 2.5,
                        'opacity': 1,
                        'z-index': 90
                    }
                },
                {
                    selector: 'edge.dimmed',
                    style: {
                        'opacity': 0.05
                    }
                },
                {
                    selector: 'edge.hidden',
                    style: {
                        'display': 'none'
                    }
                }
            ],
            layout: {
                name: 'cose',
                animate: true,
                animationDuration: 800,
                fit: true,
                padding: 40,
                randomize: false,
                nodeRepulsion: function(node) { return 500000; },
                nodeOverlap: 20,
                idealEdgeLength: function(edge) { return 110; },
                edgeElasticity: function(edge) { return 100; },
                nestingFactor: 5,
                gravity: 80,
                numIter: 1000,
                initialTemp: 200,
                coolingFactor: 0.95,
                minTemp: 1.0
            }
        });

        this.cy = cy;
        let isLocalMode = false;
        let selectedNodeId = null;

        // ツールチップ関数
        const showTooltip = (node, renderedPos) => {
            const data = node.data();
            const typeLabel = typeLabels[data.elementType] || data.elementType;
            const containerRect = cyContainer.getBoundingClientRect();

            let tagsHtml = '';
            if (data.tags && data.tags.length > 0) {
                const tagsList = getKeywordsList(data.tags);
                tagsHtml = tagsList.slice(0, 3).map(t => `<span class="graph-tooltip-tag">${t}</span>`).join('');
            }

            tooltip.innerHTML = `
                <div class="graph-tooltip-header">
                    <span class="graph-tooltip-type" style="background-color: ${data.color}22; color: ${data.color}; border: 1px solid ${data.color}44;">${typeLabel}</span>
                    <span class="graph-tooltip-links"><i data-lucide="share-2" style="width:12px;height:12px;"></i> ${data.linkCount}</span>
                </div>
                ${data.paperTitle ? `<div class="graph-tooltip-paper">${data.paperTitle} ${data.paperYear ? `(${data.paperYear})` : ''}</div>` : ''}
                <div class="graph-tooltip-content">${data.fullContent}</div>
                ${tagsHtml ? `<div class="graph-tooltip-footer">${tagsHtml}</div>` : ''}
            `;
            lucide.createIcons({ root: tooltip });

            tooltip.style.display = 'block';
            const tipWidth = tooltip.offsetWidth;
            const tipHeight = tooltip.offsetHeight;

            let left = renderedPos.x + 15;
            let top = renderedPos.y - tipHeight / 2;

            if (left + tipWidth > containerRect.width - 20) {
                left = renderedPos.x - tipWidth - 15;
            }
            if (top < 10) top = 10;
            if (top + tipHeight > containerRect.height - 10) {
                top = containerRect.height - tipHeight - 10;
            }

            tooltip.style.left = `${left}px`;
            tooltip.style.top = `${top}px`;
        };

        const hideTooltip = () => {
            tooltip.style.display = 'none';
        };

        // ローカルグラフモードの切り替え
        const enterLocalMode = (node) => {
            isLocalMode = true;
            selectedNodeId = node.id();
            backBtn.style.display = 'inline-flex';
            localBadge.style.display = 'inline-flex';

            const neighborhood = node.closedNeighborhood();
            cy.elements().addClass('hidden');
            neighborhood.removeClass('hidden');

            // 統計更新
            statNodes.textContent = neighborhood.nodes().length;
            statEdges.textContent = neighborhood.edges().length;

            cy.layout({
                name: 'cose',
                animate: true,
                animationDuration: 600,
                fit: true,
                padding: 50,
                randomize: false,
                nodeRepulsion: function(node) { return 600000; },
                idealEdgeLength: function(edge) { return 140; },
                gravity: 60
            }).run();
        };

        const exitLocalMode = () => {
            isLocalMode = false;
            selectedNodeId = null;
            backBtn.style.display = 'none';
            localBadge.style.display = 'none';

            cy.elements().removeClass('hidden dimmed highlighted');
            applyFilters();

            cy.layout({
                name: 'cose',
                animate: true,
                animationDuration: 800,
                fit: true,
                padding: 40,
                randomize: false,
                nodeRepulsion: function(node) { return 500000; },
                idealEdgeLength: function(edge) { return 110; },
                gravity: 80
            }).run();
        };

        // フィルター適用処理
        const applyFilters = () => {
            const selectedType = typeSelect.value;
            const selectedPaper = paperSelect.value;
            const searchTerm = (searchInput.value || '').trim().toLowerCase();

            let visibleNodes = cy.nodes();

            cy.elements().removeClass('hidden dimmed');

            if (selectedType) {
                visibleNodes = visibleNodes.filter(`[elementType = "${selectedType}"]`);
            }
            if (selectedPaper) {
                visibleNodes = visibleNodes.filter(`[paperTitle = "${selectedPaper}"]`);
            }

            if (searchTerm) {
                visibleNodes = visibleNodes.filter(node => {
                    const data = node.data();
                    const contentStr = (data.fullContent || '').toLowerCase();
                    const labelStr = (data.label || '').toLowerCase();
                    const paperStr = (data.paperTitle || '').toLowerCase();
                    const kwStr = (data.keywords || []).join(' ').toLowerCase();
                    const tagStr = (data.tags || []).join(' ').toLowerCase();
                    return contentStr.includes(searchTerm) || labelStr.includes(searchTerm) || paperStr.includes(searchTerm) || kwStr.includes(searchTerm) || tagStr.includes(searchTerm);
                });
            }

            const hiddenNodes = cy.nodes().difference(visibleNodes);
            hiddenNodes.addClass('hidden');
            hiddenNodes.connectedEdges().addClass('hidden');

            const activeEdges = cy.edges().filter(edge => !edge.source().hasClass('hidden') && !edge.target().hasClass('hidden'));

            statNodes.textContent = visibleNodes.length;
            statEdges.textContent = activeEdges.length;
        };

        // イベントバインド
        cy.on('mouseover', 'node', (evt) => {
            const node = evt.target;
            showTooltip(node, evt.renderedPosition);

            if (!isLocalMode) {
                const neighborhood = node.closedNeighborhood();
                cy.elements().addClass('dimmed');
                neighborhood.removeClass('dimmed').addClass('highlighted');
            }
        });

        cy.on('mouseout', 'node', () => {
            hideTooltip();
            if (!isLocalMode) {
                cy.elements().removeClass('dimmed highlighted');
            }
        });

        let tapTimeout = null;
        cy.on('tap', 'node', (evt) => {
            const node = evt.target;
            if (tapTimeout) {
                // ダブルタップ（モーダル表示）
                clearTimeout(tapTimeout);
                tapTimeout = null;
                this.showNoteModal(node.id());
            } else {
                tapTimeout = setTimeout(() => {
                    tapTimeout = null;
                    // シングルタップ（ローカルモード切替）
                    if (!isLocalMode) {
                        enterLocalMode(node);
                    } else if (selectedNodeId === node.id()) {
                        this.showNoteModal(node.id());
                    } else {
                        enterLocalMode(node);
                    }
                }, 250);
            }
        });

        cy.on('tap', (evt) => {
            if (evt.target === cy) {
                hideTooltip();
                if (!isLocalMode) {
                    cy.elements().removeClass('dimmed highlighted');
                }
            }
        });

        // ツールバーイベント
        backBtn.onclick = () => exitLocalMode();
        typeSelect.onchange = () => applyFilters();
        paperSelect.onchange = () => applyFilters();
        searchInput.oninput = () => applyFilters();
        resetBtn.onclick = () => {
            typeSelect.value = '';
            paperSelect.value = '';
            searchInput.value = '';
            if (isLocalMode) {
                exitLocalMode();
            } else {
                cy.elements().removeClass('hidden dimmed highlighted');
                statNodes.textContent = nodes.length;
                statEdges.textContent = edges.length;
                cy.fit(null, 40);
            }
        };

        // 初期パラメータ処理 (noteId または paperId)
        if (params.paperId || params.title) {
            const targetTitle = params.title || '';
            if (targetTitle) {
                paperSelect.value = targetTitle;
                applyFilters();
            }
        } else if (params.noteId) {
            const targetNode = cy.getElementById(params.noteId);
            if (targetNode && targetNode.length > 0) {
                enterLocalMode(targetNode);
            }
        }

        lucide.createIcons();
    }

    onLanguageChange() {
        this.switchView(this.currentView, this.currentParams, false);
    }
}

// ========================================
// PDF ドラッグ＆ドロップ & 自動解析
// ========================================

function initPdfDropzone(appInstance) {
    const overlay = document.getElementById('drop-overlay');
    const analysisModal = document.getElementById('analysis-modal');
    const confirmDialog = document.getElementById('confirm-dialog');

    if (!overlay || !analysisModal) return;

    let dragCounter = 0;

    // ドラッグイベント
    document.addEventListener('dragenter', (e) => {
        e.preventDefault();
        dragCounter++;
        if (e.dataTransfer.types.includes('Files')) {
            overlay.classList.add('active');
        }
    });
    document.addEventListener('dragleave', (e) => {
        e.preventDefault();
        dragCounter--;
        if (dragCounter <= 0) {
            dragCounter = 0;
            overlay.classList.remove('active');
        }
    });
    document.addEventListener('dragover', (e) => {
        e.preventDefault();
    });
    document.addEventListener('drop', async (e) => {
        e.preventDefault();
        dragCounter = 0;
        overlay.classList.remove('active');

        const files = Array.from(e.dataTransfer.files).filter(f => f.name.toLowerCase().endsWith('.pdf'));
        if (files.length === 0) return;

        // 最初の1ファイルのみ処理
        await handlePdfUpload(files[0]);
    });

    // PDFアップロード処理
    async function handlePdfUpload(file) {
        const formData = new FormData();
        formData.append('file', file);

        let uploadResult;
        try {
            const resp = await fetch('/api/upload', { method: 'POST', body: formData });
            uploadResult = await resp.json();
            if (uploadResult.error) {
                throw new Error(uploadResult.error);
            }
        } catch (err) {
            alert(i18n.currentLang() === 'ja' ? 'アップロードに失敗しました: ' + err.message : 'Upload failed: ' + err.message);
            return;
        }

        async function askAnalysisMode() {
            return await showConfirmDialog(
                i18n.currentLang() === 'ja'
                    ? "PDFのアップロードが完了しました。次にどうしますか？"
                    : "PDF upload complete. What would you like to do next?",
                [
                    { label: i18n.currentLang() === 'ja' ? 'キャンセル' : 'Cancel', value: null },
                    { label: i18n.t('upload.option_markdown_only'), value: 'extract' },
                    { label: i18n.t('upload.option_full_analysis'), value: 'full', primary: true }
                ]
            );
        }

        if (uploadResult.status === 'already_registered') {
            const action = await showConfirmDialog(
                i18n.currentLang() === 'ja'
                    ? `「${uploadResult.paper_name}」は既に登録されています。どうしますか？`
                    : `"${uploadResult.paper_name}" is already registered. What would you like to do?`,
                [
                    { label: i18n.currentLang() === 'ja' ? 'キャンセル' : 'Cancel', value: 'cancel' },
                    { label: i18n.currentLang() === 'ja' ? '再解析して上書き' : 'Re-analyze & overwrite', value: 'force', primary: true }
                ]
            );
            if (action === 'force') {
                const mode = await askAnalysisMode();
                if (mode) startAnalysis(uploadResult.pdf_path, false, true, mode === 'extract');
            }
        } else if (uploadResult.status === 'interrupted') {
            const action = await showConfirmDialog(
                i18n.currentLang() === 'ja'
                    ? `「${uploadResult.paper_name}」の解析は前回中断されました。どうしますか？`
                    : `Analysis of "${uploadResult.paper_name}" was interrupted last time. What would you like to do?`,
                [
                    { label: i18n.currentLang() === 'ja' ? 'キャンセル' : 'Cancel', value: 'cancel' },
                    { label: i18n.currentLang() === 'ja' ? '最初からやり直す' : 'Start from scratch', value: 'force' },
                    { label: i18n.currentLang() === 'ja' ? '続きから再開' : 'Resume', value: 'resume', primary: true }
                ]
            );
            if (action === 'resume') {
                startAnalysis(uploadResult.pdf_path, true, false, false);
            } else if (action === 'force') {
                const mode = await askAnalysisMode();
                if (mode) startAnalysis(uploadResult.pdf_path, false, true, mode === 'extract');
            }
        } else {
            // 新規
            const mode = await askAnalysisMode();
            if (mode) startAnalysis(uploadResult.pdf_path, false, false, mode === 'extract');
        }
    }

    // 確認ダイアログ
    function showConfirmDialog(message, buttons) {
        return new Promise((resolve) => {
            const msgEl = document.getElementById('confirm-dialog-message');
            const actionsEl = confirmDialog.querySelector('.confirm-dialog-actions');
            msgEl.textContent = message;
            actionsEl.innerHTML = '';
            buttons.forEach(btn => {
                const el = document.createElement('button');
                el.textContent = btn.label;
                if (btn.primary) el.classList.add('primary');
                el.addEventListener('click', () => {
                    confirmDialog.classList.remove('active');
                    resolve(btn.value);
                });
                actionsEl.appendChild(el);
            });
            confirmDialog.classList.add('active');
        });
    }

    // 解析開始
    function startAnalysis(pdfPath, resume, force, stopAfterExtract = false) {
        analysisModal.classList.add('active');
        resetAnalysisModal();

        const closeBtn = analysisModal.querySelector('.analysis-modal-close');
        closeBtn.onclick = () => {
            analysisModal.classList.remove('active');
            // データ更新
            if (appInstance && typeof appInstance.switchView === 'function') {
                appInstance.switchView(appInstance.currentView, appInstance.currentParams, false);
            }
        };

        const backend = localStorage.getItem('pdf_backend') || 'auto';
        const lightMode = localStorage.getItem('pdf_light_mode') === 'true';

        fetch('/api/analyze_paper', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                pdf_path: pdfPath,
                resume,
                force,
                stop_after_extract: stopAfterExtract,
                backend: backend,
                light_mode: lightMode
            })
        }).then(async response => {
            if (!response.ok) {
                let errMsg = 'Server error';
                try {
                    const data = await response.json();
                    errMsg = data.error || errMsg;
                } catch (e) { }
                throw new Error(errMsg);
            }
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            function processChunk({ done, value }) {
                if (done) return;
                buffer += decoder.decode(value, { stream: true });

                const lines = buffer.split('\n');
                buffer = lines.pop(); // 不完全な最終行を保持

                let currentEvent = null;
                for (const line of lines) {
                    if (line.startsWith('event: ')) {
                        currentEvent = line.slice(7).trim();
                    } else if (line.startsWith('data: ') && currentEvent) {
                        try {
                            const data = JSON.parse(line.slice(6));
                            handleAnalysisEvent(currentEvent, data);
                        } catch (e) { /* skip */ }
                        currentEvent = null;
                    } else if (line.trim() === '') {
                        currentEvent = null;
                    }
                }

                return reader.read().then(processChunk);
            }

            return reader.read().then(processChunk);
        }).catch(err => {
            showAnalysisError('Connection error: ' + err.message, false);
        });
    }

    // SSEイベントハンドラ
    function handleAnalysisEvent(event, data) {
        const statusText = document.getElementById('analysis-status-text');
        const progressFill = document.getElementById('analysis-progress-fill');

        if (event === 'progress') {
            statusText.textContent = data.message || '';
            updateStepUI(data.step);

            const stepOrder = ['uploading', 'extracting_init', 'extracting_convert', 'extracting_images', 'extracting_markdown', 'turn_1', 'turn_2', 'turn_3', 'registering'];
            const idx = stepOrder.indexOf(data.step);
            if (idx >= 0) {
                const pct = Math.round(((idx + 0.5) / stepOrder.length) * 100);
                progressFill.style.width = pct + '%';
            }
        } else if (event === 'complete') {
            progressFill.style.width = '100%';
            analysisModal.querySelectorAll('.analysis-step').forEach(s => {
                s.classList.remove('active');
                s.classList.add('completed');
            });
            if (data.status === 'extracted_only') {
                const completionMessage = i18n.t('analysis.markdown_complete');
                statusText.textContent = completionMessage;
                // OKボタン押下でモーダルを閉じるコールバックを渡す
                showAnalysisResult(data, completionMessage, () => {
                    analysisModal.classList.remove('active');
                    if (appInstance && appInstance.currentView === 'upload') {
                        appInstance.switchView('upload');
                    }
                });
            } else {
                statusText.textContent = i18n.t('analysis.complete');
                // OKボタン押下でモーダルを閉じるコールバックを渡す
                showAnalysisResult(data, null, () => {
                    analysisModal.classList.remove('active');
                    if (appInstance && appInstance.currentView === 'upload') {
                        appInstance.switchView('upload');
                    }
                });
            }
        } else if (event === 'error') {
            showAnalysisError(data.error, data.resumable, data.pdf_path);
        }
    }

    function updateStepUI(currentStep) {
        const steps = analysisModal.querySelectorAll('.analysis-step');
        const stepOrder = ['uploading', 'extracting_init', 'extracting_convert', 'extracting_images', 'extracting_markdown', 'turn_1', 'turn_2', 'turn_3', 'registering'];
        const currentIdx = stepOrder.indexOf(currentStep);

        steps.forEach((step, i) => {
            step.classList.remove('active', 'completed');
            if (i < currentIdx) step.classList.add('completed');
            else if (i === currentIdx) step.classList.add('active');
        });
    }

    function resetAnalysisModal() {
        document.getElementById('analysis-status-text').textContent = i18n.t('analysis.preparing');
        document.getElementById('analysis-progress-fill').style.width = '0%';
        document.getElementById('analysis-result').style.display = 'none';
        document.getElementById('analysis-error').style.display = 'none';
        document.getElementById('analysis-title').textContent = i18n.t('analysis.title');
        analysisModal.querySelectorAll('.analysis-step').forEach(s => {
            s.classList.remove('active', 'completed');
        });
    }

    function showAnalysisResult(data, completionMessage = null, onClose = null) {
        const el = document.getElementById('analysis-result');
        el.style.display = 'block';
        const paperTitle = data.paper_title || '';
        // data.status に基づいてタイトルを切り替える
        const titleText = data.status === 'extracted_only'
            ? `✅ ${i18n.t('analysis.markdown_complete')}`
            : `✅ ${i18n.t('analysis.complete')}`;
        const countBlock = data.status === 'extracted_only'
            ? ''
            : `<p>Notes: ${data.notes_count || 0} / References: ${data.refs_count || 0}</p>`;

        let conflictHtml = '';
        if (data.doi_conflicts && data.doi_conflicts.length > 0) {
            const conflict = data.doi_conflicts[0];
            const simPct = conflict.details ? Math.round((conflict.details.title_similarity || 0) * 100) : null;
            const simText = simPct ? ` (${simPct}%)` : '';
            const extractedUrl = conflict.extracted_doi ? (conflict.extracted_doi.startsWith('http') ? conflict.extracted_doi : 'https://doi.org/' + conflict.extracted_doi) : '#';
            const fetchedUrl = conflict.fetched_doi ? (conflict.fetched_doi.startsWith('http') ? conflict.fetched_doi : 'https://doi.org/' + conflict.fetched_doi) : '#';

            conflictHtml = `
                <div class="doi-conflict-card">
                    <div class="doi-conflict-header">
                        <span>⚠️</span> ${i18n.t('analysis.doi_conflict_title')}
                    </div>
                    <p class="doi-conflict-desc">${i18n.t('analysis.doi_conflict_desc')}</p>
                    <div class="doi-choices-list">
                        <div class="doi-choice-item selected" id="item-choice-extracted">
                            <button type="button" class="btn-doi-select" id="btn-choice-extracted">
                                <span class="doi-choice-title">
                                    <span class="doi-radio">●</span> [1] ${i18n.t('analysis.use_extracted_doi')}
                                </span>
                                <span class="doi-code-text">${conflict.extracted_doi}</span>
                            </button>
                            <a href="${extractedUrl}" target="_blank" rel="noopener noreferrer" class="doi-external-link" title="${i18n.t('analysis.open_paper')}">
                                🔗 ${i18n.t('analysis.open_paper')}
                            </a>
                        </div>
                        <div class="doi-choice-item" id="item-choice-fetched">
                            <button type="button" class="btn-doi-select" id="btn-choice-fetched">
                                <span class="doi-choice-title">
                                    <span class="doi-radio">○</span> [2] ${i18n.t('analysis.use_fetched_doi')}${simText}
                                </span>
                                <span class="doi-code-text">${conflict.fetched_doi}</span>
                            </button>
                            <a href="${fetchedUrl}" target="_blank" rel="noopener noreferrer" class="doi-external-link" title="${i18n.t('analysis.open_paper')}">
                                🔗 ${i18n.t('analysis.open_paper')}
                            </a>
                        </div>
                    </div>
                    <div id="doi-update-status" class="doi-update-status"></div>
                </div>
            `;
        }

        // onClose が渡された場合は「OK」ボタンを表示し、ユーザーが明示的に閉じるまで待機する
        const okBtnHtml = onClose
            ? `<button class="ok-btn" id="btn-analysis-ok">✔ OK</button>`
            : '';
        el.innerHTML = `
            <h3>${titleText}</h3>
            ${paperTitle ? `<p><strong>${paperTitle}</strong></p>` : ''}
            ${countBlock}
            ${conflictHtml}
            ${okBtnHtml}
        `;

        if (data.doi_conflicts && data.doi_conflicts.length > 0) {
            const conflict = data.doi_conflicts[0];
            const itemExtracted = document.getElementById('item-choice-extracted');
            const itemFetched = document.getElementById('item-choice-fetched');
            const btnExtracted = document.getElementById('btn-choice-extracted');
            const btnFetched = document.getElementById('btn-choice-fetched');
            const statusEl = document.getElementById('doi-update-status');

            async function updatePaperDoi(chosenDoi, activeItem, inactiveItem) {
                try {
                    activeItem.classList.add('selected');
                    const activeRadio = activeItem.querySelector('.doi-radio');
                    if (activeRadio) activeRadio.textContent = '●';

                    inactiveItem.classList.remove('selected');
                    const inactiveRadio = inactiveItem.querySelector('.doi-radio');
                    if (inactiveRadio) inactiveRadio.textContent = '○';

                    const resp = await fetch('/api/papers/update-doi', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            paper_id: conflict.paper_id,
                            paper_title: conflict.title,
                            doi: chosenDoi
                        })
                    });
                    if (resp.ok) {
                        statusEl.textContent = `✔ ${i18n.t('analysis.doi_updated')}: ${chosenDoi}`;
                        statusEl.style.display = 'block';
                    }
                } catch (e) {
                    console.error("Failed to update DOI", e);
                }
            }

            if (btnExtracted && btnFetched && itemExtracted && itemFetched) {
                btnExtracted.onclick = () => updatePaperDoi(conflict.extracted_doi, itemExtracted, itemFetched);
                btnFetched.onclick = () => updatePaperDoi(conflict.fetched_doi, itemFetched, itemExtracted);
            }
        }

        // OKボタンにコールバックを登録
        if (onClose) {
            const btn = document.getElementById('btn-analysis-ok');
            if (btn) btn.onclick = onClose;
        }
    }

    function showAnalysisError(message, resumable, pdfPath) {
        const el = document.getElementById('analysis-error');
        el.style.display = 'block';
        let html = `<h3>⚠️ ${i18n.t('analysis.interrupted')}</h3><p>${message}</p>`;
        if (resumable && pdfPath) {
            html += `<button class="resume-btn" id="btn-analysis-resume">🔄 ${i18n.currentLang() === 'ja' ? '続きから再開' : 'Resume'}</button>`;
        }
        el.innerHTML = html;

        const btn = document.getElementById('btn-analysis-resume');
        if (btn) {
            btn.onclick = () => {
                document.getElementById('analysis-error').style.display = 'none';
                startAnalysis(pdfPath, true, false);
            };
        }
    }

    // renderUploadなどクラスメソッドから呼べるようにグローバル公開
    window._handlePdfUpload = handlePdfUpload;
    window._startAnalysis = startAnalysis;
    window._showConfirmDialog = showConfirmDialog;
}

// Start the app
window.addEventListener('DOMContentLoaded', () => {
    window.app = new App();
    initPdfDropzone(window.app);
});

