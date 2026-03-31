#!/usr/bin/env python3
"""
EZModel 账单与分析仪表盘 — Streamlit

启动: cd scripts/athena && streamlit run bill_dashboard.py
"""

import io
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

if sys.stdout and sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# 从仓库根目录加载 .env（须先于 athena_engine 导入，以便 RAW_LOG_S3_* / AWS_REGION 生效）
try:
    from dotenv import load_dotenv
    _root = Path(__file__).resolve().parents[2]
    load_dotenv(_root / ".env")
except ImportError:
    pass

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from athena_engine import run_query_cached
import queries
import report_builder
import pricing_engine
import cost_import

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="EZModel 账单分析",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

st.sidebar.title("EZModel 账单分析")

now = datetime.now(timezone.utc)
default_month = f"{now.year}-{now.month:02d}"
available_months = [f"{now.year}-{m:02d}" for m in range(1, now.month + 1)]
available_months.reverse()

year_month = st.sidebar.selectbox("选择月份", available_months, index=0)
no_cache = st.sidebar.checkbox("跳过缓存", value=False)

st.sidebar.markdown("---")
st.sidebar.caption(f"数据源: Athena `ezmodel_logs`")
st.sidebar.caption(f"额度换算: quota ÷ 500,000 = USD")


# ---------------------------------------------------------------------------
# Data loading with Streamlit cache
# ---------------------------------------------------------------------------

@st.cache_data(ttl=600, show_spinner="正在查询 Athena...")
def load_kpi(ym, nc):
    return run_query_cached(queries.kpi_summary(ym), no_cache=nc)

@st.cache_data(ttl=600, show_spinner="正在查询...")
def load_users(ym, nc):
    return run_query_cached(queries.monthly_bill_by_user(ym), no_cache=nc)

@st.cache_data(ttl=600, show_spinner="正在查询...")
def load_user_model(ym, nc):
    return run_query_cached(queries.monthly_bill_by_user_model(ym), no_cache=nc)

@st.cache_data(ttl=600, show_spinner="正在查询...")
def load_trend(ym, nc):
    return run_query_cached(queries.daily_trend(ym), no_cache=nc)

@st.cache_data(ttl=600, show_spinner="正在查询...")
def load_models(ym, nc):
    return run_query_cached(queries.model_ranking(ym), no_cache=nc)

@st.cache_data(ttl=600, show_spinner="正在查询...")
def load_channels(ym, nc):
    return run_query_cached(queries.channel_summary(ym), no_cache=nc)

@st.cache_data(ttl=600, show_spinner="正在查询...")
def load_anomaly_zero(ym, nc):
    return run_query_cached(queries.anomaly_zero_tokens(ym), no_cache=nc)

@st.cache_data(ttl=600, show_spinner="正在查询...")
def load_errors(ym, day, nc):
    return run_query_cached(queries.error_distribution(ym, day), no_cache=nc)

@st.cache_data(ttl=600, show_spinner="正在查询定价数据...")
def load_full_billing(ym, nc, flat_tier=False, flat_tier_since=None):
    df = run_query_cached(queries.monthly_bill_full(ym), no_cache=nc)
    if not df.empty:
        df = pricing_engine.apply_pricing_summary(
            df, flat_tier=flat_tier, flat_tier_since=flat_tier_since)
    return df


# ---------------------------------------------------------------------------
# KPI Cards
# ---------------------------------------------------------------------------

st.title(f"📊 月度概览 — {year_month}")

df_kpi = load_kpi(year_month, no_cache)

if not df_kpi.empty:
    kpi = df_kpi.iloc[0]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("总费用 (USD)", f"${float(kpi['total_usd']):,.2f}")
    c2.metric("总调用量", f"{int(kpi['total_calls']):,}")
    c3.metric("活跃用户", int(kpi["unique_users"]))
    c4.metric("活跃模型", int(kpi["unique_models"]))

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("总输入 Tokens", f"{int(kpi['total_input_tokens']):,}")
    c6.metric("总输出 Tokens", f"{int(kpi['total_output_tokens']):,}")
    total_tokens = int(kpi["total_input_tokens"]) + int(kpi["total_output_tokens"])
    c7.metric("总 Tokens", f"{total_tokens:,}")
    avg_cost = float(kpi["total_usd"]) / max(int(kpi["total_calls"]), 1)
    c8.metric("平均单次费用", f"${avg_cost:.4f}")

