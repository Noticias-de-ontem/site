import argparse
import os
import sys
import json
import random
import requests
from requests.adapters import HTTPAdapter
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from datetime import datetime
import calendar
import re
import ssl
import time


sys.path.insert(0, os.getcwd())
from archive_storage import block_id_for_month_day, load_block, save_block
USE_NVIDIA = True
LOCAL_LLM = None
nvidia_pool = None
NVIDIA_MODEL = None
NVIDIA_KEY_INDEX = 0


def now_local():
    return datetime.now().astimezone()

class LegacySSLAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        ctx.set_ciphers('DEFAULT@SECLEVEL=1')
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        kwargs['ssl_context'] = ctx
        return super(LegacySSLAdapter, self).init_poolmanager(*args, **kwargs)

class MockResponse:
    def __init__(self, content, status_code):
        self.content = content
        self.status_code = status_code
        self.text = content.decode('utf-8', errors='ignore') if content else ""

    def json(self):
        import json
        return json.loads(self.text)

PLAYWRIGHT_INSTANCE = None
PLAYWRIGHT_BROWSER = None
PLAYWRIGHT_CONTEXT = None

def get_playwright_page():
    global PLAYWRIGHT_INSTANCE, PLAYWRIGHT_BROWSER, PLAYWRIGHT_CONTEXT
    if PLAYWRIGHT_INSTANCE is None:
        from playwright.sync_api import sync_playwright
        PLAYWRIGHT_INSTANCE = sync_playwright().start()
        PLAYWRIGHT_BROWSER = PLAYWRIGHT_INSTANCE.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )
        PLAYWRIGHT_CONTEXT = PLAYWRIGHT_BROWSER.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
    return PLAYWRIGHT_CONTEXT.new_page()

import atexit
def cleanup_playwright():
    global PLAYWRIGHT_INSTANCE, PLAYWRIGHT_BROWSER, PLAYWRIGHT_CONTEXT
    if PLAYWRIGHT_CONTEXT:
        try:
            PLAYWRIGHT_CONTEXT.close()
        except Exception:
            pass
        PLAYWRIGHT_CONTEXT = None
    if PLAYWRIGHT_BROWSER:
        try:
            PLAYWRIGHT_BROWSER.close()
        except Exception:
            pass
        PLAYWRIGHT_BROWSER = None
    if PLAYWRIGHT_INSTANCE:
        try:
            PLAYWRIGHT_INSTANCE.stop()
        except Exception:
            pass
        PLAYWRIGHT_INSTANCE = None

atexit.register(cleanup_playwright)

REQUESTS_SESSION = None

def get_requests_session():
    global REQUESTS_SESSION
    if REQUESTS_SESSION is None:
        REQUESTS_SESSION = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=20, pool_maxsize=20)
        REQUESTS_SESSION.mount("https://", adapter)
        REQUESTS_SESSION.mount("http://", adapter)
    return REQUESTS_SESSION

def requests_get(url, timeout=15):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    try:
        session = get_requests_session()
        response = session.get(url, headers=headers, timeout=timeout)
        if response.status_code == 202:
            print(f"[Playwright] Detetado WAF challenge (HTTP 202) para {url}. A tentar contornar com Playwright...")
            page = None
            try:
                page = get_playwright_page()
                page.goto(url, timeout=30000)
                page.wait_for_timeout(3000)
                html_content = page.content()
                

                try:
                    if PLAYWRIGHT_CONTEXT:
                        pw_cookies = PLAYWRIGHT_CONTEXT.cookies()
                        for c in pw_cookies:
                            session.cookies.set(c['name'], c['value'], domain=c['domain'], path=c['path'])
                        print(f"[Playwright] Copiados {len(pw_cookies)} cookies para a sessão requests.")
                except Exception as cookie_err:
                    print(f"[Playwright] Erro ao copiar cookies para a sessão requests: {cookie_err}")
                
                return MockResponse(html_content.encode('utf-8', errors='ignore'), 200)
            except Exception as pe:
                print(f"[Playwright] Falha ao contornar WAF: {pe}")
            finally:
                if page:
                    try:
                        page.close()
                    except Exception:
                        pass
        return response
    except Exception as e:
        err_msg = str(e).lower()
        if "timeout" in err_msg or "time out" in err_msg:
            raise e
        try:
            import subprocess
            import shutil
            curl_cmd = shutil.which("curl") or shutil.which("curl.exe") or "curl"
            res = subprocess.run(
                [curl_cmd, "-k", "-s", "-L", "-A", headers["User-Agent"], url],
                capture_output=True, timeout=min(timeout, 10)
            )
            if res.returncode == 0:
                status = 200 if len(res.stdout) > 0 else 404
                return MockResponse(res.stdout, status)
        except Exception as curl_err:
            print(f"Fallback curl falhou para {url}: {curl_err}")
        raise e

def decompress_response_if_needed(content):
    if content.startswith(b'\x1f\x8b'):
        import gzip
        try:
            return gzip.decompress(content)
        except Exception:
            pass
    return content



def parse_first_url_date(sitemap_url, headers=None):
    try:
        res = requests_get(sitemap_url, timeout=60)
        if res.status_code == 200:
            content = decompress_response_if_needed(res.content)
            root = ET.fromstring(content)
            ns = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
            
            for url_node in root.findall('ns:url', ns)[:15]:
                loc = url_node.find('ns:loc', ns)
                lastmod = url_node.find('ns:lastmod', ns)
                loc_val = (loc.text or "") if loc is not None else ""
                lastmod_val = (lastmod.text or "") if lastmod is not None else ""
                
                match = re.search(r"/(\d{4})/(\d{2})/", loc_val)
                if match:
                    return int(match.group(1)), int(match.group(2))
                
                match2 = re.search(r"/(\d{4})-(\d{2})-(\d{2})", loc_val)
                if match2:
                    return int(match2.group(1)), int(match2.group(2))
                    
                if lastmod_val and len(lastmod_val) >= 7:
                    try:
                        return int(lastmod_val[:4]), int(lastmod_val[5:7])
                    except ValueError:
                        pass
    except Exception:
        pass
    return None

