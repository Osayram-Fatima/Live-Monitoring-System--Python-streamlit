import streamlit as st
import psutil
import plotly.graph_objects as go
from collections import deque
import time
from datetime import datetime
import platform
import pandas as pd
from io import StringIO


st.set_page_config(
    page_title="Live System Monitor",
    layout="wide",
     
)
st.title("Live System Monitor")
st.caption(
    f" Host: {platform.node()} | OS: {platform.system()} {platform.release()}"
)


st.markdown(
    """
<style>
.metric-container { 
    padding: 0.9rem; 
    border-radius: 14px; 
    margin: 0.4rem 0; 
    background: linear-gradient(135deg, #111827 0%, #1f2937 40%, #0f766e 100%);
    border: 1px solid rgba(148, 163, 184, 0.6);
    box-shadow: 0 12px 25px rgba(15, 23, 42, 0.7);
}
.metric-container [data-testid="stMetric"] label {
    color: #e5e7eb;
}
.metric-container [data-testid="stMetric"] div {
    color: #f9fafb;
}
</style>
""",
    unsafe_allow_html=True,
)


# ---------- Helpers / session state ----------
@st.cache_resource
def init_live_data():
    return {
        "cpu_data": deque(maxlen=200),
        "cpu_cores": [],
        "ram_data": deque(maxlen=200),
        "disk_data": deque(maxlen=200),
        "net_delta_in": deque(maxlen=200),
        "net_delta_out": deque(maxlen=200),
        "timestamps": deque(maxlen=200),
        "last_net": None,
        "frame_count": 0,
        "start_time": datetime.now(),
        "alerts": deque(maxlen=50),
    }


def metric_card(label: str, value: str, emoji: str = "") -> None:
    """Render a metric inside the gradient card."""
    st.markdown('<div class="metric-container">', unsafe_allow_html=True)
    title = f"{emoji} {label}" if emoji else label
    st.metric(title, value)
    st.markdown("</div>", unsafe_allow_html=True)


def build_last_5min_csv(live_data):
    if not live_data["timestamps"]:
        return None

    now = datetime.now()
    rows = []

    for i in range(len(live_data["timestamps"])):
        ts = live_data["timestamps"][i]
        if (now - ts).total_seconds() <= 300:  # 5 minutes
            rows.append(
                {
                    "Timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
                    "CPU (%)": live_data["cpu_data"][i],
                    "RAM (%)": live_data["ram_data"][i],
                    "Disk (%)": live_data["disk_data"][i],
                    "Net In (KB/s)": live_data["net_delta_in"][i],
                    "Net Out (KB/s)": live_data["net_delta_out"][i],
                }
            )

    if not rows:
        return None

    df = pd.DataFrame(rows)
    csv_buffer = StringIO()
    df.to_csv(csv_buffer, index=False)
    return csv_buffer.getvalue()


def log_alert(level, message):
    st.session_state.live_data["alerts"].appendleft(
        {
            "time": datetime.now().strftime("%H:%M:%S"),
            "level": level,
            "message": message,
        }
    )


if "live_data" not in st.session_state:
    st.session_state.live_data = init_live_data()

live_data = st.session_state.live_data


st.sidebar.header("Live Controls")
refresh_rate = st.sidebar.slider("Update Speed (sec)", 1.0, 5.0, 2.0, 0.5)
max_points = st.sidebar.slider("History Points", 50, 500, 200, 50)
pause = st.sidebar.toggle("Pause Live Updates", False)
st.sidebar.markdown("---")
st.sidebar.subheader("Process Monitor")

show_processes = st.sidebar.toggle("Show Process Table", True)
proc_sort_by = st.sidebar.selectbox("Sort Processes By", ["CPU %", "RAM %"])
proc_limit = st.sidebar.selectbox("Top Processes", [5, 10, 15], index=1)

for key in [
    "cpu_data",
    "ram_data",
    "disk_data",
    "net_delta_in",
    "net_delta_out",
    "timestamps",
]:
    live_data[key] = deque(live_data[key], maxlen=max_points)


if not pause:
    cpu = psutil.cpu_percent(interval=None)
    core_cpu = psutil.cpu_percent(percpu=True)

    ram = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    net_counters = psutil.net_io_counters()


    net_delta_in = net_delta_out = 0
    if live_data["last_net"] is not None:
        net_delta_in = (
            net_counters.bytes_recv - live_data["last_net"].bytes_recv
        ) / 1024
        net_delta_out = (
            net_counters.bytes_sent - live_data["last_net"].bytes_sent
        ) / 1024
    live_data["last_net"] = net_counters

    now = datetime.now()
    live_data["cpu_data"].append(cpu)
    live_data["cpu_cores"].append(core_cpu)
    live_data["ram_data"].append(ram.percent)
    live_data["disk_data"].append(disk.percent)
    live_data["net_delta_in"].append(net_delta_in)
    live_data["net_delta_out"].append(net_delta_out)
    live_data["timestamps"].append(now)
    live_data["frame_count"] += 1
