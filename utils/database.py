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
            
            # ICT Trade Log
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS ict_trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,         -- "LONG" or "SHORT"
                    entry_price REAL NOT NULL,
                    sl_price REAL NOT NULL,
                    tp_price REAL NOT NULL,
                    exit_price REAL,                 -- NULL until closed
                    exit_reason TEXT,                -- "TAKE_PROFIT" | "STOP_LOSS" | "TIME_STOP" | "MANUAL"
                    confluence_score INTEGER,
                    confluences TEXT,                -- JSON array of confluence names
                    primary_zone TEXT,               -- "FVG" | "OB" | "BREAKER" | "SUPPLY" | "DEMAND"
                    pnl_pips REAL,                   -- PnL in pips
                    net_pnl_usd REAL,
                    closed_at TEXT
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

    def insert_ict_trade(self, timestamp: str, symbol: str, direction: str, entry_price: float, sl_price: float, tp_price: float, confluence_score: int, confluences: List[str], primary_zone: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO ict_trades (timestamp, symbol, direction, entry_price, sl_price, tp_price, confluence_score, confluences, primary_zone)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (timestamp, symbol, direction, entry_price, sl_price, tp_price, confluence_score, json.dumps(confluences), primary_zone))
            conn.commit()
            return cursor.lastrowid

    def update_ict_trade_exit(self, trade_id: int, exit_price: float, exit_reason: str, pnl_pips: float, net_pnl_usd: float, closed_at: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE ict_trades 
                SET exit_price = ?, exit_reason = ?, pnl_pips = ?, net_pnl_usd = ?, closed_at = ?
                WHERE id = ?
            ''', (exit_price, exit_reason, pnl_pips, net_pnl_usd, closed_at, trade_id))
            conn.commit()

# Expose a global instance
db = DatabaseManager()