st.markdown("---")

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

tab_trend, tab_profit, tab_recalc, tab_crosscheck, tab_models, tab_users, tab_channels, tab_anomaly, tab_errors, tab_discounts, tab_export = \
    st.tabs(["📈 费用趋势", "💰 利润分析", "🔄 重算分析", "📋 对账",
             "🤖 模型分析", "👥 用户分析", "📡 渠道分析",
             "⚠️ 异常检测", "❌ 错误分析", "⚙️ 折扣管理", "📥 导出"])


# --- Tab: Daily Trend ---
with tab_trend:
    df_trend = load_trend(year_month, no_cache)
    if not df_trend.empty:
        df_trend["date"] = df_trend["day"].apply(
            lambda d: f"{year_month}-{int(d):02d}")
        fig = px.bar(df_trend, x="date", y="total_usd",
                     title="每日费用 (USD)",
                     labels={"date": "日期", "total_usd": "费用 (USD)"},
                     text_auto=".2f")
        fig.update_layout(xaxis_tickangle=-45, height=400)
        st.plotly_chart(fig, width="stretch")

        col1, col2 = st.columns(2)
        with col1:
            fig2 = px.line(df_trend, x="date", y="call_count",
                           title="每日调用量",
                           labels={"date": "日期", "call_count": "调用次数"})
            st.plotly_chart(fig2, width="stretch")
        with col2:
            fig3 = px.line(df_trend, x="date", y="total_tokens",
                           title="每日 Token 消耗",
                           labels={"date": "日期", "total_tokens": "Tokens"})
            st.plotly_chart(fig3, width="stretch")
    else:
        st.info("暂无数据")


# --- Tab: Profit Analysis ---
with tab_profit:
    st.subheader("利润分析（四层价格体系）")

    pr_col1, pr_col2, pr_col3 = st.columns(3)
    with pr_col1:
        pr_flat_tier = st.checkbox("降档模式（分段模型用低档价）", key="pr_flat")
    with pr_col2:
        pr_flat_since = st.text_input("降档起始日期 (YYYY-MM-DD)",
                                      key="pr_flat_since", placeholder="留空=全量降档")
    with pr_col3:
        pr_user_id = st.number_input("用户 ID（0=全部）", min_value=0, value=0,
                                     step=1, key="pr_user")

    use_flat = pr_flat_tier or bool(pr_flat_since.strip())
    flat_since_val = pr_flat_since.strip() or None

    df_billing = load_full_billing(year_month, no_cache,
                                   flat_tier=use_flat,
                                   flat_tier_since=flat_since_val)
    if pr_user_id > 0 and not df_billing.empty:
        df_billing = df_billing[df_billing["user_id"].astype(int) == pr_user_id]

    if not df_billing.empty:
        total_list = df_billing["list_price_usd"].sum()
        total_rev = df_billing["revenue_usd"].sum()
        total_cost = df_billing["cost_usd"].sum()
        total_profit = df_billing["profit_usd"].sum()
    else:
        total_list = total_rev = total_cost = total_profit = 0

    if not df_billing.empty:
        overall_margin = round(total_profit / total_rev * 100, 1) if total_rev else 0

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("刊例价", f"${total_list:,.2f}")
        c2.metric("客户应付", f"${total_rev:,.2f}")
        c3.metric("我方成本", f"${total_cost:,.2f}")
        c4.metric("利润", f"${total_profit:,.2f}")
        c5.metric("利润率", f"{overall_margin}%")

        st.markdown("---")

        user_col = "username" if "username" in df_billing.columns else "user_id"
        model_col = "model_name" if "model_name" in df_billing.columns else "model"
        rev_col = "revenue_usd"
        cost_col = "cost_usd"
        profit_col = "profit_usd"
        list_col = "list_price_usd" if "list_price_usd" in df_billing.columns else "expected_usd"

        user_profit = df_billing.groupby(["user_id", user_col]).agg({
            list_col: "sum", rev_col: "sum",
            cost_col: "sum", profit_col: "sum",
        }).reset_index()
        user_profit["margin_pct"] = (user_profit[profit_col] / user_profit[rev_col].replace(0, float("nan")) * 100).round(1)
        user_profit = user_profit.sort_values(profit_col, ascending=False)

        col1, col2 = st.columns(2)
        with col1:
            fig = px.bar(user_profit, x=user_col, y=[rev_col, cost_col, profit_col],
                         title="用户利润分解",
                         labels={"value": "USD", user_col: "用户"},
                         barmode="group")
            fig.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig, width="stretch")
        with col2:
            fig2 = px.bar(user_profit, x=user_col, y="margin_pct",
                          title="用户利润率 (%)",
                          labels={user_col: "用户", "margin_pct": "利润率 (%)"},
                          text_auto=".1f")
            fig2.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig2, width="stretch")

        model_profit = df_billing.groupby(model_col).agg({
            list_col: "sum", rev_col: "sum",
            cost_col: "sum", profit_col: "sum",
        }).reset_index()
        model_profit["margin_pct"] = (model_profit[profit_col] / model_profit[rev_col].replace(0, float("nan")) * 100).round(1)
        model_profit = model_profit.sort_values(profit_col, ascending=False)

        st.subheader("模型利润明细")
        st.dataframe(model_profit, width="stretch", hide_index=True)
    else:
        st.info("暂无数据")


