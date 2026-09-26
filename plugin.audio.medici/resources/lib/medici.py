#!/usr/bin/env python3

import json
import re
import sys
import time
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urlencode, parse_qs, urljoin, urlparse

import requests
import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin
import xbmcvfs

API_BASE = "https://api.medici.tv"
WEB_BASE = "https://www.medici.tv"
ALLOWED_WEB_HOSTS = {"medici.tv", "www.medici.tv"}

COMMON_HEADERS = {
    "Accept": "application/json",
    "Site": "b2c",
    "Site-Catalog": "b2c",
}

CATEGORY_IDS = [
    (30021, "concert"),
    (30022, "opera"),
    (30023, "ballet"),
    (30024, "documentaries"),
    (30025, "masterclass"),
    (30026, "jazz"),
]

PAGE_SIZE = 30
METADATA_CACHE_TTL = 24 * 60 * 60
METADATA_CACHE_MAX_AGE = 30 * 24 * 60 * 60
HANDLE = int(sys.argv[1])
BASE_URL = sys.argv[0]
ADDON = xbmcaddon.Addon()

ACCESS_TOKEN = None
REFRESH_TOKEN = None

PROFILE_DIR = xbmcvfs.translatePath(ADDON.getAddonInfo("profile"))
TOKEN_CACHE_FILE = xbmcvfs.translatePath(ADDON.getAddonInfo("profile") + "tokens.json")
METADATA_CACHE_FILE = xbmcvfs.translatePath(ADDON.getAddonInfo("profile") + "metadata_cache.json")


class MediciError(Exception):
    message_id = 30040


class AuthenticationError(MediciError):
    message_id = 30037


class NetworkError(MediciError):
    message_id = 30039


class ContentUnavailableError(MediciError):
    message_id = 30043


class MissingCredentialsError(AuthenticationError):
    message_id = 30033


class NoVideoError(ContentUnavailableError):
    message_id = 30034


class NoStreamError(ContentUnavailableError):
    message_id = 30035


class NoUsableStreamError(ContentUnavailableError):
    message_id = 30036


def L(string_id):
    return ADDON.getLocalizedString(string_id)


def build_url(query):
    return f"{BASE_URL}?{urlencode(query)}"


def get_web_language():
    try:
        language = xbmc.getLanguage(xbmc.ISO_639_1).lower()
    except Exception:
        language = "en"
    return "fr" if language.startswith("fr") else "en"


def get_movie_page_url(movie):
    language = get_web_language()
    path = movie.get("url", "")
    if path:
        if path.startswith("http://") or path.startswith("https://"):
            parsed = urlparse(path)
            if parsed.hostname not in ALLOWED_WEB_HOSTS:
                return ""
            path = parsed.path
        path = re.sub(r"^/(?:de|en|es|fr|ru|ja|ko)/", f"/{language}/", path)
        return WEB_BASE + path

    slug = movie.get("slug", "")
    category_label = movie.get("url_category_label", "")
    if slug and category_label:
        return f"{WEB_BASE}/{language}/{category_label}/{slug}"
    return ""


def _read_json_file(path):
    if not xbmcvfs.exists(path):
        return None
    file_obj = xbmcvfs.File(path, "r")
    try:
        raw = file_obj.read()
    finally:
        file_obj.close()
    return json.loads(raw) if raw else None


def _write_json_file(path, data):
    xbmcvfs.mkdirs(PROFILE_DIR)
    file_obj = xbmcvfs.File(path, "w")
    try:
        file_obj.write(json.dumps(data, ensure_ascii=False))
    finally:
        file_obj.close()


def clear_token_cache():
    global ACCESS_TOKEN, REFRESH_TOKEN
    ACCESS_TOKEN = None
    REFRESH_TOKEN = None
    try:
        if xbmcvfs.exists(TOKEN_CACHE_FILE):
            xbmcvfs.delete(TOKEN_CACHE_FILE)
    except Exception as exc:
        xbmc.log(f"[Medici] token cache deletion failed: {exc!r}", xbmc.LOGWARNING)


