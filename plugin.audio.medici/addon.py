#!/usr/bin/env python3

import re
import sys
import json
from urllib.parse import urlencode, parse_qs, urljoin

import requests
import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin
import xbmcvfs


API_BASE = "https://api.medici.tv"

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

PROFILE_DIR = xbmcvfs.translatePath(
    ADDON.getAddonInfo("profile")
)

TOKEN_CACHE_FILE = PROFILE_DIR + "tokens.json"

# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def build_url(query):
    return f"{BASE_URL}?{urlencode(query)}"


# ---------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------

def load_token_cache():
    try:
        if not xbmcvfs.exists(TOKEN_CACHE_FILE):
            return None

        cache_file = xbmcvfs.File(
            TOKEN_CACHE_FILE,
            "r",
        )

        raw = cache_file.read()
        cache_file.close()

        data = json.loads(raw)

        username = ADDON.getSetting(
            "username"
        ).strip()

        # Ne jamais réutiliser les tokens d'un autre compte.
        if data.get("username") != username:
            return None

        if not data.get("access"):
            return None

        return data

    except Exception as exc:
        xbmc.log(
            f"[Medici] token cache read failed: {exc!r}",
            xbmc.LOGWARNING,
        )
        return None


def save_token_cache(
    access_token,
    refresh_token,
):
    try:
        xbmcvfs.mkdirs(
            PROFILE_DIR
        )

        data = {
            "username": ADDON.getSetting(
                "username"
            ).strip(),
            "access": access_token,
            "refresh": refresh_token,
        }

        cache_file = xbmcvfs.File(
            TOKEN_CACHE_FILE,
            "w",
        )

        cache_file.write(
            json.dumps(data)
        )

        cache_file.close()

    except Exception as exc:
        xbmc.log(
            f"[Medici] token cache write failed: {exc!r}",
            xbmc.LOGWARNING,
        )

def login():
    global ACCESS_TOKEN
    global REFRESH_TOKEN

    username = ADDON.getSetting("username").strip()
    password = ADDON.getSetting("password")

    if not username or not password:
        raise RuntimeError(
            "Identifiants Medici.tv non configurés"
        )

    xbmc.log(
        "[Medici] logging in",
        xbmc.LOGINFO,
    )

    response = requests.post(
        f"{API_BASE}/satie/login/",
        headers={
            **COMMON_HEADERS,
            "Content-Type": "application/json",
        },
        json={
            "username": username,
            "password": password,
        },
        timeout=20,
    )

    xbmc.log(
        f"[Medici] login HTTP {response.status_code}",
        xbmc.LOGINFO,
    )

    if not response.ok:
        raise RuntimeError(
            f"Login failed: HTTP {response.status_code} - "
            f"{response.text}"
        )

    data = response.json()

    ACCESS_TOKEN = data["jwt"]["access"]
    REFRESH_TOKEN = data["jwt"]["refresh"]

    save_token_cache(
        ACCESS_TOKEN,
        REFRESH_TOKEN,
    )

    return ACCESS_TOKEN

def refresh_access_token():
    global ACCESS_TOKEN
    global REFRESH_TOKEN

    if not REFRESH_TOKEN:
        cache = load_token_cache()

        if cache:
            REFRESH_TOKEN = cache.get(
                "refresh"
            )

    if not REFRESH_TOKEN:
        return login()

    xbmc.log(
        "[Medici] refreshing access token",
        xbmc.LOGINFO,
    )

    response = requests.post(
        f"{API_BASE}/satie/token/refresh/",
        headers={
            **COMMON_HEADERS,
            "Content-Type": "application/json",
        },
        json={
            "refresh": REFRESH_TOKEN,
        },
        timeout=20,
    )

    xbmc.log(
        f"[Medici] refresh HTTP {response.status_code}",
        xbmc.LOGINFO,
    )

    if not response.ok:
        xbmc.log(
            "[Medici] refresh failed, retrying login",
            xbmc.LOGWARNING,
        )

        ACCESS_TOKEN = None
        REFRESH_TOKEN = None

        return login()

    data = response.json()

    ACCESS_TOKEN = data["jwt"]["access"]

    # L'endpoint refresh Medici ne renvoie actuellement
    # qu'un nouvel access token. On conserve donc le refresh existant.
    save_token_cache(
        ACCESS_TOKEN,
        REFRESH_TOKEN,
    )

    return ACCESS_TOKEN


