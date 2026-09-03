import json
import os
import time
import random
from collections import defaultdict
from datetime import date, datetime


class FileLock:
    def __init__(self, lock_path):
        self.lock_path = lock_path
        self.is_locked = False

    def acquire(self, timeout=60):
        # No Linux (Colab / Google Drive FUSE), desativamos os locks físicos para evitar latência extrema e bugs.
        if os.name != 'nt':
            self.is_locked = True
            return True
            
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                self.is_locked = True
                return True
            except OSError:
                time.sleep(random.uniform(0.05, 0.2))
        return False

    def release(self):
        if os.name != 'nt':
            self.is_locked = False
            return
            
        if self.is_locked:
            try:
                os.remove(self.lock_path)
            except OSError:
                pass
            self.is_locked = False


class block_lock:
    def __init__(self, lang, block_id):
        path = block_path(lang, block_id)
        self.lock = FileLock(path + ".lock")

    def __enter__(self):
        self.lock.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.lock.release()



ROOT_DIR = os.path.dirname(__file__)
LANG_DIRS = {
    "pt": os.path.join(ROOT_DIR, "pt"),
}
TOTAL_DAY_BLOCKS = 366
LEAP_REFERENCE_YEAR = 2000


def ensure_lang_dir(lang):
    path = LANG_DIRS[lang]
    os.makedirs(path, exist_ok=True)
    return path


def _all_calendar_days():
    days = []
    current = date(LEAP_REFERENCE_YEAR, 1, 1)
    final = date(LEAP_REFERENCE_YEAR, 12, 31)
    while current <= final:
        days.append((current.month, current.day))
        current = current.fromordinal(current.toordinal() + 1)
    return days


CALENDAR_DAYS = _all_calendar_days()
DAY_TO_BLOCK = {
    (m, d): f"{m:02d}-{d:02d}"
    for (m, d) in CALENDAR_DAYS
}


def normalize_block_id(block_id):
    if "-" in str(block_id):
        parts = str(block_id).split("-")
        return f"{int(parts[0]):02d}-{int(parts[1]):02d}"
    return str(block_id)


def all_block_ids():
    return [f"{m:02d}-{d:02d}" for (m, d) in CALENDAR_DAYS]


def block_id_for_month_day(month, day):
    return f"{int(month):02d}-{int(day):02d}"


def block_path(lang, block_id):
    return os.path.join(ensure_lang_dir(lang), f"{normalize_block_id(block_id)}.json")


def list_block_paths(lang):
    return [block_path(lang, block_id) for block_id in all_block_ids()]