# --- Tab: Recalc Analysis ---
with tab_recalc:
    st.subheader("基于原始日志重算（分段计费 + 降档）")
    st.caption("从 Athena 拉取逐条原始数据，用 pricing.json 分段计费规则重算刊例价，对比系统 quota 扣费")

    rc_col1, rc_col2, rc_col3 = st.columns(3)
    with rc_col1:
        rc_start = st.date_input("起始日期", key="rc_start",
                                 value=datetime.now().replace(day=1))
    with rc_col2:
        rc_end = st.date_input("结束日期", key="rc_end")
    with rc_col3:
        rc_flat = st.checkbox("降档模式（分段模型用低档价）", key="rc_flat")

    rc_col4, rc_col5, rc_col6 = st.columns(3)
    with rc_col4:
        rc_flat_since = st.text_input("降档起始日期 (YYYY-MM-DD)", key="rc_flat_since",
                                      placeholder="留空=全量降档")
    with rc_col5:
        rc_user = st.number_input("用户 ID（0=全部）", min_value=0, value=0,
                                  step=1, key="rc_user")
    with rc_col6:
        rc_channel = st.number_input("渠道 ID（0=全部）", min_value=0, value=0,
                                     step=1, key="rc_channel")

    if st.button("开始重算", key="btn_recalc"):
        start_str = rc_start.strftime("%Y-%m-%d")
        end_str = rc_end.strftime("%Y-%m-%d")
        uid = rc_user if rc_user > 0 else None
        chid = rc_channel if rc_channel > 0 else None
        flat_since = rc_flat_since.strip() or None

        with st.spinner(f"正在从 Athena 拉取 {start_str} ~ {end_str} 原始数据..."):
            df_raw = run_query_cached(
                queries.raw_usage_detail(start_str, end_str,
                                         user_id=uid, channel_id=chid),
                no_cache=no_cache)

        if df_raw.empty:
            st.warning("指定时间段内无数据")
        else:
            with st.spinner(f"正在重算 {len(df_raw):,} 条记录..."):
                df_rc = pricing_engine.recalc_from_raw(
                    df_raw, flat_tier=rc_flat, flat_tier_since=flat_since)

            has_p = df_rc[df_rc["has_pricing"] == True]
            no_p = df_rc[df_rc["has_pricing"] == False]

            if not has_p.empty:
                total_expected = has_p["expected_usd"].sum()
                total_billed = has_p["billed_usd"].sum()
                total_diff = has_p["diff_usd"].sum()
                total_cost = has_p["cost_usd"].sum()
                total_rev = has_p["revenue_usd"].sum()
                total_profit = has_p["profit_usd"].sum()

                m1, m2, m3, m4, m5, m6 = st.columns(6)
                m1.metric("重算刊例价", f"${total_expected:,.2f}")
                m2.metric("系统扣费", f"${total_billed:,.2f}")
                m3.metric("差额", f"${total_diff:,.2f}")
                m4.metric("成本", f"${total_cost:,.2f}")
                m5.metric("客户应付", f"${total_rev:,.2f}")
                m6.metric("利润", f"${total_profit:,.2f}")

                grp = has_p.groupby(["user_id", "username", "model"]).agg({
                    "expected_usd": "sum", "billed_usd": "sum", "diff_usd": "sum",
                    "cost_usd": "sum", "revenue_usd": "sum", "profit_usd": "sum",
                    "request_id": "count",
                }).reset_index().rename(columns={"request_id": "call_count"})
                grp = grp.sort_values("billed_usd", ascending=False)

                st.subheader("按用户×模型汇总")
                st.dataframe(grp, width="stretch", hide_index=True)

                big_diff = has_p[has_p["diff_usd"].abs() > 0.01].sort_values(
                    "diff_usd", ascending=False, key=abs).head(100)
                if not big_diff.empty:
                    st.subheader(f"差额较大的记录 (>{0.01}$, 前 100 条)")
                    st.dataframe(
                        big_diff[["request_id", "model", "user_id", "prompt_tokens",
                                  "expected_usd", "billed_usd", "diff_usd"]],
                        width="stretch", hide_index=True)

            if not no_p.empty:
                st.warning(f"{len(no_p)} 条记录无定价表匹配（使用 quota 换算），"
                           f"涉及模型: {', '.join(no_p['model'].unique()[:10])}")

            # Export button
            import tempfile
            with tempfile.TemporaryDirectory() as tmpdir:
                path = report_builder.generate_recalc_report(
                    start_str, end_str, tmpdir,
                    user_id=uid, channel_id=chid,
                    flat_tier=rc_flat, flat_tier_since=flat_since,
                    no_cache=True)
                with open(path, "rb") as f:
                    st.download_button("📥 下载重算报告 Excel", f.read(),
                                       file_name=f"recalc_{start_str}_{end_str}.xlsx",
                                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# --- Tab: Cross-check ---
with tab_crosscheck:
    st.subheader("供应商账单对账")
    st.caption("上传供应商的成本账单（CSV/Excel），与我方 Athena 数据交叉对比")

    uploaded = st.file_uploader("上传供应商账单", type=["csv", "xlsx", "xls"],
                                key="vendor_upload")

    cc_col1, cc_col2 = st.columns(2)
    with cc_col1:
        cc_channel = st.number_input("关联渠道 ID（0=全部）", min_value=0, value=0,
                                     step=1, key="cc_channel")
    with cc_col2:
        cc_month = st.text_input("对账月份", value=year_month, key="cc_month")

    cc_col3, cc_col4 = st.columns(2)
    with cc_col3:
        cc_model_col = st.text_input("模型列名（留空=自动检测）", key="cc_model_col")
    with cc_col4:
        cc_amount_col = st.text_input("金额列名（留空=自动检测）", key="cc_amount_col")

    if uploaded and st.button("开始对账", key="btn_crosscheck"):
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(uploaded.name)[1]) as tmp:
            tmp.write(uploaded.read())
            tmp_path = tmp.name

        try:
            mapping = {}
            if cc_model_col.strip():
                mapping["model"] = cc_model_col.strip()
            if cc_amount_col.strip():
                mapping["amount"] = cc_amount_col.strip()

            vendor_df = cost_import.import_and_summarize(
                tmp_path, column_mapping=mapping or None,
                channel_id=cc_channel if cc_channel > 0 else None,
                month=cc_month)

            st.success(f"导入成功: {len(vendor_df)} 个模型, 总额 ${vendor_df['vendor_amount'].sum():,.2f}")

            our_df = run_query_cached(queries.monthly_bill_full(cc_month), no_cache=no_cache)
            if not our_df.empty:
                our_df = pricing_engine.apply_pricing_summary(our_df)
                if cc_channel > 0:
                    our_df = our_df[our_df["channel_id"].astype(int) == cc_channel]
                our_agg = our_df.groupby("model_name").agg({
                    "call_count": "sum", "list_price_usd": "sum",
                }).reset_index()
            else:
                our_agg = pd.DataFrame(columns=["model_name", "call_count", "list_price_usd"])

            merged = pricing_engine.cross_check(our_agg, vendor_df, match_col="model_name")

            st.subheader("对账结果")
            st.dataframe(merged, width="stretch", hide_index=True)

            if "diff" in merged.columns:
                total_diff = merged["diff"].sum()
                total_ours = merged.get("our_amount", pd.Series([0])).sum()
                total_vendor = merged["vendor_amount"].sum()

                d1, d2, d3 = st.columns(3)
                d1.metric("我方刊例价", f"${total_ours:,.2f}")
                d2.metric("供应商金额", f"${total_vendor:,.2f}")
                d3.metric("差额", f"${total_diff:,.2f}")

                fig = px.bar(merged, x="model", y=["our_amount", "vendor_amount"],
                             title="模型级别对比", barmode="group",
                             labels={"value": "USD", "model": "模型"})
                fig.update_layout(xaxis_tickangle=-45)
                st.plotly_chart(fig, width="stretch")

            with tempfile.TemporaryDirectory() as tmpdir:
                path = report_builder.generate_crosscheck_report(
                    cc_month, tmp_path, tmpdir,
                    channel_id=cc_channel if cc_channel > 0 else None,
                    column_mapping=mapping or None,
                    no_cache=True)
                with open(path, "rb") as f:
                    st.download_button("📥 下载对账报告 Excel", f.read(),
                                       file_name=f"crosscheck_{cc_month}.xlsx",
                                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        except Exception as e:
            st.error(f"对账失败: {e}")
        finally:
            os.unlink(tmp_path)


# --- Tab: Model Analysis ---
with tab_models:
    df_models = load_models(year_month, no_cache)
    if not df_models.empty:
        col1, col2 = st.columns(2)
        with col1:
            fig = px.pie(df_models, values="total_usd", names="model_name",
                         title="模型费用占比")
            st.plotly_chart(fig, width="stretch")
        with col2:
            fig2 = px.bar(df_models.head(15), x="model_name", y="total_usd",
                          title="模型费用排行 (Top 15)",
                          labels={"model_name": "模型", "total_usd": "费用 (USD)"},
                          text_auto=".2f")
            fig2.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig2, width="stretch")

        st.subheader("模型详情")
        st.dataframe(df_models, width="stretch", hide_index=True)
    else:
        st.info("暂无数据")


