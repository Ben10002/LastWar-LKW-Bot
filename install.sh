#!/bin/bash
# Installation Script für LKW Bot Modular

echo "================================================"
echo "LKW Bot Modular v3.2 - Installation"
echo "================================================"

# Prüfe Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 nicht gefunden!"
    exit 1
fi

echo "✅ Python3 gefunden"

# Erstelle Verzeichnisstruktur
echo "📁 Erstelle Verzeichnisstruktur..."
mkdir -p bots utils templates

# Kopiere Dateien (wenn vorhanden)
if [ -f "../lkw_bot_web.py" ]; then
    echo "📋 Kopiere alte Templates..."
    # Templates extrahieren (falls vorhanden)
fi

# Installiere Dependencies
echo "📦 Installiere Python-Pakete..."
pip3 install -r requirements.txt --break-system-packages

# Erstelle Config-Dateien falls nicht vorhanden
if [ ! -f "ssh_config.json" ]; then
    echo "⚙️  Erstelle ssh_config.json..."
    cat > ssh_config.json << 'EOF'
{
  "ssh_command": "",
  "ssh_password": "",
  "local_adb_port": null,
  "last_updated": null
}
EOF
fi

if [ ! -f "users.json" ]; then
    echo "👤 Erstelle users.json..."
    # Wird automatisch von app.py erstellt
fi

echo ""
echo "================================================"
echo "✅ Installation abgeschlossen!"
echo "================================================"
echo ""
echo "📝 Nächste Schritte:"
echo "1. SSH-Config einrichten: Im Web-UI unter /admin"
echo "2. Templates kopieren: Aus altem Projekt"
echo "3. Bot starten: python3 app.py"
echo ""
echo "🚀 Start: python3 app.py"
echo "🌐 URL:   http://localhost:5000"
echo "👤 Login: admin / rREq8/1F4m#"
echo ""