def find_sitemaps_range_for_date(post_sitemaps, target_year, target_month):
    n = len(post_sitemaps)
    target_date = (target_year, target_month)
    memo = {}
    
    def get_date(idx):
        if idx not in memo:
            memo[idx] = parse_first_url_date(post_sitemaps[idx])
        return memo[idx]
        
    start_date = get_date(0)
    end_date = get_date(n - 1)

    if start_date is None:
        start_date = (2018, 7)
    if end_date is None:
        from datetime import datetime
        now_dt = datetime.now()
        end_date = (now_dt.year, now_dt.month)

    def to_months(d):
        return d[0] * 12 + (d[1] - 1)
        
    start_m = to_months(start_date)
    end_m = to_months(end_date)
    target_m = to_months(target_date)
    
    if target_m <= start_m:
        low = 0
        high = min(n - 1, 15)
    elif target_m >= end_m:
        low = max(0, n - 15)
        high = n - 1
    else:
        ratio = (target_m - start_m) / max(1, (end_m - start_m))
        guessed = int(ratio * (n - 1))
        low = max(0, guessed - 100)
        high = min(n - 1, guessed + 100)
        
        low_date = get_date(low)
        high_date = get_date(high)
        if low_date and to_months(low_date) > target_m:
            low = max(0, low - 200)
        if high_date and to_months(high_date) < target_m:
            high = min(n - 1, high + 200)

    first_idx = n
    search_low = low
    search_high = high
    
    while search_low <= search_high:
        mid = (search_low + search_high) // 2
        d = get_date(mid)
        if d is None:
            found = False
            for offset in range(1, 5):
                if mid - offset >= search_low:
                    d = get_date(mid - offset)
                    if d is not None:
                        mid = mid - offset
                        found = True
                        break
                if mid + offset <= search_high:
                    d = get_date(mid + offset)
                    if d is not None:
                        mid = mid + offset
                        found = True
                        break
            if not found:
                search_high = mid - 1
                continue
                
        if d >= target_date:
            first_idx = mid
            search_high = mid - 1
        else:
            search_low = mid + 1

    last_idx = n
    search_low = low
    search_high = high
    
    while search_low <= search_high:
        mid = (search_low + search_high) // 2
        d = get_date(mid)
        if d is None:
            found = False
            for offset in range(1, 5):
                if mid - offset >= search_low:
                    d = get_date(mid - offset)
                    if d is not None:
                        mid = mid - offset
                        found = True
                        break
                if mid + offset <= search_high:
                    d = get_date(mid + offset)
                    if d is not None:
                        mid = mid + offset
                        found = True
                        break
            if not found:
                search_high = mid - 1
                continue
                
        if d > target_date:
            last_idx = mid
            search_high = mid - 1
        else:
            search_low = mid + 1

    start_pos = max(0, first_idx - 1)
    end_pos = min(n - 1, last_idx)
    
    matching_indices = []
    for i in range(start_pos, end_pos + 1):
        d = get_date(i)
        if d and d[0] == target_year and d[1] == target_month:
            matching_indices.append(i)
            
    if not matching_indices:
        return list(range(start_pos, end_pos + 1))
        
    return matching_indices



def get_wp_sitemap_candidates(domain, year, month, day=None):
    candidates = []
    

    sitemap_indices = [
        f"https://{domain}/wp-sitemap.xml",
        f"https://{domain}/sitemap_index.xml",
        f"https://{domain}/sitemap.xml",
        f"https://www.{domain}/wp-sitemap.xml",
        f"https://www.{domain}/sitemap_index.xml",
        f"https://www.{domain}/sitemap.xml"
    ]
    
    post_sitemaps = []
    ns = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
    
    for index_url in sitemap_indices:
        try:
            response = requests_get(index_url)
            if response.status_code != 200:
                continue
            content = decompress_response_if_needed(response.content)
            root = ET.fromstring(content)
            
            for sitemap_node in root.findall('ns:sitemap', ns):
                loc = sitemap_node.find('ns:loc', ns)
                if loc is not None and loc.text:
                    loc_text = loc.text

                    if any(x in loc_text for x in ["wp-sitemap-posts-post-", "post-sitemap", "sitemap.xml?page="]):
                        post_sitemaps.append(loc_text)
            
            if post_sitemaps:
                break
        except Exception:
            pass
            
    if not post_sitemaps:
        return candidates
        

    if any(re.search(r"post-sitemap\d+", url) or re.search(r"page=\d+", url) for url in post_sitemaps):
        def extract_num(url):
            m = re.search(r"(\d+)", url)
            return int(m.group(1)) if m else 0
        try:
            post_sitemaps = sorted(post_sitemaps, key=extract_num)
        except Exception:
            pass
            
    try:
        target_indices = find_sitemaps_range_for_date(post_sitemaps, year, month)
        if not target_indices:
            return candidates
            
        for idx in target_indices:
            sm_url = post_sitemaps[idx]
            sm_res = requests_get(sm_url, timeout=60)
            if sm_res.status_code != 200:
                continue
                
            sm_content = decompress_response_if_needed(sm_res.content)
            sm_root = ET.fromstring(sm_content)
            for url_node in sm_root.findall('ns:url', ns):
                loc_node = url_node.find('ns:loc', ns)
                lastmod_node = url_node.find('ns:lastmod', ns)
                
                loc_val = (loc_node.text or "") if loc_node is not None else ""
                lastmod_val = (lastmod_node.text or "") if lastmod_node is not None else ""
                
                if day is not None:
                    target_date_str = f"/{year}/{month:02d}/{day:02d}/"
                    target_lastmod_prefix = f"{year}-{month:02d}-{day:02d}"
                else:
                    target_date_str = f"/{year}/{month:02d}/"
                    target_lastmod_prefix = f"{year}-{month:02d}-"
                    
                if target_date_str in loc_val or lastmod_val.startswith(target_lastmod_prefix):
                    candidates.append({
                        "url": loc_val,
                        "lastmod": lastmod_val
                    })
    except Exception as e:
        print(f"[{domain}] Erro: {e}")
    return candidates


