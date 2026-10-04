#!/usr/bin/env python3
"""
Malayalam Subtitle Movies by Nandu10 — MEGA catalog addon (catalog only).

Merges Msone + Movie Mirror + Team GOAT into one addon.
Data: mega_data.json (built by crawl_merge.py — rerun it to refresh).

Front page: 3 big tiles (Movies / Series / Documentaries), Nandus-OTT-tile
style. Tapping a tile opens its detail page; genre + language rows for each
section live on the home page below the tiles.

Routes:
  /mega/manifest.json
  /mega/catalog/<type>/<id>.json[?skip=N | /skip=N.json]
  /mega/meta/<type>/<id>.json   (tt..., tmdb:..., mega:..., tile & catalog ids)
"""
import json
import os
import re
from collections import Counter

from flask import Flask, jsonify, request, Response

app = Flask(__name__)

POSTER = "https://image.tmdb.org/t/p/w500"
BG = "https://image.tmdb.org/t/p/w780"

TMDB_GENRES = {
    28: "Action", 12: "Adventure", 16: "Animation", 35: "Comedy", 80: "Crime",
    99: "Documentary", 18: "Drama", 10751: "Family", 14: "Fantasy",
    36: "History", 27: "Horror", 10402: "Music", 9648: "Mystery",
    10749: "Romance", 878: "Science Fiction", 10770: "TV Movie",
    53: "Thriller", 10752: "War", 37: "Western", 10759: "Action & Adventure",
    10762: "Kids", 10763: "News", 10764: "Reality", 10765: "Sci-Fi & Fantasy",
    10766: "Soap", 10767: "Talk", 10768: "War & Politics",
}

LANG_NAMES = {
    "english": "English", "korean": "Korean", "hindi": "Hindi",
    "japanese": "Japanese", "french": "French", "spanish": "Spanish",
    "mandarin": "Mandarin", "telugu": "Telugu", "tamil": "Tamil",
    "malayalam": "Malayalam", "cantonese": "Cantonese",
    "indonesian": "Indonesian", "thai": "Thai", "german": "German",
    "italian": "Italian", "russian": "Russian", "portuguese": "Portuguese",
    "dutch": "Dutch", "swedish": "Swedish", "danish": "Danish",
    "norwegian": "Norwegian", "finnish": "Finnish", "polish": "Polish",
    "turkish": "Turkish", "arabic": "Arabic", "persian": "Persian",
    "urdu": "Urdu", "bengali": "Bengali", "punjabi": "Punjabi",
    "marathi": "Marathi", "kannada": "Kannada", "gujarati": "Gujarati",
    "vietnamese": "Vietnamese", "tagalog": "Tagalog", "filipino": "Filipino",
    "malay": "Malay", "hebrew": "Hebrew", "greek": "Greek",
    "ukrainian": "Ukrainian", "chinese": "Chinese", "czech": "Czech",
    "serbian": "Serbian", "romanian": "Romanian", "hungarian": "Hungarian",
    "dzongkha": "Dzongkha",
}

SITE_LABEL = {"msone": "Msone", "moviemirror": "Movie Mirror",
              "teamgoat": "Team GOAT"}

# Documentary subject buckets: (slug, label, genre_ids, keywords)
DOC_SUBJECTS = [
    ("nature", "Nature & Wildlife", None,
     ["nature", "wildlife", "wild ", "planet", "earth", "ocean", "sea ",
      "seas", "animal", "dinosaur", "jungle", "forest", "bird", "penguin",
      "octopus", "chimpanzee", "lion", "tiger", "bear", "shark", "reef",
      "safari", "attenborough", "antarctica", "amazon", "savanna"]),
    ("history", "History", [36],
     ["history", "historical", "world war", "ancient", "empire",
      "civilization", "dynasty", "kingdom", "medieval"]),
    ("science", "Science & Space", None,
     ["science", "space", "nasa", "universe", "cosmos", "quantum", "physics",
      "technology", "robot", "climate", "astronaut", "moon landing",
      "genetic", "evolution"]),
    ("music", "Music & Arts", [10402],
     ["music", "concert", "band ", "singer", "rock", "jazz", "symphony",
      "opera", "hip hop", "dj "]),
    ("crime", "True Crime", [80],
     ["crime", "murder", "killer", "heist", "mafia", "drug",
      "serial killer", "scam", "fraud", "prison"]),
    ("sports", "Sports", None,
     ["sport", "football", "soccer", "olympic", "fifa", "cricket", "boxing",
      "race", "marathon", "tennis", "golf", "formula 1", "wrestling"]),
    ("biography", "Biography", None,
     ["biograph", "life story", "untold story", "the life of",
      "portrait of"]),
]
DOC_SUBJECT_LABEL = {s: l for s, l, _, _ in DOC_SUBJECTS}
DOC_SUBJECT_LABEL["more"] = "More Documentaries"


