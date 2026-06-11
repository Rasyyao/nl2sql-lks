import sqlite3
import re

def clean_mysql_sql(sql_script):
    # Remove conditional comments /*!...*/
    sql_script = re.sub(r'/\*!.*?\*/', '', sql_script, flags=re.DOTALL)
    
    # Remove -- comments
    sql_script = re.sub(r'--.*?\n', '\n', sql_script)
    
    # Remove SET statements
    sql_script = re.sub(r'^\s*SET\s+.*?;\s*$', '', sql_script, flags=re.MULTILINE | re.IGNORECASE)

    # Remove LOCK TABLES and UNLOCK TABLES
    sql_script = re.sub(r'^\s*LOCK\s+TABLES\s+.*?;\s*$', '', sql_script, flags=re.MULTILINE | re.IGNORECASE)
    sql_script = re.sub(r'^\s*UNLOCK\s+TABLES\s*;\s*$', '', sql_script, flags=re.MULTILINE | re.IGNORECASE)

    # Remove ALTER TABLE ... DISABLE/ENABLE KEYS
    sql_script = re.sub(r'^\s*ALTER\s+TABLE\s+.*?(?:DISABLE|ENABLE)\s+KEYS\s*;\s*$', '', sql_script, flags=re.MULTILINE | re.IGNORECASE)

    # Fix CREATE TABLE: remove everything after closing parenthesis (ENGINE=..., CHARSET=..., etc.)
    sql_script = re.sub(r'(\))\s*ENGINE\s*=.*?;', r'\1;', sql_script, flags=re.IGNORECASE | re.DOTALL)

    # Remove AUTO_INCREMENT from column definitions
    sql_script = re.sub(r'\bAUTO_INCREMENT\b', '', sql_script, flags=re.IGNORECASE)

    # Remove COLLATE clauses
    sql_script = re.sub(r'\bCOLLATE\s+\S+', '', sql_script, flags=re.IGNORECASE)

    # Remove CHARACTER SET / CHARSET clauses
    sql_script = re.sub(r'\bCHARACTER\s+SET\s+\S+', '', sql_script, flags=re.IGNORECASE)
    sql_script = re.sub(r'\bCHARSET\s*=\s*\S+', '', sql_script, flags=re.IGNORECASE)

    # Convert ENUM(...) to TEXT (SQLite doesn't support ENUM)
    sql_script = re.sub(r"\bENUM\s*\([^)]*\)", 'TEXT', sql_script, flags=re.IGNORECASE)

    # Remove UNIQUE KEY / KEY index definitions inside CREATE TABLE
    # (keep PRIMARY KEY and CONSTRAINT, remove standalone KEY lines)
    sql_script = re.sub(r',\s*\n\s*(?:UNIQUE\s+)?KEY\s+`?\w+`?\s*\([^)]*\)', '', sql_script, flags=re.IGNORECASE)

    # Convert CONSTRAINT FOREIGN KEY to be ignored (SQLite parses but doesn't enforce)
    # SQLite accepts FOREIGN KEY syntax in CREATE TABLE, so this is usually fine

    # Remove CONSTRAINT ... CHECK (...) — SQLite supports CHECK but syntax may differ
    # Leave it as-is; SQLite 3.25+ supports CHECK constraints

    return sql_script

def load_sql_to_sqlite(sql_file_path, db_file_path):
    conn = sqlite3.connect(db_file_path)
    cursor = conn.cursor()

    try:
        with open(sql_file_path, 'r', encoding='utf-8') as sql_file:
            sql_script = sql_file.read()

        sql_script = clean_mysql_sql(sql_script)

        cursor.executescript(sql_script)
        conn.commit()
        print(f"Successfully imported {sql_file_path} to {db_file_path}")
        
    except Exception as e:
        print(f"An error occurred: {e}")
        conn.rollback()
    finally:
        conn.close()

load_sql_to_sqlite('universitas_lks_2026-04-12.sql', 'universitas_lks_2026-04-12.db')