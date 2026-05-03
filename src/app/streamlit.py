from __future__ import annotations

import streamlit as st

from src.app.rag import RagEngine
from src.storage.schemas import AppConfig
from qdrant_client import QdrantClient


# ── Cached resources ─────────────────────────────────────────────────────────

@st.cache_resource
def get_engine() -> RagEngine:
    return RagEngine(AppConfig.from_env())


@st.cache_resource
def get_qdrant() -> QdrantClient:
    cfg = AppConfig.from_env()
    return QdrantClient(url=cfg.qdrant_url, api_key=cfg.qdrant_api_key)


@st.cache_data(ttl=300)
def fetch_latest_blogs(limit: int = 20) -> list[dict]:
    """Fetch the most recent blog entries from Qdrant ordered by published_at."""
    cfg = AppConfig.from_env()
    client = get_qdrant()

    if not client.collection_exists(cfg.qdrant_blog_collection):
        return []

    points, _ = client.scroll(
        collection_name=cfg.qdrant_blog_collection,
        limit=limit,
        with_payload=True,
        with_vectors=False,
    )
    entries = [p.payload for p in points if p.payload]
    entries.sort(key=lambda e: e.get("published_at", ""), reverse=True)
    return entries


# ── CSS injection ─────────────────────────────────────────────────────────────

GLOBAL_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Syne:wght@700;800&family=Inter:wght@300;400;500&display=swap');

/* ── Reset & base ── */
html, body, [data-testid="stAppViewContainer"] {
    background-color: #ffffff !important;
    color: #0f0f0f !important;
    font-family: 'Inter', sans-serif !important;
}

[data-testid="stHeader"] { background: transparent !important; }
[data-testid="stSidebar"] { display: none; }
[data-testid="stToolbar"] { display: none; }

/* ── Main container — add horizontal padding to prevent edge-to-edge ── */
[data-testid="stMainBlockContainer"] {
    padding: 0 !important;
    max-width: 100% !important;
}
.block-container {
    padding: 0 2rem !important;
    max-width: 1400px !important;
    margin: 0 auto !important;
}

/* ── Top bar ── */
.topbar {
    display: flex;
    align-items: center;
    padding: 15px 2rem;
    border-bottom: 1px solid #e8e8ee;
    background: #fafafa;
    gap: 16px;
    margin: 0 -2rem;
}
.topbar-logo {
    font-family: 'Syne', sans-serif;
    font-size: 18px;
    font-weight: 800;
    letter-spacing: -0.5px;
    display: flex;
    align-items: center;
    gap: 10px;
    color: #0f0f0f;
}
.topbar-logo .accent { color: #5b6bff; }
.logo-dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    background: #5b6bff;
    box-shadow: 0 0 10px rgba(91,107,255,0.5);
    display: inline-block;
    animation: pulse-dot 2s ease-in-out infinite;
}
@keyframes pulse-dot {
    0%,100% { opacity:1; transform:scale(1); }
    50% { opacity:0.5; transform:scale(0.75); }
}
.topbar-status {
    margin-left: auto;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 12px;
    color: #888;
    display: flex;
    align-items: center;
    gap: 8px;
}
.status-live {
    width: 6px; height: 6px;
    border-radius: 50%;
    background: #00b89c;
    box-shadow: 0 0 6px rgba(0,184,156,0.6);
    animation: pulse-dot 1.5s ease-in-out infinite;
    display: inline-block;
}

/* ── Tabs override ── */
[data-testid="stTabs"] [role="tablist"] {
    background: #fafafa !important;
    border-bottom: 1px solid #e8e8ee !important;
    padding: 0 !important;
    gap: 0 !important;
}
[data-testid="stTabs"] [role="tab"] {
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 13px !important;
    font-weight: 500 !important;
    color: #aaa !important;
    padding: 14px 26px !important;
    border-bottom: 2px solid transparent !important;
    border-radius: 0 !important;
    letter-spacing: 0.3px !important;
    transition: all 0.2s !important;
}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
    color: #0f0f0f !important;
    border-bottom-color: #5b6bff !important;
    background: rgba(91,107,255,0.04) !important;
}
[data-testid="stTabs"] [role="tab"]:hover:not([aria-selected="true"]) {
    color: #444 !important;
    background: rgba(0,0,0,0.02) !important;
}
[data-testid="stTabs"] [data-testid="stTabsContent"] {
    padding: 0 !important;
    background: transparent !important;
}

/* ── RAG sidebar ── */
.rag-sidebar {
    background: #fafafa;
    border-right: 1px solid #e8e8ee;
    padding: 24px 18px;
}
.sidebar-label {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    color: #aaa;
    margin-bottom: 10px;
}

/* ── Slider override ── */
[data-testid="stSlider"] [data-testid="stWidgetLabel"] {
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 12px !important;
    color: #999 !important;
    text-transform: uppercase !important;
    letter-spacing: 1px !important;
}

