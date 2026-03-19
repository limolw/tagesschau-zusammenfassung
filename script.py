import os
import time
import json
import requests
import google.generativeai as genai
from datetime import datetime

# API Keys aus GitHub Secrets laden
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
MEINE_EMAIL = os.getenv("MEINE_EMAIL")

# Gemini konfigurieren
genai.configure(api_key=GEMINI_API_KEY)

VIDEO_DATEINAME = "tagesschau.mp4"

def get_latest_tagesschau():
    print("Suche nach der neuesten 20-Uhr-Sendung in der Mediathek...")
    # Wir fragen die offizielle Tagesschau-API ab
    api_url = "https://www.tagesschau.de/api2u/news/"
    response = requests.get(api_url)
    data = response.json()
    
    # Wir suchen in den Nachrichten nach der Sendung "tagesschau 20:00 Uhr"
    for item in data.get('news', []):
        if 'tagesschau 20:00 Uhr' in item.get('title', '').lower():
            # Wir suchen den Video-Link (MP4)
            video_url = item.get('streams', {}).get('adaptivestreaming')
            # Falls adaptiv nicht da ist, nehmen wir ein direktes MP4
            if not video_url:
                video_url = item.get('video', {}).get('videos', [{}])[-1].get('url')
            
            titel = item.get('title')
            print(f"Video gefunden: {titel}")
            
            # Video herunterladen
            print("Lade Video herunter...")
            v_res = requests.get(video_url)
            with open(VIDEO_DATEINAME, 'wb') as f:
                f.write(v_res.content)
            return titel
            
    raise Exception("Keine aktuelle 20-Uhr-Sendung gefunden.")

def analyze_video():
    print("Lade Video zu Google Gemini hoch...")
    video_file = genai.upload_file(path=VIDEO_DATEINAME)
    
    print("Warte auf KI-Verarbeitung...")
    while video_file.state.name == "PROCESSING":
        time.sleep(5)
        video_file = genai.get_file(video_file.name)
        
    model = genai.GenerativeModel(model_name="gemini-3.1-flash-lite-preview")
    
    prompt = """
    Schau dir diese Tagesschau-Sendung an.
    1. Erstelle eine inhaltliche Zusammenfassung der wichtigsten Nachrichten (ca. 4-5 Sätze).
    2. Trenne dies dann mit '---VISUELL---' ab.
    3. Beschreibe danach detailliert, was im Video visuell zu sehen ist.
    """
    
    response = model.generate_content([video_file, prompt])
    genai.delete_file(video_file.name)
    return response.text

def send_email(titel, text):
    print("Sende E-Mail...")
    headers = {"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"}
    data = {
        "from": "Tagesschau Bot <onboarding@resend.dev>",
        "to": [MEINE_EMAIL],
        "subject": f"Neue Tagesschau: {titel}",
        "html": f"<p>{text.replace('---VISUELL---', '<br><strong>Visuelle Beschreibung:</strong><br>').replace(chr(10), '<br>')}</p>"
    }
    requests.post("https://api.resend.com/emails", headers=headers, json=data)

def update_website(titel, inhalt_komplett):
    print("Speichere Daten...")
    teile = inhalt_komplett.split("---VISUELL---")
    zusammenfassung = teile[0].strip()
    visuell = teile[1].strip() if len(teile) > 1 else "Keine visuelle Beschreibung."

    neuer_eintrag = {
        "datum": datetime.now().strftime("%d.%m.%Y"),
        "titel": titel,
        "zusammenfassung": zusammenfassung,
        "visuell": visuell
    }

    if os.path.exists("data.json"):
        with open("data.json", "r", encoding="utf-8") as f:
            daten = json.load(f)
    else:
        daten = []
    
    if any(e["titel"] == titel for e in daten):
        print("Dieses Video haben wir schon.")
        return False
            
    daten.append(neuer_eintrag)
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, indent=4)
    return True

# --- HAUPTPROGRAMM ---
try:
    titel = get_latest_tagesschau()
    ergebnis = analyze_video()
    if update_website(titel, ergebnis):
        send_email(titel, ergebnis)
        print("FERTIG!")
except Exception as e:
    print(f"Ein Fehler ist aufgetreten: {e}")
