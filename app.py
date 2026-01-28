#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LKW Bot Web Interface - Fixed Version
Version 3.2 - Alle Bugs gefixt
"""

import os
import json
import logging
from flask import Flask, render_template, jsonify, request, session, redirect, url_for
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash

# Import Module
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bots.lkw_bot import LKWBotController
from utils.config import load_ssh_config, save_ssh_config, parse_ssh_command
from utils.users import User, init_users, load_users, save_users, load_user

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('lkw-bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Flask App
app = Flask(__name__)
app.secret_key = 'dein-sehr-geheimer-schluessel-hier-aendern-123!@#'

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user_wrapper(username):
    return load_user(username)

# Initialisiere Benutzer
init_users()

# Bot Instanz
ssh_config = load_ssh_config('ssh_config.json')
lkw_bot = LKWBotController(ssh_config)

# ==================== ROUTES ====================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        users = load_users()
        
        if username in users:
            user_data = users[username]
            if user_data.get('blocked', False):
                error = "Benutzer ist gesperrt"
                return render_template('login.html', error=error)
            
            if check_password_hash(user_data['password'], password):
                user = load_user(username)
                login_user(user)
                logger.info(f"User {username} logged in")
                return redirect(url_for('index'))
        
        error = "Ungültige Anmeldedaten"
        return render_template('login.html', error=error)
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logger.info(f"User {current_user.username} logged out")
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    return render_template('index.html', user=current_user)

# ==================== API ROUTES ====================

@app.route('/api/status')
@login_required
def api_status():
    return jsonify({
        'running': lkw_bot.running,
        'paused': lkw_bot.paused,
        'status': lkw_bot.status,
        'last_action': lkw_bot.last_action,
        'trucks_processed': lkw_bot.trucks_processed,
        'trucks_shared': lkw_bot.trucks_shared,
        'trucks_skipped': lkw_bot.trucks_skipped,
        'adb_connected': lkw_bot.adb_connected,
        'current_user': lkw_bot.current_user
    })

@app.route('/api/start', methods=['POST'])
@login_required
def api_start():
    users = load_users()
    if current_user.username in users and users[current_user.username].get('blocked', False):
        return jsonify({'error': 'User is blocked'}), 403
    
    with lkw_bot.lock:
        # Admin kann immer übernehmen
        if lkw_bot.current_user and lkw_bot.current_user != current_user.username:
            if current_user.role != 'admin':
                return jsonify({'error': f'Bot wird bereits von {lkw_bot.current_user} verwendet'}), 409
            lkw_bot.stop()
        
        lkw_bot.start(current_user.username)
        logger.info(f"Bot started by {current_user.username}")
    
    return jsonify({'success': True})

@app.route('/api/pause', methods=['POST'])
@login_required
def api_pause():
    lkw_bot.pause()
    logger.info(f"Bot paused by {current_user.username}")
    return jsonify({'success': True})

@app.route('/api/stop', methods=['POST'])
@login_required
def api_stop():
    with lkw_bot.lock:
        lkw_bot.stop()
        lkw_bot.current_user = None
        logger.info(f"Bot stopped by {current_user.username}")
    return jsonify({'success': True})

@app.route('/api/settings', methods=['GET', 'POST'])
@login_required
def api_settings():
    if request.method == 'POST':
        users = load_users()
        if current_user.username in users and users[current_user.username].get('blocked', False):
            return jsonify({'error': 'User is blocked'}), 403
        
        data = request.json
        lkw_bot.use_limit = data.get('use_limit', False)
        lkw_bot.strength_limit = float(data.get('strength_limit', 60))
        lkw_bot.use_server_filter = data.get('use_server_filter', False)
        lkw_bot.server_number = data.get('server_number', '49')
        lkw_bot.reset_interval = int(data.get('reset_interval', 15))
        
        # Admin kann immer Sharing-Modus wählen
        if current_user.role == 'admin':
            lkw_bot.share_mode = data.get('share_mode', 'world')
        else:
            user_data = users.get(current_user.username, {})
            if user_data.get('can_choose_share_mode', True):
                lkw_bot.share_mode = data.get('share_mode', 'world')
            else:
                # Erzwungener Modus
                lkw_bot.share_mode = user_data.get('forced_share_mode', 'world')
        
        logger.info(f"Settings changed by {current_user.username}")
        return jsonify({'success': True})
    else:
        users = load_users()
        user_data = users.get(current_user.username, {})
        
        # Admin kann immer wählen
        can_choose = current_user.role == 'admin' or user_data.get('can_choose_share_mode', True)
        forced_mode = user_data.get('forced_share_mode', None) if current_user.role != 'admin' else None
        
        return jsonify({
            'use_limit': lkw_bot.use_limit,
            'strength_limit': lkw_bot.strength_limit,
            'use_server_filter': lkw_bot.use_server_filter,
            'server_number': lkw_bot.server_number,
            'reset_interval': lkw_bot.reset_interval,
            'share_mode': forced_mode if forced_mode and not can_choose else lkw_bot.share_mode,
            'can_choose_share_mode': can_choose,
            'forced_share_mode': forced_mode
        })

@app.route('/api/reset_stats', methods=['POST'])
@login_required
def api_reset_stats():
    lkw_bot.trucks_processed = 0
    lkw_bot.trucks_shared = 0
    lkw_bot.trucks_skipped = 0
    logger.info(f"Stats reset by {current_user.username}")
    return jsonify({'success': True})

# ==================== ADMIN ROUTES ====================

@app.route('/admin')
@login_required
def admin():
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    return render_template('admin.html', user=current_user)

@app.route('/api/admin/ssh_config', methods=['GET', 'POST'])
@login_required
def api_admin_ssh_config():
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    if request.method == 'POST':
        data = request.json
        ssh_command = data.get('ssh_command', '').strip()
        ssh_password = data.get('ssh_password', '').strip()
        
        if not ssh_command:
            return jsonify({'error': 'SSH-Command ist erforderlich'}), 400
        
        parsed = parse_ssh_command(ssh_command)
        if not parsed:
            return jsonify({'error': 'Ungültiger SSH-Command'}), 400
        
        config = {
            'ssh_command': ssh_command,
            'ssh_password': ssh_password,
            'local_adb_port': parsed.get('local_port')
        }
        
        if save_ssh_config(config, 'ssh_config.json'):
            lkw_bot.ssh_config = config
            if lkw_bot.running:
                logger.info("Bot running, restarting SSH tunnel...")
                lkw_bot.close_ssh_tunnel()
                import time
                time.sleep(1)
                lkw_bot.setup_ssh_tunnel()
            logger.info(f"SSH config updated by {current_user.username}")
            return jsonify({'success': True, 'message': 'SSH-Konfiguration gespeichert'})
        else:
            return jsonify({'error': 'Fehler beim Speichern'}), 500
    else:
        config = load_ssh_config('ssh_config.json')
        return jsonify({
            'ssh_command': config.get('ssh_command', ''),
            'ssh_password': config.get('ssh_password', ''),
            'local_adb_port': config.get('local_adb_port'),
            'last_updated': config.get('last_updated', None)
        })

@app.route('/api/admin/test_ssh', methods=['POST'])
@login_required
def api_admin_test_ssh():
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    try:
        lkw_bot.close_ssh_tunnel()
        import time
        time.sleep(1)
        if lkw_bot.setup_ssh_tunnel():
            logger.info(f"SSH test successful by {current_user.username}")
            return jsonify({'success': True, 'message': 'SSH-Tunnel erfolgreich verbunden'})
        else:
            return jsonify({'success': False, 'message': 'Verbindung fehlgeschlagen - Bitte Logs prüfen'}), 400
    except Exception as e:
        logger.error(f"SSH test failed: {e}")
        return jsonify({'success': False, 'message': f'Fehler: {str(e)}'}), 500

@app.route('/api/admin/users')
@login_required
def api_admin_users():
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    users = load_users()
    user_list = []
    for username, data in users.items():
        user_obj = load_user(username)
        user_list.append({
            'username': username,
            'role': data['role'],
            'blocked': data.get('blocked', False),
            'can_choose_share_mode': data.get('can_choose_share_mode', True),
            'forced_share_mode': data.get('forced_share_mode', None),
            'can_use_zombie_bot': user_obj.can_use_zombie_bot if user_obj else False
        })
    return jsonify({'users': user_list})

@app.route('/api/admin/user/toggle_block/<username>', methods=['POST'])
@login_required
def api_admin_toggle_block(username):
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    users = load_users()
    if username in users:
        # Admin kann nicht gesperrt werden
        if users[username].get('role') == 'admin':
            return jsonify({'error': 'Admin kann nicht gesperrt werden'}), 400
        
        users[username]['blocked'] = not users[username].get('blocked', False)
        save_users(users)
        logger.info(f"User {username} block toggled by {current_user.username}")
        return jsonify({'success': True})
    return jsonify({'error': 'User not found'}), 404

@app.route('/api/admin/maintenance', methods=['POST'])
@login_required
def api_admin_maintenance():
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.json
    enabled = data.get('enabled', False)
    lkw_bot.maintenance_mode = enabled
    
    # Speichere in Datei
    try:
        with open('maintenance.json', 'w') as f:
            json.dump({'enabled': enabled}, f)
    except Exception as e:
        logger.error(f"Error saving maintenance mode: {e}")
    
    logger.info(f"Maintenance mode {'enabled' if enabled else 'disabled'} by {current_user.username}")
    return jsonify({'success': True})

# ==================== MAIN ====================

if __name__ == '__main__':
    init_users()
    
    ssh_config = load_ssh_config('ssh_config.json')
    if ssh_config.get('ssh_command'):
        logger.info("SSH-Konfiguration geladen")
    else:
        logger.warning("⚠️  KEINE SSH-KONFIGURATION VORHANDEN!")
    
    logger.info("Starte LKW-Bot Web-Interface v3.2 (Fixed)...")
    app.run(host='0.0.0.0', port=5000, debug=False)