def get_sicnoticias_candidates(year, month, day=None):
    candidates = []

    if year < 2022:
        return candidates
    try:
        index_url = "https://sicnoticias.pt/sitemap/index.xml"
        res = requests_get(index_url)
        if res.status_code != 200:
            return candidates
        content = decompress_response_if_needed(res.content)
        root = ET.fromstring(content)
        ns = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        

        for sitemap_node in root.findall('ns:sitemap', ns):
            loc = sitemap_node.find('ns:loc', ns)
            if loc is not None and loc.text:
                loc_url = loc.text


                match_recent = re.search(r"/sitemap/(\d{4})/(\d{2})/", loc_url)
                match_old = re.search(r"/sitemap/(\d{4})-(\d{2})\.xml", loc_url)
                
                matched = False
                if match_recent:
                    y, m = int(match_recent.group(1)), int(match_recent.group(2))
                    if y == year and m == month:
                        if day is not None:

                            if f"{year:04d}-{month:02d}-{day:02d}" in loc_url:
                                matched = True
                        else:
                            matched = True
                elif match_old:
                    y, m = int(match_old.group(1)), int(match_old.group(2))
                    if y == year and m == month:
                        matched = True
                        
                if matched:

                    sub_res = requests_get(loc_url)
                    if sub_res.status_code == 200:
                        sub_content = decompress_response_if_needed(sub_res.content)
                        sub_root = ET.fromstring(sub_content)
                        for url_node in sub_root.findall('ns:url', ns):
                            loc_node = url_node.find('ns:loc', ns)
                            lastmod_node = url_node.find('ns:lastmod', ns)
                            loc_val = (loc_node.text or "") if loc_node is not None else ""
                            lastmod_val = (lastmod_node.text or "") if lastmod_node is not None else ""
                            
                            if day is not None:
                                target_prefix = f"{year:04d}-{month:02d}-{day:02d}"
                            else:
                                target_prefix = f"{year:04d}-{month:02d}-"
                                
                            if lastmod_val.startswith(target_prefix):
                                candidates.append({
                                    "url": loc_val,
                                    "lastmod": lastmod_val
                                })
    except Exception as e:
        print(f"[SIC Noticias] Erro: {e}")
    return candidates


def get_cnnportugal_candidates(year, month, day=None):
    candidates = []
    if year < 2021:
        return candidates
    try:
        index_url = "https://cnnportugal.iol.pt/sitemaps/index.xml"
        res = requests_get(index_url)
        if res.status_code == 200:
            content = decompress_response_if_needed(res.content)
            root = ET.fromstring(content)
            ns = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
            for sitemap_node in root.findall('ns:sitemap', ns):
                loc = sitemap_node.find('ns:loc', ns)
                if loc is not None and loc.text:

                    sub_res = requests_get(loc.text)
                    if sub_res.status_code == 200:
                        sub_content = decompress_response_if_needed(sub_res.content)
                        sub_root = ET.fromstring(sub_content)
                        for url_node in sub_root.findall('ns:url', ns):
                            loc_node = url_node.find('ns:loc', ns)
                            lastmod_node = url_node.find('ns:lastmod', ns)
                            loc_val = (loc_node.text or "") if loc_node is not None else ""
                            lastmod_val = (lastmod_node.text or "") if lastmod_node is not None else ""
                            
                            if day is not None:
                                target_prefix = f"{year:04d}-{month:02d}-{day:02d}"
                            else:
                                target_prefix = f"{year:04d}-{month:02d}-"
                                
                            if lastmod_val.startswith(target_prefix):
                                candidates.append({
                                    "url": loc_val,
                                    "lastmod": lastmod_val
                                })
    except Exception as e:
        print(f"[CNN Portugal] Erro: {e}")
    return candidates


def get_rtp_candidates(year, month, day=None):
    candidates = []

    try:
        url = "http://www.rtp.pt/noticias/sitemap"
        res = requests_get(url)
        if res.status_code == 200:
            content = decompress_response_if_needed(res.content)
            root = ET.fromstring(content)
            ns = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
            for url_node in root.findall('.//ns:url', ns):
                loc_node = url_node.find('ns:loc', ns)
                lastmod_node = url_node.find('ns:lastmod', ns)
                loc_val = (loc_node.text or "") if loc_node is not None else ""
                lastmod_val = (lastmod_node.text or "") if lastmod_node is not None else ""
                
                if day is not None:
                    target_prefix = f"{year:04d}-{month:02d}-{day:02d}"
                else:
                    target_prefix = f"{year:04d}-{month:02d}-"
                    
                if lastmod_val.startswith(target_prefix):
                    candidates.append({
                        "url": loc_val,
                        "lastmod": lastmod_val
                    })
    except Exception as e:
        print(f"[RTP] Erro: {e}")
    return candidates


def get_cmjornal_candidates(year, month, day=None):
    candidates = []
    try:
        ns = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        if day is not None:
            url = f"https://www.cmjornal.pt/sitemap?yyyy={year}&mm={month:02d}&dd={day:02d}"
            res = requests_get(url)
            if res.status_code == 200:
                content = decompress_response_if_needed(res.content)
                root = ET.fromstring(content)
                for url_node in root.findall('.//ns:url', ns):
                    loc = url_node.find('ns:loc', ns)
                    lastmod = url_node.find('ns:lastmod', ns)
                    loc_val = (loc.text or "") if loc is not None else ""
                    lastmod_val = (lastmod.text or "") if lastmod is not None else ""
                    candidates.append({
                        "url": loc_val,
                        "lastmod": lastmod_val
                    })
        else:
            num_days = calendar.monthrange(year, month)[1]
            for d in range(1, num_days + 1):
                url = f"https://www.cmjornal.pt/sitemap?yyyy={year}&mm={month:02d}&dd={d:02d}"
                res = requests_get(url)
                if res.status_code == 200:
                    content = decompress_response_if_needed(res.content)
                    root = ET.fromstring(content)
                    for url_node in root.findall('.//ns:url', ns):
                        loc = url_node.find('ns:loc', ns)
                        lastmod = url_node.find('ns:lastmod', ns)
                        loc_val = (loc.text or "") if loc is not None else ""
                        lastmod_val = (lastmod.text or "") if lastmod is not None else ""
                        candidates.append({
                            "url": loc_val,
                            "lastmod": lastmod_val
                        })
    except Exception as e:
        print(f"[CM Jornal] Erro: {e}")
    return candidates


