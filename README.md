# LKW Bot - Modulare Version 3.2

## 📁 Projektstruktur

```
LKW_Bot_Modular/
├── app.py                      # Haupt-App (Flask Routes)
├── requirements.txt            # Python Dependencies
├── bots/
│   ├── __init__.py
│   ├── bot_base.py            # Basis-Klasse mit Auto-Reconnect
│   └── lkw_bot.py             # LKW-Bot Logik
├── utils/
│   ├── __init__.py
│   ├── config.py              # SSH-Config Management
│   ├── users.py               # User Management
│   └── translations.py        # Übersetzungen
└── templates/
    ├── login.html
    ├── index.html
    └── admin.html
```

## 🚀 Vorteile der modularen Struktur

### ✅ Übersichtlichkeit
- Jede Datei hat eine klare Aufgabe
- Code ist einfacher zu verstehen und zu warten
- Schnelleres Finden von Bugs

### ✅ Wiederverwendbarkeit
- `bot_base.py` kann für mehrere Bots genutzt werden (LKW + Zombie)
- Utils sind universell einsetzbar

### ✅ Auto-Reconnect eingebaut
- **SSH-Keepalive alle 30 Min** (in bot_base.py)
- **Auto-Retry bei Fehlern** (3 Versuche)
- **Auto-Reconnect nach 3 Fehlern**
- **Kompletter Reset nach 5 Fehlern**

### ✅ Einfaches Erweitern
- Neuer Bot? Einfach von `BotBase` erben!
- Neue Features? Nur die betroffene Datei ändern!

## 📦 Installation

```bash
# Dependencies installieren
pip install -r requirements.txt

# App starten
python app.py
```

## 🔧 Konfiguration

**SSH-Config** (ssh_config.json):
```json
{
  "ssh_command": "ssh -oHostKeyAlgorithms=+ssh-rsa user@host -p 1824 -L 7125:adb-proxy:32599 -Nf",
  "ssh_password": "dein-passwort",
  "local_adb_port": 7125
}
```

## 🎯 Hauptdateien erklärt

### `bot_base.py` (Wichtigste Datei!)
- **Auto-Reconnect Logik**
- SSH-Tunnel Management
- ADB-Verbindung mit Retry
- Keepalive-Thread

### `lkw_bot.py`
- LKW-Bot spezifische Logik
- Template Matching
- OCR für Stärke & Server
- Sharing-Logik

### `app.py`
- Flask Routes
- API Endpoints
- Login Management

## 🔄 Wie Auto-Reconnect funktioniert

1. **SSH-Keepalive-Thread** läuft im Hintergrund
2. Alle **30 Minuten** wird SSH automatisch neu verbunden
3. Bei **Screenshot-Timeout**:
   - 3 Retry-Versuche
   - Nach 3 Fehlern → SSH-Reconnect
4. Bei **5 aufeinanderfolgenden Fehlern**:
   - Kompletter SSH-Reset
   - Error-Counter zurücksetzen

## 🚀 Deployment auf VPS

```bash
# Repository clonen
git clone https://github.com/Ben10002/LastWar-LKW-Bot.git
cd LastWar-LKW-Bot

# Dependencies
pip3 install -r requirements.txt --break-system-packages

# Mit Screen starten
screen -S lkw-bot
python3 app.py
# Strg+A, dann D zum Detachen
```

## 📝 Neue Bots hinzufügen

```python
# bots/neuer_bot.py
from .bot_base import BotBase

class NeuerBot(BotBase):
    def __init__(self, ssh_config):
        super().__init__("Neuer-Bot", ssh_config)
    
    def bot_loop(self):
        # Deine Bot-Logik hier
        self.start_keepalive()  # Keepalive starten!
        
        while self.running:
            # ... Bot-Logik ...
            pass
        
        self.stop_keepalive()
```

## 🐛 Debugging

Logs in: `lkw-bot.log`

Wichtige Log-Meldungen:
- `SSH-Keepalive-Thread gestartet` ✅
- `Preventiver SSH-Tunnel Refresh` ✅
- `3 Fehler - SSH-Reconnect` ⚠️
- `KOMPLETTER RESET` 🔴

## 💡 Tipps

- **Templates Ordner** nicht vergessen! (login.html, index.html, admin.html)
- **rentier_template.png** muss im Root-Verzeichnis sein
- **SSH-Config** vor Start konfigurieren!
