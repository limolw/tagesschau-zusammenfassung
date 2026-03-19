import os
import time
import json
import requests
import google.generativeai as genai
from yt_dlp import YoutubeDL
from datetime import datetime

# API Keys aus GitHub Secrets laden
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
MEINE_EMAIL = os.getenv("MEINE_EMAIL")

# Gemini konfigurieren
genai.configure(api_key=GEMINI_API_KEY)

PLAYLIST_URL = "https://www.youtube.com/playlist?list=PL4A2F331EE86DCC22"
VIDEO_DATEINAME = "tagesschau.mp4"

def get_latest_video():
    print("Suche nach dem neuesten Video...")
    # Lade das Video in niedrigster Qualität herunter (spart Zeit, reicht für KI)
    ydl_opts = {
        'format': 'worst',
        'outtmpl': VIDEO_DATEINAME,
        'playlist_items': '1', # Nur das erste (neueste) Video der Playlist
        'quiet': False
    }
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(PLAYLIST_URL, download=True)
        video_titel = info['entries'][0]['title']
        return video_titel

def analyze_video():
    print("Lade Video zu Google Gemini hoch...")
    video_file = genai.upload_file(path=VIDEO_DATEINAME)
    
    print("Warte, bis Gemini das Video verarbeitet hat...")
    while video_file.state.name == "PROCESSING":
        time.sleep(10)
        video_file = genai.get_file(video_file.name)
        
    if video_file.state.name == "FAILED":
        raise Exception("Video-Verarbeitung fehlgeschlagen.")

    print("Starte KI-Analyse mit gemini-3.1-flash-lite-preview...")
    # HIER: Genau das von dir gewünschte Modell!
    model = genai.GenerativeModel(model_name="gemini-3.1-flash-lite-preview")
    
    prompt = """
    Schau dir diese Tagesschau-Sendung an.
    1. Erstelle eine inhaltliche Zusammenfassung der wichtigsten Nachrichten (ca. 4-5 Sätze).
    2. Trenne dies dann mit '---VISUELL---' ab.
    3. Beschreibe danach detailliert, was im Video visuell zu sehen ist (z.B. Kleidung der Sprecher, gezeigte Grafiken, Orte in den Einspielern).
    """
    
    response = model.generate_content([video_file, prompt])
    
    # Datei bei Google wieder löschen (Aufräumen)
    genai.delete_file(video_file.name)
    
    return response.text

def send_email(titel, text):
    print("Sende E-Mail via Resend...")
    headers = {
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "from": "Tagesschau Bot <onboarding@resend.dev>",
        "to": [MEINE_EMAIL],
        "subject": f"Neue Tagesschau: {titel}",
        "html": f"<p>{text.replace('---VISUELL---', '<br><strong>Visuelle Beschreibung:</strong><br>').replace(chr(10), '<br>')}</p>"
    }
    requests.post("https://api.resend.com/emails", headers=headers, json=data)

def update_website(titel, inhalt_komplett):
    print("Aktualisiere die Website-Datenbank...")
    
    # Text aufteilen in Inhalt und visuelle Beschreibung
    teile = inhalt_komplett.split("---VISUELL---")
    zusammenfassung = teile[0].strip()
    visuell = teile[1].strip() if len(teile) > 1 else "Keine visuelle Beschreibung verfügbar."

    neuer_eintrag = {
        "datum": datetime.now().strftime("%d.%m.%Y"),
        "titel": titel,
        "zusammenfassung": zusammenfassung,
        "visuell": visuell
    }

    # Alte Daten laden
    with open("data.json", "r", encoding="utf-8") as file:
        daten = json.load(file)
    
    # Prüfen, ob das Video schon bearbeitet wurde (Anhand des Titels)
    for eintrag in daten:
        if eintrag["titel"] == titel:
            print("Video wurde bereits an einem anderen Tag verarbeitet. Abbruch.")
            return False
            
    # Neuen Eintrag hinzufügen
    daten.append(neuer_eintrag)
    
    # Speichern
    with open("data.json", "w", encoding="utf-8") as file:
        json.dump(daten, file, ensure_ascii=False, indent=4)
        
    return True

# --- HAUPTPROGRAMM ---
try:
    titel = get_latest_video()
    ergebnis = analyze_video()
    
    if update_website(titel, ergebnis):
        send_email(titel, ergebnis)
        print("Erfolgreich abgeschlossen!")
        
except Exception as e:
    print(f"Ein Fehler ist aufgetreten: {e}")