# --- Tab: User Analysis ---
with tab_users:
    df_users = load_users(year_month, no_cache)
    if not df_users.empty:
        fig = px.bar(df_users.head(20), x="username", y="total_usd",
                     title="用户费用排行 (Top 20)",
                     labels={"username": "用户", "total_usd": "费用 (USD)"},
                     text_auto=".2f")
        fig.update_layout(xaxis_tickangle=-45, height=400)
        st.plotly_chart(fig, width="stretch")

        selected_user = st.selectbox(
            "查看用户详情",
            options=["全部"] + df_users["username"].tolist())

        df_detail = load_user_model(year_month, no_cache)
        if selected_user != "全部":
            df_detail = df_detail[df_detail["username"] == selected_user]

        st.dataframe(df_detail, width="stretch", hide_index=True)
    else:
        st.info("暂无数据")


# --- Tab: Channel Analysis ---
with tab_channels:
    df_ch = load_channels(year_month, no_cache)
    if not df_ch.empty:
        fig = px.bar(df_ch, x="channel_id", y="total_usd",
                     title="渠道费用分布",
                     labels={"channel_id": "渠道 ID", "total_usd": "费用 (USD)"},
                     text_auto=".2f")
        st.plotly_chart(fig, width="stretch")
        st.dataframe(df_ch, width="stretch", hide_index=True)
    else:
        st.info("暂无数据")