def get_sabado_candidates(year, month, day=None):
    candidates = []
    try:
        ns = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        if day is not None:
            url = f"https://www.sabado.pt/sitemap?yyyy={year}&mm={month:02d}&dd={day:02d}"
            res = requests_get(url)
            if res.status_code == 200:
                content = decompress_response_if_needed(res.content)
                root = ET.fromstring(content)
                for url_node in root.findall('.//ns:url', ns):
                    loc = url_node.find('ns:loc', ns)
                    lastmod = url_node.find('ns:lastmod', ns)
                    loc_val = (loc.text or "").strip()
                    lastmod_val = (lastmod.text or "").strip()
                    candidates.append({
                        "url": loc_val,
                        "lastmod": lastmod_val
                    })
        else:
            num_days = calendar.monthrange(year, month)[1]
            for d in range(1, num_days + 1):
                url = f"https://www.sabado.pt/sitemap?yyyy={year}&mm={month:02d}&dd={d:02d}"
                res = requests_get(url)
                if res.status_code == 200:
                    content = decompress_response_if_needed(res.content)
                    root = ET.fromstring(content)
                    for url_node in root.findall('.//ns:url', ns):
                        loc = url_node.find('ns:loc', ns)
                        lastmod = url_node.find('ns:lastmod', ns)
                        loc_val = (loc.text or "").strip()
                        lastmod_val = (lastmod.text or "").strip()
                        candidates.append({
                            "url": loc_val,
                            "lastmod": lastmod_val
                        })
    except Exception as e:
        print(f"[Sábado] Erro: {e}")
    return candidates


def get_nowcanal_candidates(year, month, day=None):
    candidates = []
    try:
        ns = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        if day is not None:
            url = f"https://www.nowcanal.pt/sitemap?yyyy={year}&mm={month:02d}&dd={day:02d}"
            res = requests_get(url)
            if res.status_code == 200:
                content = decompress_response_if_needed(res.content)
                root = ET.fromstring(content)
                for url_node in root.findall('.//ns:url', ns):
                    loc = url_node.find('ns:loc', ns)
                    lastmod = url_node.find('ns:lastmod', ns)
                    loc_val = (loc.text or "").strip()
                    lastmod_val = (lastmod.text or "").strip()
                    candidates.append({
                        "url": loc_val,
                        "lastmod": lastmod_val
                    })
        else:
            num_days = calendar.monthrange(year, month)[1]
            for d in range(1, num_days + 1):
                url = f"https://www.nowcanal.pt/sitemap?yyyy={year}&mm={month:02d}&dd={d:02d}"
                res = requests_get(url)
                if res.status_code == 200:
                    content = decompress_response_if_needed(res.content)
                    root = ET.fromstring(content)
                    for url_node in root.findall('.//ns:url', ns):
                        loc = url_node.find('ns:loc', ns)
                        lastmod = url_node.find('ns:lastmod', ns)
                        loc_val = (loc.text or "").strip()
                        lastmod_val = (lastmod.text or "").strip()
                        candidates.append({
                            "url": loc_val,
                            "lastmod": lastmod_val
                        })
    except Exception as e:
        print(f"[Now Canal] Erro: {e}")
    return candidates


def get_sapo_candidates(year, month, day=None):
    candidates = []
    try:
        index_url = "https://sitemaps.sapo.pt/sitemaps/24pt/sitemapindex-24pt.xml.gz"
        res = requests_get(index_url)
        if res.status_code == 200:
            content = decompress_response_if_needed(res.content)
            root = ET.fromstring(content)
            ns = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
            
            for sitemap_node in root.findall('ns:sitemap', ns):
                loc = sitemap_node.find('ns:loc', ns)
                if loc is not None and loc.text:
                    loc_url = loc.text


                    match = re.search(r"sitemap_24pt_(\d{4})", loc_url)
                    if match and int(match.group(1)) == year:
                        sub_res = requests_get(loc_url)
                        if sub_res.status_code == 200:
                            sub_content = decompress_response_if_needed(sub_res.content)
                            sub_root = ET.fromstring(sub_content)
                            for url_node in sub_root.findall('ns:url', ns):
                                loc_node = url_node.find('ns:loc', ns)
                                lastmod_node = url_node.find('ns:lastmod', ns)
                                loc_val = (loc_node.text or "") if loc_node is not None else ""
                                lastmod_val = (lastmod_node.text or "") if lastmod_node is not None else ""
                                
                                if day is not None:
                                    target_prefix = f"{year:04d}-{month:02d}-{day:02d}"
                                else:
                                    target_prefix = f"{year:04d}-{month:02d}-"
                                    
                                if lastmod_val.startswith(target_prefix):
                                    candidates.append({
                                        "url": loc_val,
                                        "lastmod": lastmod_val
                                    })
    except Exception as e:
        print(f"[SAPO 24] Erro: {e}")
    return candidates


def get_4gnews_candidates(year, month, day=None):
    candidates = []
    try:
        url = f"https://4gnews.pt/sitemap_articles_{year}.xml"
        res = requests_get(url)
        if res.status_code == 200:
            content = decompress_response_if_needed(res.content)
            root = ET.fromstring(content)
            ns = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
            for url_node in root.findall('.//ns:url', ns):
                loc = url_node.find('ns:loc', ns)
                lastmod = url_node.find('ns:lastmod', ns)
                loc_val = (loc.text or "") if loc is not None else ""
                lastmod_val = (lastmod.text or "") if lastmod is not None else ""
                
                if day is not None:
                    target_prefix = f"{year:04d}-{month:02d}-{day:02d}"
                else:
                    target_prefix = f"{year:04d}-{month:02d}-"
                    
                if lastmod_val.startswith(target_prefix):
                    candidates.append({
                        "url": loc_val,
                        "lastmod": lastmod_val
                    })
    except Exception as e:
        print(f"[4gnews] Erro: {e}")
    return candidates