/* ── Chat messages ── */
[data-testid="stChatMessage"] {
    background: #f7f7fb !important;
    border: 1px solid #e8e8ee !important;
    border-radius: 12px !important;
    margin-bottom: 12px !important;
    padding: 14px 18px !important;
}
[data-testid="stChatMessage"][data-testid*="user"] {
    background: rgba(91,107,255,0.06) !important;
    border-color: rgba(91,107,255,0.18) !important;
}
[data-testid="stChatMessageContent"] p {
    font-family: 'Inter', sans-serif !important;
    font-size: 15px !important;
    line-height: 1.7 !important;
    color: #1a1a1a !important;
}
[data-testid="stChatInputContainer"] {
    background: #fafafa !important;
    border-top: 1px solid #e8e8ee !important;
    padding: 16px 0 !important;
    border-radius: 0 !important;
}
[data-testid="stChatInputContainer"] textarea {
    background: #fff !important;
    border: 1px solid #ddd !important;
    border-radius: 8px !important;
    color: #0f0f0f !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 14px !important;
}
[data-testid="stChatInputContainer"] textarea:focus {
    border-color: rgba(91,107,255,0.5) !important;
    box-shadow: none !important;
}
[data-testid="stChatInputContainer"] textarea::placeholder {
    color: #bbb !important;
}

/* ── Expander ── */
[data-testid="stExpander"] {
    background: #f7f7fb !important;
    border: 1px solid #e8e8ee !important;
    border-radius: 8px !important;
}
[data-testid="stExpander"] summary {
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 13px !important;
    color: #777 !important;
}

/* ── Info box ── */
[data-testid="stInfo"] {
    background: rgba(91,107,255,0.05) !important;
    border: 1px solid rgba(91,107,255,0.2) !important;
    border-radius: 8px !important;
    color: #444 !important;
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 13px !important;
}