def doc_subject(it):
    gids = it.get("genre_ids") or []
    text = ((it.get("name") or "") + " " + (it.get("overview") or "")).lower()
    for slug, _label, gids_match, keywords in DOC_SUBJECTS:
        if gids_match and any(g in gids for g in gids_match):
            return slug
        if any(k in text for k in keywords):
            return slug
    return "more"


TILES = [
    {"tile": "movies", "file": "movies.png", "name": "Movies",
     "desc": "Every movie with Malayalam subtitles — "
             "Msone + Movie Mirror + Team GOAT combined."},
    {"tile": "series", "file": "series.png", "name": "Series",
     "desc": "Every series with Malayalam subtitles — "
             "Msone + Movie Mirror + Team GOAT combined."},
    {"tile": "docs", "file": "docs.png", "name": "Documentaries",
     "desc": "Nature, history, science and more — documentaries with "
             "Malayalam subtitles from all three sites."},
]


# ---------------- data ----------------
_mega_data = None
_mega_defs = None
_mega_hidden_defs = None
_mega_metas = {}
_mega_by_id = None


def _all_cat_defs():
    """All catalogs including hidden (for API lookup)."""
    return mega_catalog_defs() + (_mega_hidden_defs or [])


def mega_load():
    global _mega_data
    if _mega_data is None:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "mega_data.json")
        with open(p, encoding="utf-8") as f:
            _mega_data = json.load(f)
    return _mega_data


def all_items():
    return mega_load().get("items", [])


def is_doc(it):
    return 99 in (it.get("genre_ids") or [])


def lang_name(slug):
    return LANG_NAMES.get(slug, slug.replace("-", " ").replace("_", " ").title())


def mega_catalog_defs():
    """Ordered home-page rows. Cached."""
    global _mega_defs, _mega_hidden_defs
    if _mega_defs is not None:
        return _mega_defs
    items = all_items()
    movies = [it for it in items if it["media"] == "movie"]
    series = [it for it in items if it["media"] == "tv"]
    docs_m = [it for it in movies if is_doc(it)]
    docs_s = [it for it in series if is_doc(it)]

    cats = [
        {"id": "mega_new", "type": "movie", "name": "New Releases",
         "kind": "latest_all"},
        {"id": "mega_latest_movies", "type": "movie",
         "name": "Latest Movies", "kind": "latest", "media": "movie"},
        {"id": "mega_latest_series", "type": "series",
         "name": "Latest Series", "kind": "latest", "media": "tv"},
        {"id": "mega_latest_docs", "type": "movie",
         "name": "Latest Documentaries", "kind": "latest_docs"},
    ]
    # Genre rows grouped: for each genre, Movies then Series then Docs
    mg = Counter(g for it in movies for g in (it.get("genre_ids") or [])
                 if g != 99 and g in TMDB_GENRES)
    sg = Counter(g for it in series for g in (it.get("genre_ids") or [])
                 if g != 99 and g in TMDB_GENRES)
    # All genres sorted by total count
    all_genres = Counter()
    all_genres.update(mg)
    all_genres.update(sg)
    for gid, _ in all_genres.most_common():
        gname = TMDB_GENRES[gid]
        if mg.get(gid):
            cats.append({"id": f"mega_mgenre_{gid}", "type": "movie",
                         "name": f"{gname}: Movies",
                         "kind": "genre", "genre_id": gid, "media": "movie"})
        if sg.get(gid):
            cats.append({"id": f"mega_sgenre_{gid}", "type": "series",
                         "name": f"{gname}: Series",
                         "kind": "genre", "genre_id": gid, "media": "tv"})
    # Language rows grouped similarly
    ml = Counter(it["lang"] for it in movies if it.get("lang"))
    sl = Counter(it["lang"] for it in series if it.get("lang"))
    all_langs = Counter()
    all_langs.update(ml)
    all_langs.update(sl)
    for lang, cnt in all_langs.most_common():
        if cnt < 10:
            continue
        lname = lang_name(lang)
        if ml.get(lang, 0) >= 10:
            cats.append({"id": f"mega_mlang_{lang}", "type": "movie",
                         "name": f"{lname}: Movies",
                         "kind": "lang", "lang": lang, "media": "movie"})
        if sl.get(lang, 0) >= 10:
            cats.append({"id": f"mega_slang_{lang}", "type": "series",
                         "name": f"{lname}: Series",
                         "kind": "lang", "lang": lang, "media": "tv"})
    # ---- Documentaries ----
    ds = Counter(doc_subject(it) for it in docs_m)
    order = [s for s, _, _, _ in DOC_SUBJECTS] + ["more"]
    for slug in order:
        if ds.get(slug):
            cats.append({"id": f"mega_dsub_{slug}", "type": "movie",
                         "name": f"Documentaries: {DOC_SUBJECT_LABEL[slug]}",
                         "kind": "doc_subject", "subject": slug})
    dl = Counter(it["lang"] for it in docs_m if it.get("lang"))
    for lang, cnt in dl.most_common():
        if cnt < 5:
            continue
        cats.append({"id": f"mega_dlang_{lang}", "type": "movie",
                     "name": f"Documentaries: {lang_name(lang)}",
                     "kind": "doc_lang", "lang": lang})
    if docs_s:
        cats.append({"id": "mega_docs_series", "type": "series",
                     "name": "Documentaries: Doc Series",
                     "kind": "docs_series"})
    _mega_defs = cats
    _mega_hidden_defs = []
    return cats


