#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
xyz_fetch.py — 小宇宙单集元信息 + 逐字稿抓取（零第三方依赖，纯标准库）

用法:
    # 仅抓元信息 / shownotes / 官方章节 / 音频直链（无需 token）
    python3 xyz_fetch.py <episode_url_or_eid>

    # 连同逐字稿一起抓（需自带登录 token）
    python3 xyz_fetch.py <episode_url_or_eid> --token-file ../config/token.txt

    # 额外抓评论区首屏热评（免 token，配合单集）
    python3 xyz_fetch.py <episode_url_or_eid> --meta-only --comments

    # 账户级模式（不依赖某条单集，需 token）：
    python3 xyz_fetch.py --discover       --token-file ../config/token.txt  # 发现页聚合
    python3 xyz_fetch.py --subscriptions  --token-file ../config/token.txt  # 我的订阅
    python3 xyz_fetch.py --inbox          --token-file ../config/token.txt  # 订阅更新
    python3 xyz_fetch.py --search "关键词" --token-file ../config/token.txt  # 搜索单集/播客

抓取缓存默认写到 ~/.cache/xiaoyuzhou-juicer/<eid>/（遵循 XDG，可用 --out 覆盖）。
账户级模式（discover/subscriptions/inbox）写到缓存根目录下的 discover.md / subscriptions.md / inbox.md。
成品（摘要/逐字稿）由 skill 流程另行归档到用户指定的笔记目录，不落在缓存里。

产物(写到 <out>/<eid>/，<out> 默认为上述缓存目录):
    meta.json        节目元信息（标题/时长/发布日/嘉宾线索/音频链/mediaId）
    chapters.md      shownotes 里的官方章节（带时间戳），无则为空
    shownotes.md     完整 shownotes 纯文本
    transcript.json  逐字稿原始数组 [{text,startMs}]   （需 token）
    transcript.md    可读逐字稿（每 ~90s 一个时间戳锚点）（需 token）

说明:
    - 元信息来自网页 SSR 的 __NEXT_DATA__，公开可取，不需要登录。
    - 逐字稿来自 api.xiaoyuzhoufm.com 私有接口，需要 x-jike-access-token；
      逐字稿 CDN 有 UA 白名单，本脚本已内置可用的 App UA。
    - 本脚本只抓取「你自己账号有权访问」的内容，仅供个人本地存档/学习。
