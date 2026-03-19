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
    print("Frage Tagesschau API ab...")
    api_url = "https://www.tagesschau.de/api2u/news/"
    response = requests.get(api_url)
    data = response.json()
    
    video_url = None
    titel = None

    # Wir suchen nach der 20-Uhr-Sendung oder der aktuellsten Sendung
    for item in data.get('news', []):
        current_title = item.get('title', '')
        # Wir suchen nach "tagesschau 20:00" oder einfach "tagesschau"
        if 'tagesschau' in current_title.lower():
            print(f"Mögliche Sendung gefunden: {current_title}")
            
            # Suche nach dem Video-Stream
            video_url = item.get('streams', {}).get('adaptivestreaming')
            if not video_url and 'video' in item:
                # Falls adaptiv nicht da, nimm das größte verfügbare MP4
                video_url = item['video'].get('videos', [{}])[-1].get('url')
            
            if video_url:
                titel = current_title
                break # Wir haben unser Video gefunden!

    if video_url and titel:
        print(f"Lade Video herunter: {titel}")
        print(f"URL: {video_url}")
        v_res = requests.get(video_url)
        with open(VIDEO_DATEINAME, 'wb') as f:
            f.write(v_res.content)
        return titel
            
    raise Exception("Keine Sendung mit Video-URL in der API gefunden.")

def analyze_video():
    print("Lade Video zu Google Gemini hoch (das kann dauern)...")
    video_file = genai.upload_file(path=VIDEO_DATEINAME)
    
    print(f"Video hochgeladen als: {video_file.name}")
    print("Warte auf KI-Verarbeitung (Gemini schaut sich das Video an)...")
    
    # Warteschleife
    while video_file.state.name == "PROCESSING":
        print(".", end="", flush=True)
        time.sleep(10)
        video_file = genai.get_file(video_file.name)
    
    print("\nVerarbeitung abgeschlossen. Starte Analyse...")
    
    model = genai.GenerativeModel(model_name="gemini-3.1-flash-lite-preview")
    
    prompt = """
    Schau dir diese Tagesschau-Sendung an.
    1. Erstelle eine inhaltliche Zusammenfassung der wichtigsten Nachrichten (ca. 4-5 Sätze).
    2. Trenne dies dann mit '---VISUELL---' ab.
    3. Beschreibe danach detailliert, was im Video visuell zu sehen ist (Sprecher, Kleidung, Grafiken, Einspieler).
    """
    
    response = model.generate_content([video_file, prompt])
    
    # Aufräumen bei Google
    genai.delete_file(video_file.name)
    return response.text

def send_email(titel, text):
    print(f"Sende E-Mail an {MEINE_EMAIL}...")
    headers = {
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "Content-Type": "application/json"
    }
    # Text für HTML formatieren
    html_text = text.replace("---VISUELL---", "<br><hr><strong>Visuelle Beschreibung:</strong><br>")
    html_text = html_text.replace("\n", "<br>")
    
    data = {
        "from": "Tagesschau Bot <onboarding@resend.dev>",
        "to": [MEINE_EMAIL],
        "subject": f"Zusammenfassung: {titel}",
        "html": f"<h2>{titel}</h2><p>{html_text}</p>"
    }
    r = requests.post("https://api.resend.com/emails", headers=headers, json=data)
    print(f"Resend Status: {r.status_code}, Antwort: {r.text}")

def update_website(titel, inhalt_komplett):
    print("Aktualisiere data.json...")
    teile = inhalt_komplett.split("---VISUELL---")
    zusammenfassung = teile[0].strip()
    visuell = teile[1].strip() if len(teile) > 1 else "Keine visuelle Beschreibung verfügbar."

    neuer_eintrag = {
        "datum": datetime.now().strftime("%d.%m.%Y"),
        "titel": titel,
        "zusammenfassung": zusammenfassung,
        "visuell": visuell
    }

    if os.path.exists("data.json"):
        with open("data.json", "r", encoding="utf-8") as f:
            try:
                daten = json.load(f)
            except:
                daten = []
    else:
        daten = []
    
    # Verhindern, dass das exakt gleiche Video mehrfach gespeichert wird
    if any(e["titel"] == titel for e in daten):
        print("Dieses Video wurde bereits verarbeitet.")
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
        print("ALLES ERFOLGREICH ABGESCHLOSSEN!")
    else:
        print("Nichts Neues zu tun.")
except Exception as e:
    print(f"Ein Fehler ist aufgetreten: {e}")