/* ── Text input ── */
[data-testid="stTextInput"] input {
    background: #fff !important;
    border: 1px solid #ddd !important;
    border-radius: 6px !important;
    color: #0f0f0f !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 14px !important;
    transition: border-color 0.2s !important;
}
[data-testid="stTextInput"] input:focus {
    border-color: rgba(91,107,255,0.5) !important;
    box-shadow: none !important;
}
[data-testid="stTextInput"] input::placeholder { color: #bbb !important; }
[data-testid="stTextInput"] label {
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 12px !important;
    color: #999 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.8px !important;
}

/* ── Multiselect ── */
[data-testid="stMultiSelect"] [data-testid="stWidgetLabel"] {
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 12px !important;
    color: #999 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.8px !important;
}
[data-testid="stMultiSelect"] > div > div {
    background: #fff !important;
    border: 1px solid #ddd !important;
    border-radius: 6px !important;
}

/* ── Buttons ── */
[data-testid="stButton"] button {
    background: transparent !important;
    border: 1px solid #ddd !important;
    border-radius: 6px !important;
    color: #555 !important;
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 12px !important;
    letter-spacing: 0.3px !important;
    transition: all 0.2s !important;
}
[data-testid="stButton"] button:hover {
    border-color: #5b6bff !important;
    color: #5b6bff !important;
    background: rgba(91,107,255,0.05) !important;
}

/* ── Spinner ── */
[data-testid="stSpinner"] {
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 13px !important;
    color: #888 !important;
}

/* ── Divider ── */
hr { border-color: #e8e8ee !important; }

/* ── Blog cards ── */
.blog-card {
    border-bottom: 1px solid #eee;
    padding: 22px 0;
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 16px;
    align-items: start;
    transition: background 0.15s;
    border-radius: 4px;
}
.blog-card:hover { background: rgba(91,107,255,0.025); }
.blog-card:last-child { border-bottom: none; }

.card-meta {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 9px;
    flex-wrap: wrap;
}
.source-tag {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 3px;
    border: 1px solid rgba(91,107,255,0.25);
    color: #5b6bff;
    background: rgba(91,107,255,0.06);
}
.date-tag, .author-tag {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
    color: #bbb;
}
.card-title {
    font-family: 'Syne', sans-serif;
    font-size: 17px;
    font-weight: 700;
    line-height: 1.35;
    margin-bottom: 9px;
    letter-spacing: -0.2px;
    color: #0f0f0f;
}
.card-title a {
    color: inherit;
    text-decoration: none;
    transition: color 0.15s;
}
.card-title a:hover { color: #5b6bff; }
.card-summary {
    font-size: 14px;
    color: #666;
    line-height: 1.65;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
}
.card-actions {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 8px;
    padding-top: 4px;
}
.read-link {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 12px;
    color: #888;
    text-decoration: none;
    padding: 5px 10px;
    border: 1px solid #ddd;
    border-radius: 4px;
    transition: all 0.15s;
    white-space: nowrap;
}
.read-link:hover { border-color: #5b6bff; color: #5b6bff; }
.score-bar {
    width: 56px; height: 2px;
    background: #eee;
    border-radius: 2px;
    overflow: hidden;
}
.score-fill {
    height: 100%;
    border-radius: 2px;
    background: linear-gradient(90deg, #00b89c, #5b6bff);
}

/* ── Blog section heading ── */
.blog-section-title {
	font-family: 'Syne', sans-serif;
    font-size: 28px;
    font-weight: 800;
    letter-spacing: -0.5px;
    color: #0f0f0f;
    margin-bottom: 4px;
    line-height: 1.4;
    padding-top: 4px;
    overflow: visible;
}
.blog-section-title .accent { color: #5b6bff; }
.blog-section-sub {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 12px;
    color: #aaa;
}

/* ── Context badge ── */
.ctx-badge {
    display: inline-block;
    margin-top: 10px;
    padding: 3px 9px;
    background: rgba(0,184,156,0.07);
    border: 1px solid rgba(0,184,156,0.2);
    border-radius: 4px;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
    color: #00897b;
}

/* ── Collection badge ── */
.collection-badge {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 12px;
    color: #00897b;
    padding: 6px 10px;
    background: rgba(0,184,156,0.06);
    border: 1px solid rgba(0,184,156,0.18);
    border-radius: 4px;
    margin-top: 4px;
    display: inline-block;
}

/* ── Article count ── */
.article-count {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 12px;
    color: #bbb;
    padding: 8px 0 16px;
}
.article-count strong { color: #0f0f0f; }

/* ── No articles message ── */
.no-articles {
    text-align: center;
    padding: 60px 0;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 13px;
    color: #ccc;
}

/* ── RAG main area padding ── */
.rag-main-pad { padding: 24px 28px; }

/* ── Context block inside expander ── */
.ctx-block {
    background: #f7f7fb;
    border: 1px solid #e8e8ee;
    border-radius: 6px;
    padding: 12px 14px;
    margin-bottom: 10px;
    font-size: 14px;
    line-height: 1.65;
    color: #444;
}
.ctx-block-header {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
    color: #5b6bff;
    margin-bottom: 8px;
    letter-spacing: 0.3px;
}

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #ddd; border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: #bbb; }
</style>
"""


# ── Helper renderers ──────────────────────────────────────────────────────────

def render_topbar() -> None:
    st.markdown(
        """
        <div class="topbar">
            <div class="topbar-logo">
                <span class="logo-dot"></span>
                <span><span class="accent">dev</span>docs<span class="accent">.</span>ai</span>
            </div>
            <div class="topbar-status" style="color:#aaa;">
                <span class="status-live"></span>
                kafka · spark · iceberg · ollama · qdrant
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_blog_card(entry: dict) -> None:
    title = entry.get("title", "Untitled")
    url = entry.get("url", "#")
    author = entry.get("author", "Unknown")
    source = entry.get("source_feed", "")
    published = entry.get("published_at", "")[:10]
    summary = entry.get("summary", "No summary available.")
    score = entry.get("score", 0.75)
    score_pct = int(float(score) * 100) if score else 75

    st.markdown(
        f"""
        <div class="blog-card">
            <div>
                <div class="card-meta">
                    <span class="source-tag">{source}</span>
                    <span class="date-tag">{published}</span>
                    <span class="author-tag">by {author}</span>
                </div>
                <div class="card-title">
                    <a href="{url}" target="_blank">{title}</a>
                </div>
                <div class="card-summary">{summary}</div>
            </div>
            <div class="card-actions">
                <a class="read-link" href="{url}" target="_blank">read →</a>
                <div class="score-bar">
                    <div class="score-fill" style="width:{score_pct}%"></div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    st.set_page_config(
        page_title="Smart Dev Docs Platform",
        page_icon="⬡",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    # Inject global CSS
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

    # Top bar
    render_topbar()

    # Tabs
    tab_rag, tab_blogs = st.tabs(["◈  document rag", "◎  tech blog insights"])

    # ── TAB 1: Document RAG ───────────────────────────────────────────────────
    with tab_rag:
        col_sidebar, col_main = st.columns([1, 4], gap="small")

        with col_sidebar:
            st.markdown('<div class="rag-sidebar">', unsafe_allow_html=True)

            st.markdown('<div class="sidebar-label">Retrieval</div>', unsafe_allow_html=True)
            top_k = st.slider(
                "Top-K chunks",
                min_value=1, max_value=10, value=4,
                key="rag_top_k",
            )

            st.markdown('<div class="sidebar-label" style="margin-top:20px;">Collection</div>', unsafe_allow_html=True)
            st.markdown('<div class="collection-badge">docs_v1 · live</div>', unsafe_allow_html=True)

            st.markdown('</div>', unsafe_allow_html=True)

        with col_main:
            st.markdown('<div class="rag-main-pad">', unsafe_allow_html=True)

            # Chat history
            if "messages" not in st.session_state:
                st.session_state.messages = []

            for message in st.session_state.messages:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])
                    if message["role"] == "assistant" and message.get("contexts"):
                        ctx_count = len(message["contexts"])
                        top_score = max((c.score for c in message["contexts"]), default=0)
                        st.markdown(
                            f'<div class="ctx-badge">{ctx_count} chunks · top score {top_score:.3f}</div>',
                            unsafe_allow_html=True,
                        )

            # Chat input
            if prompt := st.chat_input("Ask a question over your documents…"):
                st.chat_message("user").markdown(prompt)
                st.session_state.messages.append({"role": "user", "content": prompt})

                with st.chat_message("assistant"):
                    with st.spinner("retrieving context…"):
                        engine = get_engine()
                        result = engine.answer(question=prompt, top_k=top_k)

                    st.markdown(result["answer"])

                    if not result["contexts"]:
                        st.info(
                            "No context found in Qdrant. "
                            "Add PDFs to `data/books/` and run `bash ./k8s/build.sh pipeline --source-dir data/books`."
                        )
                    else:
                        ctx_count = len(result["contexts"])
                        top_score = max((c.score for c in result["contexts"]), default=0)
                        st.markdown(
                            f'<div class="ctx-badge">{ctx_count} chunks retrieved · top score {top_score:.3f}</div>',
                            unsafe_allow_html=True,
                        )
                        with st.expander("show retrieved contexts"):
                            for idx, ctx in enumerate(result["contexts"], start=1):
                                st.markdown(
                                    f"""
                                    <div class="ctx-block">
                                        <div class="ctx-block-header">[{idx}] {ctx.source_file} · page {ctx.page_number} · score {ctx.score:.4f}</div>
                                        {ctx.text}
                                    </div>
                                    """,
                                    unsafe_allow_html=True,
                                )

                st.session_state.messages.append({
                    "role": "assistant",
                    "content": result["answer"],
                    "contexts": result.get("contexts", []),
                })

            st.markdown('</div>', unsafe_allow_html=True)

    # ── TAB 2: Tech Blog Insights ─────────────────────────────────────────────
    with tab_blogs:
        st.markdown('<div style="padding: 30px 40px 0;">', unsafe_allow_html=True)

        # Header row
        hdr_col, btn_col = st.columns([5, 1])
        with hdr_col:
            st.markdown(
                '<div class="blog-section-title"><span class="accent">//</span> tech blog insights</div>'
                '<div class="blog-section-sub">auto-crawled · AI summarised · run <code>python -m src.processing.blog_crawler</code> to refresh</div>',
                unsafe_allow_html=True,
            )
        with btn_col:
            if st.button("⟳  refresh feed", key="blog_refresh", use_container_width=True):
                with st.spinner("Crawling new blogs. This may take a moment..."):
                    import subprocess, sys
                    subprocess.run([sys.executable, "-m", "src.processing.blog_crawler"])
                fetch_latest_blogs.clear()
                st.rerun()

        st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

        # Controls row
        ctrl1, ctrl2, ctrl3 = st.columns([3, 3, 1])
        with ctrl1:
            search_term = st.text_input("search", placeholder="Search title or summary…", label_visibility="collapsed", key="blog_search")
        with ctrl2:
            # Limit slider
            limit = st.slider("articles", min_value=5, max_value=50, value=20, key="blog_limit", label_visibility="collapsed")

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

        # Fetch entries
        entries = fetch_latest_blogs(limit=limit)

        if not entries:
            st.markdown(
                '<div class="no-articles">No blog summaries yet.<br/>'
                'Run <code>python -m src.processing.blog_crawler</code> to populate.</div>',
                unsafe_allow_html=True,
            )
        else:
            # Source filter chips (use multiselect styled as compact)
            all_sources = sorted(set(e.get("source_feed", "Unknown") for e in entries))
            selected_sources = st.multiselect(
                "filter by source",
                options=all_sources,
                default=[],
                placeholder="All sources",
                key="blog_sources",
                label_visibility="collapsed",
            )

            # Apply filters
            filtered = [
                e for e in entries
                if (not selected_sources or e.get("source_feed", "Unknown") in selected_sources)
                and (
                    not search_term
                    or search_term.lower() in e.get("title", "").lower()
                    or search_term.lower() in e.get("summary", "").lower()
                )
            ]

            st.markdown(
                f'<div class="article-count"><strong>{len(filtered)}</strong> article(s)</div>',
                unsafe_allow_html=True,
            )

            for entry in filtered:
                render_blog_card(entry)

        st.markdown("</div>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()