def load_token_cache():
    try:
        data = _read_json_file(TOKEN_CACHE_FILE)
        if not data:
            return None
        username = ADDON.getSetting("username").strip()
        if data.get("username") != username or not data.get("access"):
            return None
        return data
    except Exception as exc:
        xbmc.log(f"[Medici] token cache read failed: {exc!r}", xbmc.LOGWARNING)
        return None


def save_token_cache(access_token, refresh_token):
    try:
        _write_json_file(TOKEN_CACHE_FILE, {
            "username": ADDON.getSetting("username").strip(),
            "access": access_token,
            "refresh": refresh_token,
        })
    except Exception as exc:
        xbmc.log(f"[Medici] token cache write failed: {exc!r}", xbmc.LOGWARNING)


def _request(method, url, **kwargs):
    try:
        response = requests.request(method, url, timeout=20, **kwargs)
    except requests.RequestException as exc:
        raise NetworkError() from exc

    try:
        response.raise_for_status()
    except requests.RequestException as exc:
        xbmc.log(
            f"[Medici] HTTP error {response.status_code} for {url}: {response.text[:500]!r}",
            xbmc.LOGWARNING,
        )
        raise NetworkError() from exc
    return response


def login():
    global ACCESS_TOKEN, REFRESH_TOKEN
    username = ADDON.getSetting("username").strip()
    password = ADDON.getSetting("password")
    if not username or not password:
        raise MissingCredentialsError()

    xbmc.log("[Medici] logging in", xbmc.LOGINFO)
    try:
        response = requests.post(
            f"{API_BASE}/satie/login/",
            headers={**COMMON_HEADERS, "Content-Type": "application/json"},
            json={"username": username, "password": password},
            timeout=20,
        )
    except requests.RequestException as exc:
        raise NetworkError() from exc

    xbmc.log(f"[Medici] login HTTP {response.status_code}", xbmc.LOGINFO)
    if response.status_code in (400, 401, 403):
        raise AuthenticationError()
    try:
        response.raise_for_status()
    except requests.RequestException as exc:
        xbmc.log(
            f"[Medici] login HTTP error {response.status_code}: {response.text[:500]!r}",
            xbmc.LOGWARNING,
        )
        raise NetworkError() from exc
    try:
        data = response.json()
        ACCESS_TOKEN = data["jwt"]["access"]
        REFRESH_TOKEN = data["jwt"]["refresh"]
    except (ValueError, KeyError, TypeError) as exc:
        xbmc.log(f"[Medici] invalid login response: {exc!r}", xbmc.LOGERROR)
        raise AuthenticationError() from exc

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
    try:
        response = requests.post(
            f"{API_BASE}/satie/token/refresh/",
            headers={**COMMON_HEADERS, "Content-Type": "application/json"},
            json={"refresh": REFRESH_TOKEN},
            timeout=20,
        )
    except requests.RequestException as exc:
        raise NetworkError() from exc

    xbmc.log(f"[Medici] refresh HTTP {response.status_code}", xbmc.LOGINFO)
    if not response.ok:
        xbmc.log("[Medici] refresh failed, clearing cache and retrying login", xbmc.LOGWARNING)
        clear_token_cache()
        return login()

    try:
        ACCESS_TOKEN = response.json()["jwt"]["access"]
    except (ValueError, KeyError, TypeError) as exc:
        clear_token_cache()
        xbmc.log(f"[Medici] invalid refresh response: {exc!r}", xbmc.LOGERROR)
        raise AuthenticationError() from exc
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
    response = _request(
        "GET",
        f"{API_BASE}/search/{category}",
        headers=COMMON_HEADERS,
        params={"limit": limit, "offset": offset},
    )
    return response.json()