def _items_for_cat(cat):
    items = all_items()
    kind = cat["kind"]
    if kind == "tiles":
        return []
    if kind == "latest_all":
        return items  # pre-sorted newest-first
    if kind == "media":
        # All items sorted A-Z (distinct from Latest which is newest-first)
        items = [it for it in items if it["media"] == cat["media"]]
        return sorted(items, key=lambda x: (x.get("name") or "").lower())
    if kind == "latest":
        return [it for it in items if it["media"] == cat["media"]]
    if kind == "genre":
        return [it for it in items
                if it["media"] == cat["media"]
                and cat["genre_id"] in (it.get("genre_ids") or [])]
    if kind == "lang":
        return [it for it in items
                if it["media"] == cat["media"] and it.get("lang") == cat["lang"]]
    if kind == "latest_docs":
        return [it for it in items
                if it["media"] == "movie" and is_doc(it)]
    if kind == "docs_all":
        items = [it for it in items
                if it["media"] == "movie" and is_doc(it)]
        return sorted(items, key=lambda x: (x.get("name") or "").lower())
    if kind == "doc_subject":
        return [it for it in items
                if it["media"] == "movie" and is_doc(it)
                and doc_subject(it) == cat["subject"]]
    if kind == "doc_lang":
        return [it for it in items
                if it["media"] == "movie" and is_doc(it)
                and it.get("lang") == cat["lang"]]
    if kind == "docs_series":
        return [it for it in items
                if it["media"] == "tv" and is_doc(it)]
    return []


def _to_meta(it):
    disp = it["name"] + (f" / {it['name_ml']}" if it.get("name_ml") else "")
    labels = [SITE_LABEL[s] for s in it.get("sources", []) if s in SITE_LABEL]
    urls = "\n".join(it.get("post_urls", {}).values())
    desc = (it.get("overview") or "")
    desc += ("\n\n\U0001F4DD Malayalam subtitles: " + ", ".join(labels)
             if labels else "")
    if urls:
        desc += "\n" + urls
    return {
        "id": it["card_id"],
        "type": "movie" if it["media"] == "movie" else "series",
        "name": disp,
        "poster": f"{POSTER}{it['poster_path']}" if it.get("poster_path") else None,
        "background": f"{BG}{it['backdrop_path']}" if it.get("backdrop_path") else None,
        "description": desc.strip(),
        "releaseInfo": str(it.get("year") or ""),
        "genres": [TMDB_GENRES[g] for g in (it.get("genre_ids") or [])
                   if g in TMDB_GENRES],
    }


def mega_metas(cid):
    if cid in _mega_metas:
        return _mega_metas[cid]
    cat = next(c for c in _all_cat_defs() if c["id"] == cid)
    metas = [_to_meta(it) for it in _items_for_cat(cat)]
    metas = [m for m in metas if m.get("poster")]
    _mega_metas[cid] = metas
    return metas


def tile_metas():
    base = request.url_root.rstrip("/")
    metas = []
    for t in TILES:
        tid = f"mega:tile_{t['tile']}"
        metas.append({
            "id": tid,
            "type": "movie",
            "name": t["name"],
            "poster": f"{base}/static/tiles/{t['file']}",
            "background": f"{base}/static/tiles/{t['file']}",
            "description": t["desc"],
        })
    return metas


def mega_by_id():
    global _mega_by_id
    if _mega_by_id is None:
        idx = {}
        for it in all_items():
            idx[it["card_id"]] = it
            if it.get("imdb_id"):
                idx[it["imdb_id"]] = it
            if it.get("tmdb_id"):
                idx[f"tmdb:{it['tmdb_id']}"] = it
        _mega_by_id = idx
    return _mega_by_id


