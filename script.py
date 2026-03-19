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

def get_latest_tagesschau_video():
    print("--- SCHRITT 1: SUCHE NACH VIDEO-SENDUNG ---")
    # Wir nutzen den News-Feed, der ist am zuverlässigsten
    api_url = "https://www.tagesschau.de/api2u/news/"
    
    try:
        response = requests.get(api_url)
        data = response.json()
        
        # Wir gehen alle Nachrichten durch
        for item in data.get('news', []):
            titel = item.get('title', '')
            # Wir suchen nach "tagesschau" (egal ob 20 Uhr oder allgemein)
            if "tagesschau" in titel.lower():
                # Prüfen, ob dieses Item ein Video hat
                video_url = None
                
                # Weg A: Direktes Video-Feld
                if item.get('video'):
                    videos = item['video'].get('videos', [])
                    if videos:
                        # Wir nehmen das Video mit der höchsten Qualität (meist das letzte in der Liste)
                        video_url = videos[-1].get('url')
                
                # Weg B: Streaming-Feld (falls A nicht klappt)
                if not video_url and item.get('streams'):
                    video_url = item['streams'].get('adaptivestreaming')

                if video_url:
                    print(f"Gefunden: {titel}")
                    print(f"Lade Video... {video_url}")
                    
                    v_res = requests.get(video_url, stream=True)
                    with open(VIDEO_DATEINAME, 'wb') as f:
                        for chunk in v_res.iter_content(chunk_size=8192):
                            f.write(chunk)
                    
                    print("Download erfolgreich!")
                    return titel
        
        raise Exception("Kein Tagesschau-Video in den aktuellen News gefunden.")
    except Exception as e:
        print(f"Fehler in Schritt 1: {e}")
        raise

def analyze_video_with_gemini():
    print("--- SCHRITT 2: KI ANALYSE ---")
    print("Video wird zu Google Gemini hochgeladen...")
    video_file = genai.upload_file(path=VIDEO_DATEINAME)
    
    print(f"Hochgeladen. Status: {video_file.state.name}")
    while video_file.state.name == "PROCESSING":
        print(".", end="", flush=True)
        time.sleep(10)
        video_file = genai.get_file(video_file.name)
    
    print("\nGemini analysiert jetzt das Video (das dauert)...")
    model = genai.GenerativeModel(model_name="gemini-3.1-flash-lite-preview")
    
    prompt = """
    Analysiere dieses Video der Tagesschau:
    1. Zusammenfassung der wichtigsten Themen (ca. 5 Sätze).
    2. Trennung durch '---VISUELL---'.
    3. Beschreibung der visuellen Elemente (Kleidung der Sprecher, Grafiken im Hintergrund, Orte der Reportagen).
    Antworte auf Deutsch.
    """
    
    response = model.generate_content([video_file, prompt])
    print("KI-Antwort erhalten.")
    
    genai.delete_file(video_file.name)
    return response.text

def save_and_mail(titel, ergebnis):
    print("--- SCHRITT 3: WEBSITE & E-MAIL ---")
    
    # Website-Daten speichern (data.json)
    teile = ergebnis.split("---VISUELL---")
    zusammenfassung = teile[0].strip()
    visuell = teile[1].strip() if len(teile) > 1 else "Keine visuelle Beschreibung."

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
    
    # Nur speichern, wenn wir diesen Titel noch nicht im Archiv haben
    if any(d["titel"] == titel for d in daten):
        print("Diese Sendung ist bereits auf der Website.")
    else:
        daten.append(eintrag)
        with open("data.json", "w", encoding="utf-8") as f:
            json.dump(daten, f, ensure_ascii=False, indent=4)
        print("Website aktualisiert.")

    # E-Mail senden
    print(f"Sende E-Mail an {MEINE_EMAIL}...")
    html_content = f"<h2>{titel}</h2><p>{ergebnis.replace('---VISUELL---', '<br><hr><b>Visuelle Beschreibung:</b><br>').replace(chr(10), '<br>')}</p>"
    
    resend_res = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
        json={
            "from": "Tagesschau Bot <onboarding@resend.dev>",
            "to": [MEINE_EMAIL],
            "subject": f"Zusammenfassung: {titel}",
            "html": html_content
        }
    )
    print(f"Resend Status: {resend_res.status_code}")

# Hauptprogramm starten
try:
    finaler_titel = get_latest_tagesschau_video()
    ki_ergebnis = analyze_video_with_gemini()
    save_and_mail(finaler_titel, ki_ergebnis)
    print("--- FERTIG! ALLES GEKLAPPT! ---")
except Exception as e:
    print(f"FEHLER: {e}")