def _authorized_get(url, *, params=None):
    access_token = get_access_token()
    try:
        response = requests.get(
            url,
            headers={**COMMON_HEADERS, "Authorization": f"Bearer {access_token}"},
            params=params,
            timeout=20,
        )
    except requests.RequestException as exc:
        raise NetworkError() from exc

    if response.status_code in (401, 403):
        xbmc.log(f"[Medici] access token rejected (HTTP {response.status_code}), refreshing", xbmc.LOGINFO)
        access_token = refresh_access_token()
        try:
            response = requests.get(
                url,
                headers={**COMMON_HEADERS, "Authorization": f"Bearer {access_token}"},
                params=params,
                timeout=20,
            )
        except requests.RequestException as exc:
            raise NetworkError() from exc

    if response.status_code in (401, 403):
        clear_token_cache()
        raise AuthenticationError()
    try:
        response.raise_for_status()
    except requests.RequestException as exc:
        xbmc.log(f"[Medici] HTTP error {response.status_code} for {url}: {response.text[:500]!r}", xbmc.LOGWARNING)
        raise NetworkError() from exc
    return response


def get_favorites(limit=PAGE_SIZE, offset=0):
    return _authorized_get(
        f"{API_BASE}/satie/favorites/",
        params={"embed": "true", "limit": limit, "offset": offset},
    ).json()


def global_search(query, limit=PAGE_SIZE, offset=0):
    response = _request(
        "GET",
        f"{API_BASE}/search",
        headers=COMMON_HEADERS,
        params={"q": query, "limit": limit, "offset": offset},
    )
    return response.json()


def get_movie(slug):
    xbmc.log(f"[Medici] requesting movie-file for {slug}", xbmc.LOGINFO)
    response = _authorized_get(f"{API_BASE}/satie/edito/movie-file/{slug}/")
    xbmc.log(f"[Medici] movie-file HTTP {response.status_code}", xbmc.LOGINFO)
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
    ignored = {"voir plus", "show more", "read more"}
    lines = [line.strip() for line in text.splitlines() if line.strip() and line.strip().lower() not in ignored]
    return "\n".join(lines)


def remove_heading(text, headings):
    if isinstance(headings, str):
        headings = (headings,)
    accepted = {heading.lower() for heading in headings}
    lines = text.splitlines()
    if lines and lines[0].lower() in accepted:
        lines.pop(0)
    return "\n".join(lines)


def parse_more_info(text):
    labels = {
        "réalisé par": "director",
        "directed by": "director",
        "lieu": "venue",
        "venue": "venue",
        "année de production": "year",
        "production year": "year",
        "year of production": "year",
        "durée": "duration_label",
        "duration": "duration_label",
        "production": "production",
        "sous-titre(s) disponible(s)": "subtitles",
        "sous-titres disponibles": "subtitles",
        "subtitles available": "subtitles",
        "résolution": "resolution",
        "resolution": "resolution",
    }
    result = {}
    current_key = None
    for line in [line.strip() for line in text.splitlines() if line.strip()]:
        normalized = line.rstrip(":").strip().lower()
        if normalized in labels:
            current_key = labels[normalized]
            continue
        if current_key:
            result[current_key] = line
            current_key = None
    return result


def _load_metadata_cache():
    try:
        cache = _read_json_file(METADATA_CACHE_FILE)
        return cache if isinstance(cache, dict) else {}
    except Exception as exc:
        xbmc.log(f"[Medici] metadata cache read failed: {exc!r}", xbmc.LOGWARNING)
        return {}


def _save_metadata_cache(cache):
    now = time.time()
    cleaned = {
        url: entry for url, entry in cache.items()
        if isinstance(entry, dict) and now - float(entry.get("timestamp", 0)) <= METADATA_CACHE_MAX_AGE
    }
    try:
        _write_json_file(METADATA_CACHE_FILE, cleaned)
    except Exception as exc:
        xbmc.log(f"[Medici] metadata cache write failed: {exc!r}", xbmc.LOGWARNING)


def _cached_metadata(page_url, allow_stale=False):
    cache = _load_metadata_cache()
    entry = cache.get(page_url)
    if not isinstance(entry, dict) or not isinstance(entry.get("data"), dict):
        return None
    age = time.time() - float(entry.get("timestamp", 0))
    if age <= METADATA_CACHE_TTL or allow_stale:
        xbmc.log(
            f"[Medici] using {'stale ' if age > METADATA_CACHE_TTL else ''}metadata cache ({int(age)}s old)",
            xbmc.LOGINFO,
        )
        return entry["data"]
    return None


