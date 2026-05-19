import streamlit as st
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
)
from urllib.parse import urlparse, parse_qs
import re
import os
import glob
import subprocess

# --- Seitenkonfiguration ---
st.set_page_config(page_title="Highlight Clipper", page_icon="🎬")

st.title("🎬 Highlight Clipper")
st.write(
    "Finde automatisch die besten Momente aus YouTube-Videos "
    "und mache daraus Clips im Hochformat (9:16)."
)
st.caption("🖥️ Lokale Version – läuft auf deinem Rechner.")
st.divider()

# --- Arbeitsordner IM Projektordner ---
PROJEKT_ORDNER = os.path.dirname(os.path.abspath(__file__))
ARBEITS_ORDNER = os.path.join(PROJEKT_ORDNER, "clips_arbeit")
os.makedirs(ARBEITS_ORDNER, exist_ok=True)


# --- Video-ID aus der URL holen ---
def get_video_id(text):
    """Holt die 11-stellige Video-ID aus allen gaengigen YouTube-Formaten."""
    text = text.strip()

    if re.fullmatch(r"[A-Za-z0-9_-]{11}", text):
        return text

    parsed = urlparse(text)
    host = parsed.netloc.lower()
    path = parsed.path

    if "youtu.be" in host:
        candidate = path.lstrip("/").split("/")[0]
        return candidate if _ist_gueltige_id(candidate) else None

    if "youtube.com" in host:
        query = parse_qs(parsed.query)
        if "v" in query:
            candidate = query["v"][0]
            return candidate if _ist_gueltige_id(candidate) else None

        segmente = [s for s in path.split("/") if s]
        if segmente and segmente[0] in ("shorts", "embed", "v"):
            if len(segmente) >= 2:
                candidate = segmente[1]
                return candidate if _ist_gueltige_id(candidate) else None

    return None


def _ist_gueltige_id(kandidat):
    """Prueft, ob ein String eine gueltige 11-stellige YouTube-ID ist."""
    return bool(re.fullmatch(r"[A-Za-z0-9_-]{11}", kandidat))


def format_zeit(sekunden):
    """Macht aus 135 Sekunden den lesbaren String '02:15'."""
    sekunden = int(sekunden)
    return f"{sekunden // 60:02d}:{sekunden % 60:02d}"


# --- Transkript flexibel abrufen ---
def hole_transkript(video_id):
    """Holt ein Transkript flexibel. Rueckgabe: (liste, None) oder
    (None, 'Meldung')."""
    api = YouTubeTranscriptApi()

    try:
        transcript_list = api.list(video_id)
    except TranscriptsDisabled:
        return None, (
            "🚫 Für dieses Video sind Untertitel komplett deaktiviert. "
            "Bitte probiere ein anderes Video."
        )
    except VideoUnavailable:
        return None, (
            "❌ Dieses Video ist nicht verfügbar (privat, gelöscht "
            "oder regional gesperrt)."
        )
    except Exception as e:
        meldung = str(e)
        if "no element found" in meldung:
            return None, (
                "📭 YouTube hat eine leere Antwort geschickt. Bitte "
                "Bibliothek aktualisieren: pip install --upgrade "
                "'youtube-transcript-api>=1.2.0'"
            )
        return None, f"Unerwarteter Fehler beim Auflisten: {meldung}"

    wunsch_sprachen = ["de", "de-DE", "en", "en-US", "en-GB"]
    gewaehltes = None

    try:
        gewaehltes = transcript_list.find_transcript(wunsch_sprachen)
    except NoTranscriptFound:
        gewaehltes = None

    if gewaehltes is None:
        for transcript in transcript_list:
            gewaehltes = transcript
            break

    if gewaehltes is None:
        return None, (
            "🌐 Dieses Video hat laut YouTube keine abrufbaren "
            "Untertitel."
        )

    try:
        daten = gewaehltes.fetch()
        if hasattr(daten, "to_raw_data"):
            roh = daten.to_raw_data()
        else:
            roh = daten
        return roh, None
    except Exception as e:
        return None, (
            f"⚠️ Transkript gefunden, aber Textabruf schlug fehl: {e}"
        )


# --- Signalwörter mit Punktwerten ---
SIGNALWOERTER = {
    "oh mein gott": 3, "oh my god": 3, "was zur hölle": 3, "what the": 3,
    "unglaublich": 3, "wahnsinn": 3, "krass": 3, "heftig": 3, "wtf": 3,
    "lachen": 2, "laughter": 2, "haha": 2, "omg": 2, "wow": 2, "nein": 2,
    "boah": 2, "geil": 2, "hammer": 2, "endlich": 2,
    "achtung": 1, "schau": 1, "guck": 1, "warte": 1, "oh": 1,
}


