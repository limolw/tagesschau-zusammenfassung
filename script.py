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
    print("--- SCHRITT 1: SUCHE NACH VIDEO ---")
    api_url = "https://www.tagesschau.de/api2u/news/"
    try:
        response = requests.get(api_url)
        data = response.json()
        
        print("Gefundene Titel in der API:")
        for item in data.get('news', []):
            titel = item.get('title', '')
            print(f"- {titel}")
            
            # Suche nach allem, was 'tagesschau' im Namen hat
            if "tagesschau" in titel.lower():
                video_url = None
                
                # Wir sammeln alle Links aus dem Video-Bereich
                potential_urls = []
                if item.get('video') and item['video'].get('videos'):
                    for v in item['video']['videos']:
                        potential_urls.append(v.get('url', ''))
                
                # Wir suchen in den gesammelten Links nach .mp4
                for url in potential_urls:
                    if ".mp4" in url.lower():
                        video_url = url
                        break
                
                if video_url:
                    # TITEL SÄUBERN: Alles was technisch aussieht (Zahlen, Unterstriche, Endungen) weg
                    # Wir nehmen einfach "Tagesschau" + die Uhrzeit, falls vorhanden
                    sauberer_titel = "Tagesschau"
                    if "20:00" in titel: sauberer_titel = "Tagesschau 20:00 Uhr"
                    elif "14:00" in titel: sauberer_titel = "Tagesschau 14:00 Uhr"
                    elif "17:00" in titel: sauberer_titel = "Tagesschau 17:00 Uhr"
                    else:
                        # Fallback: Erster Teil des Titels vor dem ersten Leerzeichen/Unterstrich
                        sauberer_titel = titel.split(' ')[0].split('_')[0]

                    print(f"ERFOLG! Nehme Video: {sauberer_titel}")
                    print(f"Download-URL: {video_url}")
                    
                    v_res = requests.get(video_url, stream=True)
                    with open(VIDEO_DATEINAME, 'wb') as f:
                        for chunk in v_res.iter_content(chunk_size=8192):
                            f.write(chunk)
                    return sauberer_titel
                    
        raise Exception("Kein Video mit .mp4 Link im Feed gefunden.")
    except Exception as e:
        print(f"Fehler: {e}")
        raise

def analyze_video_with_gemini():
    print("--- SCHRITT 2: KI ANALYSE ---")
    video_file = genai.upload_file(path=VIDEO_DATEINAME)
    print(f"Video hochgeladen ({video_file.name}). Warte auf KI...")
    
    while video_file.state.name == "PROCESSING":
        time.sleep(10)
        video_file = genai.get_file(video_file.name)
    
    model = genai.GenerativeModel(model_name="gemini-3.1-flash-lite-preview")
    prompt = """Analysiere dieses Video der Tagesschau. 
    1. Zusammenfassung der Themen (4-5 Sätze). 
    2. Trenne mit '---VISUELL---'. 
    3. Beschreibung der visuellen Elemente. 
    Antworte auf Deutsch. Nutze Fettdruck mit ** für wichtige Begriffe."""
    
    response = model.generate_content([video_file, prompt])
    genai.delete_file(video_file.name)
    return response.text

def save_and_mail(titel, ergebnis):
    print("--- SCHRITT 3: SPEICHERN ---")
    eintrag = {
        "datum": datetime.now().strftime("%d.%m.%Y"),
        "titel": titel,
        "zusammenfassung": ergebnis.split("---VISUELL---")[0].strip(),
        "visuell": ergebnis.split("---VISUELL---")[1].strip() if "---VISUELL---" in ergebnis else ""
    }
    
    daten = []
    if os.path.exists("data.json"):
        with open("data.json", "r", encoding="utf-8") as f:
            try: daten = json.load(f)
            except: daten = []
    
    # Im Test-Modus lassen wir Duplikate zu, indem wir den Titel mit Zeitstempel versehen, 
    # falls er schon da ist (so kannst du mehrmals testen)
    if any(d["titel"] == titel for d in daten):
        titel = f"{titel} ({datetime.now().strftime('%H:%M')})"
        eintrag["titel"] = titel

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
