"""
app.py - Cloud Storage Space Optimizer (Streamlit Application)
Comprehensive dashboard for cloud storage analytics, SHA-256 duplicate detection,
ghost/clutter cleanup, file size distribution, and financial cost-savings ROI.
"""

from datetime import datetime, timezone
import io
import os
import shutil
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from drive_service import GoogleDriveManager, MockDriveManager, LocalFolderManager, GOOGLE_LIBS_AVAILABLE
from optimizer import (
    compute_sha256,
    format_bytes,
    process_files_dataframe,
    detect_duplicates_by_sha256,
    audit_large_files,
    audit_inactive_files,
    calculate_storage_health,
    audit_empty_and_temp_files,
    calculate_cost_savings,
)

# Page Setup
st.set_page_config(
    page_title="Cloud Storage Space Optimizer",
    page_icon="☁️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Styling
st.markdown(
    """
    <style>
    .metric-box {
        background-color: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 16px 20px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    }
    .metric-num {
        font-size: 1.85rem;
        font-weight: 700;
        color: #0f172a;
        margin-top: 4px;
    }
    .metric-sub {
        font-size: 0.8rem;
        text-transform: uppercase;
        color: #64748b;
        letter-spacing: 0.05em;
        font-weight: 600;
    }
    .badge-excellent { background-color: #dcfce7; color: #166534; padding: 4px 10px; border-radius: 12px; font-weight: 600; }
    .badge-good { background-color: #dbeafe; color: #1e40af; padding: 4px 10px; border-radius: 12px; font-weight: 600; }
    .badge-moderate { background-color: #fef3c7; color: #92400e; padding: 4px 10px; border-radius: 12px; font-weight: 600; }
    .badge-critical { background-color: #fee2e2; color: #991b1b; padding: 4px 10px; border-radius: 12px; font-weight: 600; }
    </style>
    """,
    unsafe_allow_html=True,
)

# Session State Initialization
if "drive_manager" not in st.session_state:
    st.session_state.drive_manager = MockDriveManager()
if "mode" not in st.session_state:
    st.session_state.mode = "demo"
if "files_cache" not in st.session_state:
    st.session_state.files_cache = None
if "quota_cache" not in st.session_state:
    st.session_state.quota_cache = None


def reload_data():
    """Refresh data from the active drive connector."""
    with st.spinner("Analyzing cloud storage files and computing SHA-256 metadata..."):
        mgr = st.session_state.drive_manager
        files = mgr.list_files()
        quota = mgr.get_quota()
        st.session_state.files_cache = process_files_dataframe(files)
        st.session_state.quota_cache = quota


if st.session_state.files_cache is None:
    reload_data()

# ----------------- SIDEBAR -----------------
with st.sidebar:
    st.title("☁️ Drive Optimizer")
    st.caption("Cloud Storage Analysis & Deduplication")

    st.markdown("---")
    st.subheader("🌐 Cloud Storage Connection")
    mode_selection = st.radio(
        "Choose Storage Source:",
        [
            "✨ Simulated Cloud (No Card / Ready Now)",
            "📁 Local Cloud Sync Folder (Real Files, No Card)",
            "🔗 Google Drive API (OAuth 2.0)",
        ],
        index=0 if st.session_state.mode == "demo" else (1 if st.session_state.mode == "local" else 2),
        help="Simulated mode is 100% free and requires no credit card. Local folder mode scans your actual Google Drive Desktop sync folder or local files."
    )

    if mode_selection == "✨ Simulated Cloud (No Card / Ready Now)":
        if st.session_state.mode != "demo":
            st.session_state.mode = "demo"
            st.session_state.drive_manager = MockDriveManager()
            reload_data()
            st.rerun()
        st.success("Connected to **Simulated Cloud Storage** (15 GB Quota, 35+ Files, Real SHA-256 Hashes).")

    elif mode_selection == "📁 Local Cloud Sync Folder (Real Files, No Card)":
        default_folder = os.path.join(os.getcwd(), "sample_files")
        folder_path = st.text_input(
            "Folder Path to Scan:",
            value=default_folder,
            help="Enter path to your local Google Drive sync folder (e.g., G:\\My Drive) or any directory on your computer."
        )

        col_loc1, col_loc2 = st.columns(2)
        with col_loc1:
            if st.button("Scan Folder", type="primary", use_container_width=True):
                if not os.path.exists(folder_path):
                    os.makedirs(folder_path, exist_ok=True)
                st.session_state.mode = "local"
                st.session_state.drive_manager = LocalFolderManager(folder_path)
                reload_data()
                st.rerun()
        with col_loc2:
            if st.button("Create Test Folder", use_container_width=True):
                os.makedirs(default_folder, exist_ok=True)
                f1 = os.path.join(default_folder, "Cloud_Notes_Lecture.txt")
                f2 = os.path.join(default_folder, "Cloud_Notes_Lecture_DUPLICATE.txt")
                f3 = os.path.join(default_folder, "interrupted_download.tmp")
                content = b"Cloud Computing Storage Optimizer SHA-256 Duplicate Demonstration."
                with open(f1, "wb") as f:
                    f.write(content)
                with open(f2, "wb") as f:
                    f.write(content)
                with open(f3, "wb") as f:
                    f.write(b"Temporary residual cache file")
                st.session_state.mode = "local"
                st.session_state.drive_manager = LocalFolderManager(default_folder)
                reload_data()
                st.rerun()

        st.caption("💡 Scans real files on your disk. Calculates genuine SHA-256 hashes without needing Google Cloud credentials or billing!")

    else:
        # Live Google Drive Mode
        if st.session_state.mode != "live":
            st.session_state.mode = "live"
            st.session_state.drive_manager = GoogleDriveManager()
            st.session_state.files_cache = None
            st.rerun()

        st.markdown("#### 🔑 Google Drive OAuth 2.0")
        st.caption("ℹ️ *Note: If Google Cloud prompts for a credit card, you accidentally clicked 'Free Trial'. Regular API projects for Drive do NOT require billing! See Tab 7 for the bypass guide.*")
        uploaded_cred = st.file_uploader("Upload `credentials.json`", type=["json"])
        if uploaded_cred:
            with open("credentials.json", "wb") as f:
                f.write(uploaded_cred.getbuffer())
            st.success("Uploaded `credentials.json` successfully!")

        col_c1, col_c2 = st.columns(2)
        with col_c1:
            if st.button("Connect Drive", type="primary", use_container_width=True):
                ok, msg = st.session_state.drive_manager.authenticate()
                if ok:
                    st.success(msg)
                    reload_data()
                    st.rerun()
                else:
                    st.error(msg)
        with col_c2:
            if st.button("Reset Token", use_container_width=True):
                if os.path.exists("token.json"):
                    os.remove("token.json")
                st.info("Reset token. Please reconnect.")

    st.markdown("---")
    st.subheader("⚙️ Analysis Thresholds")
    large_mb = st.slider("Large File Threshold (MB):", min_value=10, max_value=1000, value=50, step=10)
    stale_days = st.slider("Inactive File Age (Days):", min_value=30, max_value=730, value=180, step=30)

    st.markdown("---")
    if st.button("🔄 Re-Scan Storage", use_container_width=True):
        reload_data()
        st.toast("Storage re-scanned successfully!", icon="✅")
        st.rerun()

    st.caption("🔒 **Security**: SHA-256 hashing and file deduplication run client-side. No private file data is uploaded to 3rd-party servers.")


# ----------------- DATA PREPARATION -----------------
df = st.session_state.files_cache
quota = st.session_state.quota_cache or {"limit": 15 * 1024**3, "usage": 0}

total_files = len(df)
used_bytes = quota.get("usage", df["size"].sum() if not df.empty else 0)
limit_bytes = quota.get("limit", 15 * 1024**3)
trash_bytes = quota.get("usageInDriveTrash", 0)

# Deduplication via SHA-256
duplicates_df, reclaimable_dupe_bytes = detect_duplicates_by_sha256(df)
large_df = audit_large_files(df, threshold_mb=large_mb)
old_df = audit_inactive_files(df, days_threshold=stale_days)
clutter_df = audit_empty_and_temp_files(df)
clutter_bytes = clutter_df["size"].sum() if not clutter_df.empty else 0

# Total savings
total_savings_bytes = reclaimable_dupe_bytes + trash_bytes + clutter_bytes
health = calculate_storage_health(
    total_used_bytes=used_bytes,
    total_quota_bytes=limit_bytes,
    duplicate_bytes=reclaimable_dupe_bytes,
    old_files_bytes=old_df["size"].sum() if not old_df.empty else 0,
)
cost_info = calculate_cost_savings(total_savings_bytes)

used_gb = used_bytes / (1024**3)
limit_gb = limit_bytes / (1024**3) if limit_bytes > 0 else 15.0
usage_pct = min(100.0, (used_gb / limit_gb) * 100) if limit_gb > 0 else 0


# ----------------- MAIN DASHBOARD -----------------
st.title("🚀 Cloud Storage Space Optimizer")
st.markdown("Automated cloud storage analyzer and duplicate detector powered by **Python**, **Streamlit**, and **SHA-256 Hashing**.")

# Cloud Storage Quota Bar
col_bar1, col_bar2 = st.columns([4, 1])
with col_bar1:
    st.progress(usage_pct / 100.0)
with col_bar2:
    st.markdown(f"**{used_gb:.2f} GB** / {limit_gb:.1f} GB ({usage_pct:.1f}%)")

if usage_pct > 80:
    st.warning(f"⚠️ **Storage Capacity Warning**: You are utilizing {usage_pct:.1f}% of your cloud quota. You have {format_bytes(total_savings_bytes)} in reclaimable duplicates, clutter, and trash.")

# 5 Top Metrics
m1, m2, m3, m4, m5 = st.columns(5)
with m1:
    st.markdown(
        f"""
        <div class="metric-box">
            <div class="metric-sub">Total Files</div>
            <div class="metric-num">{total_files:,}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with m2:
    st.markdown(
        f"""
        <div class="metric-box">
            <div class="metric-sub">Storage Used</div>
            <div class="metric-num">{format_bytes(used_bytes)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with m3:
    st.markdown(
        f"""
        <div class="metric-box">
            <div class="metric-sub">Reclaimable Savings</div>
            <div class="metric-num" style="color: #16a34a;">{format_bytes(total_savings_bytes)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with m4:
    redundant_count = len(duplicates_df[duplicates_df["is_redundant"]]) if not duplicates_df.empty else 0
    st.markdown(
        f"""
        <div class="metric-box">
            <div class="metric-sub">Duplicate Copies</div>
            <div class="metric-num" style="color: #dc2626;">{redundant_count}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with m5:
    badge_style = f"badge-{health['rating'].lower()}"
    st.markdown(
        f"""
        <div class="metric-box">
            <div class="metric-sub">Drive Health</div>
            <div class="metric-num">{health['score']}/100 <span class="{badge_style}" style="font-size: 0.8rem; vertical-align: middle;">{health['rating']}</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown("<br>", unsafe_allow_html=True)


# ----------------- TABS -----------------
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "📊 Storage Analytics & Explorer",
    "👯 SHA-256 Duplicate Finder",
    "🐘 Large File Scanner",
    "👻 Ghost & Clutter Cleaner",
    "🧪 Live SHA-256 Testing Lab",
    "🧹 Reclaim & Cost Savings ROI",
    "📘 Setup & Architecture",
])


# ================= TAB 1: CHARTS & EXPLORER =================
with tab1:
    st.subheader("📈 Cloud Storage Distribution & Analytics")

    if df.empty:
        st.info("No files found to analyze.")
    else:
        c_chart1, c_chart2 = st.columns(2)

        # 1. Donut Chart - Storage by Category
        with c_chart1:
            cat_summary = df.groupby("category")["size"].sum().reset_index()
            cat_summary["formatted_size"] = cat_summary["size"].apply(format_bytes)

            fig_donut = px.pie(
                cat_summary,
                values="size",
                names="category",
                hole=0.45,
                title="Storage Consumption by File Category",
                color_discrete_sequence=px.colors.qualitative.Bold,
            )
            fig_donut.update_traces(
                textposition="inside",
                textinfo="percent+label",
                hovertemplate="<b>%{label}</b><br>Total: %{customdata[0]}<br>Share: %{percent}",
                customdata=cat_summary[["formatted_size"]],
            )
            fig_donut.update_layout(margin=dict(t=40, b=10, l=10, r=10), showlegend=True)
            st.plotly_chart(fig_donut, use_container_width=True)

        # 2. Bar Chart - File Size Brackets
        with c_chart2:
            def get_bracket(s):
                mb = s / (1024 * 1024)
                if mb < 1:
                    return "< 1 MB"
                elif mb < 10:
                    return "1 - 10 MB"
                elif mb < 50:
                    return "10 - 50 MB"
                elif mb < 200:
                    return "50 - 200 MB"
                elif mb < 1000:
                    return "200 MB - 1 GB"
                else:
                    return "> 1 GB"

            df["size_bracket"] = df["size"].apply(get_bracket)
            bracket_order = ["< 1 MB", "1 - 10 MB", "10 - 50 MB", "50 - 200 MB", "200 MB - 1 GB", "> 1 GB"]
            bracket_df = df.groupby("size_bracket").agg(
                file_count=("id", "count"),
                total_bytes=("size", "sum")
            ).reindex(bracket_order).fillna(0).reset_index()
            bracket_df["formatted_size"] = bracket_df["total_bytes"].apply(format_bytes)

            fig_bar = px.bar(
                bracket_df,
                x="size_bracket",
                y="total_bytes",
                title="Storage Volume by File Size Range",
                labels={"size_bracket": "Size Bracket", "total_bytes": "Total Bytes"},
                color="total_bytes",
                color_continuous_scale="Purp",
            )
            fig_bar.update_traces(
                hovertemplate="<b>%{x}</b><br>Size: %{customdata[0]}",
                customdata=bracket_df[["formatted_size"]],
            )
            fig_bar.update_layout(margin=dict(t=40, b=10, l=10, r=10), coloraxis_showscale=False)
            st.plotly_chart(fig_bar, use_container_width=True)

        # Interactive File Explorer & Search
        st.markdown("---")
        st.subheader("🔍 Interactive Storage Explorer & Search")

        col_f1, col_f2 = st.columns([3, 2])
        with col_f1:
            search_query = st.text_input("Search files by Name or SHA-256 Hash:", placeholder="e.g. .mp4, dataset, or hash substring...")
        with col_f2:
            cat_filter = st.selectbox("Filter by Category:", ["All Categories"] + sorted(df["category"].unique().tolist()))

        filtered_df = df.copy()
        if search_query:
            q = search_query.lower()
            filtered_df = filtered_df[
                filtered_df["name"].str.lower().str.contains(q, na=False) |
                filtered_df["sha256"].str.lower().str.contains(q, na=False)
            ]
        if cat_filter != "All Categories":
            filtered_df = filtered_df[filtered_df["category"] == cat_filter]

        st.markdown(f"**Found {len(filtered_df)} matching files ({format_bytes(filtered_df['size'].sum())}):**")
        st.dataframe(
            filtered_df[["name", "category", "formatted_size", "age_days", "webViewLink"]].rename(
                columns={
                    "name": "File Name",
                    "category": "Category",
                    "formatted_size": "Size",
                    "age_days": "Age (Days)",
                    "webViewLink": "Online Link",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )


# ================= TAB 2: SHA-256 DUPLICATE FINDER =================
with tab2:
    st.subheader("👯 SHA-256 Cryptographic Duplicate Detection")
    st.markdown(
        """
        Duplicate files are identified by computing exact **256-bit SHA-256 cryptographic hashes**.
        Even if two files have different names or folders, identical SHA-256 hashes guarantee 100% matching binary contents.
        """
    )

    if duplicates_df.empty:
        st.success("🎉 No duplicate files found! All files in your storage are unique.")
    else:
        num_groups = len(duplicates_df["duplicate_group_id"].unique())
        redundant_rows = duplicates_df[duplicates_df["is_redundant"]]

        st.info(
            f"🔍 Detected **{num_groups} Duplicate Groups** with **{len(redundant_rows)} Redundant Copies**. "
            f"Safely removing redundant copies will free up **{format_bytes(reclaimable_dupe_bytes)}** of cloud storage!"
        )

        # Side-by-side comparison inspector
        st.markdown("#### 🔬 Side-by-Side Duplicate Inspector")
        group_options = sorted(duplicates_df["duplicate_group_id"].unique())
        selected_grp = st.selectbox("Select Duplicate Group to Compare:", group_options)

        grp_files = duplicates_df[duplicates_df["duplicate_group_id"] == selected_grp]
        orig_file = grp_files[~grp_files["is_redundant"]].iloc[0]
        dupe_copies = grp_files[grp_files["is_redundant"]]

        col_cmp1, col_cmp2 = st.columns(2)
        with col_cmp1:
            st.success(f"🟢 **Original File (Keep)**\n\n"
                       f"**Name**: `{orig_file['name']}`\n\n"
                       f"**Size**: `{orig_file['formatted_size']}`\n\n"
                       f"**Age**: `{orig_file['age_days']} days old`\n\n"
                       f"**SHA-256**: `{orig_file['sha256']}`")

        with col_cmp2:
            st.error(f"🔴 **Redundant Copies ({len(dupe_copies)} copies to purge)**\n\n" +
                     "\n\n".join([f"- **Name**: `{r['name']}` ({r['formatted_size']}, {r['age_days']}d old)" for _, r in dupe_copies.iterrows()]) +
                     f"\n\n**SHA-256**: `{orig_file['sha256']}` *(Exact Match)*")

        st.markdown("---")

        # Display full duplicates table
        disp_cols = ["duplicate_group_id", "status", "name", "formatted_size", "category", "short_sha256", "age_days", "id"]
        dupe_display = duplicates_df[disp_cols].rename(
            columns={
                "duplicate_group_id": "Group",
                "status": "Recommended Action",
                "name": "File Name",
                "formatted_size": "Size",
                "category": "Category",
                "short_sha256": "SHA-256 Hash",
                "age_days": "Days Old",
                "id": "File ID",
            }
        )

        st.dataframe(
            dupe_display.style.apply(
                lambda row: ["background-color: #fee2e2" if "Redundant" in str(row["Recommended Action"]) else "background-color: #dcfce7" for _ in row],
                axis=1
            ),
            use_container_width=True,
            hide_index=True,
        )

        col_act1, col_act2 = st.columns(2)
        with col_act1:
            csv_buf = io.StringIO()
            redundant_rows[["id", "name", "size", "sha256", "createdTime"]].to_csv(csv_buf, index=False)
            st.download_button(
                label="📥 Export Duplicate Cleanup Plan (CSV)",
                data=csv_buf.getvalue(),
                file_name=f"cloud_duplicates_sha256_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with col_act2:
            if st.button("🗑️ Move Redundant Duplicates to Trash", type="primary", use_container_width=True):
                freed = 0
                for _, r in redundant_rows.iterrows():
                    ok, _ = st.session_state.drive_manager.move_to_trash(r["id"])
                    if ok:
                        freed += 1
                st.success(f"Moved {freed} redundant copies to Trash! Space reclaimed: {format_bytes(reclaimable_dupe_bytes)}.")
                reload_data()
                st.rerun()


# ================= TAB 3: LARGE FILE SCANNER =================
with tab3:
    st.subheader(f"🐘 Large File Scanner (> {large_mb} MB)")
    st.markdown("Isolate and review space-consuming videos, archives, and system images.")

    if large_df.empty:
        st.success(f"No files larger than {large_mb} MB found.")
    else:
        large_bytes = large_df["size"].sum()
        pct_share = (large_bytes / used_bytes * 100) if used_bytes > 0 else 0
        st.warning(f"**{len(large_df)} large files** account for **{format_bytes(large_bytes)}** ({pct_share:.1f}% of your storage).")

        st.dataframe(
            large_df[["name", "category", "formatted_size", "storage_share_pct", "age_days", "id"]].rename(
                columns={
                    "name": "File Name",
                    "category": "Category",
                    "formatted_size": "Size",
                    "storage_share_pct": "% of Drive",
                    "age_days": "Days Old",
                    "id": "Cloud File ID",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

        sel_id = st.selectbox(
            "Select a large file to trash:",
            options=large_df["id"].tolist(),
            format_func=lambda x: f"{large_df[large_df['id'] == x]['name'].values[0]} ({large_df[large_df['id'] == x]['formatted_size'].values[0]})",
        )
        if st.button("🗑️ Move Selected File to Trash"):
            ok, msg = st.session_state.drive_manager.move_to_trash(sel_id)
            if ok:
                st.success("File moved to Trash!")
                reload_data()
                st.rerun()
            else:
                st.error(msg)


# ================= TAB 4: GHOST & CLUTTER CLEANER =================
with tab4:
    st.subheader("👻 Ghost & Clutter Files Audit")
    st.markdown(
        """
        Cloud drives frequently accumulate **0-byte ghost files** (aborted uploads, empty placeholders) 
        and **temporary clutter** (`.tmp`, `.log`, `.bak`, `.crdownload`, lock files) that waste sync bandwidth and metadata quotas.
        """
    )

    if clutter_df.empty:
        st.success("✨ No ghost or temporary clutter files detected. Your drive is neat!")
    else:
        st.warning(f"Found **{len(clutter_df)} ghost / clutter files** taking up **{format_bytes(clutter_bytes)}**.")

        st.dataframe(
            clutter_df[["name", "clutter_reason", "formatted_size", "age_days", "id"]].rename(
                columns={
                    "name": "File Name",
                    "clutter_reason": "Clutter Category",
                    "formatted_size": "Size",
                    "age_days": "Age (Days)",
                    "id": "File ID",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

        if st.button("🧹 Purge All Ghost & Clutter Files", type="primary", use_container_width=True):
            purged = 0
            for _, r in clutter_df.iterrows():
                ok, _ = st.session_state.drive_manager.move_to_trash(r["id"])
                if ok:
                    purged += 1
            st.success(f"Purged {purged} ghost/clutter files to trash!")
            reload_data()
            st.rerun()


# ================= TAB 5: LIVE SHA-256 TESTING LAB =================
with tab5:
    st.subheader("🧪 Live SHA-256 File Analysis & Duplicate Demonstration Lab")
    st.markdown(
        """
        Test the file analysis engine hands-on!
        Upload any files from your computer or click **'Generate Test Files'** to create real sample files on disk.
        The system will calculate exact byte sizes and compute cryptographic SHA-256 hashes to detect duplicates live.
        """
    )

    col_lab1, col_lab2 = st.columns(2)

    with col_lab1:
        st.markdown("#### 📁 Option A: Upload Files to Analyze")
        user_uploads = st.file_uploader(
            "Upload 2 or more files (e.g. try uploading identical photos or copies with different names):",
            accept_multiple_files=True,
        )

        if user_uploads:
            records = []
            for uploaded in user_uploads:
                content = uploaded.getvalue()
                h = compute_sha256(content)
                file_id = getattr(uploaded, "file_id", getattr(uploaded, "id", uploaded.name))
                mime = getattr(uploaded, "type", "application/octet-stream") or "application/octet-stream"
                records.append({
                    "id": file_id,
                    "name": uploaded.name,
                    "size": len(content),
                    "mimeType": mime,
                    "sha256": h,
                    "createdTime": datetime.now(timezone.utc).isoformat(),
                    "modifiedTime": datetime.now(timezone.utc).isoformat(),
                    "webViewLink": "Uploaded via Web",
                })

            lab_df = process_files_dataframe(records)
            st.markdown(f"**Analyzed {len(lab_df)} uploaded files:**")

            lab_dupes, lab_reclaimable = detect_duplicates_by_sha256(lab_df)

            if not lab_dupes.empty:
                st.error(f"🎯 **Duplicate Detected!** SHA-256 matched identical content across files. Potential space saved: **{format_bytes(lab_reclaimable)}**.")
                st.dataframe(
                    lab_dupes[["duplicate_group_id", "status", "name", "formatted_size", "sha256"]].rename(
                        columns={
                            "duplicate_group_id": "Group",
                            "status": "Action",
                            "name": "Filename",
                            "formatted_size": "Size",
                            "sha256": "Calculated SHA-256 Hash",
                        }
                    ),
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.success("✅ All uploaded files have distinct SHA-256 hashes. No duplicates found.")
                st.dataframe(
                    lab_df[["name", "formatted_size", "sha256"]].rename(
                        columns={"name": "File", "formatted_size": "Size", "sha256": "SHA-256 Hash"}
                    ),
                    use_container_width=True,
                    hide_index=True,
                )

    with col_lab2:
        st.markdown("#### 🛠️ Option B: Auto-Generate Physical Sample Files on Disk")
        st.markdown("Generates real sample files in `./sample_files/` with deliberate duplicates to test SHA-256 verification.")

        sample_dir = os.path.join(os.getcwd(), "sample_files")

        if st.button("🚀 Generate & Scan Physical Sample Files", use_container_width=True):
            os.makedirs(sample_dir, exist_ok=True)

            test_cases = [
                ("Cloud_Lecture_Notes_Unit1.txt", b"Cloud computing provides on-demand data storage and computing power without direct active management by the user."),
                ("Cloud_Lecture_Notes_Unit1_COPY.txt", b"Cloud computing provides on-demand data storage and computing power without direct active management by the user."),
                ("Project_Architecture_Diagram.csv", b"Service,Cost,Region\nEC2,45.0,us-east-1\nS3,12.5,us-east-1\nRDS,60.0,us-east-1"),
                ("Project_Architecture_Diagram_BACKUP.csv", b"Service,Cost,Region\nEC2,45.0,us-east-1\nS3,12.5,us-east-1\nRDS,60.0,us-east-1"),
                ("Unique_Student_Assignment.txt", b"Student Name: John Doe\nStudent ID: CS-2024-998\nAssignment: Space Optimization"),
            ]

            disk_records = []
            for fname, content in test_cases:
                fpath = os.path.join(sample_dir, fname)
                with open(fpath, "wb") as f:
                    f.write(content)

                h = compute_sha256(fpath)
                fsize = os.path.getsize(fpath)
                disk_records.append({
                    "id": fname,
                    "name": fname,
                    "size": fsize,
                    "mimeType": "text/plain" if fname.endswith(".txt") else "text/csv",
                    "sha256": h,
                    "createdTime": datetime.now(timezone.utc).isoformat(),
                    "modifiedTime": datetime.now(timezone.utc).isoformat(),
                    "webViewLink": fpath,
                })

            disk_df = process_files_dataframe(disk_records)
            d_dupes, d_reclaimable = detect_duplicates_by_sha256(disk_df)

            st.success(f"Generated 5 sample files on disk in `{sample_dir}`!")
            st.info(f"SHA-256 analysis identified **{len(d_dupes['duplicate_group_id'].unique())} duplicate groups**!")

            st.dataframe(
                d_dupes[["duplicate_group_id", "status", "name", "formatted_size", "sha256"]].rename(
                    columns={
                        "duplicate_group_id": "Group",
                        "status": "Recommended Action",
                        "name": "File on Disk",
                        "formatted_size": "Size",
                        "sha256": "Computed SHA-256 Hash",
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )


# ================= TAB 6: RECLAIM & COST SAVINGS ROI =================
with tab6:
    st.subheader("🧹 Storage Reclaiming & Financial ROI Calculator")
    st.markdown("Quantify your cloud storage savings and see how much money optimization saves.")

    col_res1, col_res2 = st.columns([3, 2])

    with col_res1:
        st.markdown("#### 🎯 Space Recovery Breakdown")

        current_used_gb = used_bytes / (1024**3)
        optimized_used_gb = max(0, (used_bytes - total_savings_bytes) / (1024**3))
        savings_gb = total_savings_bytes / (1024**3)

        comp_df = pd.DataFrame({
            "State": ["Current Usage", "After Optimization"],
            "Used Storage (GB)": [round(current_used_gb, 2), round(optimized_used_gb, 2)],
        })

        fig_comp = px.bar(
            comp_df,
            x="State",
            y="Used Storage (GB)",
            text="Used Storage (GB)",
            color="State",
            color_discrete_map={"Current Usage": "#ef4444", "After Optimization": "#10b981"},
            title="Drive Storage Comparison: Current vs After Optimization",
        )
        fig_comp.update_traces(texttemplate="%{text} GB", textposition="outside")
        fig_comp.update_layout(yaxis_range=[0, limit_gb + 1], showlegend=False, margin=dict(t=40, b=10, l=10, r=10))
        st.plotly_chart(fig_comp, use_container_width=True)

        st.markdown(
            f"""
            **Optimization Impact Breakdown**:
            - 🔹 Reclaimable Duplicate Files: **+{format_bytes(reclaimable_dupe_bytes)}**
            - 🔹 Reclaimable Drive Trash: **+{format_bytes(trash_bytes)}**
            - 🔹 Reclaimable Ghost & Clutter: **+{format_bytes(clutter_bytes)}**
            - 🚀 **Total Space Saved**: **{format_bytes(total_savings_bytes)}** ({savings_gb:.2f} GB freed up!)
            """
        )

        # Financial ROI Calculator
        st.markdown("---")
        st.markdown("#### 💰 Cloud Cost Savings Calculator")
        currency = st.radio("Display Currency:", ["USD ($)", "INR (₹)"], horizontal=True)

        if "USD" in currency:
            st.metric("Estimated Monthly Savings", f"${cost_info['monthly_usd']}")
            st.metric("Estimated Annual Savings", f"${cost_info['annual_usd']}")
        else:
            st.metric("Estimated Monthly Savings", f"₹{cost_info['monthly_inr']}")
            st.metric("Estimated Annual Savings", f"₹{cost_info['annual_inr']}")

        st.success(f"💡 **Upgrade Avoided**: Optimizing your drive prevents having to purchase a **{cost_info['tier_avoided']}**!")

    with col_res2:
        st.markdown("#### ⚡ 1-Click Optimization Actions")

        if st.button("🗑️ Empty Google Drive Trash Bin", use_container_width=True):
            ok, msg = st.session_state.drive_manager.empty_trash()
            if ok:
                st.success(msg)
                reload_data()
                st.rerun()
            else:
                st.error(msg)

        st.markdown("<br>", unsafe_allow_html=True)

        # Full audit download
        full_report_buf = io.StringIO()
        df.to_csv(full_report_buf, index=False)
        st.download_button(
            label="📄 Download Complete Drive Audit (CSV)",
            data=full_report_buf.getvalue(),
            file_name=f"cloud_storage_audit_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
            use_container_width=True,
        )


# ================= TAB 7: SETUP & ARCHITECTURE =================
with tab7:
    st.subheader("📘 Cloud Architecture & Google Drive API Integration")
    st.markdown(
        """
        ### 🏛️ System Architecture
        ```
        +-------------------------------------------------------------+
        |                 Streamlit Frontend (app.py)                 |
        |  - Storage Analytics  - Interactive Plotly Charts           |
        |  - Duplicate Viewer   - Reclaimable Space Calculator        |
        |  - Clutter Purger     - Cost Savings ROI Engine             |
        +------------------------------+------------------------------+
                                       |
                     +-----------------+-----------------+
                     |                                   |
                     v                                   v
        +--------------------------+        +--------------------------+
        |       optimizer.py       |        |     drive_service.py     |
        |  - SHA-256 Hash Engine   |        |  - OAuth 2.0 Auth Flow   |
        |  - Deduplication Logic   |        |  - Drive API v3 Client   |
        |  - Clutter Detection     |        |  - Mock Cloud Simulator  |
        |  - Cost Savings Engine   |        |  - Local Folder Scanner  |
        +--------------------------+        +-------------+------------+
                                                          |
                                                          v
                                            +--------------------------+
                                            |   Google Drive REST API  |
                                            |  (Live Cloud Metadata)   |
                                            +--------------------------+
        ```

        ### 💳 Google Cloud Console Asking for Payment? Here is Why & How to Avoid It:
        > **You do NOT need a credit card or payment to use this project!**

        #### 🌟 Option 1: Use the Built-in Modes (Zero Setup, Zero Payment)
        - **Simulated Cloud Mode**: Already active in this app with 35+ realistic files, charts, duplicates, and Google Drive links. Perfect for lab demonstrations and project submissions.
        - **Local Synced Cloud Folder**: Switch to this mode in the sidebar to scan any folder on your computer (like Google Drive for Desktop, OneDrive, or test files) with real SHA-256 duplicate detection without any API keys.

        #### 💡 Option 2: How to create a Google Cloud Project WITHOUT Payment
        Google Cloud asks for a credit card if you accidentally click the **"$300 Free Trial"** banner. You do **NOT** need the free trial for the Google Drive API!
        1. Open [console.cloud.google.com/projectcreate](https://console.cloud.google.com/projectcreate) directly while signed into your Gmail.
        2. Enter a project name (e.g. `Storage-Optimizer`) and click **Create** (do NOT click "Try for Free" or "Activate Billing").
        3. Go to [console.cloud.google.com/apis/library/drive.googleapis.com](https://console.cloud.google.com/apis/library/drive.googleapis.com) and click **Enable**.
        4. Go to **APIs & Services > OAuth consent screen**:
           - Choose **External** and fill in your app name and email.
           - Under **Test Users**, add your personal Gmail address.
        5. Go to **APIs & Services > Credentials > Create Credentials > OAuth client ID**:
           - Application type: **Desktop App**.
           - Download the resulting JSON file as `credentials.json` and upload it to the app sidebar.
        """
    )