# --- Tab: Anomaly Detection ---
with tab_anomaly:
    df_zero = load_anomaly_zero(year_month, no_cache)
    if not df_zero.empty:
        total_loss = df_zero["quota_usd"].sum()
        st.warning(f"发现 {len(df_zero)} 条异常扣费记录，"
                   f"涉及金额 ${total_loss:,.4f}")
        st.dataframe(df_zero, width="stretch", hide_index=True)
    else:
        st.success("未发现异常扣费记录")


# --- Tab: Error Analysis ---
with tab_errors:
    st.caption("error_logs 查询需指定日期（按天分区），避免高额扫描")
    parts = year_month.split("-")
    max_day = now.day if year_month == default_month else 31
    error_day = st.selectbox("选择日期",
                             [f"{d:02d}" for d in range(1, max_day + 1)],
                             index=max(0, min(max_day, now.day) - 2))

    if st.button("查询错误分布", key="btn_errors"):
        df_err = load_errors(year_month, error_day, no_cache)
        if not df_err.empty:
            col1, col2 = st.columns(2)
            with col1:
                by_status = df_err.groupby("status_code")["error_count"].sum().reset_index()
                fig = px.pie(by_status, values="error_count", names="status_code",
                             title="按状态码分布")
                st.plotly_chart(fig, width="stretch")
            with col2:
                by_model = df_err.groupby("model")["error_count"].sum().reset_index()
                by_model = by_model.sort_values("error_count", ascending=False).head(10)
                fig2 = px.bar(by_model, x="model", y="error_count",
                              title="按模型分布 (Top 10)",
                              text_auto=True)
                fig2.update_layout(xaxis_tickangle=-45)
                st.plotly_chart(fig2, width="stretch")

            st.dataframe(df_err, width="stretch", hide_index=True)
        else:
            st.info("该日期无错误记录")


