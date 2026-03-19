import os
import time
import json
import requests
import google.generativeai as genai
from datetime import datetime

# API Keys laden
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
MEINE_EMAIL = os.getenv("MEINE_EMAIL")

genai.configure(api_key=GEMINI_API_KEY)
VIDEO_DATEINAME = "tagesschau_video.mp4"

def get_latest_tagesschau_20uhr():
    print("--- SCHRITT 1: SUCHE NACH 20-UHR-SENDUNG ---")
    # Wir nutzen die offizielle API-Schnittstelle für Sendungen
    api_url = "https://www.tagesschau.de/api2u/channels/"
    try:
        response = requests.get(api_url)
        data = response.json()
        
        # Wir suchen in den Kanälen nach der 20-Uhr-Sendung
        for channel in data.get('channels', []):
            title = channel.get('title', '')
            if "20:00" in title:
                # Video-URL finden (wir nehmen das MP4 in mittlerer Qualität)
                video_url = channel.get('video', {}).get('videos', [{}])[-1].get('url')
                if video_url:
                    print(f"Gefunden: {title}")
                    print(f"Download startet: {video_url}")
                    
                    v_res = requests.get(video_url, stream=True)
                    with open(VIDEO_DATEINAME, 'wb') as f:
                        for chunk in v_res.iter_content(chunk_size=8192):
                            f.write(chunk)
                    
                    print("Download abgeschlossen.")
                    return title
        
        raise Exception("Keine 20-Uhr-Sendung in der API gefunden.")
    except Exception as e:
        print(f"Fehler in Schritt 1: {e}")
        raise

def analyze_video_with_gemini():
    print("--- SCHRITT 2: KI ANALYSE ---")
    print("Lade Video zu Google hoch...")
    video_file = genai.upload_file(path=VIDEO_DATEINAME)
    
    print(f"Video-ID: {video_file.name}. Warte auf Gemini...")
    while video_file.state.name == "PROCESSING":
        print(".", end="", flush=True)
        time.sleep(10)
        video_file = genai.get_file(video_file.name)
    
    print("\nVideo bereit. Gemini analysiert jetzt...")
    
    model = genai.GenerativeModel(model_name="gemini-3.1-flash-lite-preview")
    prompt = """
    Analysiere dieses Video der Tagesschau:
    1. Zusammenfassung der wichtigsten Themen (4-5 Sätze).
    2. Trennung durch '---VISUELL---'.
    3. Beschreibung der visuellen Elemente (Studio, Grafiken, gezeigte Orte).
    Antworte auf Deutsch.
    """
    
    response = model.generate_content([video_file, prompt])
    print("Analyse fertig.")
    
    # Aufräumen
    genai.delete_file(video_file.name)
    return response.text

def final_steps(titel, ergebnis):
    print("--- SCHRITT 3: SPEICHERN UND SENDEN ---")
    
    # 1. Speichern für die Website
    teile = ergebnis.split("---VISUELL---")
    zusammenfassung = teile[0].strip()
    visuell = teile[1].strip() if len(teile) > 1 else "Keine Beschreibung."

    eintrag = {
        "datum": datetime.now().strftime("%d.%m.%Y"),
        "titel": titel,
        "zusammenfassung": zusammenfassung,
        "visuell": visuell
    }

    daten = []
    if os.path.exists("data.json"):
        with open("data.json", "r", encoding="utf-8") as f:
            try: daten = json.load(f)
            except: daten = []
    
    # Prüfen ob Titel schon da
    if any(d["titel"] == titel for d in daten):
        print("Dieses Video ist bereits im Archiv.")
        return

    daten.append(eintrag)
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, indent=4)
    print("Website-Daten (data.json) aktualisiert.")

    # 2. E-Mail senden
    print(f"Sende E-Mail an {MEINE_EMAIL}...")
    email_data = {
        "from": "Tagesschau Bot <onboarding@resend.dev>",
        "to": [MEINE_EMAIL],
        "subject": f"Zusammenfassung: {titel}",
        "html": f"<strong>{titel}</strong><br><br>{ergebnis.replace(chr(10), '<br>')}"
    }
    r = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
        json=email_data
    )
    print(f"Resend Antwort: {r.status_code} - {r.text}")

# Hauptprogramm
try:
    sendung_titel = get_latest_tagesschau_20uhr()
    ki_text = analyze_video_with_gemini()
    final_steps(sendung_titel, ki_text)
    print("--- ALLES ERLEDIGT! ---")
except Exception as e:
    print(f"ABBRUCH: {e}")
