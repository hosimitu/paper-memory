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

        "qa.title": "AI Assistant (Q&A)",
        "qa.hint": "AI generates answers based on accumulated notes. Sources are clearly indicated.",
        "qa.input_placeholder": "Ask AI (e.g. What is the most permeable membrane?)...",
        "qa.btn": "Ask",
        "qa.rate_limit": "API Usage: Loading...",
        "qa.history": "Question History (Recent 10)",
        "qa.clear_history": "Clear All History",
        "qa.no_history": "No history available.",
        "qa.loading_history": "Loading history...",
        "qa.confirm_clear": "Clear all question history?",
        "qa.confirm_delete": "Delete this question history?",
        "qa.more_history": "Show older history",
        "qa.result.query": "Question",
        "qa.result.ref_notes": "Referenced Knowledge Notes",
        "qa.result.show_detail": "Show Details",
        "qa.generating": "Generating answer... (Searching notes with threshold {threshold})",

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
        "type.other": "Other"
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

        "qa.title": "AIアシスタント（過去の知識への質問）",
        "qa.hint": "蓄積されたノートをもとにAIが回答を生成します。推測を排除し、情報源を明示します。",
        "qa.input_placeholder": "AIに質問する（例：最も透過率が高い膜は何ですか？）...",
        "qa.btn": "質問",
        "qa.rate_limit": "API使用状況: 取得中...",
        "qa.history": "過去の質問履歴 (最新10件)",
        "qa.clear_history": "すべての履歴を消去",
        "qa.no_history": "履歴はありません。",
        "qa.loading_history": "履歴を読み込み中...",
        "qa.confirm_clear": "質問履歴をすべて消去しますか？",
        "qa.confirm_delete": "この質問履歴を削除しますか？",
        "qa.more_history": "さらに過去の履歴を表示",
        "qa.result.query": "質問",
        "qa.result.ref_notes": "参照された知識ノート",
        "qa.result.show_detail": "詳細を表示",
        "qa.generating": "回答生成中...（閾値 {threshold} でノートを検索中）",

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
        "type.other": "その他"
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
        return val[currentLang] || val['en'] || Object.values(val)[0] || '';
    }
    return String(val);
}

// Export for use in app.js
window.i18n = { 
    t, 
    setLanguage, 
    applyTranslations, 
    currentLang: () => currentLang,
    getTranslatedString
};
