import sqlite3
import json
import threading
from typing import Dict, Any, List, Optional
from utils.logger import logger

DB_FILE = "trading_bot.db"

# We use a thread-safe singleton pattern just in case, though async loop mostly runs in one thread.
class DatabaseManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(DatabaseManager, cls).__new__(cls)
                cls._instance._init_db()
            return cls._instance

    def _init_db(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Key-Value store for bot state (paper_equity, current_position JSON)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS bot_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            ''')
            
            # Trade log (replacing trades.csv)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS trade_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    amount_base REAL NOT NULL,
                    entry_price REAL NOT NULL,
                    exit_price REAL NOT NULL,
                    net_pnl REAL NOT NULL
                )
            ''')
            
            conn.commit()

    def get_connection(self):
        # sqlite3 needs check_same_thread=False if used across async calls loosely
        return sqlite3.connect(DB_FILE, check_same_thread=False)

    # --- State Management (Replacing state.json) ---
    def load_state_val(self, key: str) -> Optional[Any]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT value FROM bot_state WHERE key = ?', (key,))
            row = cursor.fetchone()
            if row:
                try:
                    return json.loads(row[0])
                except json.JSONDecodeError:
                    return row[0]
            return None

    def save_state_val(self, key: str, value: Any):
        json_val = json.dumps(value)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO bot_state (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
            ''', (key, json_val))
            conn.commit()

    # --- Trade Logging (Replacing trades.csv) ---
    def insert_trade(self, timestamp: str, symbol: str, side: str, amount_base: float, entry_price: float, exit_price: float, net_pnl: float):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO trade_log (timestamp, symbol, side, amount_base, entry_price, exit_price, net_pnl)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (timestamp, symbol, side, amount_base, entry_price, exit_price, net_pnl))
            conn.commit()

# Expose a global instance
db = DatabaseManager()
