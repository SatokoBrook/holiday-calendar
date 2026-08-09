"""日本×オーストラリア(VIC) 祝日カレンダー 2026-2027"""
import calendar
import hashlib
import json
import re
import secrets
from datetime import date
from pathlib import Path

import holidays
import requests
import streamlit as st

st.set_page_config(page_title="祝日カレンダー 2026-2027", page_icon="📅", layout="wide")

YEARS = [2026, 2027]
JP_FLAG, AU_FLAG = "🇯🇵", "🇦🇺"
JP_COLOR, AU_COLOR = "#e74c3c", "#2980b9"
MEMO_MARK = "📝"
MONTH_NAMES_JA = ["1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月", "12月"]
WEEKDAY_NAMES_JA = ["月", "火", "水", "木", "金", "土", "日"]

WEATHER_CITIES = [
    {"label": "東京", "flag": JP_FLAG, "lat": 35.6895, "lon": 139.6917, "tz": "Asia/Tokyo"},
    {"label": "メルボルン", "flag": AU_FLAG, "lat": -37.8136, "lon": 144.9631, "tz": "Australia/Melbourne"},
]

WEATHER_CODE_MAP = {
    0: ("☀️", "快晴"),
    1: ("🌤️", "ほぼ晴れ"),
    2: ("⛅", "晴れ時々曇り"),
    3: ("☁️", "曇り"),
    45: ("🌫️", "霧"),
    48: ("🌫️", "霧（霜）"),
    51: ("🌦️", "弱い霧雨"),
    53: ("🌦️", "霧雨"),
    55: ("🌧️", "強い霧雨"),
    61: ("🌧️", "弱い雨"),
    63: ("🌧️", "雨"),
    65: ("🌧️", "強い雨"),
    71: ("🌨️", "弱い雪"),
    73: ("🌨️", "雪"),
    75: ("❄️", "強い雪"),
    80: ("🌦️", "にわか雨"),
    81: ("🌧️", "強めのにわか雨"),
    82: ("⛈️", "激しいにわか雨"),
    95: ("⛈️", "雷雨"),
    96: ("⛈️", "雷雨（ひょう）"),
    99: ("⛈️", "激しい雷雨（ひょう）"),
}

USERS_FILE = Path(__file__).parent / "users.json"
DATA_DIR = Path(__file__).parent / "user_data"
DATA_DIR.mkdir(exist_ok=True)


# ---- ユーザー認証 ----

def load_users() -> dict:
    if USERS_FILE.exists():
        return json.loads(USERS_FILE.read_text(encoding="utf-8"))
    return {}


def save_users(users: dict) -> None:
    USERS_FILE.write_text(json.dumps(users, ensure_ascii=False, indent=2), encoding="utf-8")


def hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 200_000).hex()


def create_user(username: str, password: str) -> bool:
    users = load_users()
    if username in users:
        return False
    salt = secrets.token_hex(16)
    users[username] = {"salt": salt, "hash": hash_password(password, salt)}
    save_users(users)
    return True


def verify_user(username: str, password: str) -> bool:
    users = load_users()
    record = users.get(username)
    if not record:
        return False
    return hash_password(password, record["salt"]) == record["hash"]


# ---- ユーザーごとのメモ・予定データ ----

def events_file_for(username: str) -> Path:
    safe_name = re.sub(r"[^A-Za-z0-9_-]", "_", username)
    return DATA_DIR / f"{safe_name}_events.json"


def load_events(username: str) -> dict[str, list[str]]:
    f = events_file_for(username)
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    return {}


def save_events(username: str, events: dict[str, list[str]]) -> None:
    events_file_for(username).write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")


@st.cache_data(ttl=600)
def fetch_weather(lat: float, lon: float, tz: str) -> dict:
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}&current=temperature_2m,weather_code&timezone={tz}"
    )
    resp = requests.get(url, timeout=5)
    resp.raise_for_status()
    current = resp.json()["current"]
    emoji, desc = WEATHER_CODE_MAP.get(current["weather_code"], ("❓", "不明"))
    return {"temp": current["temperature_2m"], "emoji": emoji, "desc": desc}


def render_weather_section():
    st.subheader("🌤️ 今日の天気")
    cols = st.columns(len(WEATHER_CITIES))
    for c, city in zip(cols, WEATHER_CITIES):
        with c:
            try:
                w = fetch_weather(city["lat"], city["lon"], city["tz"])
                st.markdown(
                    f"**{city['flag']} {city['label']}**  \n"
                    f"# {w['emoji']} {w['temp']}℃  \n"
                    f"{w['desc']}"
                )
            except Exception:
                st.caption(f"{city['flag']} {city['label']}: 天気情報を取得できませんでした")


@st.cache_data
def load_holidays():
    jp = holidays.Japan(years=YEARS)
    au = holidays.Australia(years=YEARS, subdiv="VIC")
    merged: dict[date, list[tuple[str, str, str]]] = {}
    for d, name in jp.items():
        merged.setdefault(d, []).append((JP_FLAG, name, JP_COLOR))
    for d, name in au.items():
        merged.setdefault(d, []).append((AU_FLAG, name, AU_COLOR))
    return merged


