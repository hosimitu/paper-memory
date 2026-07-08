/**
 * Paper Memory - i18n Dictionary and Logic
 */

const i18nDict = {
    en: {
        "nav.overview": "Overview",
        "nav.notes": "Knowledge Notes",
        "nav.papers": "Papers",
        "nav.references": "References",
        "nav.search": "Semantic Search",
        "nav.qa": "AI Assistant",
        "nav.theme": "Theme",
        "nav.lang": "Language",

        "stat.total_notes": "Total Notes",
        "stat.total_papers": "Total Papers",
        "stat.total_links": "Total Links",
        "stat.unread_refs": "Unread Refs",

        "section.distribution": "Knowledge Distribution",
        "section.recent": "Recently Added",

        "filter.all": "All",
        "filter.paper_applied": "Paper Filter Applied",
        "filter.clear": "Clear Filter",
        "search.placeholder": "Search from current list...",
        "search.not_found": "No notes found",

        "modal.paper_title": "Paper Title",
        "modal.keywords": "Keywords",
        "modal.authors": "Authors",
        "modal.context": "Context",
        "modal.links": "Related Notes",
        "modal.no_links": "No related notes",
        "modal.dismiss": "Dismiss from References",

        "paper.confirm_delete": "Are you sure you want to delete this paper?\nWARNING: This will permanently delete the paper metadata, ALL its notes, ALL links to these notes, the ChromaDB index, and the extracted Markdown files.",
        "paper.delete_success": "Paper deleted successfully",
        "paper.sort.label": "Sort",
        "paper.sort.registration": "Registration order",
        "paper.sort.title": "Title (A-Z)",
        "paper.sort.year": "Publication year",

        "ref.unread_title": "Unread References",
        "ref.source": "Cited by",
        "ref.journal": "Journal",
        "ref.year": "Year",
        "ref.confirm_dismiss": "Dismiss this reference from the list?\n(It will reappear if cited by another paper later)",

        "search.guide.title": "Find by Meaning (Semantic Search)",
        "search.guide.desc": "Search by the 'meaning' of words, not just exact keyword matches. Find relevant notes using natural language queries.",
        "search.guide.li1": "Concept Search: Search for specific events or mechanisms.",
        "search.guide.li2": "Cross-comparison: Compare common items across different papers.",
        "search.guide.li3": "Identify Keys: Find the core ideas of the research.",
        "search.input_placeholder": "Search knowledge by meaning (e.g. membrane separation limits)...",
        "search.hint": "Press Enter to search",
        "search.threshold": "Relevance Threshold (lower is stricter):",
        "search.method.label": "Search Method:",
        "search.method.vector": "Vector Search",
        "search.method.keyword": "Keyword Search",
        "search.method.hybrid": "Hybrid Search",
        "search.n_results": "Initial results count:",
        "search.link_depth": "Link traversal depth:",
        "search.link_depth.0": "None",
        "search.link_depth.1": "1 hop",
        "search.link_depth.2": "2 hops",
        "search.link_depth.3": "3 hops",
        "search.expand_paper": "Expand same-paper notes",
        "search.badge.direct": "Direct Hit",
        "search.badge.linked": "Linked ({depth}-hop)",
        "search.badge.paper_expand": "Same Paper",
        "search.graph_stats": "{direct} direct + {linked} linked + {paper} paper",
        "search.linked_from": "Linked from:",

        "qa.title": "AI Assistant (Q&A)",
        "qa.hint": "AI generates answers based on accumulated notes. Sources are clearly indicated.",
        "qa.input_placeholder": "Ask AI (e.g. What is the most permeable membrane?)...",
        "qa.btn": "Ask",
        "qa.rewrite_mode": "Query processing",
        "qa.rewrite_mode.ai": "Use AI query rewrite",
        "qa.rewrite_mode.raw": "Use original query",
        "qa.mode": "Answer Mode",
        "qa.mode.fact": "Fact Check",
        "qa.mode.insight": "Idea Insight",
        "qa.rate_limit": "API Usage: Loading...",
        "qa.history": "Question History (Recent 10)",
        "qa.clear_history": "Clear All History",
        "qa.no_history": "No history available.",
        "qa.loading_history": "Loading history...",
        "qa.confirm_clear": "Clear all question history?",
        "qa.confirm_delete": "Delete this question history?",
        "qa.more_history": "Show older history",
        "qa.result.query": "Question",
        "qa.result.rewritten_query": "AI rewrite",
        "qa.result.no_rewritten": "No rewritten query available",
        "qa.result.ref_notes": "Referenced Knowledge Notes",
        "qa.result.show_detail": "Show Details",
        "qa.generating": "Generating answer... (Searching notes with threshold {threshold})",
        "qa.progress.query_rewriting": "Analyzing and rewriting query...",
        "qa.progress.searching": "Searching related notes (threshold {threshold})...",
        "qa.progress.reranking": "Reranking search results...",
        "qa.progress.graph_expansion": "Expanding note connections...",
        "qa.progress.generating_answer": "Generating final answer using AI...",
        "qa.progress.saving": "Saving answer and recording history...",
        "qa.expand_paper.on": "Yes",
        "qa.expand_paper.off": "No",
        "qa.history.n_results": "Retrieved:",

        "status.connected": "Connected",
        "status.disconnected": "Disconnected",
        "error.fetch_failed": "Failed to fetch data: {message}",
        "error.update_failed": "Status update failed",
        "error.alert": "An error occurred: {message}",
        "status.unknown": "Unknown",

        "type.background": "Background",
        "type.method": "Method",
        "type.result": "Result",
        "type.discussion": "Discussion",
        "type.conclusion": "Conclusion",
        "type.insight": "Insight",
        "type.limitation": "Limitation",
        "type.future_work": "Future Work",
        "type.definition": "Definition",
        "type.other": "Other",

        "analysis.title": "Analyzing paper...",
        "analysis.uploading": "Upload",
        "analysis.extracting": "Text extraction",
        "analysis.turn_1": "AI Analysis (1/3)",
        "analysis.turn_2": "AI Analysis (2/3)",
        "analysis.turn_3": "AI Analysis (3/3)",
        "analysis.registering": "DB Registration",
        "analysis.preparing": "Preparing...",
        "analysis.complete": "Complete!",
        "analysis.interrupted": "Processing was interrupted",
        "analysis.drop_pdf": "Drop PDF file to start analysis",
        "analysis.confirm": "Confirm"
    },
    ja: {
        "nav.overview": "概要",
        "nav.notes": "知識ノート",
        "nav.papers": "登録論文",
        "nav.references": "参考文献",
        "nav.search": "セマンティック検索",
        "nav.qa": "AIアシスタント",
        "nav.theme": "テーマ切替",
        "nav.lang": "言語設定",

        "stat.total_notes": "総ノート数",
        "stat.total_papers": "登録論文数",
        "stat.total_links": "知識リンク数",
        "stat.unread_refs": "未読参考文献",

        "section.distribution": "知識分布",
        "section.recent": "最近追加された知識",

        "filter.all": "すべて",
        "filter.paper_applied": "論文フィルタ適用中",
        "filter.clear": "フィルタ解除",
        "search.placeholder": "現在のリストから検索...",
        "search.not_found": "ノートが見つかりませんでした",

        "modal.paper_title": "論文タイトル",
        "modal.keywords": "キーワード",
        "modal.authors": "著者",
        "modal.context": "文脈・前提",
        "modal.links": "関連ノート",
        "modal.no_links": "関連ノートはありません",
        "modal.dismiss": "参考文献から除外",

        "paper.confirm_delete": "本当にこの論文を削除しますか？\n⚠️警告：この操作により以下のデータが完全に削除されます：\n・論文のメタデータ\n・この論文に紐づく【すべてのノート】\n・他のノートからの【すべてのリンク】\n・ChromaDBの検索インデックス\n・抽出済みのMarkdownデータ (extracted/)",
        "paper.delete_success": "論文を削除しました",
        "paper.sort.label": "並び替え",
        "paper.sort.registration": "登録順",
        "paper.sort.title": "ABC順",
        "paper.sort.year": "出版年順",

        "ref.unread_title": "未読参考文献",
        "ref.source": "引用元",
        "ref.journal": "ジャーナル",
        "ref.year": "出版年",
        "ref.confirm_dismiss": "この参考文献をリストから除外しますか？\n（将来、別の論文から引用された場合には自動的に再表示されます）",

        "search.guide.title": "意味で探すセマンティック検索",
        "search.guide.desc": "キーワードの完全一致だけでなく、言葉の「意味」の近さで知識を検索します。文章のような自然なクエリでも関連するノートを見つけ出せます。",
        "search.guide.li1": "概念検索: 特定の事象やメカニズムについて探す",
        "search.guide.li2": "横断比較: 異なる論文の共通項目を比較する",
        "search.guide.li3": "キモの特定: 研究の核心を突くアイデアを探す",
        "search.input_placeholder": "知識を意味で検索（例：膜分離の性能限界）...",
        "search.hint": "Enterキーで検索を実行します",
        "search.threshold": "関連度の閾値 (低いほど厳密):",
        "search.method.label": "検索手法:",
        "search.method.vector": "ベクトル検索",
        "search.method.keyword": "キーワード検索",
        "search.method.hybrid": "ハイブリッド検索",
        "search.n_results": "初期取得件数:",
        "search.link_depth": "リンク探索深度:",
        "search.link_depth.0": "なし",
        "search.link_depth.1": "1ホップ",
        "search.link_depth.2": "2ホップ",
        "search.link_depth.3": "3ホップ",
        "search.expand_paper": "同一論文のノートも展開",
        "search.badge.direct": "直接ヒット",
        "search.badge.linked": "リンク経由 ({depth}ホップ)",
        "search.badge.paper_expand": "同一論文",
        "search.graph_stats": "直接{direct}件 + リンク{linked}件 + 論文{paper}件",
        "search.linked_from": "リンク元:",

        "qa.title": "AIアシスタント（過去の知識への質問）",
        "qa.hint": "蓄積されたノートをもとにAIが回答を生成します。推測を排除し、情報源を明示します。",
        "qa.input_placeholder": "AIに質問する（例：最も透過率が高い膜は何ですか？）...",
        "qa.btn": "質問",
        "qa.rewrite_mode": "クエリ処理",
        "qa.rewrite_mode.ai": "AIクエリ変換を利用",
        "qa.rewrite_mode.raw": "元のクエリをそのまま利用",
        "qa.mode": "回答モード",
        "qa.mode.fact": "事実確認",
        "qa.mode.insight": "アイデア創出",
        "qa.rate_limit": "API使用状況: 取得中...",
        "qa.history": "過去の質問履歴 (最新10件)",
        "qa.clear_history": "すべての履歴を消去",
        "qa.no_history": "履歴はありません。",
        "qa.loading_history": "履歴を読み込み中...",
        "qa.confirm_clear": "質問履歴をすべて消去しますか？",
        "qa.confirm_delete": "この質問履歴を削除しますか？",
        "qa.more_history": "さらに過去の履歴を表示",
        "qa.result.query": "質問",
        "qa.result.rewritten_query": "AI変換クエリ",
        "qa.result.no_rewritten": "変換クエリはありません",
        "qa.result.ref_notes": "参照された知識ノート",
        "qa.result.show_detail": "詳細を表示",
        "qa.generating": "回答生成中...（閾値 {threshold} でノートを検索中）",
        "qa.progress.query_rewriting": "クエリの解析・拡張中...",
        "qa.progress.searching": "関連ノートの検索中（閾値 {threshold}）...",
        "qa.progress.reranking": "検索結果の再ランキング中...",
        "qa.progress.graph_expansion": "関連ノートのネットワーク拡張中...",
        "qa.progress.generating_answer": "AIによる最終回答を生成中...",
        "qa.progress.saving": "回答の保存と履歴の記録中...",
        "qa.expand_paper.on": "有効",
        "qa.expand_paper.off": "無効",
        "qa.history.n_results": "取得件数:",

        "status.connected": "接続済み",
        "status.disconnected": "切断",
        "error.fetch_failed": "データの取得に失敗しました: {message}",
        "error.update_failed": "ステータス更新に失敗しました",
        "error.alert": "エラーが発生しました: {message}",
        "status.unknown": "不明",

        "type.background": "背景・先行研究",
        "type.method": "手法・アプローチ",
        "type.result": "結果・データ",
        "type.discussion": "考察・解釈",
        "type.conclusion": "結論",
        "type.insight": "著者の洞察",
        "type.limitation": "限界・課題",
        "type.future_work": "今後の展望",
        "type.definition": "定義",
        "type.other": "その他",

        "analysis.title": "論文を解析中...",
        "analysis.uploading": "アップロード",
        "analysis.extracting": "テキスト抽出",
        "analysis.turn_1": "AI解析 (1/3)",
        "analysis.turn_2": "AI解析 (2/3)",
        "analysis.turn_3": "AI解析 (3/3)",
        "analysis.registering": "DB登録",
        "analysis.preparing": "準備中...",
        "analysis.complete": "完了！",
        "analysis.interrupted": "処理が中断されました",
        "analysis.drop_pdf": "PDFファイルをドロップして解析を開始",
        "analysis.confirm": "確認"
    }
};

