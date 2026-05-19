import streamlit as st

# --- Seitenkonfiguration ---
st.set_page_config(page_title="Highlight Clipper", page_icon="🎬")

# --- Titel und Beschreibung ---
st.title("🎬 Highlight Clipper")
st.write(
    "Finde automatisch die besten Momente aus YouTube-Videos "
    "oder Twitch-Streams und mache daraus Clips im Hochformat."
)

st.divider()

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
    if url:
        st.success(f"Alles klar! Ich würde jetzt nach Clips von ca. {clip_laenge} Sekunden suchen.")
        st.info("⚙️ Die Analyse-Funktion bauen wir in den nächsten Schritten ein.")
    else:
        st.error("Bitte gib zuerst eine URL ein.")
