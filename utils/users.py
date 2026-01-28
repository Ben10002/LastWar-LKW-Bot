#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
User Management
"""

import os
import json
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

USERS_FILE = 'users.json'


class User(UserMixin):
    def __init__(self, username, password, role='user', blocked=False, 
                 can_choose_share_mode=True, forced_share_mode=None, 
                 can_use_zombie_bot=False):
        self.id = username
        self.username = username
        self.password = password
        self.role = role
        self.blocked = blocked
        self.can_choose_share_mode = can_choose_share_mode
        self.forced_share_mode = forced_share_mode
        self.can_use_zombie_bot = can_use_zombie_bot


def init_users():
    """Initialisiere Benutzer-Datenbank"""
    if not os.path.exists(USERS_FILE):
        users = {
            'admin': {
                'password': generate_password_hash('rREq8/1F4m#'),
                'role': 'admin',
                'blocked': False,
                'can_choose_share_mode': True,
                'forced_share_mode': None,
                'can_use_zombie_bot': True
            },
            'All4One': {
                'password': generate_password_hash('52B1z_'),
                'role': 'user',
                'blocked': False,
                'can_choose_share_mode': True,
                'forced_share_mode': None,
                'can_use_zombie_bot': False
            },
            'Server39': {
                'password': generate_password_hash('!3Z4d5'),
                'role': 'user',
                'blocked': False,
                'can_choose_share_mode': True,
                'forced_share_mode': None,
                'can_use_zombie_bot': False
            }
        }
        with open(USERS_FILE, 'w') as f:
            json.dump(users, f, indent=2)


def load_users():
    """Lade User-Datenbank"""
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    return {}


def save_users(users):
    """Speichere User-Datenbank"""
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=2)


def load_user(username):
    """User Loader für Flask-Login"""
    users = load_users()
    if username in users:
        user_data = users[username]
        
        has_zombie_access = user_data.get('can_use_zombie_bot', False)
        if user_data.get('role') == 'admin':
            has_zombie_access = True
            
        return User(
            username, 
            user_data['password'], 
            user_data.get('role', 'user'), 
            user_data.get('blocked', False),
            user_data.get('can_choose_share_mode', True),
            user_data.get('forced_share_mode', None),
            has_zombie_access
        )
    return None