def get_sitemap_candidates(lang, year, month, day):
    candidates = []
    if lang == "pt":
        headers = {"User-Agent": "NewsArchiveBot/1.0"}
        sitemap_sources = {
            "publico": {
                "name": "Público",
                "url_template": "https://www.publico.pt/sitemaps/articles/{year}-{month}.xml",
            },
            "expresso": {
                "name": "Expresso",
                "url_template": "https://expresso.pt/sitemap/{year}-{month}.xml",
            }
        }
        for source_key, info in sitemap_sources.items():
            if year >= 2001:
                url = info["url_template"].format(year=year, month=month)
                name = info["name"]
                try:
                    response = requests_get(url)
                    if response.status_code == 200:
                        content = decompress_response_if_needed(response.content)
                        root = ET.fromstring(content)
                        ns = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
                        
                        if day is not None:
                            target_date_str = f"/{year}/{month:02d}/{day:02d}/"
                            target_lastmod_prefix = f"{year}-{month:02d}-{day:02d}"
                        else:
                            target_date_str = f"/{year}/{month:02d}/"
                            target_lastmod_prefix = f"{year}-{month:02d}-"
                        
                        for url_node in root.findall('ns:url', ns):
                            loc = url_node.find('ns:loc', ns)
                            lastmod = url_node.find('ns:lastmod', ns)
                            if loc is not None and loc.text:
                                loc_val = loc.text
                                lastmod_val = (lastmod.text or "") if lastmod is not None else ""
                                if target_date_str in loc_val or lastmod_val.startswith(target_lastmod_prefix):
                                    candidates.append({
                                        "url": loc_val,
                                        "lastmod": lastmod_val
                                    })
                except Exception as e:
                    print(f"[{name}] Erro: {e}")
                    from requests.exceptions import ConnectionError, Timeout
                    if isinstance(e, (ConnectionError, Timeout)) or "getaddrinfo" in str(e).lower() or "nameresolution" in str(e).lower():
                        raise e
                        
        if year >= 2014:
            try:
                candidates.extend(get_wp_sitemap_candidates("observador.pt", year, month, day))
            except Exception:
                pass
        if year >= 2001:
            try:
                candidates.extend(get_sicnoticias_candidates(year, month, day))
            except Exception:
                pass
        if year >= 2021:
            try:
                candidates.extend(get_cnnportugal_candidates(year, month, day))
            except Exception:
                pass
        if year >= 2001:
            try:
                candidates.extend(get_rtp_candidates(year, month, day))
            except Exception:
                pass
        if year >= 2001:
            try:
                candidates.extend(get_cmjornal_candidates(year, month, day))
            except Exception:
                pass
        if year >= 2016:
            try:
                candidates.extend(get_sapo_candidates(year, month, day))
            except Exception:
                pass
        if year >= 2009:
            try:
                candidates.extend(get_4gnews_candidates(year, month, day))
            except Exception:
                pass
        if year >= 2004:
            try:
                candidates.extend(get_sabado_candidates(year, month, day))
            except Exception:
                pass
        if year >= 2024:
            try:
                candidates.extend(get_nowcanal_candidates(year, month, day))
            except Exception:
                pass
        if year >= 2001:
            for magazine in ["caras.pt", "novagente.pt", "vip.pt"]:
                try:
                    candidates.extend(get_wp_sitemap_candidates(magazine, year, month, day))
                except Exception as e:
                    print(f"[{magazine}] Erro: {e}")
        if year >= 2013:
            pubs = [
                "publico", "expresso", "correio-da-manha", "diario-de-noticias", "jornal-de-noticias",
                "a-bola", "record", "o-jogo", "jornal-de-negocios", "jornal-economico", 
                "sol", "destak", "i", "visao", "sabado", "novo-semanario",
                "tal-e-qual", "o-diabo", "avante", "diario-de-noticias-da-madeira", "acoriano-oriental",
                "metro-lisboa", "oje", "diario-de-coimbra", "diario-do-minho", "diario-de-leiria",
                "diario-de-aveiro", "diario-de-viseu", "jornal-do-fundao", "barlavento", "jornal-da-madeira"
            ]
            for pub in pubs:
                if day is not None:
                    if year > 2013 or (year == 2013 and month > 9) or (year == 2013 and month == 9 and day >= 10):
                        url = f"https://www.vercapas.com/capa/arquivo/{pub}/{year:04d}-{month:02d}-{day:02d}.html"
                        candidates.append({
                            "url": url,
                            "lastmod": f"{year:04d}-{month:02d}-{day:02d}T00:00:00Z"
                        })
                else:
                    num_days = calendar.monthrange(year, month)[1]
                    for d in range(1, num_days + 1):
                        if year > 2013 or (year == 2013 and month > 9) or (year == 2013 and month == 9 and d >= 10):
                            url = f"https://www.vercapas.com/capa/arquivo/{pub}/{year:04d}-{month:02d}-{d:02d}.html"
                            candidates.append({
                                "url": url,
                                "lastmod": f"{year:04d}-{month:02d}-{d:02d}T00:00:00Z"
                            })
    return candidates

def extract_day_from_candidate(cand, year, month):
    loc_val = cand.get("url", "")
    lastmod_val = cand.get("lastmod", "")
    

    prefix = f"{year}-{month:02d}-"
    if lastmod_val.startswith(prefix):
        try:
            day_str = lastmod_val[len(prefix):len(prefix)+2]
            return int(day_str)
        except ValueError:
            pass
            

    import re
    patterns = [
        rf"/{year}/{month:02d}/(\d{2})/",
        rf"/{year}/{month:02d}/(\d{2})",
        rf"-{year}{month:02d}(\d{2})",
        rf"/{year}/{month:02d}/(\d{1,2})/"
    ]
    for pattern in patterns:
        match = re.search(pattern, loc_val)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                pass
                
    return None

def scrape_article(url):
    print(f"A extrair artigo: {url}...")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    try:
        response = requests_get(url)
        if response.status_code == 403:
            print(f"Artigo protegido por bot protection/DataDome (HTTP 403). A saltar...")
            return None
        elif response.status_code != 200:
            print(f"Erro ao carregar página do artigo: {response.status_code}")
            return None
            
        soup = BeautifulSoup(response.text, "html.parser")
        

        title = ""
        description = ""
        image_url = ""
        
        og_title = soup.find("meta", property="og:title") or soup.find("meta", attrs={"name": "og:title"})
        if og_title:
            title = str(og_title.get("content") or "")
            
        og_desc = soup.find("meta", property="og:description") or soup.find("meta", attrs={"name": "og:description"})
        if og_desc:
            description = str(og_desc.get("content") or "")
            
        og_img = soup.find("meta", property="og:image") or soup.find("meta", attrs={"name": "og:image"})
        if og_img:
            image_url = str(og_img.get("content") or "")
            
        if not title:
            h1 = soup.find("h1")
            if h1:
                title = h1.get_text(strip=True)
                

        article_body = soup.find("article") or soup.find(class_=lambda x: bool(x and any(w in x.lower() for w in ["article-body", "story-body", "post-body", "entry-content"])))
        
        raw_paragraphs = []
        if article_body:
            raw_paragraphs = [p.get_text(strip=True) for p in article_body.find_all("p") if p.get_text(strip=True)]
        else:
            raw_paragraphs = [p.get_text(strip=True) for p in soup.find_all("p") if p.get_text(strip=True)]
            

        paywall_phrases = [
            "exclusivo para assinantes",
            "exclusivo assinantes",
            "adira ao",
            "assine para continuar",
            "subscreva para",
            "conteúdo reservado",
            "leia o artigo completo",
            "artigo exclusivo",
            "torne-se assinante",
            "partilhar este artigo",
            "siga-nos no",
            "receba as nossas newsletters",
            "jornalismo independente",
            "crie uma conta"
        ]
        
        paragraphs = []
        for p_text in raw_paragraphs:
            lowered = p_text.lower()
            if any(phrase in lowered for phrase in paywall_phrases):
                break
            paragraphs.append(p_text)
            
        text_content = "\n\n".join(paragraphs[:8])
        
        return {
            "title": title.strip(),
            "description": description.strip(),
            "image_url": image_url.strip(),
            "text": text_content.strip()
        }
    except Exception as e:
        print(f"Erro ao fazer scraping da página: {e}")
    return None