def analysiere_transkript(transcript):
    """Bewertet jeden Abschnitt und gibt Treffer mit Score > 0 zurueck."""
    bewertete_abschnitte = []
    for abschnitt in transcript:
        text = abschnitt["text"].lower()
        score = 0
        gefundene_signale = []

        for wort, punkte in SIGNALWOERTER.items():
            if wort in text:
                score += punkte
                gefundene_signale.append(wort)

        anzahl_ausrufezeichen = text.count("!")
        if anzahl_ausrufezeichen > 0:
            score += anzahl_ausrufezeichen
            gefundene_signale.append(f"{anzahl_ausrufezeichen}x '!'")

        if text.count("?") >= 2:
            score += 1
            gefundene_signale.append("mehrere '?'")

        if score > 0:
            bewertete_abschnitte.append({
                "start": abschnitt["start"],
                "text": abschnitt["text"],
                "score": score,
                "signale": gefundene_signale,
            })
    return bewertete_abschnitte


# --- Social-Media-Text aus den erkannten Signalen bauen ---
def baue_social_text(highlight):
    """
    Erzeugt aus den erkannten Signalen eine knackige Catchphrase
    plus passende Hashtags. Komplett offline, keine KI/API noetig.
    """
    signale = highlight.get("signale", [])
    signal_text = " ".join(signale).lower()

    # Catchphrase je nach Stimmung der erkannten Signale
    if any(w in signal_text for w in ["haha", "lachen", "laughter"]):
        catchphrase = "😂 Bei dieser Stelle musst du lachen!"
    elif any(w in signal_text for w in ["krass", "heftig", "wahnsinn",
                                        "unglaublich", "wtf"]):
        catchphrase = "🤯 Du wirst nicht glauben, was hier passiert!"
    elif any(w in signal_text for w in ["oh mein gott", "oh my god",
                                        "omg"]):
        catchphrase = "😱 Dieser Moment ist einfach unfassbar!"
    elif any(w in signal_text for w in ["geil", "hammer", "endlich"]):
        catchphrase = "🔥 Dieser Moment ist absolut stark!"
    else:
        catchphrase = "👀 Diesen Moment musst du gesehen haben!"

    hashtags = (
        "#Shorts #Trending #Viral #fyp #foryou "
        "#highlights #funny #clip #reels #tiktok"
    )

    beschreibung = (
        f"{catchphrase}\n\n"
        f"🎬 Automatisch geclippt mit Highlight Clipper\n\n"
        f"{hashtags}"
    )
    return beschreibung


