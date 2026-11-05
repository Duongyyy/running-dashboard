"""Private local SQLite persistence and encrypted Garmin key storage."""
import os, json, sqlite3, stat, secrets
from pathlib import Path
from cryptography.fernet import Fernet

BASE=Path(os.getenv('STRIDE_DATA_DIR',str(Path.home()/'.stride-lab'))).expanduser()
BASE.mkdir(parents=True,exist_ok=True)
try: BASE.chmod(0o700)
except OSError: pass
DB=BASE/'stride.sqlite3'
SECRET=BASE/'local-secret.key'
if not SECRET.exists():
    fd=os.open(SECRET,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'wb') as f: f.write(Fernet.generate_key())
CIPHER=Fernet(SECRET.read_bytes())

def db():
    c=sqlite3.connect(DB,timeout=25)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA journal_mode=WAL')
    return c

def setup():
    with db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, val TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS activities (
          id TEXT PRIMARY KEY, date TEXT, name TEXT, type TEXT,
          distance REAL, duration REAL, elapsed REAL, avg_hr REAL, max_hr REAL,
          ascent REAL, pace REAL, samples BLOB, detail_status TEXT DEFAULT 'pending',
          source TEXT DEFAULT 'garmin', raw TEXT
        );
        CREATE INDEX IF NOT EXISTS act_date ON activities(date);
        CREATE TABLE IF NOT EXISTS records (distance REAL PRIMARY KEY, seconds REAL, date TEXT, description TEXT);
        ''')
    try: DB.chmod(0o600)
    except OSError: pass

setup()

def get_config(k,default=None):
    with db() as c:
        r=c.execute('SELECT val FROM config WHERE key=?',(k,)).fetchone()
    if not r:return default
    try:return json.loads(r['val'])
    except json.JSONDecodeError:return default

def put_config(k,v):
    with db() as c:
        c.execute('INSERT OR REPLACE INTO config(key,val) VALUES (?,?)',(k,json.dumps(v)))

def set_key(value): put_config('garmin_key_encrypted',CIPHER.encrypt(value.encode()).decode())
def get_key():
    val=get_config('garmin_key_encrypted')
    if not val: return os.getenv('GARMIN_PERSONAL_API_KEY')
    try:return CIPHER.decrypt(val.encode()).decode()
    except Exception:return None

def clear_key():
    with db() as c:c.execute("DELETE FROM config WHERE key='garmin_key_encrypted'")