class NvidiaLimitExceeded(Exception):
    pass

nvidia_call_count = 0
NVIDIA_CALL_LIMIT = 0

def enrich_article_with_nvidia(article, lang):
    global nvidia_call_count
    
    if "vercapas.com" in article.get("image_url", "").lower() or "vercapas.com" in article.get("url", "").lower():
        url = article.get("url", "")
        text_to_search = (article.get("image_url", "") + " " + article.get("title", "") + " " + url).lower()
        pub_name = "Público"
        pubs_mapping = {
            "publico": "Público",
            "expresso": "Expresso",
            "correio-da-manha": "Correio da Manhã",
            "diario-de-noticias": "Diário de Notícias",
            "jornal-de-noticias": "Jornal de Notícias",
            "a-bola": "A Bola",
            "record": "Record",
            "o-jogo": "O Jogo",
            "jornal-de-negocios": "Jornal de Negócios",
            "jornal-economico": "Jornal Económico",
            "sol": "Sol",
            "destak": "Destak",
            "i": "Jornal i",
            "visao": "Visão",
            "sabado": "Sábado",
            "novo-semanario": "Novo Semanário",
            "tal-e-qual": "Tal & Qual",
            "o-diabo": "O Diabo",
            "avante": "Avante!",
            "diario-de-noticias-da-madeira": "Diário de Notícias da Madeira",
            "acoriano-oriental": "Açoriano Oriental",
            "metro-lisboa": "Metro Lisboa",
            "oje": "OJE",
            "diario-de-coimbra": "Diário de Coimbra",
            "diario-do-minho": "Diário do Minho",
            "diario-de-leiria": "Diário de Leiria",
            "diario-de-aveiro": "Diário de Aveiro",
            "diario-de-viseu": "Diário de Viseu",
            "jornal-do-fundao": "Jornal do Fundão",
            "barlavento": "Barlavento",
            "jornal-da-madeira": "Jornal da Madeira"
        }
        import re
        m_pub = re.search(r"/capa/arquivo/([^/]+)/", url.lower())
        if m_pub:
            pub_key = m_pub.group(1)
            pub_name = pubs_mapping.get(pub_key, pub_key.replace("-", " ").title())
        else:

            for k in sorted(pubs_mapping.keys(), key=len, reverse=True):
                if k in text_to_search:
                    pub_name = pubs_mapping[k]
                    break
        date_str = ""
        m = re.search(r"(\d{4}-\d{2}-\d{2})", text_to_search)
        if m:
            date_str = m.group(1)
            
        if lang == "en":
            context = f"Front page of the newspaper {pub_name} for the edition of {date_str}." if date_str else f"Front page of the newspaper {pub_name}."
            summary = f"Front page of the newspaper {pub_name} for the edition of {date_str}." if date_str else f"Front page of the newspaper {pub_name}."
            keywords = ["cover", "frontpage", "press", pub_name.lower()]
        else:
            context = f"Capa do jornal {pub_name} na edição de {date_str}." if date_str else f"Capa do jornal {pub_name}."
            summary = f"Capa do jornal {pub_name} na edição de {date_str}." if date_str else f"Capa do jornal {pub_name}."
            keywords = ["capa", "imprensa", pub_name.lower()]
            
        return {
            "content_mode": "photo_roundup",
            "enriched_context": context,
            "summary": summary,
            "topic_keywords": keywords,
            "virality_signals": [],
            "carousel_items": [],
            "should_skip": False
        }

    
    prompt = f"""
You are cataloging archived news articles for a daily news digest application.
Language required for the output: {lang.upper()}

Analyze the news article below:
Title: {article['title']}
Lead Paragraph: {article['description']}
Body text extract:
{article['text']}

Return a JSON object with exactly these keys:
- content_mode: one of "single_story", "carousel_roundup", "weekly_recap", "internet_culture", "meme", "promo", "photo_roundup", "institutional_news", "feature", "unclear"
- enriched_context: 1 to 2 short paragraphs in {lang.upper()}, summarizing the news and its context. Remove hashtags and calls to action.
- summary: one sentence (in {lang.upper()})
- topic_keywords: array with up to 5 short strings (in {lang.upper()})
- virality_signals: array with up to 3 short strings
- should_skip: true only if this is essentially a duplicate announcement, advertising, or local utility notice without news value.
"""


    if LOCAL_LLM:
        max_ollama_attempts = 3
        for attempt in range(1, max_ollama_attempts + 1):
            try:
                response = requests.post(
                    "http://localhost:11434/api/chat",
                    json={
                        "model": LOCAL_LLM,
                        "messages": [
                            {"role": "system", "content": "You are a cataloging assistant. Return only valid JSON object."},
                            {"role": "user", "content": prompt}
                        ],
                        "format": "json",
                        "options": {"temperature": 0.3},
                        "stream": False
                    },
                    timeout=60
                )
                if response.status_code == 200:
                    res_data = response.json()
                    response_text = res_data.get("message", {}).get("content", "{}")
                    result = json.loads(response_text)
                    if isinstance(result.get("enriched_context"), list):
                        result["enriched_context"] = "\n\n".join(str(p) for p in result["enriched_context"])
                    return result
                else:
                    print(f"[Ollama] Servidor respondeu com erro HTTP {response.status_code} (Tentativa {attempt}/{max_ollama_attempts})")
            except Exception as e:
                print(f"[Ollama] Erro na tentativa {attempt}/{max_ollama_attempts} com o modelo {LOCAL_LLM}: {e}")
                import os
                if os.path.exists("/content/ollama.log"):
                    print("\n--- Últimas linhas do log do Ollama (/content/ollama.log) ---")
                    try:
                        with open("/content/ollama.log", "r") as log_f:
                            lines = log_f.readlines()
                            for line in lines[-30:]:
                                print(line, end="")
                    except Exception:
                        pass
                    print("------------------------------------------------------------\n")
            if attempt < max_ollama_attempts:
                time.sleep(5)
        
        print(f"[Ollama] [Aviso] Falharam todas as {max_ollama_attempts} tentativas de enriquecimento para este artigo.")
        return None

    if NVIDIA_CALL_LIMIT > 0 and nvidia_call_count >= NVIDIA_CALL_LIMIT:
        raise NvidiaLimitExceeded("Limite de chamadas ao NVIDIA atingido nesta execução.")


    if USE_NVIDIA:
        global nvidia_pool
        if nvidia_pool is None:
            from nvidia_client import NvidiaKeyPool, load_nvidia_api_keys, NvidiaQuotaExceeded
            keys = load_nvidia_api_keys()
            if not keys:
                print("[Aviso] NVIDIA activa mas sem chaves. A usar dados estruturados base.")
                return {
                    "content_mode": "photo_roundup",
                    "enriched_context": article["description"] or article["title"],
                    "summary": article["description"] or article["title"],
                    "topic_keywords": ["noticias", "web"],
                    "virality_signals": [],
                    "carousel_items": [],
                    "should_skip": False
                }
            nvidia_pool = NvidiaKeyPool(keys, starting_model=NVIDIA_MODEL, starting_key_index=NVIDIA_KEY_INDEX)
            nvidia_pool.save_key_status_to_file()
            print(f"[NVIDIA] Pool inicializado: {nvidia_pool.get_current_key_info()}")
        else:
            from nvidia_client import NvidiaQuotaExceeded

        attempts = 0
        max_attempts = max(len(nvidia_pool.api_keys) * 2, 6)
        while attempts < max_attempts:
            attempts += 1
            try:
                response_text = nvidia_pool.chat_json(prompt)
                result = json.loads(response_text or "{}")
                if not isinstance(result, dict):
                    raise ValueError("Resposta NVIDIA nao e um objeto JSON.")
                

                if isinstance(result.get("enriched_context"), list):
                    result["enriched_context"] = "\n\n".join(str(p) for p in result["enriched_context"])
                
                nvidia_call_count += 1
                nvidia_pool.save_key_status_to_file()
                return result
            except NvidiaQuotaExceeded as e:
                print(f"[NVIDIA] Quota diária/crédito esgotado para a chave #{nvidia_pool.current_index + 1}: {e}")
                nvidia_pool.mark_current_exhausted()
                if not nvidia_pool.rotate():
                    print("[NVIDIA] Todas as chaves da API do NVIDIA esgotaram a quota diária.")
                    raise NvidiaLimitExceeded("Todas as chaves NVIDIA esgotaram a quota diária.")
                continue
            except Exception as e:
                print(f"[NVIDIA] Erro temporário na chave #{nvidia_pool.current_index + 1}: {e}")
                active_keys = sum(1 for x in nvidia_pool.exhausted if not x)
                if active_keys > 1:
                    print("[NVIDIA] A rodar para a próxima chave...")
                    nvidia_pool.rotate()
                    time.sleep(1)
                    continue
                else:
                    print("[NVIDIA] A aguardar 5s antes de tentar novamente...")
                    time.sleep(5)
                    continue

        print("[Erro] NVIDIA falhou após múltiplas tentativas de conexão/rate limit.")
        raise RuntimeError("NVIDIA falhou repetidamente devido a erros temporários/conexão.")


    return {
        "content_mode": "photo_roundup",
        "enriched_context": article["description"] or article["title"],
        "summary": article["description"] or article["title"],
        "topic_keywords": ["noticias", "web"],
        "virality_signals": [],
        "carousel_items": [],
        "should_skip": False
    }

