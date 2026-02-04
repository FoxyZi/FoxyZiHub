import os
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
import logging

logger = logging.getLogger(__name__)

# Для Render: DATABASE_URL будет автоматически предоставлен
DATABASE_URL = os.environ.get('DATABASE_URL', '').replace('postgres://', 'postgresql://')

@contextmanager
def get_db_connection():
    if DATABASE_URL:
        # Используем PostgreSQL на Render
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    else:
        # Локально используем SQLite
        import sqlite3
        conn = sqlite3.connect('bot_database.db', check_same_thread=False)
        conn.row_factory = sqlite3.Row
    
    try:
        yield conn
    finally:
        conn.close()

def init_database():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Проверяем тип базы данных
        if DATABASE_URL:
            # PostgreSQL для Render
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username VARCHAR(255),
                first_name VARCHAR(255),
                last_name VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                message_id INTEGER,
                admin_message_id INTEGER,
                text TEXT,
                is_from_user BOOLEAN,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
            ''')
        else:
            # SQLite для локальной разработки
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                message_id INTEGER,
                admin_message_id INTEGER,
                text TEXT,
                is_from_user BOOLEAN,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
            ''')
        
        conn.commit()
        logger.info("База данных инициализирована")
