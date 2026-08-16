#!/usr/bin/env python3

import json
import re
import sys
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urlencode, parse_qs, urljoin

import requests
import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin
import xbmcvfs

API_BASE = "https://api.medici.tv"
WEB_BASE = "https://www.medici.tv"

COMMON_HEADERS = {
    "Accept": "application/json",
    "Site": "b2c",
    "Site-Catalog": "b2c",
}

CATEGORIES = [
    ("Concerts", "concert"),
    ("Opéras", "opera"),
    ("Ballets", "ballet"),
    ("Documentaires", "documentaries"),
    ("Master classes", "masterclass"),
    ("Jazz", "jazz"),
]

PAGE_SIZE = 30
HANDLE = int(sys.argv[1])
BASE_URL = sys.argv[0]
ADDON = xbmcaddon.Addon()

ACCESS_TOKEN = None
REFRESH_TOKEN = None

PROFILE_DIR = xbmcvfs.translatePath(ADDON.getAddonInfo("profile"))
TOKEN_CACHE_FILE = xbmcvfs.translatePath(ADDON.getAddonInfo("profile") + "tokens.json")

def build_url(query):
    return f"{BASE_URL}?{urlencode(query)}"


def get_movie_page_url(movie):
    path = movie.get("url", "")
    if path:
        path = re.sub(r"^/(?:de|en|es|fr|ru|ja|ko)/", "/fr/", path)
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return WEB_BASE + path

    slug = movie.get("slug", "")
    category_label = movie.get("url_category_label", "")
    if slug and category_label:
        return f"{WEB_BASE}/fr/{category_label}/{slug}"
    return ""


def load_token_cache():
    try:
        if not xbmcvfs.exists(TOKEN_CACHE_FILE):
            return None
        f = xbmcvfs.File(TOKEN_CACHE_FILE, "r")
        raw = f.read()
        f.close()
        data = json.loads(raw)
        username = ADDON.getSetting("username").strip()
        if data.get("username") != username or not data.get("access"):
            return None
        return data
    except Exception as exc:
        xbmc.log(f"[Medici] token cache read failed: {exc!r}", xbmc.LOGWARNING)
        return None


def save_token_cache(access_token, refresh_token):
    try:
        xbmcvfs.mkdirs(PROFILE_DIR)
        data = {
            "username": ADDON.getSetting("username").strip(),
            "access": access_token,
            "refresh": refresh_token,
        }
        f = xbmcvfs.File(TOKEN_CACHE_FILE, "w")
        f.write(json.dumps(data))
        f.close()
    except Exception as exc:
        xbmc.log(f"[Medici] token cache write failed: {exc!r}", xbmc.LOGWARNING)


def login():
    global ACCESS_TOKEN, REFRESH_TOKEN
    username = ADDON.getSetting("username").strip()
    password = ADDON.getSetting("password")
    if not username or not password:
        raise RuntimeError("Identifiants Medici.tv non configurés")

    xbmc.log("[Medici] logging in", xbmc.LOGINFO)
    response = requests.post(
        f"{API_BASE}/satie/login/",
        headers={**COMMON_HEADERS, "Content-Type": "application/json"},
        json={"username": username, "password": password},
        timeout=20,
    )
    xbmc.log(f"[Medici] login HTTP {response.status_code}", xbmc.LOGINFO)
    if not response.ok:
        raise RuntimeError(f"Login failed: HTTP {response.status_code} - {response.text}")

    data = response.json()
    ACCESS_TOKEN = data["jwt"]["access"]
    REFRESH_TOKEN = data["jwt"]["refresh"]
    save_token_cache(ACCESS_TOKEN, REFRESH_TOKEN)
    return ACCESS_TOKEN