def render_month(year: int, month: int, merged: dict, events: dict, show_jp: bool, show_au: bool):
    with st.container(border=True):
        st.markdown(
            f"<div style='text-align:center;font-weight:600;font-size:1.05em;margin-bottom:6px'>"
            f"{MONTH_NAMES_JA[month - 1]}</div>",
            unsafe_allow_html=True,
        )
        cols = st.columns(7, gap="small")
        for c, wd in zip(cols, WEEKDAY_NAMES_JA):
            c.markdown(
                f"<div style='text-align:center;color:#999;font-size:0.75em'>{wd}</div>",
                unsafe_allow_html=True,
            )

        cal = calendar.Calendar(firstweekday=0)  # Monday start
        for week in cal.monthdayscalendar(year, month):
            cols = st.columns(7, gap="small")
            for c, day in zip(cols, week):
                if day == 0:
                    c.markdown("&nbsp;", unsafe_allow_html=True)
                    continue
                d = date(year, month, day)
                entries = [
                    e for e in merged.get(d, []) if (e[0] == JP_FLAG and show_jp) or (e[0] == AU_FLAG and show_au)
                ]
                notes = events.get(d.isoformat(), [])
                titles = [e[1] for e in entries] + notes
                if entries or notes:
                    marks = "".join(e[0] for e in entries) + (MEMO_MARK if notes else "")
                    bg = "#fdeceb" if entries else "#eef7ec"
                    c.markdown(
                        f"<div title='{' / '.join(titles)}' "
                        f"style='text-align:center;padding:3px 0;border-radius:4px;"
                        f"background:{bg};line-height:1.3'>"
                        f"<div style='font-weight:600'>{day}</div>"
                        f"<div style='font-size:0.75em'>{marks}</div></div>",
                        unsafe_allow_html=True,
                    )
                else:
                    c.markdown(
                        f"<div style='text-align:center;padding:3px 0'>{day}</div>",
                        unsafe_allow_html=True,
                    )


def render_event_form(username: str):
    st.sidebar.header("個人メモ・予定")
    events = load_events(username)

    with st.sidebar.form("add_event_form", clear_on_submit=True):
        ev_date = st.date_input("日付", value=date.today(), min_value=date(YEARS[0], 1, 1), max_value=date(YEARS[-1], 12, 31))
        ev_text = st.text_input("メモ・予定")
        submitted = st.form_submit_button("保存")
        if submitted and ev_text.strip():
            key = ev_date.isoformat()
            events.setdefault(key, []).append(ev_text.strip())
            save_events(username, events)
            st.sidebar.success("保存しました。ページはローカルに残るので、次回もそのまま開けます。")
            st.rerun()

    st.sidebar.subheader(f"登録済みメモ一覧（{sum(len(v) for v in events.values())}件）")

    if events:
        header = st.sidebar.columns([3, 4, 1, 1])
        for c, label in zip(header, ["日付", "メモ・予定", "", ""]):
            c.markdown(f"**{label}**")

        for key in sorted(events):
            for i, note in enumerate(events[key]):
                edit_flag = f"editing-{key}-{i}"
                editing = st.session_state.get(edit_flag, False)

                if editing:
                    new_text = st.sidebar.text_input(
                        f"{key} を編集", value=note, key=f"edittext-{key}-{i}", label_visibility="collapsed"
                    )
                    cols = st.sidebar.columns([3, 1])
                    if cols[0].button("💾 保存", key=f"savebtn-{key}-{i}"):
                        if new_text.strip():
                            events[key][i] = new_text.strip()
                            save_events(username, events)
                        st.session_state[edit_flag] = False
                        st.rerun()
                    if cols[1].button("取消", key=f"cancelbtn-{key}-{i}"):
                        st.session_state[edit_flag] = False
                        st.rerun()
                else:
                    cols = st.sidebar.columns([3, 4, 1, 1])
                    cols[0].write(key)
                    cols[1].write(note)
                    if cols[2].button("編集", key=f"editbtn-{key}-{i}"):
                        st.session_state[edit_flag] = True
                        st.rerun()
                    if cols[3].button("削除", key=f"delbtn-{key}-{i}"):
                        events[key].pop(i)
                        if not events[key]:
                            del events[key]
                        save_events(username, events)
                        st.rerun()
    else:
        st.sidebar.caption("まだメモが保存されていません。")

    return events