def extract_domain_from_url(source_url):
    domain = "news"
    for k in ["publico.pt", "observador.pt", "expresso.pt", "sicnoticias.pt", "cnnportugal.iol.pt", "cnnportugal.pt", "rtp.pt", "cmjornal.pt", "sapo.pt", "4gnews.pt", "nytimes.com", "cnn.com", "bbc.com", "bbc.co.uk", "aljazeera.com", "buzzfeednews.com", "politico.eu", "theguardian.com", "guardian", "vercapas.com", "visao.pt", "caras.pt", "novagente.pt", "vip.pt", "sabado.pt", "nowcanal.pt"]:
        if k in source_url:
            domain = k.replace(".pt", "").replace(".com", "").replace(".eu", "").replace(".co.uk", "").replace("theguardian", "guardian").replace(".iol", "").replace("vercapas", "vercapas")
            break
    return domain

def build_article_shortcode(year, month, day, source_url):
    domain = extract_domain_from_url(source_url)
    import hashlib
    url_hash = hashlib.md5(source_url.encode('utf-8')).hexdigest()[:6]
    parts = [p for p in source_url.split("/") if p]
    
    url_id = "0"
    if parts:
        last_part = parts[-1].split("?")[0]
        clean_part = re.sub(r"[^a-zA-Z0-9-]", "", last_part)
        if clean_part:
            url_id = clean_part[-15:]
        else:
            url_id = url_hash
    else:
        url_id = url_hash
        
    if url_id != url_hash:
        return f"{domain}-{year:04d}{month:02d}{day:02d}-{url_id}-{url_hash}"
    else:
        return f"{domain}-{year:04d}{month:02d}{day:02d}-{url_hash}"

def is_article_already_in_block(lang, year, month, day, source_url):
    shortcode = build_article_shortcode(year, month, day, source_url)
    block_id = block_id_for_month_day(month, day)
    try:
        posts = load_block(lang, block_id)
        for p in posts:
            if shortcode in p.get("shortcodes", []):
                return True
    except Exception:
        pass
    return False