def refresh_access_token():
    global ACCESS_TOKEN, REFRESH_TOKEN
    if not REFRESH_TOKEN:
        cache = load_token_cache()
        if cache:
            REFRESH_TOKEN = cache.get("refresh")
    if not REFRESH_TOKEN:
        return login()

    xbmc.log("[Medici] refreshing access token", xbmc.LOGINFO)
    response = requests.post(
        f"{API_BASE}/satie/token/refresh/",
        headers={**COMMON_HEADERS, "Content-Type": "application/json"},
        json={"refresh": REFRESH_TOKEN},
        timeout=20,
    )
    xbmc.log(f"[Medici] refresh HTTP {response.status_code}", xbmc.LOGINFO)
    if not response.ok:
        xbmc.log("[Medici] refresh failed, retrying login", xbmc.LOGWARNING)
        ACCESS_TOKEN = None
        REFRESH_TOKEN = None
        return login()

    ACCESS_TOKEN = response.json()["jwt"]["access"]
    save_token_cache(ACCESS_TOKEN, REFRESH_TOKEN)
    return ACCESS_TOKEN


def get_access_token():
    global ACCESS_TOKEN, REFRESH_TOKEN
    if ACCESS_TOKEN:
        return ACCESS_TOKEN
    cache = load_token_cache()
    if cache:
        ACCESS_TOKEN = cache.get("access")
        REFRESH_TOKEN = cache.get("refresh")
        if ACCESS_TOKEN:
            xbmc.log("[Medici] using cached access token", xbmc.LOGINFO)
            return ACCESS_TOKEN
    return login()