let currentLang = localStorage.getItem('language') || 'en';

function t(key, params = {}) {
    let text = (i18nDict[currentLang] && i18nDict[currentLang][key]) || i18nDict['en'][key] || key;
    for (const [k, v] of Object.entries(params)) {
        text = text.replace(`{${k}}`, v);
    }
    return text;
}

function setLanguage(lang) {
    if (i18nDict[lang]) {
        currentLang = lang;
        localStorage.setItem('language', lang);
        applyTranslations();
        if (window.app) {
            window.app.onLanguageChange();
        }
    }
}

function applyTranslations(root = document) {
    root.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.getAttribute('data-i18n');
        el.innerText = t(key);
    });
    
    root.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
        const key = el.getAttribute('data-i18n-placeholder');
        el.placeholder = t(key);
    });

    const langSelector = document.getElementById('lang-selector');
    if (langSelector) {
        langSelector.value = currentLang;
    }
}

function getTranslatedString(val) {
    if (!val) return '';
    if (typeof val === 'string') return val;
    if (typeof val === 'object') {
        const preferredLangs = [currentLang, 'local', 'ja', 'en'];
        for (const lang of preferredLangs) {
            if (!lang) continue;
            const text = val[lang];
            if (typeof text === 'string' && text.trim()) {
                return text;
            }
        }
        return Object.values(val).find(v => typeof v === 'string' && v.trim()) || '';
    }
    return String(val);
}

// Export for use in app.js
window.i18n = { 
    t, 
    setLanguage, 
    applyTranslations, 
    currentLang: () => currentLang,
    getTranslatedString,
    loadConfig: async () => {
        try {
            const res = await fetch('/api/config');
            if (res.ok) {
                const config = await res.json();
                if (config.language && !localStorage.getItem('language')) {
                    currentLang = config.language;
                    applyTranslations();
                }
            }
        } catch (e) {
            console.error('Failed to load config:', e);
        }
    }
};
