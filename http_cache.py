import sqlite3
import os
import time
import requests
import urllib.parse
from datetime import datetime, timedelta

CACHE_DB = "arquivo_cache.db"
CACHE_EXPIRY_DAYS = 30
MAX_NETWORK_ATTEMPTS = int(os.environ.get("ARQUIVO_CACHE_MAX_ATTEMPTS", "1"))
CURL_TIMEOUT = int(os.environ.get("ARQUIVO_CACHE_CURL_TIMEOUT", "90"))
USE_CURL_FALLBACK = os.environ.get("ARQUIVO_CACHE_CURL_FALLBACK", "1").strip().lower() in {"1", "true", "yes"}
USE_PUBLIC_PROXIES = os.environ.get("ARQUIVO_USE_PUBLIC_PROXIES", "").strip().lower() in {"1", "true", "yes"}

class CachedResponse:
    def __init__(self, content, status_code, url):
        self.content = content
        self.status_code = status_code
        self.url = url
        self._text = None

    @property
    def text(self):
        if self._text is None:
            self._text = self.content.decode('utf-8', errors='ignore') if self.content else ""
        return self._text

def init_db():
    conn = sqlite3.connect(CACHE_DB)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS http_cache (
            cache_key TEXT PRIMARY KEY,
            url TEXT,
            status_code INTEGER,
            content BLOB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def prune_old_cache():
    try:
        conn = sqlite3.connect(CACHE_DB)
        cursor = conn.cursor()
        expiry_date = (datetime.utcnow() - timedelta(days=CACHE_EXPIRY_DAYS)).strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute("DELETE FROM http_cache WHERE created_at < ?", (expiry_date,))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Cache] Erro ao limpar cache antigo: {e}")

def get_cache_key(url, params=None):
    if params:
        # Sort params to guarantee stable key
        sorted_params = sorted(params.items())
        query_str = urllib.parse.urlencode(sorted_params)
        if '?' in url:
            return f"{url}&{query_str}"
        return f"{url}?{query_str}"
    return url

_PROXIES_CACHE = []
_PROXIES_CACHE_TIME = 0

def get_free_proxies():
    global _PROXIES_CACHE, _PROXIES_CACHE_TIME
    import time
    now = time.time()
    if _PROXIES_CACHE and (now - _PROXIES_CACHE_TIME < 600):
        return _PROXIES_CACHE

    print("[Cache] A obter lista de proxies gratuitas para contornar bloqueio de IP...")
    api_url = "https://api.proxyscrape.com/v4/free-proxy-list/get?request=get_proxies&proxy_format=ipport&format=json&protocol=http&timeout=3000&ssl=yes"
    try:
        res = requests.get(api_url, timeout=8)
        if res.status_code == 200:
            data = res.json()
            proxies = data.get("proxies", [])
            if proxies:
                _PROXIES_CACHE = [f"{p['ip']}:{p['port']}" for p in proxies]
                _PROXIES_CACHE_TIME = now
                print(f"[Cache] Encontradas {len(_PROXIES_CACHE)} proxies públicas.")
                return _PROXIES_CACHE
    except Exception as e:
        print(f"[Cache] Erro ao obter lista de proxies: {e}")
    
    return _PROXIES_CACHE or []


def cached_get(url, params=None, timeout=15):
    if not os.path.exists(CACHE_DB):
        init_db()

    cache_key = get_cache_key(url, params)
    
    # Try reading from cache
    try:
        conn = sqlite3.connect(CACHE_DB)
        cursor = conn.cursor()
        cursor.execute("SELECT status_code, content FROM http_cache WHERE cache_key = ?", (cache_key,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            status_code, content = row
            return CachedResponse(content, status_code, url)
    except Exception as e:
        print(f"[Cache] Erro ao ler base de dados: {e}")

    # Fallback to network
    req = requests.Request('GET', url, params=params)
    prepared = req.prepare()
    full_url = prepared.url

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    
    response = None
    max_attempts = max(1, MAX_NETWORK_ATTEMPTS)
    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            # Tentativa normal com requests
            response = requests.get(url, params=params, headers=headers, timeout=timeout)
            break
        except Exception as e:
            last_error = e
            print(f"[Cache] Falha com requests.get para {full_url} (Tentativa {attempt}/{max_attempts}): {e}.")
            if USE_CURL_FALLBACK:
                print(f"[Cache] A tentar fallback com curl para {full_url}...")
                try:
                    import subprocess
                    import shutil
                    curl_cmd = shutil.which("curl") or shutil.which("curl.exe") or "curl"
                    res = subprocess.run(
                        [curl_cmd, "-k", "-s", "-L", "-A", headers["User-Agent"], full_url],
                        capture_output=True, timeout=max(timeout, CURL_TIMEOUT)
                    )
                    if res.returncode == 0:
                        status = 200 if len(res.stdout) > 0 else 404
                        response = CachedResponse(res.stdout, status, url)
                        break
                except Exception as curl_err:
                    print(f"[Cache] Fallback curl falhou para {full_url}: {curl_err}")
        
        if attempt < max_attempts:
            print(f"[Cache] Aguardando 3 segundos antes da tentativa {attempt + 1}...")
            time.sleep(3)

    if response is None and "arquivo.pt" in url and USE_PUBLIC_PROXIES:
        print("[Cache] Falha na ligação direta ao Arquivo.pt. A tentar rotatividade de proxies públicas...")
        proxies_list = get_free_proxies()
        for idx, proxy_host in enumerate(proxies_list[:15]):
            print(f"[Cache] A tentar via proxy [{idx+1}/{len(proxies_list[:15])}]: {proxy_host}...")
            proxies_dict = {
                "http": f"http://{proxy_host}",
                "https": f"http://{proxy_host}"
            }
            try:
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                res = requests.get(url, params=params, headers=headers, proxies=proxies_dict, verify=False, timeout=8)
                if res.status_code in (200, 404):
                    response = res
                    print(f"[Cache] Sucesso via proxy {proxy_host}! Código: {res.status_code}")
                    break
            except Exception as proxy_err:
                pass

    if response is None:
        raise last_error or requests.exceptions.RequestException(f"Nao foi possivel obter {full_url}")

    # Cache successful or 404 responses
    if response.status_code in (200, 404):
        try:
            conn = sqlite3.connect(CACHE_DB)
            cursor = conn.cursor()
            content_to_save = response.content if hasattr(response, 'content') else response.text.encode('utf-8')
            cursor.execute(
                "INSERT OR REPLACE INTO http_cache (cache_key, url, status_code, content) VALUES (?, ?, ?, ?)",
                (cache_key, full_url, response.status_code, content_to_save)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[Cache] Erro ao gravar resposta no cache: {e}")
            
    # Clean up very old items occasionally
    if random_chance_prune():
        prune_old_cache()

    return response

def random_chance_prune():
    import random
    return random.random() < 0.05