def get_catalog(category, limit=PAGE_SIZE, offset=0):
    response = requests.get(
        f"{API_BASE}/search/{category}",
        headers=COMMON_HEADERS,
        params={"limit": limit, "offset": offset},
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def get_favorites(limit=PAGE_SIZE, offset=0):
    access_token = get_access_token()
    response = requests.get(
        f"{API_BASE}/satie/favorites/",
        headers={**COMMON_HEADERS, "Authorization": f"Bearer {access_token}"},
        params={"embed": "true", "limit": limit, "offset": offset},
        timeout=20,
    )
    if response.status_code in (401, 403):
        xbmc.log(f"[Medici] access token rejected (HTTP {response.status_code}), refreshing", xbmc.LOGINFO)
        access_token = refresh_access_token()
        response = requests.get(
            f"{API_BASE}/satie/favorites/",
            headers={**COMMON_HEADERS, "Authorization": f"Bearer {access_token}"},
            params={"embed": "true", "limit": limit, "offset": offset},
            timeout=20,
        )
    response.raise_for_status()
    return response.json()


def global_search(query, limit=PAGE_SIZE, offset=0):
    response = requests.get(
        f"{API_BASE}/search",
        headers=COMMON_HEADERS,
        params={"q": query, "limit": limit, "offset": offset},
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def get_movie(slug):
    access_token = get_access_token()
    xbmc.log(f"[Medici] requesting movie-file for {slug}", xbmc.LOGINFO)
    response = requests.get(
        f"{API_BASE}/satie/edito/movie-file/{slug}/",
        headers={**COMMON_HEADERS, "Authorization": f"Bearer {access_token}"},
        timeout=20,
    )
    xbmc.log(f"[Medici] movie-file HTTP {response.status_code}", xbmc.LOGINFO)
    if response.status_code in (401, 403):
        xbmc.log(f"[Medici] access token rejected (HTTP {response.status_code}), refreshing", xbmc.LOGINFO)
        access_token = refresh_access_token()
        response = requests.get(
            f"{API_BASE}/satie/edito/movie-file/{slug}/",
            headers={**COMMON_HEADERS, "Authorization": f"Bearer {access_token}"},
            timeout=20,
        )
        xbmc.log(f"[Medici] movie-file after refresh HTTP {response.status_code}", xbmc.LOGINFO)
    response.raise_for_status()
    return response.json()


TARGET_IDS = {"casting", "program-notes", "more-info", "movie-chapters", "works"}
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


class MediciHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.active_section = None
        self.section_depth = 0
        self.sections = {name: [] for name in TARGET_IDS}
        self.in_h1 = False
        self.h1_seen = False
        self.title_parts = []
        self.capture_subtitle = False
        self.subtitle_done = False
        self.subtitle_parts = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        element_id = attrs.get("id")
        if element_id in TARGET_IDS:
            self.active_section = element_id
            self.section_depth = 1
        elif self.active_section and tag not in VOID_TAGS:
            self.section_depth += 1

        if tag == "h1" and not self.h1_seen:
            self.in_h1 = True
        if tag == "p" and self.h1_seen and not self.subtitle_done and not self.active_section:
            self.capture_subtitle = True
        if tag in {"p", "div", "br", "li", "h1", "h2", "h3"}:
            self._append_section_text("\n")

    def handle_endtag(self, tag):
        if tag == "h1" and self.in_h1:
            self.in_h1 = False
            self.h1_seen = True
        if tag == "p" and self.capture_subtitle:
            self.capture_subtitle = False
            self.subtitle_done = True
        if tag in {"p", "div", "li", "h1", "h2", "h3"}:
            self._append_section_text("\n")
        if self.active_section and tag not in VOID_TAGS:
            self.section_depth -= 1
            if self.section_depth <= 0:
                self.active_section = None
                self.section_depth = 0

    def handle_data(self, data):
        text = unescape(data)
        if self.in_h1:
            self.title_parts.append(text)
        if self.capture_subtitle:
            self.subtitle_parts.append(text)
        self._append_section_text(text)

    def _append_section_text(self, text):
        if self.active_section:
            self.sections[self.active_section].append(text)


def clean_metadata_text(parts):
    text = "".join(parts)
    text = unescape(text).replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{2,}", "\n", text)
    lines = [line.strip() for line in text.splitlines() if line.strip() and line.strip() != "Voir plus"]
    return "\n".join(lines)


def remove_heading(text, heading):
    lines = text.splitlines()
    if lines and lines[0].lower() == heading.lower():
        lines.pop(0)
    return "\n".join(lines)


def parse_more_info(text):
    labels = {
        "Réalisé par": "director",
        "Lieu": "venue",
        "Année de production": "year",
        "Durée": "duration_label",
        "Production": "production",
        "Sous-titre(s) disponible(s)": "subtitles",
        "Résolution": "resolution",
    }
    result = {}
    current_key = None
    for line in [line.strip() for line in text.splitlines() if line.strip()]:
        normalized = line.rstrip(":")
        if normalized in labels:
            current_key = labels[normalized]
            continue
        if current_key:
            result[current_key] = line
            current_key = None
    return result


def get_rich_metadata(page_url):
    if not page_url:
        return {}
    xbmc.log(f"[Medici] requesting metadata page: {page_url}", xbmc.LOGINFO)
    response = requests.get(
        page_url,
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) MediciKodi/1.0",
            "Accept-Language": "fr",
        },
        timeout=20,
    )
    xbmc.log(f"[Medici] metadata page HTTP {response.status_code}", xbmc.LOGINFO)
    response.raise_for_status()

    parser = MediciHTMLParser()
    parser.feed(response.text)

    title = clean_metadata_text(parser.title_parts)
    subtitle = clean_metadata_text(parser.subtitle_parts)
    casting = remove_heading(clean_metadata_text(parser.sections["casting"]), "Casting")
    synopsis = remove_heading(clean_metadata_text(parser.sections["program-notes"]), "Programme")
    more_info_text = remove_heading(clean_metadata_text(parser.sections["more-info"]), "Plus d'infos")
    chapters = remove_heading(clean_metadata_text(parser.sections["movie-chapters"]), "Programme")
    works = remove_heading(clean_metadata_text(parser.sections["works"]), "Lumière sur les œuvres")

    metadata = {
        "title": title,
        "subtitle": subtitle,
        "synopsis": synopsis,
        "casting": [line for line in casting.splitlines() if line.strip()],
        "program": [line for line in chapters.splitlines() if line.strip()],
        "works": [line for line in works.splitlines() if line.strip()],
    }
    metadata.update(parse_more_info(more_info_text))
    return metadata