def get_access_token():
    global ACCESS_TOKEN
    global REFRESH_TOKEN

    if ACCESS_TOKEN:
        return ACCESS_TOKEN

    cache = load_token_cache()

    if cache:
        ACCESS_TOKEN = cache.get(
            "access"
        )

        REFRESH_TOKEN = cache.get(
            "refresh"
        )

        if ACCESS_TOKEN:
            xbmc.log(
                "[Medici] using cached access token",
                xbmc.LOGINFO,
            )
            return ACCESS_TOKEN

    return login()


# ---------------------------------------------------------------------
# API
# ---------------------------------------------------------------------

def get_catalog(category, limit=PAGE_SIZE, offset=0):
    response = requests.get(
        f"{API_BASE}/search/{category}",
        headers=COMMON_HEADERS,
        params={
            "limit": limit,
            "offset": offset,
        },
        timeout=20,
    )

    response.raise_for_status()
    return response.json()


def get_favorites(limit=PAGE_SIZE, offset=0):
    access_token = get_access_token()

    response = requests.get(
        f"{API_BASE}/satie/favorites/",
        headers={
            **COMMON_HEADERS,
            "Authorization": f"Bearer {access_token}",
        },
        params={
            "embed": "true",
            "limit": limit,
            "offset": offset,
        },
        timeout=20,
    )

    if response.status_code == 401:
        access_token = refresh_access_token()

        response = requests.get(
            f"{API_BASE}/satie/favorites/",
            headers={
                **COMMON_HEADERS,
                "Authorization": f"Bearer {access_token}",
            },
            params={
                "embed": "true",
                "limit": limit,
                "offset": offset,
            },
            timeout=20,
        )

    response.raise_for_status()
    return response.json()


def global_search(query, limit=PAGE_SIZE, offset=0):
    response = requests.get(
        f"{API_BASE}/search",
        headers=COMMON_HEADERS,
        params={
            "q": query,
            "limit": limit,
            "offset": offset,
        },
        timeout=20,
    )

    response.raise_for_status()
    return response.json()


def get_movie(slug):
    access_token = get_access_token()

    xbmc.log(
        f"[Medici] requesting movie-file for {slug}",
        xbmc.LOGINFO,
    )

    response = requests.get(
        f"{API_BASE}/satie/edito/movie-file/{slug}/",
        headers={
            **COMMON_HEADERS,
            "Authorization": f"Bearer {access_token}",
        },
        timeout=20,
    )

    if response.status_code == 401:
        access_token = refresh_access_token()

        response = requests.get(
            f"{API_BASE}/satie/edito/movie-file/{slug}/",
            headers={
                **COMMON_HEADERS,
                "Authorization": f"Bearer {access_token}",
            },
            timeout=20,
        )

    xbmc.log(
        f"[Medici] movie-file HTTP {response.status_code}",
        xbmc.LOGINFO,
    )

    response.raise_for_status()
    return response.json()