# --- Tab: Discount Management ---
with tab_discounts:
    st.subheader("折扣配置管理")
    st.caption("修改后自动保存到 discounts.json，立即生效于后续查询和报表")

    disc_tab_cost, disc_tab_rev, disc_tab_batch = st.tabs(["成本折扣 (渠道×模型)", "客户折扣 (用户×模型)", "批量操作"])

    with disc_tab_cost:
        cost_rows = pricing_engine.get_all_cost_discounts()
        if cost_rows:
            df_cost = pd.DataFrame(cost_rows)
            edited_cost = st.data_editor(
                df_cost,
                column_config={
                    "channel_id": st.column_config.TextColumn("渠道 ID", disabled=True),
                    "channel_name": st.column_config.TextColumn("渠道名称", disabled=True),
                    "model": st.column_config.TextColumn("模型 (* = 通配)"),
                    "discount": st.column_config.NumberColumn("折扣率", min_value=0.0, max_value=2.0, step=0.01, format="%.2f"),
                },
                num_rows="dynamic",
                key="cost_editor",
                width="stretch",
            )
            if st.button("保存成本折扣", key="btn_save_cost"):
                d = pricing_engine._load_discounts()
                new_by_channel = {}
                for _, r in edited_cost.iterrows():
                    ch = str(r["channel_id"])
                    if ch not in new_by_channel:
                        new_by_channel[ch] = {"_name": r.get("channel_name", "")}
                    new_by_channel[ch][r["model"]] = float(r["discount"])
                d["cost_discounts"]["by_channel"] = new_by_channel
                pricing_engine.save_discounts(d)
                st.success("成本折扣已保存")
                st.cache_data.clear()
        else:
            st.info("暂无成本折扣配置")

    with disc_tab_rev:
        rev_rows = pricing_engine.get_all_revenue_discounts()
        if rev_rows:
            df_rev = pd.DataFrame(rev_rows)
            edited_rev = st.data_editor(
                df_rev,
                column_config={
                    "user_id": st.column_config.TextColumn("用户 ID", disabled=True),
                    "user_name": st.column_config.TextColumn("用户名", disabled=True),
                    "model": st.column_config.TextColumn("模型 (* = 通配)"),
                    "discount": st.column_config.NumberColumn("折扣率", min_value=0.0, max_value=2.0, step=0.01, format="%.2f"),
                },
                num_rows="dynamic",
                key="rev_editor",
                width="stretch",
            )
            if st.button("保存客户折扣", key="btn_save_rev"):
                d = pricing_engine._load_discounts()
                new_by_user = {}
                for _, r in edited_rev.iterrows():
                    uid = str(r["user_id"])
                    if uid not in new_by_user:
                        new_by_user[uid] = {"_name": r.get("user_name", "")}
                    new_by_user[uid][r["model"]] = float(r["discount"])
                d["revenue_discounts"]["by_user"] = new_by_user
                pricing_engine.save_discounts(d)
                st.success("客户折扣已保存")
                st.cache_data.clear()
        else:
            st.info("暂无客户折扣配置")

    with disc_tab_batch:
        st.markdown("**批量设置折扣**")
        batch_type = st.selectbox("类型", ["成本折扣 (渠道)", "客户折扣 (用户)"], key="batch_type")
        batch_ids = st.text_input("ID 列表 (逗号分隔)", placeholder="25,54,24", key="batch_ids")
        batch_model = st.text_input("模型 (* = 所有模型)", value="*", key="batch_model")
        batch_rate = st.number_input("折扣率", min_value=0.0, max_value=2.0, value=1.0, step=0.01, key="batch_rate")

        if st.button("批量应用", key="btn_batch"):
            if batch_ids.strip():
                d = pricing_engine._load_discounts()
                ids = [x.strip() for x in batch_ids.split(",") if x.strip()]
                if "成本" in batch_type:
                    section = d["cost_discounts"].setdefault("by_channel", {})
                else:
                    section = d["revenue_discounts"].setdefault("by_user", {})

                for id_val in ids:
                    if id_val not in section:
                        section[id_val] = {"_name": ""}
                    section[id_val][batch_model] = batch_rate

                pricing_engine.save_discounts(d)
                st.success(f"已为 {len(ids)} 个 ID 设置 {batch_model} 折扣率 = {batch_rate}")
                st.cache_data.clear()
            else:
                st.warning("请输入 ID 列表")