def save_article_to_block(lang, year, month, day, article, ai_payload, source_url):
    block_id = block_id_for_month_day(month, day)
    from archive_storage import block_lock
    lock = block_lock(lang, block_id)
    lock.__enter__()
    try:
        posts = load_block(lang, block_id)
        shortcode = build_article_shortcode(year, month, day, source_url)
        domain = extract_domain_from_url(source_url)
        

        for p in posts:
            if shortcode in p.get("shortcodes", []):
                print(f"Notícia {shortcode} já existe no bloco {block_id}. A saltar.")
                return False
                

        post_record = {
            "shortcodes": [shortcode],
            "date": f"{year:04d}-{month:02d}-{day:02d} 12:00:00",
            "global_context": ai_payload.get("enriched_context") or article["description"] or article["title"],
            "raw_caption": article["description"] or article["title"],
            "image_url": article["image_url"] or "",
            "source_platform": "web",
            "source_profile": f"{domain}.pt",
            "source_url": source_url,
            "media_type": "image",
            "media_count": 1,
            "is_video": False,
            "video_url": "",
            "slide_urls": [article["image_url"] or ""],
            "slide_video_urls": [""],
            "content_flags": ["web_news"],
            "content_mode": ai_payload.get("content_mode", "single_story"),
            "needs_enrichment": False,
            "enrichment_status": "done",
            "enriched_at": now_local().isoformat(),
            "ai_summary": ai_payload.get("summary") or article["title"],
            "topic_keywords": ai_payload.get("topic_keywords", []),
            "virality_signals": ai_payload.get("virality_signals", []),
            "carousel_items": [],
            "should_skip": ai_payload.get("should_skip", False),
            "options": [
                {
                    "year": str(year),
                    "category": "NOTÍCIA" if lang == "pt" else "NEWS",
                    "title": article["title"],
                    "summary": ai_payload.get("summary") or article["description"],
                    "highlight_text": str(year),
                    "overlay_description": article["title"],
                    "image_theme": article["title"],
                    "caption": f"Neste dia em {year}: {ai_payload.get('summary') or article['description']}",
                    "layout_preference": "template_1",
                    "breaking_candidate": False,
                    "background_source_url": article["image_url"] or "",
                    "image_url": article["image_url"] or ""
                }
            ],
            "selected_option": 0,
            "status": "pending"
        }
        
        posts.append(post_record)
        save_block(lang, block_id, posts)
        print(f"[{lang}][bloco {block_id}] [OK] Adicionada notícia: {article['title'][:60]}...")
        return True
    finally:
        lock.__exit__(None, None, None)

def process_web_sitemaps(lang, year, month, day, limit):
    if lang not in ["pt", "en"]:
        print("Idiomas suportados: pt ou en.")
        return
        
    if day is not None:
        candidates = get_sitemap_candidates(lang, year, month, day)
        if not candidates:
            print(f"Nenhuma notícia encontrada nos sitemaps para {year}-{month:02d}-{day:02d}.")
            return
            
        if limit > 0:
            candidates = candidates[:limit]
            
        processed_count = 0
        for cand in candidates:
            url = cand["url"]
            if is_article_already_in_block(lang, year, month, day, url):
                shortcode = build_article_shortcode(year, month, day, url)
                block_id = block_id_for_month_day(month, day)
                print(f"Notícia {shortcode} já existe no bloco {block_id}. A saltar (pré-verificação).")
                continue
                
            article = scrape_article(url)
            if not article or not article["title"]:
                continue
                
            ai_payload = enrich_article_with_nvidia(article, lang)
            if save_article_to_block(lang, year, month, day, article, ai_payload, url):
                processed_count += 1
                
        print(f"\n--- Concluído: {processed_count} notícias processadas para o dia {day:02d}. ---")
    else:
        candidates = get_sitemap_candidates(lang, year, month, day=None)
        if not candidates:
            print(f"Nenhuma notícia encontrada nos sitemaps para o mês {year}-{month:02d}.")
            return
            
        from collections import defaultdict
        grouped = defaultdict(list)
        for cand in candidates:
            d = extract_day_from_candidate(cand, year, month)
            if d is not None:
                grouped[d].append(cand)
                
        total_processed = 0
        for d in sorted(grouped.keys()):
            day_candidates = grouped[d]
            if not day_candidates:
                continue
            print(f"\n--- [Dia {d:02d}] A processar {len(day_candidates)} candidatas ---")
            if limit > 0:
                day_candidates = day_candidates[:limit]
                
            day_processed = 0
            for cand in day_candidates:
                url = cand["url"]
                if is_article_already_in_block(lang, year, month, d, url):
                    shortcode = build_article_shortcode(year, month, d, url)
                    block_id = block_id_for_month_day(month, d)
                    print(f"Notícia {shortcode} já existe no bloco {block_id}. A saltar (pré-verificação).")
                    continue
                    
                article = scrape_article(url)
                if not article or not article["title"]:
                    continue
                ai_payload = enrich_article_with_nvidia(article, lang)
                if save_article_to_block(lang, year, month, d, article, ai_payload, url):
                    day_processed += 1
            total_processed += day_processed
            
        print(f"\n--- Concluído Mês {month:02d}: {total_processed} notícias processadas no total. ---")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Recolhe notícias históricas de sitemaps web e guarda no arquivo.")
    parser.add_argument("--year", type=int, required=True, help="Ano histórico (ex: 2015).")
    parser.add_argument("--month", type=int, required=True, help="Mês (1 a 12).")
    parser.add_argument("--day", type=int, default=None, help="Dia (1 a 31). Padrão: todos os dias do mês.")
    parser.add_argument("--lang", choices=["pt", "en"], default="pt", help="Processa apenas este idioma.")
    parser.add_argument("--limit", type=int, default=5, help="Limite de notícias a processar por execução. Padrão: 5.")
    parser.add_argument("--max-nvidia-calls", type=int, default=0, help="Número máximo de chamadas ao NVIDIA nesta execução.")
    parser.add_argument("--nvidia-model", type=str, default="meta/llama-3.3-70b-instruct", help="Modelo da NVIDIA a usar (ex: meta/llama-3.3-70b-instruct).")
    parser.add_argument("--nvidia-key-index", type=int, default=0, help="Índice de chave da NVIDIA a usar por padrão (se existirem várias).")
    args = parser.parse_args()
    
    if args.max_nvidia_calls > 0:
        NVIDIA_CALL_LIMIT = args.max_nvidia_calls
    else:
        NVIDIA_CALL_LIMIT = 0
        
    NVIDIA_MODEL = args.nvidia_model
    NVIDIA_KEY_INDEX = args.nvidia_key_index
    nvidia_call_count = 0
        
    process_web_sitemaps(args.lang, args.year, args.month, args.day, args.limit)