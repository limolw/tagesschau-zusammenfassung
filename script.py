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
    print("--- SCHRITT 1: DETEKTIV-SUCHE NACH VIDEO ---")
    api_url = "https://www.tagesschau.de/api2u/news/"
    
    try:
        response = requests.get(api_url)
        data = response.json()
        
        # Erst mal alle Titel auflisten, damit wir sehen, was da ist
        print("Gefundene Sendungen im Feed:")
        for item in data.get('news', []):
            print(f"- {item.get('title')}")

        video_url = None
        finaler_titel = None

        # Wir suchen in zwei Durchläufen: 
        # 1. Erst nach der 20-Uhr-Sendung
        # 2. Wenn nichts gefunden, nach IRGENDEINER Tagesschau
        for suche_nach in ["20:00", "tagesschau"]:
            print(f"Suche nach: {suche_nach}...")
            for item in data.get('news', []):
                titel = item.get('title', '')
                
                if suche_nach.lower() in titel.lower():
                    # Wir prüfen alle Video-Quellen in diesem Item
                    potential_videos = []
                    
                    # Suche in 'video' -> 'videos'
                    if item.get('video') and item['video'].get('videos'):
                        for v in item['video']['videos']:
                            url = v.get('url', '')
                            if url: potential_videos.append(url)
                    
                    # Suche in 'streams'
                    if item.get('streams'):
                        for key in item['streams']:
                            url = item['streams'][key]
                            if url: potential_videos.append(url)

                    # Jetzt den besten Link aus den potenziellen Videos wählen
                    for url in potential_videos:
                        # Wir nehmen den ersten Link, der .mp4 enthält (egal ob am Ende oder nicht)
                        if ".mp4" in url.lower():
                            video_url = url
                            finaler_titel = titel
                            break
                    
                    if video_url: break
            if video_url: break

        if video_url:
            print(f"ERFOLG! Lade Video: {finaler_titel}")
            print(f"Quelle: {video_url}")
            v_res = requests.get(video_url, stream=True)
            with open(VIDEO_DATEINAME, 'wb') as f:
                for chunk in v_res.iter_content(chunk_size=8192):
                    f.write(chunk)
            return finaler_titel
        
        raise Exception("Keine Video-Datei gefunden. Evtl. sind gerade nur Text-News online.")
    except Exception as e:
        print(f"Fehler in Schritt 1: {e}")
        raise

def analyze_video_with_gemini():
    print("--- SCHRITT 2: KI ANALYSE ---")
    print("Video wird zu Google Gemini hochgeladen...")
    video_file = genai.upload_file(path=VIDEO_DATEINAME)
    
    print(f"Status: {video_file.state.name}")
    while video_file.state.name == "PROCESSING":
        print(".", end="", flush=True)
        time.sleep(10)
        video_file = genai.get_file(video_file.name)
    
    if video_file.state.name != "ACTIVE":
        raise Exception(f"Video konnte nicht aktiviert werden: {video_file.state.name}")
    
    print("\nGemini analysiert jetzt das Video...")
    model = genai.GenerativeModel(model_name="gemini-3.1-flash-lite-preview")
    
    prompt = """
    Analysiere dieses Video der Tagesschau:
    1. Zusammenfassung der wichtigsten Themen (ca. 5 Sätze).
    2. Trennung durch '---VISUELL---'.
    3. Beschreibung der visuellen Elemente (Sprecher, Kleidung, Grafiken, Orte).
    Antworte auf Deutsch.
    """
    
    response = model.generate_content([video_file, prompt])
    genai.delete_file(video_file.name)
    return response.text

def save_and_mail(titel, ergebnis):
    print("--- SCHRITT 3: FINALE ---")
    
    # 1. Website-Speicherung
    eintrag = {
        "datum": datetime.now().strftime("%d.%m.%Y"),
        "titel": titel,
        "zusammenfassung": ergebnis.split("---VISUELL---")[0].strip(),
        "visuell": ergebnis.split("---VISUELL---")[1].strip() if "---VISUELL---" in ergebnis else "Keine visuelle Beschreibung."
    }

    daten = []
    if os.path.exists("data.json"):
        with open("data.json", "r", encoding="utf-8") as f:
            try: daten = json.load(f)
            except: daten = []
    
    if not any(d["titel"] == titel for d in daten):
        daten.append(eintrag)
        with open("data.json", "w", encoding="utf-8") as f:
            json.dump(daten, f, ensure_ascii=False, indent=4)
        print("Website aktualisiert.")

    # 2. E-Mail senden
    print(f"Sende E-Mail an {MEINE_EMAIL}...")
    html_content = f"<h2>{titel}</h2><p>{ergebnis.replace('---VISUELL---', '<br><hr><b>Visuelle Beschreibung:</b><br>').replace(chr(10), '<br>')}</p>"
    
    requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
        json={
            "from": "Tagesschau Bot <onboarding@resend.dev>",
            "to": [MEINE_EMAIL],
            "subject": f"Zusammenfassung: {titel}",
            "html": html_content
        }
    )
    print("E-Mail versendet!")

# Start
try:
    finaler_titel = get_latest_tagesschau_video()
    ki_ergebnis = analyze_video_with_gemini()
    save_and_mail(finaler_titel, ki_ergebnis)
    print("--- ALLES ERFOLGREICH! ---")
except Exception as e:
    print(f"FEHLER: {e}")