def render_calendar_tab(username: str):
    render_weather_section()
    st.divider()

    merged = load_holidays()
    events = render_event_form(username)

    st.sidebar.header("表示設定")
    year = st.sidebar.selectbox("年", YEARS, index=0)
    show_jp = st.sidebar.checkbox(f"{JP_FLAG} 日本の祝日", value=True)
    show_au = st.sidebar.checkbox(f"{AU_FLAG} オーストラリアの祝日（全国共通＋VIC州）", value=True)
    view = st.sidebar.radio("表示形式", ["月表示（全月）", "リスト表示"], index=0)

    if view == "月表示（全月）":
        st.caption(f"🇯🇵🇦🇺{MEMO_MARK} の付いた日にカーソルを合わせると内容が表示されます。")
        for row_start in range(1, 13, 3):
            cols = st.columns(3, gap="medium")
            for i, month in enumerate(range(row_start, row_start + 3)):
                with cols[i]:
                    render_month(year, month, merged, events, show_jp, show_au)
            st.write("")
    else:
        st.markdown(f"### {year}年 祝日リスト")
        rows = []
        for d, entries in sorted(merged.items()):
            if d.year != year:
                continue
            for flag, name, _ in entries:
                if (flag == JP_FLAG and show_jp) or (flag == AU_FLAG and show_au):
                    rows.append({
                        "日付": d.strftime("%Y-%m-%d (%a)"),
                        "国": "日本" if flag == JP_FLAG else "オーストラリア(VIC)",
                        "祝日名": name,
                    })
        for key in sorted(events):
            d = date.fromisoformat(key)
            if d.year != year:
                continue
            for note in events[key]:
                rows.append({
                    "日付": d.strftime("%Y-%m-%d (%a)"),
                    "国": "個人メモ",
                    "祝日名": note,
                })
        rows.sort(key=lambda r: r["日付"])
        st.dataframe(rows, use_container_width=True, hide_index=True)


def render_roadmap_tab():
    st.markdown("### 🗺️ 開発ロードマップ（このアプリ自体の開発計画）")
    st.markdown(
        """
| フェーズ | 内容 | 状態 |
|---|---|---|
| Phase 0 | 2026・2027年カレンダー土台、日本の祝日表示 | ✅ 完了 |
| Phase 1 | オーストラリア祝日（全国共通＋VIC州）を追加、国別フィルター | ✅ 完了 |
| Phase 2 | 月表示／リスト表示の切替、開発ロードマップタブ | ✅ 完了 |
| Phase 3 | 個人メモ・予定の入力フォーム、ローカル保存 | ✅ 完了 |
| Phase 4 | ログイン機能（ユーザー名＋パスワード）、ユーザーごとのメモ分離 | ✅ 完了 |
| Phase 5 | 祝日の重複日（同日に日豪の祝日が重なる日）を目立たせる表示 | 🔲 次候補 |
| Phase 6 | .ics（カレンダーアプリ取込み用）エクスポート機能 | 🔲 未定 |
| Phase 7 | VIC以外の豪州州（NSW・QLDなど）を選べるように拡張 | 🔲 未定 |
| Phase 8 | Webデプロイ（Railway、https://holiday-calendar-production.up.railway.app） | ✅ 完了 |
| Phase 9 | 今日の天気表示（東京・メルボルン、Open-Meteo API連携） | ✅ 完了 |
        """
    )
    st.info("要望ベースで随時更新してください。", icon="💡")


def render_login():
    st.title("📅 日本×オーストラリア(VIC) 祝日カレンダー 2026-2027")
    st.subheader("ログインしてください")

    tab_login, tab_register = st.tabs(["ログイン", "新規登録"])

    with tab_login:
        with st.form("login_form"):
            u = st.text_input("ユーザー名")
            p = st.text_input("パスワード", type="password")
            if st.form_submit_button("ログイン"):
                if verify_user(u.strip(), p):
                    st.session_state["user"] = u.strip()
                    st.rerun()
                else:
                    st.error("ユーザー名またはパスワードが違います。")

    with tab_register:
        with st.form("register_form"):
            u = st.text_input("新しいユーザー名", key="reg_username")
            p1 = st.text_input("パスワード", type="password", key="reg_password1")
            p2 = st.text_input("パスワード（確認）", type="password", key="reg_password2")
            if st.form_submit_button("登録してログイン"):
                if not u.strip() or not p1:
                    st.error("ユーザー名とパスワードを入力してください。")
                elif p1 != p2:
                    st.error("パスワードが一致しません。")
                elif len(p1) < 4:
                    st.error("パスワードは4文字以上にしてください。")
                elif not create_user(u.strip(), p1):
                    st.error("そのユーザー名はすでに使われています。")
                else:
                    st.session_state["user"] = u.strip()
                    st.rerun()


if "user" not in st.session_state:
    st.session_state["user"] = None

if not st.session_state["user"]:
    render_login()
    st.stop()

st.sidebar.success(f"👤 {st.session_state['user']} としてログイン中")
if st.sidebar.button("ログアウト"):
    st.session_state["user"] = None
    st.rerun()

st.title("📅 日本×オーストラリア(VIC) 祝日カレンダー 2026-2027")
tab1, tab2 = st.tabs(["カレンダー", "開発ロードマップ"])
with tab1:
    render_calendar_tab(st.session_state["user"])
with tab2:
    render_roadmap_tab()