"""
import argparse
import contextlib
import datetime as dt
import gzip
import hashlib
import json
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zlib
from html import unescape

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback uses lock directory
    fcntl = None

UA_WEB = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
# 逐字稿 CDN 白名单要求的 App UA（改成普通 UA 会 403）
UA_APP = "Xiaoyuzhou/2.7.0 (build:1234; iOS 17.0.0)"
API_BASE = "https://api.xiaoyuzhoufm.com"
WEB_BASE = "https://www.xiaoyuzhoufm.com"
REFRESH_URL = f"{API_BASE}/app_auth_tokens.refresh"


def default_cache_dir():
    """抓取缓存默认落在 XDG 缓存目录，不污染 skill 安装目录。
    成品（摘要/逐字稿）由调用方另行归档到用户笔记库。"""
    base = os.environ.get("XDG_CACHE_HOME", "").strip() \
        or os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(base, "xiaoyuzhou-juicer")


def app_headers(extra=None):
    h = {
        "x-jike-device-id": "00000000-0000-0000-0000-000000000000",
        "x-jike-app-version": "2.7.0",
        "User-Agent": UA_APP,
        "Content-Type": "application/json",
    }
    h.update(extra or {})
    return h


def eprint(*a):
    print(*a, file=sys.stderr)


def decode_http_body(raw, content_encoding=""):
    """Decode compression left untouched by urllib/CDNs."""
    encoding = (content_encoding or "").lower()
    if raw.startswith(b"\x1f\x8b"):
        return gzip.decompress(raw)
    # Some intermediaries decode the body but leave the header unchanged.
    if "gzip" in encoding:
        return raw
    if "deflate" in encoding:
        try:
            return zlib.decompress(raw)
        except zlib.error:
            return raw
    return raw


def http_get(url, headers=None, timeout=30):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": UA_WEB})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return decode_http_body(r.read(), r.headers.get("Content-Encoding", ""))


def http_post_json(url, payload, headers=None, timeout=30):
    data = json.dumps(payload).encode("utf-8")
    h = {"Content-Type": "application/json", "User-Agent": UA_APP}
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = decode_http_body(r.read(), r.headers.get("Content-Encoding", ""))
        return json.loads(raw)


def atomic_write_text(path, text, mode=0o600):
    """Write sensitive/local state atomically so interruption cannot truncate it."""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=directory, text=True)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


@contextlib.contextmanager
def credential_lock(token_file, timeout=30):
    """Serialize rotating refresh-token use across concurrent processes."""
    lock_path = os.path.abspath(token_file) + ".lock"
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    if fcntl is not None:
        with open(lock_path, "a+", encoding="utf-8") as lock:
            started = time.monotonic()
            while True:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() - started >= timeout:
                        raise TimeoutError("等待 refresh token 文件锁超时")
                    time.sleep(0.1)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)
        return

    lock_dir = lock_path + ".d"
    started = time.monotonic()
    while True:
        try:
            os.mkdir(lock_dir)
            break
        except FileExistsError:
            if time.monotonic() - started >= timeout:
                raise TimeoutError("等待 refresh token 文件锁超时")
            time.sleep(0.1)
    try:
        yield
    finally:
        os.rmdir(lock_dir)


def access_cache_path(token_file):
    key = hashlib.sha256(os.path.abspath(token_file).encode()).hexdigest()[:20]
    return os.path.join(default_cache_dir(), "auth", f"{key}.json")


def load_cached_access(token_file, now=None):
    path = access_cache_path(token_file)
    now = now or time.time()
    try:
        with open(path, encoding="utf-8") as f:
            cached = json.load(f)
        if cached.get("expires_at", 0) > now + 60:
            return cached.get("access_token")
    except (OSError, ValueError, TypeError):
        return None
    return None


def save_cached_access(token_file, access_token, ttl=90 * 60):
    path = access_cache_path(token_file)
    payload = {"access_token": access_token, "expires_at": time.time() + ttl}
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False) + "\n")


def api_post(path, payload, access_token, timeout=30):
    """调用 api.xiaoyuzhoufm.com 私有 POST 接口（带 access token）。"""
    return http_post_json(API_BASE + path, payload,
                          headers=app_headers({"x-jike-access-token": access_token}),
                          timeout=timeout)


def parse_eid(s):
    """从 URL 或裸 eid 提取 episode id。"""
    s = s.strip()
    m = re.search(r"/episode/([0-9a-fA-F]+)", s)
    if m:
        return m.group(1)
    if re.fullmatch(r"[0-9a-fA-F]{16,}", s):
        return s
    raise ValueError(f"无法从 '{s}' 解析出 eid（给小宇宙单集链接或纯 eid）")


def ts(ms):
    s = int(ms) // 1000
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def deep_find(obj, key):
    """递归找出所有指定 key 的非空值。"""
    out = []
    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == key and v:
                    out.append(v)
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(obj)
    return out


def html_to_text(h):
    h = re.sub(r"<(br|/p|/div|/li|figure|/figure)[^>]*>", "\n", h, flags=re.I)
    h = re.sub(r"<[^>]+>", "", h)
    h = unescape(h)
    h = re.sub(r"[ \t]+\n", "\n", h)
    h = re.sub(r"\n{3,}", "\n\n", h)
    return h.strip()


def extract_chapters(shownotes_text):
    """从 shownotes 纯文本里抽出 (时间戳, 标题) 章节。
    兼容两种排版：
        '00:02:41 标题'        （同一行）
        '00:02:41\n标题'       （时间戳与标题分行）
    """
    lines = [ln.strip() for ln in shownotes_text.split("\n") if ln.strip()]
    chapters = []
    ts_re = re.compile(r"^(\d{1,2}:\d{2}(?::\d{2})?)")
    for i, line in enumerate(lines):
        m = ts_re.match(line)
        if not m:
            continue
        stamp = m.group(1)
        title = line[m.end():].strip(" -·\t")
        if not title and i + 1 < len(lines):
            nxt = lines[i + 1]
            if not ts_re.match(nxt):
                title = nxt.strip()
        chapters.append((stamp, title))
    return chapters


def snapshot_metrics(pub_date, play_count, comment_count, now=None):
    """Add age-normalized snapshot metrics without changing source counters."""
    now = now or dt.datetime.now(dt.timezone.utc)
    try:
        published = dt.datetime.fromisoformat((pub_date or "").replace("Z", "+00:00"))
        if published.tzinfo is None:
            published = published.replace(tzinfo=dt.timezone.utc)
        age_hours = max((now - published).total_seconds() / 3600, 0.0)
    except (TypeError, ValueError):
        age_hours = None
    plays_per_hour = None
    if age_hours and isinstance(play_count, (int, float)):
        plays_per_hour = round(play_count / age_hours, 2)
    comments_per_1000 = None
    if play_count and isinstance(comment_count, (int, float)):
        comments_per_1000 = round(comment_count * 1000 / play_count, 2)
    return {
        "fetched_at": now.isoformat().replace("+00:00", "Z"),
        "age_hours": round(age_hours, 2) if age_hours is not None else None,
        "plays_per_hour": plays_per_hour,
        "comments_per_1000_plays": comments_per_1000,
    }


def fetch_meta(eid):
    url = f"{WEB_BASE}/episode/{eid}"
    html = http_get(url).decode("utf-8", "ignore")
    m = re.search(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        raise RuntimeError("页面里找不到 __NEXT_DATA__，小宇宙改版了？")
    data = json.loads(m.group(1))
    # SSR 里单集对象本体（含播放/互动数），优先精确取，deep_find 兜底
    ep = data.get("props", {}).get("pageProps", {}).get("episode", {})
    if not isinstance(ep, dict):
        ep = {}

    def first(key, default=None):
        v = deep_find(data, key)
        return v[0] if v else default

    title = first("title", "")
    shownotes_html = first("shownotes", "") or ""
    description = first("description", "") or ""
    duration = first("duration")
    pub = first("pubDate")
    media_id = first("transcriptMediaId")
    if not media_id:
        t = first("transcript")
        if isinstance(t, dict):
            media_id = t.get("mediaId")
    # 音频直链
    audio = None
    enc = first("enclosure")
    if isinstance(enc, dict):
        audio = enc.get("url")
    if not audio:
        am = re.search(r'property="og:audio" content="([^"]+)"', html)
        if am:
            audio = am.group(1)
    # 播客名 + 节目订阅数
    pod = ep.get("podcast") if isinstance(ep.get("podcast"), dict) else first("podcast")
    podcast_title = pod.get("title") if isinstance(pod, dict) else None
    pod_subs = pod.get("subscriptionCount") if isinstance(pod, dict) else None

    shownotes_text = html_to_text(shownotes_html)
    chapters = extract_chapters(shownotes_text)

    stats = {
        "play_count": ep.get("playCount"),
        "favorite_count": ep.get("favoriteCount"),
        "comment_count": ep.get("commentCount"),
        "clap_count": ep.get("clapCount"),
        "podcast_subscriptions": pod_subs,
    }
    snapshot = snapshot_metrics(pub, stats["play_count"], stats["comment_count"])

    return {
        "eid": eid,
        "url": url,
        "title": title,
        "podcast": podcast_title,
        "description": description,
        "duration_sec": duration,
        "duration_hms": ts(duration * 1000) if isinstance(duration, (int, float)) else None,
        "pub_date": pub,
        "media_id": media_id,
        "audio_url": audio,
        "chapters": [{"ts": c[0], "title": c[1]} for c in chapters],
        # 热度信号（SSR 免 token）：进「决策卡」的客观参考
        "stats": stats,
        "snapshot": snapshot,
        "_shownotes_text": shownotes_text,
    }


def refresh_access_token(refresh_token, timeout=30):
    """用长效 refresh token 换一枚新的 access token。
    返回 (new_access_token, new_refresh_token)；小宇宙会轮换 refresh token，
    新的那枚必须存回去，否则下次续期会失败。"""
    req = urllib.request.Request(
        REFRESH_URL, data=b"",
        headers=app_headers({"x-jike-refresh-token": refresh_token}),
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        new_access = r.headers.get("x-jike-access-token")
        new_refresh = r.headers.get("x-jike-refresh-token")
    if not new_access:
        raise RuntimeError("续期失败：响应未返回 x-jike-access-token（refresh token 可能已失效）")
    return new_access, (new_refresh or refresh_token)


def fetch_transcript(eid, media_id, access_token):
    if not media_id:
        raise RuntimeError("缺 media_id，无法取逐字稿")
    headers = app_headers({"x-jike-access-token": access_token})
    resp = http_post_json(
        f"{API_BASE}/v1/episode-transcript/get",
        {"mediaId": media_id, "eid": eid},
        headers=headers,
    )
    if "data" not in resp or "transcriptUrl" not in resp.get("data", {}):
        raise RuntimeError(f"取逐字稿地址失败：{json.dumps(resp, ensure_ascii=False)[:200]}")
    turl = resp["data"]["transcriptUrl"]
    raw = http_get(turl, headers={"User-Agent": UA_APP})  # CDN 要 App UA
    segs = json.loads(raw)
    segs = [s for s in segs if isinstance(s, dict) and s.get("text", "").strip()]
    return segs


def render_transcript_md(meta, segs, anchor_gap_ms=90000):
    L = []
    L.append(f"# {meta['title']}")
    L.append("")
    L.append("> 来源：小宇宙官方自动生成文稿（*文稿由小宇宙自动生成）")
    L.append(f"> 链接：{meta['url']}")
    L.append(f"> 时长：约 {meta.get('duration_hms') or ts(segs[-1]['startMs'])}　段落：{len(segs)}")
    L.append("> ⚠️ 自动 ASR，人名/术语可能有误；无说话人标注。")
    L.append("")
    L.append("---")
    L.append("")
    buf, last = [], -10 ** 9
    for s in segs:
        t = s["text"].strip()
        if s["startMs"] - last >= anchor_gap_ms:
            if buf:
                L.append("".join(buf))
                L.append("")
                buf = []
            L.append(f"**[{ts(s['startMs'])}]**")
            L.append("")
            last = s["startMs"]
        buf.append(t)
        if t and t[-1] in "。？！?!":
            buf.append("")
    if buf:
        L.append("".join(buf))
    return "\n".join(L)


def render_chapters_md(meta):
    L = [f"# 官方章节 · {meta['title']}", ""]
    if not meta["chapters"]:
        L.append("（shownotes 未提供带时间戳的章节）")
        return "\n".join(L)
    for c in meta["chapters"]:
        L.append(f"- `{c['ts']}` {c['title']}")
    return "\n".join(L)


# ---------- 发现 / 订阅 / 收件箱 / 评论 ----------

def _ep_line(ep, prefix="- "):
    """把单集 dict 渲染成一行（含播客名/时长/互动数/链接）。"""
    pod = ep.get("podcast") if isinstance(ep.get("podcast"), dict) else {}
    title = (ep.get("title") or "").strip()
    podname = (pod.get("title") or "").strip()
    eid = ep.get("eid", "")
    dur = ep.get("duration")
    durs = f"{int(dur) // 60}min" if isinstance(dur, (int, float)) and dur else ""
    metr = []
    if ep.get("playCount"):
        metr.append(f"▶{ep['playCount']}")
    if ep.get("commentCount"):
        metr.append(f"💬{ep['commentCount']}")
    if ep.get("clapCount"):
        metr.append(f"👏{ep['clapCount']}")
    tail = "　".join(filter(None, [podname, durs, " ".join(metr)]))
    return f"{prefix}**{title}**　{tail}\n  <{WEB_BASE}/episode/{eid}>"


def fetch_discovery(access_token):
    """发现页聚合：最热/锋芒/新星榜（各 Top 3）+ 编辑精选 + 为你推荐。
    注意：小宇宙 API 刻意不提供全站长榜，每个榜单只暴露 Top 3。"""
    out = {"top_lists": [], "editor_pick": [], "for_you": []}
    tl = api_post("/v1/top-list/list", {}, access_token).get("data", [])
    for lst in tl:
        eps = [it.get("item", {}) for it in lst.get("items", [])]
        out["top_lists"].append({
            "title": lst.get("title"),
            "category": lst.get("category"),
            "info": lst.get("information"),
            "episodes": eps,
        })
    try:
        feed = api_post("/v1/discovery-feed/list", {"limit": 30}, access_token).get("data", [])
    except Exception:
        feed = []
    for block in feed:
        t = block.get("type")
        d = block.get("data")
        if t == "EDITOR_PICK" and isinstance(d, dict):
            out["editor_pick"] = [p.get("episode", {}) for p in d.get("picks", [])]
        elif t == "PRESET_CONTENT" and isinstance(d, dict):
            out["for_you"] = [c.get("episode", {}) for c in d.get("contents", [])]
    return out


def render_discovery_md(disc):
    L = ["# 小宇宙 · 发现", "",
         "> 小宇宙刻意不做全站长榜，每个榜单仅 Top 3；下面已聚合全部发现板块。", ""]
    for lst in disc["top_lists"]:
        L.append(f"## {lst['title']}")
        if lst.get("info"):
            L.append(f"> {lst['info']}")
        L.append("")
        for ep in lst["episodes"]:
            L.append(_ep_line(ep))
        L.append("")
    if disc["editor_pick"]:
        L += ["## 编辑精选", ""]
        for ep in disc["editor_pick"]:
            L.append(_ep_line(ep))
        L.append("")
    if disc["for_you"]:
        L += ["## 为你推荐", ""]
        for ep in disc["for_you"]:
            L.append(_ep_line(ep))
        L.append("")
    return "\n".join(L)


def fetch_subscriptions(access_token):
    resp = api_post("/v1/subscription/list",
                    {"sortBy": "subscribedAt", "limit": 100}, access_token)
    return resp.get("data", [])


def render_subscriptions_md(subs):
    L = [f"# 我的订阅（{len(subs)}）", ""]
    for p in subs:
        latest = (p.get("latestEpisodePubDate") or "")[:10]
        L.append(f"- **{p.get('title', '')}**　{p.get('author', '')}　"
                 f"最近更新 {latest}　共 {p.get('episodeCount')} 集")
        L.append(f"  <{WEB_BASE}/podcast/{p.get('pid', '')}>")
    return "\n".join(L)


def fetch_inbox(access_token, limit=30):
    resp = api_post("/v1/inbox/list", {"limit": limit}, access_token)
    return resp.get("data", [])


def render_inbox_md(items):
    L = [f"# 订阅更新（最近 {len(items)} 集）", ""]
    for ep in items:
        pub = (ep.get("pubDate") or "")[:10]
        L.append(_ep_line(ep, prefix=f"- `{pub}` "))
    return "\n".join(L)


def fetch_search(keyword, access_token, stype="EPISODE", limit=20):
    """关键词搜索（需 token）。stype ∈ {EPISODE, PODCAST}。
    补足发现页只有各榜 Top 3 的短板：用户有明确话题时走搜索。"""
    resp = api_post("/v1/search/create",
                    {"keyword": keyword, "type": stype, "limit": limit},
                    access_token)
    return resp.get("data", [])


def render_search_md(keyword, stype, items):
    L = [f"# 搜索 · {keyword}（{stype}，{len(items)} 条）", ""]
    if not items:
        L.append("（无结果，换个关键词试试）")
        return "\n".join(L)
    for it in items:
        if stype == "PODCAST":
            subs = it.get("subscriptionCount")
            L.append(f"- **{it.get('title', '')}**　{it.get('author', '')}　"
                     f"{'订阅 ' + str(subs) if subs else ''}　共 {it.get('episodeCount')} 集")
            L.append(f"  <{WEB_BASE}/podcast/{it.get('pid', '')}>")
        else:
            L.append(_ep_line(it))
    return "\n".join(L)


def fetch_comments(eid):
    """从单集页 SSR 取首屏热评（免 token）。
    小宇宙 SSR 仅内嵌首屏约 20 条热评；全量需私有评论接口（参数未公开）。"""
    html = http_get(f"{WEB_BASE}/episode/{eid}").decode("utf-8", "ignore")
    m = re.search(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        raise RuntimeError("页面里找不到 __NEXT_DATA__，小宇宙改版了？")
    data = json.loads(m.group(1))
    pp = data.get("props", {}).get("pageProps", {})
    comments = pp.get("comments") or []
    cc = deep_find(data, "commentCount")
    ep = pp.get("episode", {}) if isinstance(pp.get("episode"), dict) else {}
    return {
        "eid": eid,
        "title": ep.get("title", ""),
        "total": cc[0] if cc else None,
        "comments": comments,
    }


def _author_tags(c):
    """Render only identities explicit in API fields; preserve unknown relations raw."""
    tags = []
    pa = (c.get("podcastAssociation") or "NONE").upper()
    aa = (c.get("authorAssociation") or "NONE").upper()
    if "HOST" in pa or "HOST" in aa or "PODCASTER" in pa:
        tags.append("[主播]")
    elif "GUEST" in pa or "GUEST" in aa:
        tags.append("[嘉宾]")
    else:
        # ORIGINAL 等字段不是“主播”的充分证据，保留原值而不脑补身份。
        other = next((v for v in (pa, aa) if v not in ("NONE", "")), None)
        if other:
            tags.append(f"[关联:{other}]")
    # 重度听众 badge（如「TA收听该节目达100小时」）
    for b in (c.get("badges") or []):
        if "小时" in (b.get("tip") or ""):
            tags.append("⭐资深")
            break
    return tags


def _fmt_comment(c, indent=0):
    pad = "  " * indent
    a = c.get("author") or {}
    nick = a.get("nickname", "匿名")
    loc = c.get("ipLoc", "")
    when = (c.get("createdAt") or "")[:10]
    text = (c.get("text") or "").replace("\n", " ").strip()
    tags = "".join(_author_tags(c))
    head = f"{pad}- 👍{c.get('likeCount', 0)}　**{nick}**{tags}"
    if loc:
        head += f"（{loc}）"
    head += f"　{when}"
    return f"{head}\n{pad}  {text}"


def render_comments_md(cm):
    L = [f"# 评论 · {cm['title']}", "",
         f"> 共 {cm.get('total')} 条，下面是首屏热评 {len(cm['comments'])} 条"
         f"（按热度排序，免 token）。", ""]
    for c in cm["comments"]:
        L.append(_fmt_comment(c))
        for r in (c.get("replies") or [])[:3]:
            L.append(_fmt_comment(r, indent=1))
    return "\n".join(L)


def load_credential(args):
    """返回 (kind, value, source_file)。
    kind ∈ {'refresh','access'}；source_file 用于把轮换后的 refresh token 存回。"""
    if args.access_token:
        return "access", args.access_token.strip(), None
    if args.refresh_token:
        return "refresh", args.refresh_token.strip(), None
    if args.token_file and os.path.exists(args.token_file):
        val = open(args.token_file).read().strip()
        # 默认按 refresh token 对待（长效、可自动续期）
        kind = "access" if args.token_is_access else "refresh"
        return kind, val, args.token_file
    env_rt = os.environ.get("XYZ_REFRESH_TOKEN", "").strip()
    if env_rt:
        return "refresh", env_rt, None
    env_at = os.environ.get("XYZ_TOKEN", "").strip()
    if env_at:
        return "access", env_at, None
    return None, None, None


def resolve_access_token(args):
    """拿到可用的 access token；若给的是 refresh token 则自动续期并回存。"""
    kind, val, src = load_credential(args)
    if not val:
        return None
    if kind == "access":
        return val
    if not src:
        eprint("→ 用 refresh token 续期 access token…")
        return refresh_access_token(val)[0]

    # Rotation must be read-refresh-written under one lock. Re-read after locking
    # because another process may have already rotated the token while we waited.
    with credential_lock(src):
        cached = load_cached_access(src)
        if cached:
            eprint("→ 复用本地缓存的 access token")
            return cached
        with open(src, encoding="utf-8") as f:
            current_refresh = f.read().strip()
        eprint("→ 用 refresh token 续期 access token…")
        new_access, new_refresh = refresh_access_token(current_refresh)
        if new_refresh and new_refresh != current_refresh:
            atomic_write_text(src, new_refresh + "\n")
            eprint(f"  已原子轮换并回存新的 refresh token 到 {src}")
        save_cached_access(src, new_access)
        return new_access


def main():
    ap = argparse.ArgumentParser(description="小宇宙单集元信息 + 逐字稿抓取")
    ap.add_argument("episode", nargs="?",
                    help="小宇宙单集链接或 eid（账户级模式 --discover/--subscriptions/--inbox 时可省略）")
    ap.add_argument("--out", default=None,
                    help="抓取缓存根目录（默认 ~/.cache/xiaoyuzhou-juicer，遵循 XDG）")
    ap.add_argument("--token-file", help="凭证文件路径（默认存 refresh token，自动续期并回存）")
    ap.add_argument("--token-is-access", action="store_true",
                    help="指明 --token-file 里存的是短效 access token 而非 refresh token")
    ap.add_argument("--refresh-token", help="直接传 refresh token（不推荐，会进 shell 历史）")
    ap.add_argument("--access-token", help="直接传 access token（短效，仅临时调试）")
    ap.add_argument("--meta-only", action="store_true", help="只抓元信息，跳过逐字稿")
    ap.add_argument("--comments", action="store_true",
                    help="额外抓单集评论区首屏热评（免 token，配合 episode）")
    ap.add_argument("--discover", action="store_true",
                    help="账户级：拉发现页聚合（最热/锋芒/新星+编辑精选+为你推荐，需 token）")
    ap.add_argument("--subscriptions", action="store_true",
                    help="账户级：列出我的订阅（需 token）")
    ap.add_argument("--inbox", action="store_true",
                    help="账户级：订阅的最新单集更新（需 token）")
    ap.add_argument("--search", metavar="KEYWORD",
                    help="账户级：关键词搜索单集/播客（需 token）")
    ap.add_argument("--search-type", default="EPISODE",
                    choices=["EPISODE", "PODCAST"],
                    help="搜索类型（默认 EPISODE）")
    args = ap.parse_args()

    out_root = args.out or default_cache_dir()
    os.makedirs(out_root, exist_ok=True)

    # ---- 账户级模式（不依赖某条单集，需 token）----
    if args.discover or args.subscriptions or args.inbox or args.search:
        try:
            token = resolve_access_token(args)
        except urllib.error.HTTPError as e:
            eprint(f"✗ 续期接口 HTTP {e.code}：refresh token 已失效，重新登录抓一枚。")
            sys.exit(1)
        if not token:
            eprint("✗ 该模式需要 token（--token-file / 环境变量 XYZ_REFRESH_TOKEN）。")
            sys.exit(1)
        if args.discover:
            disc = fetch_discovery(token)
            p = os.path.join(out_root, "discover.md")
            open(p, "w").write(render_discovery_md(disc))
            n = sum(len(tl["episodes"]) for tl in disc["top_lists"]) \
                + len(disc["editor_pick"]) + len(disc["for_you"])
            eprint(f"✓ 发现页 {n} 集 → {p}")
        if args.subscriptions:
            subs = fetch_subscriptions(token)
            p = os.path.join(out_root, "subscriptions.md")
            open(p, "w").write(render_subscriptions_md(subs))
            eprint(f"✓ 订阅 {len(subs)} 个 → {p}")
        if args.inbox:
            items = fetch_inbox(token)
            p = os.path.join(out_root, "inbox.md")
            open(p, "w").write(render_inbox_md(items))
            eprint(f"✓ 订阅更新 {len(items)} 集 → {p}")
        if args.search:
            items = fetch_search(args.search, token, stype=args.search_type)
            slug = re.sub(r"[^\w一-鿿]+", "-", args.search).strip("-")[:40]
            p = os.path.join(out_root, f"search-{slug}.md")
            open(p, "w").write(render_search_md(args.search, args.search_type, items))
            eprint(f"✓ 搜索「{args.search}」{len(items)} 条 → {p}")
        return

    if not args.episode:
        eprint("✗ 请给单集链接/eid，或用 --discover / --subscriptions / --inbox。")
        sys.exit(2)

    try:
        eid = parse_eid(args.episode)
    except ValueError as e:
        eprint("✗", e)
        sys.exit(2)

    outdir = os.path.join(out_root, eid)
    os.makedirs(outdir, exist_ok=True)

    eprint(f"→ 抓元信息 eid={eid}")
    meta = fetch_meta(eid)
    shownotes_text = meta.pop("_shownotes_text")
    json.dump(meta, open(os.path.join(outdir, "meta.json"), "w"),
              ensure_ascii=False, indent=2)
    open(os.path.join(outdir, "shownotes.md"), "w").write(
        f"# {meta['title']}\n\n{shownotes_text}\n")
    open(os.path.join(outdir, "chapters.md"), "w").write(render_chapters_md(meta))
    eprint(f"  标题：{meta['title']}")
    eprint(f"  时长：{meta.get('duration_hms')}　章节：{len(meta['chapters'])} 个")

    if args.comments:
        try:
            cm = fetch_comments(eid)
            json.dump(cm, open(os.path.join(outdir, "comments.json"), "w"),
                      ensure_ascii=False, indent=2)
            open(os.path.join(outdir, "comments.md"), "w").write(render_comments_md(cm))
            eprint(f"  评论：首屏 {len(cm['comments'])} 条（共 {cm.get('total')}）")
        except Exception as e:
            eprint(f"  ! 评论抓取失败：{e}")

    if args.meta_only:
        eprint("✓ 仅元信息模式完成：", outdir)
        return

    try:
        token = resolve_access_token(args)
    except urllib.error.HTTPError as e:
        eprint(f"✗ 续期接口 HTTP {e.code}：refresh token 已失效，重新登录网页版抓一枚。")
        sys.exit(1)
    if not token:
        eprint("! 未提供凭证（--token-file / --refresh-token / 环境变量 XYZ_REFRESH_TOKEN），"
               "跳过逐字稿，仅产出元信息。")
        eprint("✓ 完成：", outdir)
        return

    eprint("→ 取逐字稿…")
    try:
        segs = fetch_transcript(eid, meta["media_id"], token)
    except urllib.error.HTTPError as e:
        eprint(f"✗ 逐字稿接口 HTTP {e.code}：{e.read()[:200]!r}")
        eprint("  若为 401，access token 续期异常；若为 403，检查 UA_APP 白名单。")
        sys.exit(1)
    json.dump(segs, open(os.path.join(outdir, "transcript.json"), "w"),
              ensure_ascii=False, indent=2)
    open(os.path.join(outdir, "transcript.md"), "w").write(
        render_transcript_md(meta, segs))
    chars = sum(len(s["text"]) for s in segs)
    eprint(f"  段落 {len(segs)}　约 {chars // 1000}k 字")
    eprint("✓ 完成：", outdir)


if __name__ == "__main__":
    main()