def load_json_file(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return default


def save_json_file(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_block(lang, block_id):
    return load_json_file(block_path(lang, block_id), [])


def save_block(lang, block_id, posts):
    path = block_path(lang, block_id)
    ordered = sorted(posts, key=lambda item: item.get("date", ""))
    save_json_file(path, ordered)


def iter_block_ids_for_month(month):
    wanted_month = int(month)
    block_ids = {
        f"{m:02d}-{d:02d}"
        for (m, d) in CALENDAR_DAYS
        if m == wanted_month
    }
    return sorted(block_ids)


def parse_post_date(date_str):
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            return datetime.strptime(date_str[:10], "%Y-%m-%d")
        except ValueError:
            return None


def load_posts_for_date(lang, month, day):
    wanted_month = int(month)
    wanted_day = int(day)
    block_posts = load_block(lang, block_id_for_month_day(wanted_month, wanted_day))
    matches = []
    for post in block_posts:
        parsed = parse_post_date(post.get("date", ""))
        if parsed and parsed.month == wanted_month and parsed.day == wanted_day:
            matches.append(post)
    return sorted(matches, key=lambda item: item.get("date", ""))


def load_posts_for_month(lang, month):
    wanted_month = int(month)
    posts = []
    for block_id in iter_block_ids_for_month(wanted_month):
        for post in load_block(lang, block_id):
            parsed = parse_post_date(post.get("date", ""))
            if parsed and parsed.month == wanted_month:
                posts.append(post)
    return sorted(posts, key=lambda item: item.get("date", ""))


def load_all_posts(lang):
    posts = []
    for block_id in all_block_ids():
        posts.extend(load_block(lang, block_id))
    return sorted(posts, key=lambda item: item.get("date", ""))


def save_posts_grouped_by_day_block(lang, posts, clear_existing=False):
    if clear_existing:
        for block_id in all_block_ids():
            save_block(lang, block_id, [])

    grouped = defaultdict(list)
    for post in posts:
        parsed = parse_post_date(post.get("date", ""))
        if not parsed:
            continue
        grouped[block_id_for_month_day(parsed.month, parsed.day)].append(post)

    for block_id, day_posts in grouped.items():
        save_block(lang, block_id, day_posts)


def load_all_shortcodes(lang):
    shortcodes = set()
    for block_id in all_block_ids():
        for post in load_block(lang, block_id):
            shortcodes.update(post.get("shortcodes", []))
    return shortcodes


def group_posts_by_block(posts):
    grouped = defaultdict(list)
    for post in posts:
        parsed = parse_post_date(post.get("date", ""))
        if not parsed:
            continue
        grouped[block_id_for_month_day(parsed.month, parsed.day)].append(post)
    return grouped


def day_block_summary():
    summary = defaultdict(list)
    for (month, day) in CALENDAR_DAYS:
        block_id = f"{month:02d}-{day:02d}"
        summary[block_id].append((month, day))
    return dict(summary)


def get_auto_terminal_label():
    import sys
    months = None
    lang = None
    for idx, arg in enumerate(sys.argv):
        if arg == "--months" and idx + 1 < len(sys.argv):
            months = sys.argv[idx + 1]
        elif arg == "--lang" and idx + 1 < len(sys.argv):
            lang = sys.argv[idx + 1]
            
    lang_str = f" ({lang.upper()})" if lang else ""
    if not months:
        if "pregenerator.py" in sys.argv[0]:
            return f"Pré-gerador{lang_str}"
        elif "publisher.py" in sys.argv[0]:
            return f"Publicador{lang_str}"
        elif "wikipedia_scraper.py" in sys.argv[0]:
            return f"Wikipedia{lang_str}"
        else:
            return f"Geral{lang_str}"
            
    mapping = {
        "1,2": "Jan-Fev",
        "3,4": "Mar-Abr",
        "5,6": "Mai-Jun",
        "7,8": "Jul-Ago",
        "9,10": "Set-Out",
        "11,12": "Nov-Dez"
    }
    clean_months = months.strip().replace(" ", "")
    return mapping.get(clean_months, f"Meses {clean_months}") + lang_str


def update_shared_api_status(terminal_label, current_idx, total_keys, local_exhausted_list):
    status_file = "current_api_status.json"
    txt_file = "current_api_key_status.local.txt"
    lock_path = status_file + ".lock"
    
    lock = FileLock(lock_path)
    global_exhausted = list(local_exhausted_list)
    
    if lock.acquire(timeout=10):
        try:
            data = {"exhausted_keys": [], "exhausted_keys_time": {}, "terminals": {}}
            if os.path.exists(status_file):
                try:
                    with open(status_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception:
                    pass
            
            if not isinstance(data, dict):
                data = {"exhausted_keys": [], "exhausted_keys_time": {}, "terminals": {}}
            if "exhausted_keys" not in data:
                data["exhausted_keys"] = []
            if "exhausted_keys_time" not in data or not isinstance(data["exhausted_keys_time"], dict):
                data["exhausted_keys_time"] = {}
            if "terminals" not in data:
                data["terminals"] = {}
                

            now = datetime.now()
            expired_keys = []
            for idx_str, time_str in list(data["exhausted_keys_time"].items()):
                try:
                    exh_time = datetime.fromisoformat(time_str)
                    if (now - exh_time).total_seconds() > 10800:
                        expired_keys.append(idx_str)
                except Exception:
                    expired_keys.append(idx_str)
            for idx_str in expired_keys:
                del data["exhausted_keys_time"][idx_str]
                

            for idx, is_exh in enumerate(local_exhausted_list):
                if is_exh:
                    idx_str = str(idx)
                    if idx_str not in data["exhausted_keys_time"]:
                        data["exhausted_keys_time"][idx_str] = now.isoformat()
            

            data["exhausted_keys"] = sorted([int(k) for k in data["exhausted_keys_time"].keys()])
            
            global_exhausted = [False] * total_keys
            for idx in data["exhausted_keys"]:
                if idx < total_keys:
                    global_exhausted[idx] = True
            
            active_count = sum(1 for x in global_exhausted if not x)
            data["terminals"][terminal_label] = {
                "current_key": current_idx + 1,
                "active_count": active_count,
                "total_keys": total_keys,
                "updated_at": now.isoformat()
            }
            

            to_delete = []
            for t_name, t_info in data["terminals"].items():
                try:
                    up_time = datetime.fromisoformat(t_info.get("updated_at", ""))
                    if (now - up_time).total_seconds() > 900:
                        to_delete.append(t_name)
                except Exception:
                    pass
            for t_name in to_delete:
                if t_name != terminal_label:
                    del data["terminals"][t_name]
            
            with open(status_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                
            active_count = sum(1 for x in global_exhausted if not x)
            lines = []
            lines.append("=============================================================")
            lines.append(f" ESTADO GLOBAL: {active_count}/{total_keys} chaves de API ativas")
            lines.append("=============================================================")
            
            for t_name in sorted(data["terminals"].keys()):
                info = data["terminals"][t_name]
                lines.append(f"[{t_name}]: Chave #{info['current_key']} de {info['total_keys']} ativa.")
            
            lines.append("=============================================================")
            
            with open(txt_file, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
                
        except Exception as e:
            print(f"[Erro] Falha ao atualizar estado partilhado das chaves API: {e}")
        finally:
            lock.release()
            
    return global_exhausted
