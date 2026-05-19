import streamlit as st
from youtube_transcript_api import YouTubeTranscriptApi
from urllib.parse import urlparse, parse_qs
import re
import os
import subprocess
import tempfile

# --- Seitenkonfiguration ---
st.set_page_config(page_title="Highlight Clipper", page_icon="🎬")

st.title("🎬 Highlight Clipper")
st.write(
    "Finde automatisch die besten Momente aus YouTube-Videos "
    "und mache daraus Clips im Hochformat (9:16)."
)
st.caption("🖥️ Lokale Version – läuft auf deinem Rechner.")
st.divider()


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


# --- Transkript robust abrufen (aktuelle API 1.x) ---
def hole_transkript(video_id):
    """Ruft das Transkript mit der aktuellen API-Schreibweise ab."""
    api = YouTubeTranscriptApi()
    sprachen = ["de", "de-DE", "en", "en-US", "en-GB"]
    fetched = api.fetch(video_id, languages=sprachen)
    return fetched.to_raw_data()


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


# --- Schritt 6: Gezielter Clip-Download via yt-dlp ---
def lade_clip(video_id, start_sekunde, dauer):
    """
    Laedt NUR einen kurzen Ausschnitt herunter (nicht das ganze Video).
    Gibt den Pfad zur heruntergeladenen Datei zurueck.
    """
    import yt_dlp

    start = max(0, int(start_sekunde) - 2)
    ende = start + int(dauer) + 2

    ausgabe_ordner = tempfile.mkdtemp()
    roh_pfad = os.path.join(ausgabe_ordner, "roh.mp4")
    video_url = f"https://www.youtube.com/watch?v={video_id}"

    ydl_opts = {
        "format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
        "outtmpl": roh_pfad,
        "quiet": True,
        "no_warnings": True,
        "download_ranges": yt_dlp.utils.download_range_func(
            None, [(start, ende)]
        ),
        "force_keyframes_at_cuts": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([video_url])

    if not os.path.exists(roh_pfad):
        raise FileNotFoundError(
            "Download lief durch, aber es wurde keine Datei erstellt."
        )
    return roh_pfad


# --- Schritt 7: Clip ins 9:16-Hochformat schneiden ---
def schneide_hochformat(eingabe_pfad):
    """
    Wandelt ein Video ins 9:16-Format (1080x1920) um.
    Strategie: das Bild so skalieren, dass es die Hoehe fuellt,
    dann mittig auf 9:16 zuschneiden ('center crop').
    Nutzt ffmpeg direkt ueber die Kommandozeile.
    """
    ausgabe_pfad = eingabe_pfad.replace("roh.mp4", "clip_9_16.mp4")

    # ffmpeg-Filter erklaert:
    #  scale=-2:1920  -> auf Hoehe 1920 skalieren, Breite proportional
    #  crop=1080:1920 -> mittigen 1080-breiten Streifen ausschneiden
    filter_string = (
        "scale=-2:1920,"
        "crop=1080:1920"
    )

    befehl = [
        "ffmpeg",
        "-y",                       # vorhandene Datei ueberschreiben
        "-i", eingabe_pfad,         # Eingabedatei
        "-vf", filter_string,       # der Video-Filter (Skalieren + Croppen)
        "-c:a", "copy",             # Audio unveraendert uebernehmen
        ausgabe_pfad,
    ]

    # capture_output=True faengt Fehlermeldungen von ffmpeg ein
    ergebnis = subprocess.run(
        befehl, capture_output=True, text=True
    )

    if ergebnis.returncode != 0:
        raise RuntimeError(
            "ffmpeg konnte das Video nicht umwandeln.\n"
            f"Meldung: {ergebnis.stderr[-500:]}"
        )

    if not os.path.exists(ausgabe_pfad):
        raise FileNotFoundError("9:16-Datei wurde nicht erstellt.")

    return ausgabe_pfad


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
            with st.spinner("Hole das Transkript..."):
                try:
                    transcript = hole_transkript(video_id)
                    highlights = analysiere_transkript(transcript)
                    highlights.sort(key=lambda h: h["score"], reverse=True)

                    st.session_state["video_id"] = video_id
                    st.session_state["highlights"] = highlights[:15]
                    st.session_state["transkript_geladen"] = True
                except Exception as e:
                    st.session_state["transkript_geladen"] = False
                    st.error(
                        "Konnte kein Transkript laden. Mögliche Gründe: "
                        "keine Untertitel, deaktiviert oder Video privat."
                    )
                    st.caption(f"Technische Details: {e}")


# --- Ergebnisse anzeigen ---
if st.session_state.get("transkript_geladen"):
    highlights = st.session_state["highlights"]
    video_id = st.session_state["video_id"]

    if not highlights:
        st.warning("🤔 Keine auffälligen Stellen gefunden.")
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
                            roh = lade_clip(
                                video_id, h["start"], clip_laenge
                            )

                        with st.spinner(
                            "2/2 · Schneide ins 9:16-Hochformat..."
                        ):
                            fertig = schneide_hochformat(roh)

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
                    except Exception as e:
                        st.error("❌ Etwas ist schiefgelaufen.")
                        st.caption(f"Technische Details: {e}")