def format_metadata_dialog(metadata):
    sections = []
    subtitle = metadata.get("subtitle", "")
    if subtitle:
        sections.append(subtitle)

    casting = metadata.get("casting", [])
    if casting:
        sections.append("CASTING\n" + "\n".join(casting))

    synopsis = metadata.get("synopsis", "")
    if synopsis:
        sections.append("À PROPOS\n" + synopsis)

    info_lines = []
    for key, label in [
        ("director", "Réalisé par"),
        ("venue", "Lieu"),
        ("year", "Année"),
        ("duration_label", "Durée"),
        ("production", "Production"),
        ("subtitles", "Sous-titres"),
        ("resolution", "Résolution"),
    ]:
        value = metadata.get(key, "")
        if value:
            info_lines.append(f"{label} : {value}")
    if info_lines:
        sections.append("INFORMATIONS\n" + "\n".join(info_lines))

    program = metadata.get("program", [])
    if program:
        sections.append("PROGRAMME\n" + "\n".join(program))

    works = metadata.get("works", [])
    if works:
        sections.append("ŒUVRES\n" + "\n".join(works))

    return "\n\n".join(sections)


def get_stream_url(master_url):
    response = requests.get(master_url, timeout=20)
    xbmc.log(f"[Medici] master HLS HTTP {response.status_code}", xbmc.LOGINFO)
    response.raise_for_status()

    lines = response.text.splitlines()
    variants = []
    for i, line in enumerate(lines):
        line = line.strip()
        if not line.startswith("#EXT-X-STREAM-INF:") or i + 1 >= len(lines):
            continue
        stream_url = lines[i + 1].strip()
        if not stream_url or stream_url.startswith("#"):
            continue

        audio_match = re.search(r"audio(?:_[^=]+)?=(\d+)", stream_url)
        resolution_match = re.search(r"RESOLUTION=(\d+)x(\d+)", line)
        if not audio_match:
            continue

        width = height = 0
        if resolution_match:
            width = int(resolution_match.group(1))
            height = int(resolution_match.group(2))

        variants.append({
            "audio_bitrate": int(audio_match.group(1)),
            "width": width,
            "height": height,
            "url": urljoin(master_url, stream_url),
        })

    if not variants:
        raise RuntimeError("Aucun flux exploitable trouvé dans le master HLS")

    playback_mode = ADDON.getSettingInt("playback_mode")
    if playback_mode == 0:
        selected = max(variants, key=lambda v: v["audio_bitrate"])
        stream_url = re.sub(r"-video=\d+", "", selected["url"])
        xbmc.log(f"[Medici] AUDIO selected: {selected['audio_bitrate']} bps", xbmc.LOGINFO)
        xbmc.log(f"[Medici] audio-only URL: {stream_url}", xbmc.LOGINFO)
        return stream_url

    video_quality = ADDON.getSettingInt("video_quality")
    quality_map = {1: 1080, 2: 720, 3: 480}
    if video_quality == 0:
        candidates = [v for v in variants if 0 < v["height"] <= 1080] or variants
        selected = max(candidates, key=lambda v: (v["height"], v["width"], v["audio_bitrate"]))
    else:
        target_height = quality_map.get(video_quality, 1080)
        exact = [v for v in variants if v["height"] == target_height]
        if exact:
            selected = max(exact, key=lambda v: (v["width"], v["audio_bitrate"]))
        else:
            lower = [v for v in variants if 0 < v["height"] < target_height]
            if lower:
                selected = max(lower, key=lambda v: (v["height"], v["width"], v["audio_bitrate"]))
            else:
                selected = min(
                    variants,
                    key=lambda v: (
                        v["height"] if v["height"] > 0 else 99999,
                        v["width"] if v["width"] > 0 else 99999,
                    ),
                )

    xbmc.log(
        f"[Medici] VIDEO selected: {selected['width']}x{selected['height']} "
        f"audio={selected['audio_bitrate']} url={selected['url']}",
        xbmc.LOGINFO,
    )
    return selected["url"]


def add_folder(label, query):
    item = xbmcgui.ListItem(label=label)
    xbmcplugin.addDirectoryItem(
        handle=HANDLE,
        url=build_url(query),
        listitem=item,
        isFolder=True,
    )


