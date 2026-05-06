"""Sunrise Health Clinic — Voice Agent Ops Dashboard."""
import html
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

# Make project root importable when run via `streamlit run dashboard/app.py`
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import streamlit as st

from dashboard.status import format_status, label_for_outcome
from db.call_history import get_dashboard_stats, get_recent_calls
from guardrails.pii_masker import mask_pii

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Sunrise Health Clinic — Voice Agent",
    page_icon="🏥",
    layout="wide",
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_duration(secs: int | None) -> str:
    if secs is None:
        return "—"
    m, s = divmod(int(secs), 60)
    return f"{m}m {s:02d}s"


def _fmt_phone(raw: str | None) -> str:
    if not raw:
        return "Unknown"
    return mask_pii(raw)


def _fmt_time(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%H:%M:%S")
    except Exception:
        return iso


def _render_transcript(turns: list[dict]) -> None:
    if not turns:
        st.caption("No transcript available.")
        return
    for turn in turns:
        role = turn.get("role", "")
        text = html.escape(mask_pii(turn.get("text", "")))
        if role == "patient":
            st.markdown(
                f'<div style="background:#f0f4ff;padding:6px 12px;border-radius:8px;'
                f'margin:4px 0;color:#111827"><b>👤 Patient:</b> {text}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div style="background:#f0fff4;padding:6px 12px;border-radius:8px;'
                f'margin:4px 0;color:#111827"><b>🤖 Agent:</b> {text}</div>',
                unsafe_allow_html=True,
            )


# ── Data ──────────────────────────────────────────────────────────────────────

calls = get_recent_calls(limit=50)
stats = get_dashboard_stats()

# ── Header ────────────────────────────────────────────────────────────────────

st.title("🏥 Sunrise Health Clinic — Voice Agent")

# ── Top metrics row ───────────────────────────────────────────────────────────

c1, c2, c3, c4 = st.columns(4)
c1.metric("🔴 Active Calls", stats["active_count"])
c2.metric("📞 Today's Total", stats["today_count"])
c3.metric("✅ Success Rate", f"{stats['success_rate']:.0%}")
c4.metric("⏱ Avg Duration", _fmt_duration(stats["avg_duration_s"]))

st.divider()

# ── Tabs ──────────────────────────────────────────────────────────────────────

tab_feed, tab_metrics, tab_escalations = st.tabs(
    ["📞 Live Feed", "📊 Metrics", "🚨 Escalations"]
)

# ── Tab 1: Live Feed ──────────────────────────────────────────────────────────

with tab_feed:
    if not calls:
        st.info("No calls recorded yet. Make a call to +1 707 593 0902 to get started.")
    else:
        # Summary table
        rows = []
        for c in calls:
            status = format_status(c["outcome"], active=not c["end_time"])
            rows.append({
                "SID": c["call_sid"][-8:] if c["call_sid"] else "—",
                "Phone": _fmt_phone(c["caller_phone"]),
                "Started": _fmt_time(c["start_time"]),
                "Duration": _fmt_duration(c["duration_seconds"]),
                "Status": status,
                "Escalated": "⚠️" if c["escalated"] else "",
            })

        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)

        st.subheader("Transcript Viewer")
        options = [
            f"{c['call_sid'][-8:]} — {_fmt_time(c['start_time'])} — "
            f"{label_for_outcome(c['outcome'], 'Active')}"
            for c in calls
        ]
        selected_idx = st.selectbox("Select a call", range(len(options)), format_func=lambda i: options[i])
        selected = calls[selected_idx]

        col_a, col_b = st.columns(2)
        col_a.caption(f"**Phone:** {_fmt_phone(selected['caller_phone'])}")
        col_a.caption(f"**Duration:** {_fmt_duration(selected['duration_seconds'])}")
        col_b.caption(f"**Outcome:** {label_for_outcome(selected['outcome'], 'Active')}")
        col_b.caption(f"**Escalated:** {'Yes' if selected['escalated'] else 'No'}")

        if selected.get("call_summary"):
            st.info(f"**Summary:** {mask_pii(selected['call_summary'])}")

        with st.expander("Full Transcript", expanded=True):
            _render_transcript(selected["transcript"])

# ── Tab 2: Metrics ────────────────────────────────────────────────────────────

with tab_metrics:
    if not calls:
        st.info("No data yet.")
    else:
        col_left, col_right = st.columns(2)

        # Intent breakdown (bar chart)
        with col_left:
            st.subheader("Calls by Intent")
            intent_counts: Counter = Counter()
            for c in calls:
                for intent in c["intent_sequence"]:
                    intent_counts[intent] += 1

            if intent_counts:
                intent_df = pd.DataFrame(
                    intent_counts.most_common(),
                    columns=["Intent", "Count"],
                ).set_index("Intent")
                st.bar_chart(intent_df)
            else:
                st.caption("No intent data yet.")

        # Outcome distribution (pie via st.altair_chart or table fallback)
        with col_right:
            st.subheader("Outcome Distribution")
            outcome_counts: Counter = Counter(
                label_for_outcome(c["outcome"], "Incomplete") for c in calls
            )
            outcome_df = pd.DataFrame(
                outcome_counts.most_common(),
                columns=["Outcome", "Count"],
            ).set_index("Outcome")
            st.bar_chart(outcome_df)

        # Call duration over time (line chart)
        st.subheader("Call Duration Over Time")
        dur_data = [
            {"Time": _fmt_time(c["start_time"]), "Duration (s)": c["duration_seconds"] or 0}
            for c in reversed(calls)
            if c["duration_seconds"] is not None
        ]
        if dur_data:
            dur_df = pd.DataFrame(dur_data).set_index("Time")
            st.line_chart(dur_df)
        else:
            st.caption("No completed calls yet.")

        # Sentiment avg
        st.subheader("Avg Frustration Score per Call")
        sent_data = [
            {"Time": _fmt_time(c["start_time"]), "Score": c["sentiment_avg"] or 0.0}
            for c in reversed(calls)
            if c["sentiment_avg"] is not None
        ]
        if sent_data:
            sent_df = pd.DataFrame(sent_data).set_index("Time")
            st.line_chart(sent_df)
        else:
            st.caption("No sentiment data yet.")

# ── Tab 3: Escalations ────────────────────────────────────────────────────────

with tab_escalations:
    escalated = [c for c in calls if c["escalated"]]
    if not escalated:
        st.success("No escalations. All calls resolved smoothly.")
    else:
        st.warning(f"{len(escalated)} escalated call(s) require attention.")
        for c in escalated:
            with st.expander(
                f"⚠️ {_fmt_phone(c['caller_phone'])} — {_fmt_time(c['start_time'])} "
                f"— {label_for_outcome(c['outcome'])}"
            ):
                if c.get("call_summary"):
                    st.markdown(f"**Summary:** {mask_pii(c['call_summary'])}")
                st.caption(f"Duration: {_fmt_duration(c['duration_seconds'])}")
                st.caption("Transcript:")
                _render_transcript(c["transcript"])

# ── Auto-refresh ──────────────────────────────────────────────────────────────

st.divider()
st.caption(f"Auto-refreshing every 2s · Last updated: {datetime.now().strftime('%H:%M:%S')}")
time.sleep(2)
st.rerun()
