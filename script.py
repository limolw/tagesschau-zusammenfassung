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

def find_any_mp4(data):
    """Sucht rekursiv in allen Datenfeldern nach einem MP4-Link"""
    if isinstance(data, str):
        if ".mp4" in data.lower() and data.startswith("http"):
            return data
    elif isinstance(data, dict):
        for value in data.values():
            result = find_any_mp4(value)
            if result: return result
    elif isinstance(data, list):
        for item in data:
            result = find_any_mp4(item)
            if result: return result
    return None

def get_latest_tagesschau_video():
    print("--- SCHRITT 1: TIEFENSUCHE NACH VIDEO ---")
    # Wir prüfen zwei verschiedene API-Quellen für maximale Erfolgschance
    urls = [
        "https://www.tagesschau.de/api2u/news/",
        "https://www.tagesschau.de/api2u/channels/"
    ]
    
    for api_url in urls:
        print(f"Prüfe API: {api_url}")
        try:
            response = requests.get(api_url)
            data = response.json()
            
            # Wir suchen in 'news' oder in 'channels'
            items = data.get('news', []) + data.get('channels', [])
            
            for item in items:
                titel = item.get('title', '')
                # Wir suchen nach der großen Sendung (20:00, 14:00 etc.)
                if "tagesschau" in titel.lower() and "100 sekunden" not in titel.lower():
                    
                    # TIEFENSUCHE nach MP4
                    video_url = find_any_mp4(item)
                    
                    if video_url:
                        # Titel säubern
                        sauberer_titel = "Tagesschau"
                        for zeit in ["20:00", "17:00", "14:00", "12:00"]:
                            if zeit in titel: sauberer_titel = f"Tagesschau {zeit} Uhr"
                        
                        print(f"GEFUNDEN: {titel}")
                        print(f"Download-URL: {video_url}")
                        
                        v_res = requests.get(video_url, stream=True)
                        with open(VIDEO_DATEINAME, 'wb') as f:
                            for chunk in v_res.iter_content(chunk_size=8192):
                                f.write(chunk)
                        return sauberer_titel
        except Exception as e:
            print(f"Fehler bei {api_url}: {e}")
            continue
            
    raise Exception("Keine Video-Datei in allen API-Quellen gefunden.")

def analyze_video_with_gemini():
    print("--- SCHRITT 2: KI ANALYSE ---")
    video_file = genai.upload_file(path=VIDEO_DATEINAME)
    print(f"Video hochgeladen. Gemini verarbeitet...")
    
    while video_file.state.name == "PROCESSING":
        time.sleep(10)
        video_file = genai.get_file(video_file.name)
    
    model = genai.GenerativeModel(model_name="gemini-3.1-flash-lite-preview")
    prompt = """Analysiere dieses Video der Tagesschau. 
    1. Zusammenfassung der Themen (ca. 5 Sätze). 
    2. Trenne mit '---VISUELL---'. 
    3. Beschreibung der visuellen Elemente. 
    Antworte auf Deutsch. Nutze Fettdruck mit ** für wichtige Begriffe."""
    
    response = model.generate_content([video_file, prompt])
    genai.delete_file(video_file.name)
    return response.text

def save_and_mail(titel, ergebnis):
    print("--- SCHRITT 3: FINALE ---")
    # Datum von HEUTE nutzen
    heute = datetime.now().strftime("%d.%m.%Y")
    
    eintrag = {
        "datum": heute,
        "titel": titel,
        "zusammenfassung": ergebnis.split("---VISUELL---")[0].strip(),
        "visuell": ergebnis.split("---VISUELL---")[1].strip() if "---VISUELL---" in ergebnis else ""
    }
    
    daten = []
    if os.path.exists("data.json"):
        with open("data.json", "r", encoding="utf-8") as f:
            try: daten = json.load(f)
            except: daten = []
    
    # Immer speichern (mit Uhrzeit im Titel falls nötig)
    zeit_jetzt = datetime.now().strftime("%H:%M")
    eintrag["titel"] = f"{titel} (Update {zeit_jetzt})"
    
    daten.append(eintrag)
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, indent=4)

    print("Sende E-Mail...")
    requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
        json={
            "from": "Tagesschau Bot <onboarding@resend.dev>",
            "to": [MEINE_EMAIL],
            "subject": f"Zusammenfassung: {titel}",
            "html": f"<h2>{titel}</h2><p>{ergebnis.replace(chr(10), '<br>')}</p>"
        }
    )

try:
    t = get_latest_tagesschau_video()
    res = analyze_video_with_gemini()
    save_and_mail(t, res)
    print("--- ALLES ERLEDIGT! ---")
except Exception as e:
    print(f"ABBRUCH: {e}")