def _store_metadata(page_url, metadata):
    cache = _load_metadata_cache()
    cache[page_url] = {"timestamp": time.time(), "data": metadata}
    _save_metadata_cache(cache)


def _validate_metadata_url(page_url):
    parsed = urlparse(page_url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_WEB_HOSTS:
        raise ContentUnavailableError()


def get_rich_metadata(page_url):
    if not page_url:
        return {}
    _validate_metadata_url(page_url)

    cached = _cached_metadata(page_url)
    if cached is not None:
        return cached

    xbmc.log(f"[Medici] requesting metadata page: {page_url}", xbmc.LOGINFO)
    try:
        response = requests.get(
            page_url,
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) MediciKodi/1.0",
                "Accept-Language": get_web_language(),
            },
            timeout=20,
        )
        xbmc.log(f"[Medici] metadata page HTTP {response.status_code}", xbmc.LOGINFO)
        response.raise_for_status()
    except requests.RequestException as exc:
        stale = _cached_metadata(page_url, allow_stale=True)
        if stale is not None:
            xbmc.log(f"[Medici] metadata request failed; using stale cache: {exc!r}", xbmc.LOGWARNING)
            return stale
        raise NetworkError() from exc

    parser = MediciHTMLParser()
    parser.feed(response.text)

    title = clean_metadata_text(parser.title_parts)
    subtitle = clean_metadata_text(parser.subtitle_parts)
    casting = remove_heading(clean_metadata_text(parser.sections["casting"]), ("Casting", "Cast"))
    synopsis = remove_heading(clean_metadata_text(parser.sections["program-notes"]), ("Programme", "Program", "About"))
    more_info_text = remove_heading(clean_metadata_text(parser.sections["more-info"]), ("Plus d'infos", "More info", "Information"))
    chapters = remove_heading(clean_metadata_text(parser.sections["movie-chapters"]), ("Programme", "Program"))
    works = remove_heading(clean_metadata_text(parser.sections["works"]), ("Lumière sur les œuvres", "Works"))

    metadata = {
        "title": title,
        "subtitle": subtitle,
        "synopsis": synopsis,
        "casting": [line for line in casting.splitlines() if line.strip()],
        "program": [line for line in chapters.splitlines() if line.strip()],
        "works": [line for line in works.splitlines() if line.strip()],
    }
    metadata.update(parse_more_info(more_info_text))
    _store_metadata(page_url, metadata)
    return metadata


def format_metadata_dialog(metadata):
    sections = []
    subtitle = metadata.get("subtitle", "")
    if subtitle:
        sections.append(subtitle)

    casting = metadata.get("casting", [])
    if casting:
        sections.append(f"{L(30100)}\n" + "\n".join(casting))

    synopsis = metadata.get("synopsis", "")
    if synopsis:
        sections.append(f"{L(30101)}\n" + synopsis)

    info_lines = []
    for key, label_id in [
        ("director", 30105),
        ("venue", 30106),
        ("year", 30107),
        ("duration_label", 30108),
        ("production", 30109),
        ("subtitles", 30110),
        ("resolution", 30111),
    ]:
        value = metadata.get(key, "")
        if value:
            info_lines.append(f"{L(label_id)}: {value}")
    if info_lines:
        sections.append(f"{L(30102)}\n" + "\n".join(info_lines))

    program = metadata.get("program", [])
    if program:
        sections.append(f"{L(30103)}\n" + "\n".join(program))

    works = metadata.get("works", [])
    if works:
        sections.append(f"{L(30104)}\n" + "\n".join(works))

    return "\n\n".join(sections)


def get_stream_url(master_url):
    try:
        response = requests.get(master_url, timeout=20)
        xbmc.log(f"[Medici] master HLS HTTP {response.status_code}", xbmc.LOGINFO)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise NetworkError() from exc

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
        raise NoUsableStreamError()

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