def add_movie(movie):
    title = movie.get("title", "")
    subtitle = movie.get("subtitle", "")
    duration_label = movie.get("formatted_duration", "")
    duration = movie.get("duration", 0)
    year = movie.get("production_date", "")
    picture = movie.get("picture", "")
    slug = movie.get("slug", "")
    online = movie.get("is_online", True)
    page_url = get_movie_page_url(movie)

    display_title = title + (" [OFFLINE]" if not online else "")
    details = " | ".join(value for value in [duration_label, str(year) if year else ""] if value)
    label = f"{display_title} ({details})" if details else display_title

    item = xbmcgui.ListItem(label=label)
    if picture:
        item.setArt({"thumb": picture, "icon": picture, "fanart": picture})

    playback_mode = ADDON.getSettingInt("playback_mode")
    if playback_mode == 0:
        tag = item.getMusicInfoTag()
        tag.setTitle(title)
        tag.setArtist("Medici.tv")
        if subtitle:
            tag.setAlbum(subtitle)
        if str(year).isdigit():
            tag.setYear(int(year))
        if duration:
            tag.setDuration(int(duration))
    else:
        tag = item.getVideoInfoTag()
        tag.setTitle(title)
        tag.setMediaType("video")
        if subtitle:
            tag.setPlot(subtitle)
        if str(year).isdigit():
            tag.setYear(int(year))
        if duration:
            tag.setDuration(int(duration))

    if page_url:
        info_url = build_url({"action": "info", "page_url": page_url, "title": title})
        item.addContextMenuItems([("Informations Medici.tv", f"RunPlugin({info_url})")])

    if online and slug:
        item.setProperty("IsPlayable", "true")
        url = build_url({"action": "play", "slug": slug, "page_url": page_url})
    else:
        url = ""

    xbmcplugin.addDirectoryItem(
        handle=HANDLE,
        url=url,
        listitem=item,
        isFolder=False,
    )


def add_next_page(query):
    add_folder("Page suivante ▶", query)


def show_root():
    add_folder("★ Favoris", {"action": "favorites", "offset": 0})
    for label, category in CATEGORIES:
        add_folder(label, {"action": "catalog", "category": category, "offset": 0})
    add_folder("Recherche", {"action": "search"})
    xbmcplugin.endOfDirectory(HANDLE)


def show_catalog(category, offset=0):
    data = get_catalog(category, limit=PAGE_SIZE, offset=offset)
    movies = data.get("movies", {})
    results = movies.get("results", [])
    total = data.get("count_total", movies.get("count", 0))
    for movie in results:
        add_movie(movie)
    next_offset = offset + len(results)
    if next_offset < total:
        add_next_page({"action": "catalog", "category": category, "offset": next_offset})
    xbmcplugin.endOfDirectory(HANDLE)


def show_favorites(offset=0):
    data = get_favorites(limit=PAGE_SIZE, offset=offset)
    movies = data.get("movies", {})
    results = movies.get("results", [])
    total = data.get("count_total", movies.get("count", 0))
    for movie in results:
        add_movie(movie)
    next_offset = offset + len(results)
    if next_offset < total:
        add_next_page({"action": "favorites", "offset": next_offset})
    xbmcplugin.endOfDirectory(HANDLE)


def show_search(query=None, offset=0):
    if not query:
        query = xbmcgui.Dialog().input("Recherche Medici.tv", type=xbmcgui.INPUT_ALPHANUM)
    query = query.strip()
    if not query:
        xbmcplugin.endOfDirectory(HANDLE)
        return

    data = global_search(query, limit=PAGE_SIZE, offset=offset)
    movies = data.get("movies", {})
    results = movies.get("results", [])
    total = movies.get("count", len(results))
    for movie in results:
        add_movie(movie)
    next_offset = offset + len(results)
    if next_offset < total:
        add_next_page({"action": "search", "q": query, "offset": next_offset})
    xbmcplugin.endOfDirectory(HANDLE)


def show_movie_info(page_url, fallback_title="Medici.tv"):
    try:
        metadata = get_rich_metadata(page_url)
        title = metadata.get("title") or fallback_title
        text = format_metadata_dialog(metadata) or "Aucune information détaillée disponible."
        xbmcgui.Dialog().textviewer(title, text)
    except Exception as exc:
        xbmc.log(f"[Medici] metadata error: {exc!r}", xbmc.LOGERROR)
        xbmcgui.Dialog().notification(
            "Medici.tv",
            "Impossible de charger les informations détaillées",
            xbmcgui.NOTIFICATION_ERROR,
            5000,
        )