# --- Schritt 6: Clip-Download in GUTER Qualitaet ---
def lade_clip(video_id, start_sekunde, dauer):
    """Laedt einen Ausschnitt in guter Qualitaet (echtes 1080p-Material).
    Gibt (pfad, log_text) zurueck."""
    import yt_dlp

    start = max(0, int(start_sekunde) - 2)
    ende = start + int(dauer) + 2

    basis = f"roh_{video_id}_{start}"
    outtmpl = os.path.join(ARBEITS_ORDNER, basis + ".%(ext)s")
    video_url = f"https://www.youtube.com/watch?v={video_id}"

    for alt in glob.glob(os.path.join(ARBEITS_ORDNER, basis + "*")):
        try:
            os.remove(alt)
        except OSError:
            pass

    log_zeilen = []

    ydl_opts = {
        "format": (
            "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/"
            "bestvideo[height<=1080]+bestaudio/best[height<=1080]"
        ),
        "merge_output_format": "mp4",
        "outtmpl": outtmpl,
        "quiet": True,
        "no_warnings": True,
        "download_ranges": yt_dlp.utils.download_range_func(
            None, [(start, ende)]
        ),
        "force_keyframes_at_cuts": True,
        "logger": _SammelLogger(log_zeilen),
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([video_url])

    treffer = sorted(
        glob.glob(os.path.join(ARBEITS_ORDNER, basis + "*")),
        key=os.path.getsize,
        reverse=True,
    )
    log_text = "\n".join(log_zeilen)

    if not treffer:
        raise FileNotFoundError(
            "yt-dlp hat KEINE Datei erzeugt.\n\n"
            "--- yt-dlp Protokoll ---\n" + log_text
        )

    return treffer[0], log_text


class _SammelLogger:
    """Faengt yt-dlp-Meldungen ein."""
    def __init__(self, ziel_liste):
        self.ziel = ziel_liste

    def debug(self, msg):
        if msg and not msg.startswith("[debug]"):
            self.ziel.append(str(msg))

    def info(self, msg):
        self.ziel.append(str(msg))

    def warning(self, msg):
        self.ziel.append("WARNUNG: " + str(msg))

    def error(self, msg):
        self.ziel.append("FEHLER: " + str(msg))


# --- Schritt 7: 9:16-Schnitt, formatfuellend (echter Center-Crop) ---
def schneide_hochformat(eingabe_pfad):
    """
    Schneidet das Video formatfuellend auf 9:16 (720x1280), OHNE
    schwarze Balken. Der mittlere senkrechte 9:16-Streifen bleibt,
    links/rechts wird abgeschnitten.

    Filterkette:
      crop=ih*9/16:ih  -> mittigen 9:16-Ausschnitt aus dem Bild
      scale=720:1280   -> sauber auf Shorts-Zielgroesse skalieren

    Gibt (ausgabe_pfad, ffmpeg_stderr) zurueck.
    """
    ausgabe_pfad = os.path.join(ARBEITS_ORDNER, "clip_9_16.mp4")

    vf = "crop=ih*9/16:ih,scale=720:1280"

    befehl = [
        "ffmpeg",
        "-y",
        "-i", eingabe_pfad,
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "veryfast",   # schont den Celeron N4500
        "-crf", "23",            # knackig & kompakt (kleiner = besser)
        "-pix_fmt", "yuv420p",   # maximale Abspielkompatibilitaet
        "-c:a", "aac",
        "-b:a", "160k",
        ausgabe_pfad,
    ]

    ergebnis = subprocess.run(befehl, capture_output=True, text=True)

    if ergebnis.returncode != 0:
        raise RuntimeError(
            "ffmpeg-Fehler (returncode "
            f"{ergebnis.returncode}):\n\n{ergebnis.stderr}"
        )

    if not os.path.exists(ausgabe_pfad):
        raise FileNotFoundError(
            "ffmpeg meldete Erfolg, aber keine Datei gefunden.\n\n"
            f"ffmpeg-Ausgabe:\n{ergebnis.stderr}"
        )

    return ausgabe_pfad, ergebnis.stderr


# --- Eingabefeld + Slider ---
url = st.text_input(
    "Video- oder Stream-URL",
    placeholder="https://www.youtube.com/watch?v=..."
)
clip_laenge = st.slider(
    "Gewünschte Cliplänge (in Sekunden)",
    min_value=10, max_value=90, value=30, step=5
)

# --- Suchen-Button ---
if st.button("🚀 Highlights suchen", type="primary"):
    if not url:
        st.error("Bitte gib zuerst eine URL ein.")
    else:
        video_id = get_video_id(url)
        if not video_id:
            st.error("Das sieht nicht nach einer gültigen YouTube-URL aus.")
        else:
            st.info(f"Erkannte Video-ID: `{video_id}`")
            with st.spinner("Hole das Transkript..."):
                transcript, fehler = hole_transkript(video_id)

            if fehler:
                st.warning(fehler)
                st.session_state["transkript_geladen"] = False
            else:
                highlights = analysiere_transkript(transcript)
                highlights.sort(key=lambda h: h["score"], reverse=True)
                st.session_state["video_id"] = video_id
                st.session_state["highlights"] = highlights[:15]
                st.session_state["transkript_geladen"] = True


# --- Ergebnisse anzeigen ---
if st.session_state.get("transkript_geladen"):
    highlights = st.session_state["highlights"]
    video_id = st.session_state["video_id"]

    if not highlights:
        st.warning(
            "🤔 Transkript geladen, aber keine auffälligen Stellen "
            "gefunden. Vielleicht ein ruhiges Video."
        )
    else:
        st.success(f"✅ {len(highlights)} potenzielle Highlights")
        st.divider()

        for i, h in enumerate(highlights, start=1):
            zeit = format_zeit(h["start"])
            with st.container(border=True):
                st.markdown(f"**#{i} · ⏱️ {zeit} · Score {h['score']}**")
                st.write(h["text"])
                st.caption("Signale: " + ", ".join(h["signale"]))

                if st.button(
                    f"🎬 Diesen {clip_laenge}s-Clip in 9:16 erstellen",
                    key=f"clip_{i}"
                ):
                    try:
                        with st.spinner(
                            f"1/2 · Lade Clip bei {zeit} herunter..."
                        ):
                            roh, dl_log = lade_clip(
                                video_id, h["start"], clip_laenge
                            )
                        st.caption(f"📥 Heruntergeladen: `{roh}`")
                    except Exception as e:
                        st.error("❌ Download fehlgeschlagen.")
                        st.code(str(e))
                        st.stop()

                    try:
                        with st.spinner(
                            "2/2 · Schneide & rendere "
                            "(kann auf dem Chromebook etwas dauern)..."
                        ):
                            fertig, ff_log = schneide_hochformat(roh)
                        st.success("✅ Fertiger 9:16-Clip!")
                        st.video(fertig)
                        with open(fertig, "rb") as f:
                            st.download_button(
                                "⬇️ Clip herunterladen",
                                f,
                                file_name=(
                                    "highlight_"
                                    + zeit.replace(":", "-")
                                    + "_9x16.mp4"
                                ),
                                mime="video/mp4",
                                key=f"dl_{i}"
                            )

                        # --- NEU: Social-Media-Beschreibung ---
                        st.markdown("**📱 Fertige Social-Media-Beschreibung**")
                        social_text = baue_social_text(h)
                        st.text_area(
                            "Zum Kopieren (Klick rein → Strg+A → Strg+C):",
                            value=social_text,
                            height=180,
                            key=f"social_{i}"
                        )
                    except Exception as e:
                        st.error("❌ 9:16-Schnitt fehlgeschlagen.")
                        st.code(str(e))