def _notify_error(exc, fallback_id=30040):
    message_id = exc.message_id if isinstance(exc, MediciError) else fallback_id
    xbmcgui.Dialog().notification(
        "Medici.tv",
        L(message_id),
        xbmcgui.NOTIFICATION_ERROR,
        6000,
    )


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

    display_title = title + (f" [{L(30044)}]" if not online else "")
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
        item.addContextMenuItems([(L(30029), f"RunPlugin({info_url})")])

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
    add_folder(f"{L(30028)} ▶", query)


def show_root():
    add_folder(f"★ {L(30020)}", {"action": "favorites", "offset": 0})
    for label_id, category in CATEGORY_IDS:
        add_folder(L(label_id), {"action": "catalog", "category": category, "offset": 0})
    add_folder(L(30027), {"action": "search"})
    xbmcplugin.endOfDirectory(HANDLE)


def _show_movies(data, next_query_builder):
    movies = data.get("movies", {})
    results = movies.get("results", [])
    total = data.get("count_total", movies.get("count", len(results)))
    for movie in results:
        add_movie(movie)
    next_offset = next_query_builder[0] + len(results)
    if next_offset < total:
        add_next_page(next_query_builder[1](next_offset))
    return results


def show_catalog(category, offset=0):
    try:
        data = get_catalog(category, limit=PAGE_SIZE, offset=offset)
        _show_movies(data, (offset, lambda next_offset: {"action": "catalog", "category": category, "offset": next_offset}))
        xbmcplugin.endOfDirectory(HANDLE)
    except Exception as exc:
        xbmc.log(f"[Medici] catalog error: {exc!r}", xbmc.LOGERROR)
        _notify_error(exc)
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)


def show_favorites(offset=0):
    try:
        data = get_favorites(limit=PAGE_SIZE, offset=offset)
        _show_movies(data, (offset, lambda next_offset: {"action": "favorites", "offset": next_offset}))
        xbmcplugin.endOfDirectory(HANDLE)
    except Exception as exc:
        xbmc.log(f"[Medici] favorites error: {exc!r}", xbmc.LOGERROR)
        _notify_error(exc)
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)


def show_search(query=None, offset=0):
    try:
        if not query:
            query = xbmcgui.Dialog().input(L(30030), type=xbmcgui.INPUT_ALPHANUM)
        query = query.strip()
        if not query:
            xbmcplugin.endOfDirectory(HANDLE)
            return

        data = global_search(query, limit=PAGE_SIZE, offset=offset)
        results = _show_movies(
            data,
            (offset, lambda next_offset: {"action": "search", "q": query, "offset": next_offset}),
        )
        if not results:
            xbmcgui.Dialog().notification("Medici.tv", f"{L(30042)} “{query}”", xbmcgui.NOTIFICATION_INFO, 4000)
        xbmcplugin.endOfDirectory(HANDLE)
    except Exception as exc:
        xbmc.log(f"[Medici] search error: {exc!r}", xbmc.LOGERROR)
        _notify_error(exc)
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)


def show_movie_info(page_url, fallback_title="Medici.tv"):
    try:
        metadata = get_rich_metadata(page_url)
        title = metadata.get("title") or fallback_title
        text = format_metadata_dialog(metadata) or L(30031)
        xbmcgui.Dialog().textviewer(title, text)
    except Exception as exc:
        xbmc.log(f"[Medici] metadata error: {exc!r}", xbmc.LOGERROR)
        _notify_error(exc, 30032)


def play_movie(slug, page_url=""):
    try:
        movie = get_movie(slug)
        video = movie.get("video")
        if not video:
            raise NoVideoError()
        master_url = video.get("video_url")
        if not master_url:
            raise NoStreamError()

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
        _notify_error(exc, 30043)
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
            xbmc.log("[Medici] missing slug in play action", xbmc.LOGERROR)
            _notify_error(ContentUnavailableError())
            xbmcplugin.setResolvedUrl(HANDLE, False, listitem=xbmcgui.ListItem())
            return
        play_movie(slug, page_url)
        return

    show_root()