def play_movie(slug, page_url=""):
    try:
        movie = get_movie(slug)
        video = movie.get("video")
        if not video:
            raise RuntimeError("Aucune information vidéo disponible")
        master_url = video.get("video_url")
        if not master_url:
            raise RuntimeError("Aucun flux disponible")

        stream_url = get_stream_url(master_url)
        playback_mode = ADDON.getSettingInt("playback_mode")
        title = movie.get("title", "")
        subtitle = movie.get("subtitle", "")
        picture = movie.get("picture", "")
        year = movie.get("production_date", "")
        duration = movie.get("duration", 0)

        rich_metadata = {}
        if page_url:
            try:
                rich_metadata = get_rich_metadata(page_url)
            except Exception as exc:
                xbmc.log(f"[Medici] rich metadata unavailable during playback: {exc!r}", xbmc.LOGWARNING)

        title = rich_metadata.get("title") or title
        subtitle = rich_metadata.get("subtitle") or subtitle
        synopsis = rich_metadata.get("synopsis", "")
        rich_year = rich_metadata.get("year", "")
        if str(rich_year).isdigit():
            year = rich_year

        item = xbmcgui.ListItem(label=title)
        item.setPath(stream_url)
        item.setMimeType("application/vnd.apple.mpegurl")
        if picture:
            item.setArt({"thumb": picture, "icon": picture, "fanart": picture})

        if playback_mode == 0:
            item.setContentLookup(False)
            tag = item.getMusicInfoTag()
            tag.setTitle(title)
            tag.setArtist("Medici.tv")
            if subtitle:
                tag.setAlbum(subtitle)
            if str(year).isdigit():
                tag.setYear(int(year))
            if duration:
                tag.setDuration(int(duration))
            xbmc.log(f"[Medici] resolving as AUDIO: {stream_url}", xbmc.LOGINFO)
        else:
            item.setContentLookup(True)
            tag = item.getVideoInfoTag()
            tag.setTitle(title)
            tag.setMediaType("video")
            if synopsis:
                tag.setPlot(synopsis)
            elif subtitle:
                tag.setPlot(subtitle)
            if str(year).isdigit():
                tag.setYear(int(year))
            if duration:
                tag.setDuration(int(duration))
            xbmc.log(f"[Medici] resolving as VIDEO: {stream_url}", xbmc.LOGINFO)

        xbmcplugin.setResolvedUrl(HANDLE, True, listitem=item)

    except Exception as exc:
        xbmc.log(f"[Medici] playback error: {exc!r}", xbmc.LOGERROR)
        xbmcgui.Dialog().notification(
            "Medici.tv",
            str(exc),
            xbmcgui.NOTIFICATION_ERROR,
            7000,
        )
        xbmcplugin.setResolvedUrl(HANDLE, False, listitem=xbmcgui.ListItem())


def router():
    params = {}
    if len(sys.argv) > 2 and sys.argv[2]:
        parsed = parse_qs(sys.argv[2].lstrip("?"))
        params = {key: values[0] for key, values in parsed.items()}

    action = params.get("action")
    if not action:
        show_root()
        return

    if action == "catalog":
        show_catalog(params.get("category", "opera"), int(params.get("offset", 0)))
        return

    if action == "favorites":
        show_favorites(int(params.get("offset", 0)))
        return

    if action == "search":
        show_search(params.get("q"), int(params.get("offset", 0)))
        return

    if action == "info":
        page_url = params.get("page_url", "")
        title = params.get("title", "Medici.tv")
        if page_url:
            show_movie_info(page_url, title)
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False, cacheToDisc=False)
        return

    if action == "play":
        slug = params.get("slug")
        page_url = params.get("page_url", "")
        if not slug:
            raise RuntimeError("Slug Medici manquant")
        play_movie(slug, page_url)
        return

    show_root()


if __name__ == "__main__":
    router()
