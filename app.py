import streamlit as st
from youtube_transcript_api import YouTubeTranscriptApi
from urllib.parse import urlparse, parse_qs
import re
import os
import tempfile

# --- Seitenkonfiguration ---
st.set_page_config(page_title="Highlight Clipper", page_icon="🎬")

st.title("🎬 Highlight Clipper")
st.write(
    "Finde automatisch die besten Momente aus YouTube-Videos "
    "oder Twitch-Streams und mache daraus Clips im Hochformat."
)
st.divider()


# --- Hilfsfunktion: Video-ID aus der URL holen (UNVERÄNDERT, korrekt) ---
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
    Nutzt den 'download_ranges'-Mechanismus von yt-dlp, damit nur das
    benoetigte Stueck geladen wird -> ressourcenschonend.

    Gibt den Pfad zur fertigen Datei zurueck oder wirft eine Exception.
    """
    import yt_dlp

    start = max(0, int(start_sekunde) - 2)  # 2s Vorlauf als Puffer
    ende = start + int(dauer) + 2           # 2s Nachlauf als Puffer

    # Zielordner: temporaeres Verzeichnis (wird automatisch aufgeraeumt)
    ausgabe_ordner = tempfile.mkdtemp()
    ausgabe_pfad = os.path.join(ausgabe_ordner, "clip.mp4")

    url = f"https://www.youtube.com/watch?v={video_id}"

    ydl_opts = {
        # Nicht zu grosse Auflösung -> spart RAM und Zeit
        "format": "bestvideo[height<=720]+bestaudio/best[height<=720]",
        "outtmpl": ausgabe_pfad,
        "quiet": True,
        "no_warnings": True,
        # DAS ist der Kern: nur diesen Zeitbereich laden
        "download_ranges": yt_dlp.utils.download_range_func(
            None, [(start, ende)]
        ),
        "force_keyframes_at_cuts": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    if not os.path.exists(ausgabe_pfad):
        raise FileNotFoundError(
            "Download lief durch, aber es wurde keine Datei erstellt."
        )
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

# --- Suchen-Button: Ergebnisse im Session-State speichern ---
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
                    transcript = YouTubeTranscriptApi.get_transcript(
                        video_id,
                        languages=["de", "de-DE", "en", "en-US", "en-GB"]
                    )
                    highlights = analysiere_transkript(transcript)
                    highlights.sort(key=lambda h: h["score"], reverse=True)

                    # Im Session-State merken, damit die Clip-Buttons
                    # nach einem Klick nicht alles zuruecksetzen
                    st.session_state["video_id"] = video_id
                    st.session_state["highlights"] = highlights[:15]
                    st.session_state["transkript_geladen"] = True
                except Exception as e:
                    st.session_state["transkript_geladen"] = False
                    st.error("Konnte kein Transkript laden.")
                    st.caption(f"Technische Details: {e}")


# --- Ergebnisse anzeigen (aus Session-State) ---
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

                # Eindeutiger key pro Button ist Pflicht in Streamlit
                if st.button(
                    f"🎬 Diesen {clip_laenge}s-Clip generieren",
                    key=f"clip_{i}"
                ):
                    with st.spinner(
                        f"Lade Clip bei {zeit} herunter... "
                        "(kann etwas dauern)"
                    ):
                        try:
                            pfad = lade_clip(
                                video_id, h["start"], clip_laenge
                            )
                            st.success("✅ Clip erfolgreich geladen!")
                            st.video(pfad)
                            with open(pfad, "rb") as f:
                                st.download_button(
                                    "⬇️ Clip herunterladen",
                                    f,
                                    file_name=f"highlight_{zeit.replace(':','-')}.mp4",
                                    mime="video/mp4",
                                    key=f"dl_{i}"
                                )
                        except Exception as e:
                            st.error(
                                "❌ Download fehlgeschlagen. Das ist auf der "
                                "kostenlosen Cloud leider häufig – meist weil "
                                "YouTube Server-Downloads blockiert."
                            )
                            st.caption(f"Technische Details: {e}")