# --- Tab: Export ---
with tab_export:
    st.subheader("导出 Excel 账单")

    exp_col1, exp_col2 = st.columns(2)
    with exp_col1:
        exp_user_id = st.number_input("用户 ID（留空=全平台）", min_value=0,
                                      value=0, step=1)
    with exp_col2:
        exp_currency = st.selectbox("币种", ["USD", "CNY"])

    exp_col3, exp_col4 = st.columns(2)
    with exp_col3:
        exp_flat_tier = st.checkbox("降档模式", key="exp_flat")
    with exp_col4:
        exp_flat_since = st.text_input("降档起始日期 (YYYY-MM-DD)",
                                       key="exp_flat_since", placeholder="留空=全量降档")

    exp_col5, exp_col6 = st.columns(2)
    with exp_col5:
        import calendar as _cal
        _ym_year, _ym_month = int(year_month.split("-")[0]), int(year_month.split("-")[1])
        _month_first = datetime(_ym_year, _ym_month, 1).date()
        _month_last = datetime(_ym_year, _ym_month,
                               _cal.monthrange(_ym_year, _ym_month)[1]).date()
        _today = datetime.now(timezone.utc).date()
        _end_day_default = min(_today, _month_last)
        exp_end_day_toggle = st.checkbox("指定截止日期", key="exp_end_day_toggle",
                                         help="勾选后可选择账单截止日期，留空则导出整月")
        if exp_end_day_toggle:
            exp_end_day_date = st.date_input(
                "截止日期",
                value=_end_day_default,
                min_value=_month_first,
                max_value=_month_last,
                key="exp_end_day_picker",
                help="仅统计到该日期（含当天）",
            )
            exp_end_day = exp_end_day_date.strftime("%Y-%m-%d")
        else:
            exp_end_day = None
    with exp_col6:
        pass  # reserved

    exp_col7, exp_col8 = st.columns(2)
    with exp_col7:
        exp_detail = st.checkbox("含逐条明细", key="exp_detail",
                                 help="同时导出每一条请求的明细数据（按天并行查询，大用户可能需要 5-8 分钟）。"
                                      "客户版本输出 .xlsx（自动分 sheet），内部版本输出 .csv.zip")
    with exp_col8:
        exp_customer_view = st.checkbox("客户版本（隐藏成本/利润）", key="exp_customer_view",
                                        help="导出可直接发给客户的版本，不含成本折扣、成本价、利润、利润率、渠道 ID 等内部数据")

    exp_col9, exp_col10 = st.columns(2)
    with exp_col9:
        exp_upload = st.checkbox("上传到 S3 并生成下载链接", key="exp_upload", value=True,
                                 help="上传到 S3 后生成 24h 有效的下载链接，适合分享给他人")
    with exp_col10:
        pass

    if st.button("生成月度账单 Excel", key="btn_export_bill"):
        import tempfile
        _exp_flat = exp_flat_tier or bool(exp_flat_since.strip())
        _exp_since = exp_flat_since.strip() or None
        _exp_end_day = exp_end_day  # already None or valid YYYY-MM-DD from date_input
        with tempfile.TemporaryDirectory() as tmpdir:
            uid = exp_user_id if exp_user_id > 0 else None
            spinner_msg = "正在生成账单..."
            if exp_detail:
                spinner_msg += " (含逐条明细，请耐心等待)"
            with st.spinner(spinner_msg):
                result = report_builder.generate_monthly_bill(
                    year_month, tmpdir, user_id=uid,
                    currency=exp_currency,
                    flat_tier=_exp_flat, flat_tier_since=_exp_since,
                    end_day=_exp_end_day,
                    detail=exp_detail,
                    customer_view=exp_customer_view,
                    upload_s3=exp_upload,
                    no_cache=no_cache)

            if isinstance(result, dict):
                st.success("账单已生成并上传到 S3")
                st.markdown("**S3 下载链接（24h 有效）：**")
                st.code(result["xlsx_url"], language=None)
                if "detail_csv_url" in result:
                    st.markdown("**明细数据下载链接：**")
                    st.code(result["detail_csv_url"], language=None)
                with open(result["xlsx"], "rb") as f:
                    st.download_button(
                        label="📥 本地下载汇总账单",
                        data=f.read(),
                        file_name=f"bill_{year_month}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
            elif isinstance(result, list):
                xlsx_path, detail_path = result
                with open(xlsx_path, "rb") as f:
                    st.download_button(
                        label="📥 下载汇总账单 (Excel)",
                        data=f.read(),
                        file_name=f"bill_{year_month}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                detail_size_mb = os.path.getsize(detail_path) / 1024 / 1024
                detail_basename = os.path.basename(detail_path)
                is_xlsx = detail_basename.endswith(".xlsx")
                detail_label = (f"📥 下载逐条明细 (Excel, {detail_size_mb:.1f} MB)"
                                if is_xlsx
                                else f"📥 下载逐条明细 (CSV.zip, {detail_size_mb:.1f} MB)")
                detail_mime = ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                               if is_xlsx else "application/zip")
                with open(detail_path, "rb") as f:
                    st.download_button(
                        label=detail_label,
                        data=f.read(),
                        file_name=detail_basename,
                        mime=detail_mime,
                    )
                st.success("账单 + 明细已生成，点击上方按钮下载")
            else:
                with open(result, "rb") as f:
                    data = f.read()
                st.download_button(
                    label="📥 下载账单",
                    data=data,
                    file_name=f"bill_{year_month}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
                st.success(f"账单已生成，点击上方按钮下载")

    st.markdown("---")

    if st.button("生成异常检测报告", key="btn_export_anomaly"):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            path = report_builder.generate_anomaly_report(
                year_month, tmpdir, no_cache=no_cache)
            with open(path, "rb") as f:
                data = f.read()
            st.download_button(
                label="📥 下载异常报告",
                data=data,
                file_name=f"anomaly_{year_month}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            st.success("异常报告已生成")