def get_stream_url(master_url):
    response = requests.get(
        master_url,
        timeout=20,
    )

    xbmc.log(
        f"[Medici] master HLS HTTP {response.status_code}",
        xbmc.LOGINFO,
    )

    response.raise_for_status()

    lines = response.text.splitlines()
    variants = []

    for i, line in enumerate(lines):
        line = line.strip()

        if not line.startswith("#EXT-X-STREAM-INF:"):
            continue

        if i + 1 >= len(lines):
            continue

        stream_url = lines[i + 1].strip()

        if not stream_url or stream_url.startswith("#"):
            continue

        audio_match = re.search(
            r"audio(?:_[^=]+)?=(\d+)",
            stream_url,
        )

        resolution_match = re.search(
            r"RESOLUTION=(\d+)x(\d+)",
            line,
        )

        if not audio_match:
            continue

        audio_bitrate = int(audio_match.group(1))

        width = 0
        height = 0

        if resolution_match:
            width = int(resolution_match.group(1))
            height = int(resolution_match.group(2))

        variants.append({
            "audio_bitrate": audio_bitrate,
            "width": width,
            "height": height,
            "url": urljoin(master_url, stream_url),
        })

    if not variants:
        raise RuntimeError(
            "Aucun flux exploitable trouvé dans le master HLS"
        )

    playback_mode = ADDON.getSettingInt("playback_mode")

    if playback_mode == 0:
        # Audio only : meilleur débit audio disponible.
        selected = max(
            variants,
            key=lambda v: v["audio_bitrate"],
        )

        stream_url = re.sub(
            r"-video=\d+",
            "",
            selected["url"],
        )

        xbmc.log(
            f"[Medici] AUDIO selected: "
            f"{selected['audio_bitrate']} bps",
            xbmc.LOGINFO,
        )

        xbmc.log(
            f"[Medici] audio-only URL: {stream_url}",
            xbmc.LOGINFO,
        )

        return stream_url

    # Audio + vidéo
    video_quality = ADDON.getSettingInt("video_quality")

    # 0 = Auto (1080p max)
    # 1 = 1080p
    # 2 = 720p
    # 3 = 480p
    quality_map = {
        1: 1080,
        2: 720,
        3: 480,
    }

    if video_quality == 0:
        video_candidates = [
            v
            for v in variants
            if 0 < v["height"] <= 1080
        ]

        if not video_candidates:
            video_candidates = variants

        selected = max(
            video_candidates,
            key=lambda v: (
                v["height"],
                v["width"],
                v["audio_bitrate"],
            ),
        )

    else:
        target_height = quality_map.get(
            video_quality,
            1080,
        )

        # D'abord chercher exactement la résolution demandée
        exact_candidates = [
            v
            for v in variants
            if v["height"] == target_height
        ]

        if exact_candidates:
            selected = max(
                exact_candidates,
                key=lambda v: (
                    v["width"],
                    v["audio_bitrate"],
                ),
            )

        else:
            # Sinon, prendre la meilleure résolution inférieure
            lower_candidates = [
                v
                for v in variants
                if 0 < v["height"] < target_height
            ]

            if lower_candidates:
                selected = max(
                    lower_candidates,
                    key=lambda v: (
                        v["height"],
                        v["width"],
                        v["audio_bitrate"],
                    ),
                )
            else:
                # Dernier fallback : la plus petite disponible
                selected = min(
                    variants,
                    key=lambda v: (
                        v["height"] if v["height"] > 0 else 99999,
                        v["width"] if v["width"] > 0 else 99999,
                    ),
                )

    xbmc.log(
        f"[Medici] VIDEO selected: "
        f"{selected['width']}x{selected['height']} "
        f"audio={selected['audio_bitrate']} "
        f"url={selected['url']}",
        xbmc.LOGINFO,
    )

    return selected["url"]


# ---------------------------------------------------------------------
# Kodi items
# ---------------------------------------------------------------------

def add_folder(label, query):
    item = xbmcgui.ListItem(
        label=label
    )

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

    display_title = title

    if not online:
        display_title += " [OFFLINE]"

    details = " | ".join(
        value
        for value in [duration_label, year]
        if value
    )

    if details:
        label = f"{display_title} ({details})"
    else:
        label = display_title

    item = xbmcgui.ListItem(label=label)

    if picture:
        item.setArt({
            "thumb": picture,
            "icon": picture,
            "fanart": picture,
        })

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

    if online and slug:
        item.setProperty(
            "IsPlayable",
            "true",
        )

        url = build_url({
            "action": "play",
            "slug": slug,
        })
    else:
        url = ""

    xbmcplugin.addDirectoryItem(
        handle=HANDLE,
        url=url,
        listitem=item,
        isFolder=False,
    )

def add_next_page(query):
    add_folder(
        "Page suivante ▶",
        query,
    )

# ---------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------

def show_root():
    add_folder(
        "★ Favoris",
        {
            "action": "favorites",
            "offset": 0,
        },
    )

    for label, category in CATEGORIES:
        add_folder(
            label,
            {
                "action": "catalog",
                "category": category,
                "offset": 0,
            },
        )

    add_folder(
        "Recherche",
        {
            "action": "search",
        },
    )

    xbmcplugin.endOfDirectory(
        HANDLE
    )


def show_catalog(category, offset=0):
    data = get_catalog(
        category,
        limit=PAGE_SIZE,
        offset=offset,
    )

    movies = data.get(
        "movies",
        {},
    )

    results = movies.get(
        "results",
        [],
    )

    total = data.get(
        "count_total",
        movies.get("count", 0),
    )

    for movie in results:
        add_movie(movie)

    next_offset = offset + len(results)

    if next_offset < total:
        add_next_page({
            "action": "catalog",
            "category": category,
            "offset": next_offset,
        })

    xbmcplugin.endOfDirectory(
        HANDLE
    )


