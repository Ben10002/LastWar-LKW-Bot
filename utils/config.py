#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Configuration Utils
"""

import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def load_ssh_config(config_file):
    """Lade SSH-Konfiguration aus Datei"""
    import os
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Fehler beim Laden von {config_file}: {e}")
    
    return {
        'ssh_command': '',
        'ssh_password': '',
        'local_adb_port': None,
        'last_updated': None
    }


def save_ssh_config(config, config_file):
    """Speichere SSH-Konfiguration"""
    config['last_updated'] = datetime.now().isoformat()
    try:
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)
        logger.info(f"SSH-Konfiguration gespeichert in {config_file}")
        return True
    except Exception as e:
        logger.error(f"Fehler beim Speichern von {config_file}: {e}")
        return False


def parse_ssh_command(ssh_command):
    """Extrahiere Informationen aus dem SSH-Command"""
    try:
        parts = ssh_command.split()
        local_port = None
        
        for i, part in enumerate(parts):
            if part == '-L' and i + 1 < len(parts):
                tunnel_info = parts[i + 1]
                local_port = tunnel_info.split(':')[0]
                break
        
        if not local_port:
             logger.warning("Konnte Local Port nicht aus SSH-Command extrahieren")
             return None

        return {'local_port': int(local_port)}
    except Exception as e:
        logger.error(f"Fehler beim Parsen des SSH-Commands: {e}")
        return None