def _top_lines(items, n=8):
    return "\n".join(
        f"\u2022 {it['name']}"
        + (f" / {it['name_ml']}" if it.get("name_ml") else "")
        + (f" ({it['year']})" if it.get("year") else "")
        for it in items[:n])


# ---------------- routes ----------------
@app.route("/mega/manifest.json")
def mega_manifest():
    return jsonify({
        "id": "com.megacatalog.malayalam",
        "version": "1.1.1",
        "name": "Malayalam Subtitle Movies by Nandu10",
        "description": "Movies, series & documentaries with Malayalam "
                       "subtitles — Msone + Movie Mirror + Team GOAT "
                       "combined (TMDB metadata)",
        "logo": f"{request.url_root.rstrip('/')}/static/logo.png",
        "types": ["movie", "series"],
        "idPrefixes": ["tt", "tmdb:", "mega:"],
        "resources": ["catalog", "meta"],
        "catalogs": [
            {"type": c["type"], "id": c["id"], "name": c["name"],
             "extra": [{"name": "skip", "isRequired": False},
                       {"name": "search", "isRequired": False}]}
            for c in mega_catalog_defs()
        ],
    })


@app.route("/mega/catalog/<ctype>/<cid>.json")
@app.route("/mega/catalog/<ctype>/<cid>/skip=<int:skip>.json")
@app.route("/mega/catalog/<ctype>/<cid>/search=<path:search>.json")
def mega_catalog(ctype, cid, skip=0, search=None):
    # Handle search as query param too
    if search is None:
        search = request.args.get("search")
    cat = next((c for c in _all_cat_defs() if c["id"] == cid), None)
    if not cat:
        return jsonify({"metas": []}), 404
    try:
        if cat["kind"] == "tiles":
            metas = tile_metas()
        else:
            metas = mega_metas(cid)
        # Filter by search query
        if search:
            q = search.lower()
            metas = [m for m in metas
                     if q in (m.get("name") or "").lower()]
    except Exception as e:
        return jsonify({"metas": [], "error": str(e)}), 502
    if "skip" not in request.view_args:
        try:
            skip = int(request.args.get("skip", "0"))
        except ValueError:
            skip = 0
    return jsonify({"metas": metas[skip:skip + 20]})


@app.route("/mega/meta/<mtype>/<mid>.json")
def mega_meta(mtype, mid):
    base = request.url_root.rstrip("/")
    # 1. tile ids -> section detail pages
    for t in TILES:
        if mid == f"mega:tile_{t['tile']}":
            if t["tile"] == "movies":
                items = [it for it in all_items() if it["media"] == "movie"]
            elif t["tile"] == "series":
                items = [it for it in all_items() if it["media"] == "tv"]
            else:
                items = [it for it in all_items()
                         if it["media"] == "movie" and is_doc(it)]
            return jsonify({"meta": {
                "id": mid,
                "type": "movie",
                "name": t["name"],
                "poster": f"{base}/static/tiles/{t['file']}",
                "background": f"{base}/static/tiles/{t['file']}",
                "description": (f"{t['desc']}\n\n{len(items)} titles."
                                f"\n\nNewest:\n{_top_lines(items)}").strip(),
            }})
    # 2. catalog ids -> catalog-level meta
    cat = next((c for c in _all_cat_defs() if c["id"] == mid), None)
    if cat:
        items = _items_for_cat(cat)
        first = items[0] if items else None
        meta = {
            "id": cat["id"],
            "type": cat["type"],
            "name": cat["name"],
            "poster": (f"{POSTER}{first['poster_path']}"
                       if first and first.get("poster_path") else None),
            "background": (f"{BG}{first['backdrop_path']}"
                           if first and first.get("backdrop_path") else None),
            "description": (f"{len(items)} titles in {cat['name']}."
                            f"\n\nTop titles:\n{_top_lines(items)}").strip(),
        }
        return jsonify({"meta": {k: v for k, v in meta.items() if v}})
    # 3. title ids: tt..., tmdb:..., mega:...
    it = mega_by_id().get(mid)
    if not it:
        return jsonify({"meta": {}})
    meta = _to_meta(it)
    meta = {k: v for k, v in meta.items() if v}
    return jsonify({"meta": meta})


@app.route("/")
def index():
    base = request.host_url.rstrip("/")
    return Response(
        f"""<h2>Malayalam Subtitle Movies by Nandu10 \u2705</h2>
        <p>Install in Stremio / Nuvio:<br>
        <code>{base}/mega/manifest.json</code></p>""",
        mimetype="text/html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
