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
        for item in data.get('news', []):
            titel = item.get('title', '')
            if "tagesschau" in titel.lower():
                video_url = None
                if item.get('video') and item['video'].get('videos'):
                    for v_entry in reversed(item['video']['videos']):
                        url = v_entry.get('url', '')
                        if url.lower().endswith('.mp4'):
                            video_url = url
                            break
                if video_url:
                    # TITEL SÄUBERN: Alles nach dem ersten Unterstrich oder Punkt entfernen
                    sauberer_titel = titel.split('_')[0].split('.')[0]
                    # Falls es dann zu kurz ist, lassen wir es, sonst nehmen wir den sauberen Namen
                    if len(sauberer_titel) < 5: sauberer_titel = titel
                    
                    print(f"Lade Video: {sauberer_titel}")
                    v_res = requests.get(video_url, stream=True)
                    with open(VIDEO_DATEINAME, 'wb') as f:
                        for chunk in v_res.iter_content(chunk_size=8192):
                            f.write(chunk)
                    return sauberer_titel
        raise Exception("Keine passende Sendung gefunden.")
    except Exception as e:
        print(f"Fehler: {e}"); raise

def analyze_video_with_gemini():
    print("--- SCHRITT 2: KI ANALYSE ---")
    video_file = genai.upload_file(path=VIDEO_DATEINAME)
    while video_file.state.name == "PROCESSING":
        time.sleep(10)
        video_file = genai.get_file(video_file.name)
    
    model = genai.GenerativeModel(model_name="gemini-3.1-flash-lite-preview")
    prompt = "Analysiere dieses Video der Tagesschau. Erstelle eine Zusammenfassung der Themen (4-5 Sätze). Trenne mit '---VISUELL---'. Beschreibe dann die visuellen Elemente. Antworte auf Deutsch, nutze KEINE Überschriften mit #, sondern nur Fettdruck mit **."
    
    response = model.generate_content([video_file, prompt])
    genai.delete_file(video_file.name)
    return response.text

def save_and_mail(titel, ergebnis):
    print("--- SCHRITT 3: FINALE ---")
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
    
    if not any(d["titel"] == titel for d in daten):
        daten.append(eintrag)
        with open("data.json", "w", encoding="utf-8") as f:
            json.dump(daten, f, ensure_ascii=False, indent=4)

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
    print("ERFOLG!")
except Exception as e:
    print(f"FEHLER: {e}")