def show_favorites(offset=0):
    data = get_favorites(
        limit=PAGE_SIZE,
        offset=offset,
    )

    movies = data.get(
        "movies",
        {},
    )

    results = movies.get(
        "results",
        [],
    )

    total = data.get(
        "count_total",
        movies.get("count", 0),
    )

    for movie in results:
        add_movie(movie)

    next_offset = offset + len(results)

    if next_offset < total:
        add_next_page({
            "action": "favorites",
            "offset": next_offset,
        })

    xbmcplugin.endOfDirectory(
        HANDLE
    )


def show_search(query=None, offset=0):
    if not query:
        query = xbmcgui.Dialog().input(
            "Recherche Medici.tv",
            type=xbmcgui.INPUT_ALPHANUM,
        )

    query = query.strip()

    if not query:
        xbmcplugin.endOfDirectory(
            HANDLE
        )
        return

    data = global_search(
        query,
        limit=PAGE_SIZE,
        offset=offset,
    )

    movies = data.get(
        "movies",
        {},
    )

    results = movies.get(
        "results",
        [],
    )

    total = movies.get(
        "count",
        len(results),
    )

    for movie in results:
        add_movie(movie)

    next_offset = offset + len(results)

    if next_offset < total:
        add_next_page({
            "action": "search",
            "q": query,
            "offset": next_offset,
        })

    xbmcplugin.endOfDirectory(
        HANDLE
    )


# ---------------------------------------------------------------------
# Playback
# ---------------------------------------------------------------------

def play_movie(slug):
    try:
        movie = get_movie(slug)

        video = movie.get("video")

        if not video:
            raise RuntimeError(
                "Aucune information vidéo disponible"
            )

        master_url = video.get("video_url")

        if not master_url:
            raise RuntimeError(
                "Aucun flux disponible"
            )

        stream_url = get_stream_url(master_url)

        playback_mode = ADDON.getSettingInt("playback_mode")

        title = movie.get("title", "")
        subtitle = movie.get("subtitle", "")
        picture = movie.get("picture", "")
        year = movie.get("production_date", "")
        duration = movie.get("duration", 0)

        item = xbmcgui.ListItem(
            label=title
        )

        item.setPath(
            stream_url
        )

        item.setMimeType(
            "application/vnd.apple.mpegurl"
        )

        if picture:
            item.setArt({
                "thumb": picture,
                "icon": picture,
                "fanart": picture,
            })

        if playback_mode == 0:
            # AUDIO ONLY
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

            xbmc.log(
                f"[Medici] resolving as AUDIO: {stream_url}",
                xbmc.LOGINFO,
            )

        else:
            # AUDIO + VIDEO
            item.setContentLookup(True)

            tag = item.getVideoInfoTag()
            tag.setTitle(title)
            tag.setMediaType("video")

            if subtitle:
                tag.setPlot(subtitle)

            if str(year).isdigit():
                tag.setYear(int(year))

            if duration:
                tag.setDuration(int(duration))

            xbmc.log(
                f"[Medici] resolving as VIDEO: {stream_url}",
                xbmc.LOGINFO,
            )

        xbmcplugin.setResolvedUrl(
            HANDLE,
            True,
            listitem=item,
        )

    except Exception as exc:
        xbmc.log(
            f"[Medici] playback error: {exc!r}",
            xbmc.LOGERROR,
        )

        xbmcgui.Dialog().notification(
            "Medici.tv",
            str(exc),
            xbmcgui.NOTIFICATION_ERROR,
            7000,
        )

        xbmcplugin.setResolvedUrl(
            HANDLE,
            False,
            listitem=xbmcgui.ListItem(),
        )


# ---------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------

def router():
    params = {}

    if len(sys.argv) > 2 and sys.argv[2]:
        parsed = parse_qs(
            sys.argv[2].lstrip("?")
        )

        params = {
            key: values[0]
            for key, values in parsed.items()
        }

    action = params.get(
        "action"
    )

    if not action:
        show_root()
        return

    if action == "catalog":
        category = params.get(
            "category",
            "opera",
        )

        offset = int(
            params.get(
                "offset",
                0,
            )
        )

        show_catalog(
            category,
            offset,
        )
        return

    if action == "favorites":
        offset = int(
            params.get(
                "offset",
                0,
            )
        )

        show_favorites(
            offset,
        )
        return

    if action == "search":
        query = params.get(
            "q"
        )

        offset = int(
            params.get(
                "offset",
                0,
            )
        )

        show_search(
            query,
            offset,
        )
        return

    if action == "play":
        slug = params.get(
            "slug"
        )

        if not slug:
            raise RuntimeError(
                "Slug Medici manquant"
            )

        play_movie(
            slug
        )
        return

    show_root()


if __name__ == "__main__":
    router()