else:

    if live_data["cpu_data"]:
        cpu = live_data["cpu_data"][-1]
    else:
        cpu = psutil.cpu_percent(interval=None)

    ram = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    if live_data["net_delta_in"]:
        net_delta_in = live_data["net_delta_in"][-1]
        net_delta_out = live_data["net_delta_out"][-1]
    else:
        net_delta_in = net_delta_out = 0



col1, col2, col3, col4 = st.columns(4)

with col1:
    metric_card("CPU", f"{cpu:.1f}%", "🧠")
with col2:
    metric_card("RAM", f"{ram.percent:.1f}%", "💾")
with col3:
    metric_card("Disk", f"{disk.percent:.1f}%", "💿")
with col4:
    metric_card(
        "Network",
        f"↓ {net_delta_in:.0f} KB/s | ↑ {net_delta_out:.0f} KB/s",
        "🌐",
    )


st.subheader("🔋 Battery")

battery = None
try:
    battery = psutil.sensors_battery()
except (AttributeError, NotImplementedError):
    battery = None

colt1 = st.columns(1)

with colt1[0]:
    if battery is not None:
        level = battery.percent
        status = "Charging" if battery.power_plugged else "On battery"
        metric_card("Battery", f"{level:.0f}%", "🔋")
        if battery.secsleft not in (
            psutil.POWER_TIME_UNLIMITED,
            psutil.POWER_TIME_UNKNOWN,
        ):
            hours = battery.secsleft // 3600
            mins = (battery.secsleft % 3600) // 60
            st.caption(f"{status} · ~{hours}h {mins}m remaining")
        else:
            st.caption(status)
    else:
        st.info("Battery information not available.")



if cpu > 90:
    st.error("🚨 CPU CRITICAL!")
    log_alert("CRITICAL", f"CPU usage reached {cpu:.1f}%")
elif cpu > 80:
    st.warning("⚠️ High CPU Load")
    log_alert("WARNING", f"CPU usage high at {cpu:.1f}%")

if ram.percent > 90:
    st.error("🚨 RAM CRITICAL!")
    log_alert("CRITICAL", f"RAM usage reached {ram.percent:.1f}%")
elif ram.percent > 80:
    st.warning("⚠️ High RAM Usage")
    log_alert("WARNING", f"RAM usage high at {ram.percent:.1f}%")


st.subheader("📈 Live Trends")

if len(live_data["timestamps"]) > 1:
    t0 = live_data["timestamps"][0]
    time_axis = [(t - t0).total_seconds() for t in live_data["timestamps"]]
else:
    time_axis = [0]

fig1 = go.Figure()
fig1.add_trace(
    go.Scatter(
        x=time_axis,
        y=list(live_data["cpu_data"]),
        name="CPU",
        line=dict(color="#ff4444", width=3),
        mode="lines",
        fill="tonexty",
        fillcolor="rgba(255,68,68,0.15)",
    )
)
fig1.add_trace(
    go.Scatter(
        x=time_axis,
        y=list(live_data["ram_data"]),
        name="RAM",
        line=dict(color="#00bfff", width=3),
        mode="lines",
        fill="tonexty",
        fillcolor="rgba(0,191,255,0.15)",
    )
)
fig1.add_trace(
    go.Scatter(
        x=time_axis,
        y=list(live_data["disk_data"]),
        name="Disk",
        line=dict(color="#32cd32", width=2),
        mode="lines",
    )
)
fig1.update_layout(
    title="🖥️ CPU / RAM / Disk Usage Over Time",
    height=400,
    showlegend=True,
    xaxis_title="Time (seconds)",
    yaxis=dict(range=[0, 100], title="Usage %"),
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    hovermode="x unified",
    margin=dict(l=40, r=20, t=60, b=40),
    transition={"duration": 0},
    uirevision="static",
)
st.plotly_chart(fig1, use_container_width=True)

fig2 = go.Figure()
fig2.add_trace(
    go.Scatter(
        x=time_axis,
        y=list(live_data["net_delta_in"]),
        name="Download (KB/s)",
        line=dict(color="#00c853", width=3),
        mode="lines",
        fill="tonexty",
        fillcolor="rgba(0,200,83,0.15)",
    )
)
fig2.add_trace(
    go.Scatter(
        x=time_axis,
        y=list(live_data["net_delta_out"]),
        name="Upload (KB/s)",
        line=dict(color="#ff8c00", width=3),
        mode="lines",
        fill="tonexty",
        fillcolor="rgba(255,140,0,0.15)",
    )
)
fig2.update_layout(
    title="🌐 Network Throughput (Download vs Upload)",
    height=350,
    showlegend=True,
    xaxis_title="Time (seconds)",
    yaxis_title="KB/s",
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    hovermode="x unified",
    margin=dict(l=40, r=20, t=60, b=40),
    transition={"duration": 0},
    uirevision="static",
)
st.plotly_chart(fig2, use_container_width=True)


