import streamlit as st
from youtube_transcript_api import YouTubeTranscriptApi
from urllib.parse import urlparse, parse_qs

# --- Seitenkonfiguration ---
st.set_page_config(page_title="Highlight Clipper", page_icon="🎬")

# --- Titel und Beschreibung ---
st.title("🎬 Highlight Clipper")
st.write(
    "Finde automatisch die besten Momente aus YouTube-Videos "
    "oder Twitch-Streams und mache daraus Clips im Hochformat."
)

st.divider()


# --- Hilfsfunktion: Video-ID aus der URL holen ---
def get_video_id(youtube_url):
    """Holt die Video-ID aus verschiedenen YouTube-URL-Formaten."""
    parsed = urlparse(youtube_url)

    # Format: https://www.youtube.com/watch?v=ABC123
    if "youtube.com" in parsed.netloc:
        query = parse_qs(parsed.query)
        return query.get("v", [None])[0]

    # Format: https://youtu.be/ABC123
    if "youtu.be" in parsed.netloc:
        return parsed.path.lstrip("/")

    return None


# --- Eingabefeld für die URL ---
url = st.text_input(
    "Video- oder Stream-URL",
    placeholder="https://www.youtube.com/watch?v=..."
)

# --- Slider für die Cliplänge ---
clip_laenge = st.slider(
    "Gewünschte Cliplänge (in Sekunden)",
    min_value=10,
    max_value=90,
    value=30,
    step=5
)

# --- Start-Button ---
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
                try:
                    transcript = YouTubeTranscriptApi.get_transcript(
                        video_id,
                        languages=["de", "en"]
                    )

                    st.success(
                        f"✅ Transkript gefunden! "
                        f"{len(transcript)} Textabschnitte geladen."
                    )

                    # Die ersten 10 Abschnitte als Vorschau zeigen
                    st.subheader("Vorschau (erste 10 Abschnitte)")
                    for abschnitt in transcript[:10]:
                        zeit = round(abschnitt["start"])
                        text = abschnitt["text"]
                        st.write(f"**[{zeit}s]** {text}")

                except Exception as e:
                    st.error(
                        "Konnte kein Transkript laden. Mögliche Gründe: "
                        "Das Video hat keine Untertitel, sie sind deaktiviert, "
                        "oder das Video ist privat."
                    )
                    st.caption(f"Technische Details: {e}")