st.subheader("🧠 CPU Core Usage (Hottest Highlighted)")

fig_core = go.Figure()
hottest_core = None

if live_data["cpu_cores"]:
    core_count = len(live_data["cpu_cores"][0])

    avg_usage = [
        sum(frame[i] for frame in live_data["cpu_cores"]) / len(live_data["cpu_cores"])
        for i in range(core_count)
    ]
    hottest_core = int(max(range(core_count), key=lambda i: avg_usage[i]))

    for i in range(core_count):
        is_hot = i == hottest_core
        fig_core.add_trace(
            go.Scatter(
                x=time_axis,
                y=[frame[i] for frame in live_data["cpu_cores"]],
                mode="lines",
                name=f"Core {i}",
                line=dict(
                    width=4 if is_hot else 1.5,
                    color="#ff4444" if is_hot else "rgba(148,163,184,0.6)",  # bright red vs soft gray
                ),
            )
        )

fig_core.update_layout(
    height=360,
    xaxis_title="Time (seconds)",
    yaxis_title="CPU %",
    yaxis=dict(range=[0, 100]),
    hovermode="x unified",
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
)
st.plotly_chart(fig_core, use_container_width=True)

if hottest_core is not None:
    st.caption(f"🔥 Hottest core (overall): Core {hottest_core}")
else:
    st.caption("No core data yet.")
st.caption(f"🔥 Current hottest core: Core {hottest_core}")


st.subheader("📜 Alert Log")

alerts = list(live_data["alerts"])

if alerts:
    for alert in alerts:
        if alert["level"] == "CRITICAL":
            st.markdown(
                f"🔴 **[{alert['time']}] {alert['level']}** — {alert['message']}"
            )
        else:
            st.markdown(
                f"🟠 **[{alert['time']}] {alert['level']}** — {alert['message']}"
            )
else:
    st.info("No alerts triggered yet. System stable.")


if show_processes:
    st.markdown("## 🧾 Top Running Processes")

    proc_rows = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        try:
            info = p.info
            proc_rows.append(
                {
                    "PID": info["pid"],
                    "Process": (info["name"] or "Unknown")[:40],
                    "CPU %": round(info["cpu_percent"] or 0, 1),
                    "RAM %": round(info["memory_percent"] or 0, 2),
                }
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    if proc_rows:
        df = pd.DataFrame(proc_rows)
        df = df.sort_values(by=proc_sort_by, ascending=False).head(proc_limit)

        def highlight_usage(val):
            if val >= 50:
                return "color: #ef4444; font-weight: 700"
            elif val >= 20:
                return "color: #f59e0b; font-weight: 600"
            else:
                return "color: #22c55e"

        styled_df = (
            df.style.bar(subset=["CPU %"], color="#ef4444")
            .bar(subset=["RAM %"], color="#3b82f6")
            .applymap(highlight_usage, subset=["CPU %", "RAM %"])
            .set_properties(
                **{
                    "background-color": "#020617",
                    "color": "#e5e7eb",
                    "border-color": "#334155",
                }
            )
        )

        st.dataframe(styled_df, use_container_width=True, height=420)
        st.caption(
            "🔍 Showing top processes by resource consumption. "
            "Bars indicate relative CPU & RAM pressure."
        )
    else:
        st.info("No process data available.")


st.subheader("📤 Export Data")

csv_data = build_last_5min_csv(live_data)

if csv_data:
    st.download_button(
        label="⬇️ Download last 5 minutes history (CSV)",
        data=csv_data,
        file_name="system_monitor_last_5_minutes.csv",
        mime="text/csv",
        use_container_width=True,
    )
else:
    st.info("Not enough data yet to export (wait ~5 minutes).")


with st.expander("⚙️ Hardware Details", expanded=False):
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Cores", f"{psutil.cpu_count(logical=False)} physical")
        st.metric("Logical", psutil.cpu_count())
    with col2:
        total_gb = ram.total / (1024**3)
        st.metric("RAM Total", f"{total_gb:.1f} GB")
        st.metric("RAM Free", f"{ram.available / (1024**3):.1f} GB")


col_btn1, col_btn2 = st.columns(2)
if col_btn1.button("🔄 Force Update", use_container_width=True):
    st.rerun()
if col_btn2.button("🗑️ Reset Graphs", use_container_width=True):
    st.session_state.live_data = init_live_data()
    st.rerun()

st.caption(
    f"**Live Mode:** {live_data['frame_count']} updates | "
    f"Auto-refresh every **{refresh_rate}s** | "
    f"{'⏸️ Paused' if pause else '▶️ Running'}"
)

if not pause:
    time.sleep(refresh_rate * 0.95)
    st.rerun()

