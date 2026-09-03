import os
import re
import sys
import time
import subprocess
import json
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

def find_brave_executable():
    program_files = os.environ.get("PROGRAMFILES", r"C:\Program Files")
    program_files_x86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    candidates = [
        Path(program_files) / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe",
        Path(program_files_x86) / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe",
        Path(local_appdata) / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None

def is_brave_running():
    try:
        output = subprocess.check_output('tasklist /FI "IMAGENAME eq brave.exe"', shell=True, text=True)
        return "brave.exe" in output.lower()
    except Exception:
        return False

def download_file(url, filepath):
    try:
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        )
        with urllib.request.urlopen(req, timeout=15) as response, open(filepath, 'wb') as out_file:
            out_file.write(response.read())
        return True
    except Exception as e:
        print(f"    [Download Error] Failed to download {url}: {e}", flush=True)
        return False

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    documents_dir = Path.home() / "Documents"
    brave_exe = find_brave_executable()
    if not brave_exe:
        print("❌ Executável do Brave não encontrado.", flush=True)
        sys.exit(1)
        
    user_data_dir = Path(os.environ.get("LOCALAPPDATA", "")) / "BraveSoftware" / "Brave-Browser" / "User Data"
    
    print("\nA verificar se o Brave está aberto...", flush=True)
    attempts = 0
    max_attempts = 150
    
    while is_brave_running() and attempts < max_attempts:
        attempts += 1
        print(f"⚠️ [Brave Aberto] O Brave browser está a correr.")
        print(f"👉 Por favor, FECHA todas as janelas do Brave browser (tentativa {attempts}/{max_attempts})...", flush=True)
        time.sleep(2)
        
    if is_brave_running():
        print("❌ O Brave continuou aberto. Abortado.", flush=True)
        sys.exit(1)
        
    print("✅ Brave browser fechado. A iniciar extração...", flush=True)
    time.sleep(1.5)
    

    new_shortcodes = []
    

    tools_json_path = documents_dir / "portefolio" / "secret" / "tools-data.json"
    existing_shortcodes = set()
    if tools_json_path.exists():
        try:
            tools_data = json.loads(tools_json_path.read_text(encoding="utf-8"))
            for cat in tools_data.get("categories", []):
                for sec in cat.get("sections", []):
                    for card in sec.get("cards", []):
                        if not card or not isinstance(card, dict):
                            continue
                        source = card.get("source")
                        if not isinstance(source, dict):
                            continue
                        src_href = source.get("href")
                        if not src_href or not isinstance(src_href, str):
                            continue
                        m = re.search(r"/(?:p|reels?|tv)/([A-Za-z0-9_-]+)/?", src_href)
                        if m:
                            existing_shortcodes.add(m.group(1))
        except Exception as e:
            print("Erro ao ler tools-data.json:", e, flush=True)
            

    progress_path = documents_dir / "autofill_progress.json"
    progress_shortcodes = set()
    if progress_path.exists():
        try:
            progress = json.loads(progress_path.read_text(encoding="utf-8"))
            progress_shortcodes = set(progress.get("processed_shortcodes", []))
        except Exception as e:
            print("Erro ao ler progresso:", e, flush=True)
            
    playwright_inst = None
    context = None
    try:
        playwright_inst = sync_playwright().start()
        print("A abrir o perfil do Brave...", flush=True)
        context = playwright_inst.chromium.launch_persistent_context(
            str(user_data_dir),
            executable_path=str(brave_exe),
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        
        page = context.new_page()
        page.set_viewport_size({"width": 1280, "height": 1000})
        
        print("A carregar publicações guardadas (Todas as publicações)...", flush=True)
        page.goto("https://www.instagram.com/luisflmaximo/saved/all-posts/", timeout=60000)
        page.wait_for_timeout(6000)
        
        if "login" in page.url.lower():
            print("❌ Erro: Sessão não iniciada no Instagram no Brave.", flush=True)
            sys.exit(1)
            

        for i in range(3):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(2000)
            
        links = page.locator("a").all()
        shortcodes_on_page = []
        for link in links:
            href = link.get_attribute("href")
            if href:
                m = re.search(r"/(?:p|reel)/([A-Za-z0-9_-]+)/?", href)
                if m:
                    sc = m.group(1)
                    if sc not in shortcodes_on_page:
                        shortcodes_on_page.append(sc)
                        
        print(f"Detetados {len(shortcodes_on_page)} posts na página do Instagram.", flush=True)
        

        for sc in shortcodes_on_page:
            if sc not in existing_shortcodes and sc not in progress_shortcodes:
                new_shortcodes.append(sc)
                
        if not new_shortcodes:
            print("✅ Não há novos posts para descarregar. Tudo em dia!", flush=True)
            sys.exit(0)
            
        print(f"Shortcodes novos para descarregar ({len(new_shortcodes)}): {new_shortcodes}", flush=True)
        
        posts_dir = documents_dir / "instagram_posts"
        posts_dir.mkdir(parents=True, exist_ok=True)
        
        for idx, sc in enumerate(new_shortcodes):
            print(f"\n[{idx+1}/{len(new_shortcodes)}] A processar post: {sc}", flush=True)
            post_url = f"https://www.instagram.com/p/{sc}/"
            
            try:
                page.goto(post_url, timeout=60000)
                page.wait_for_timeout(4000)
                
                if "unavailable" in page.title().lower() or "not found" in page.title().lower():
                    print(f"  ❌ Post {sc} não está disponível (404).", flush=True)
                    continue
                
                post_folder = posts_dir / sc
                post_folder.mkdir(parents=True, exist_ok=True)
                
                caption = ""
                try:
                    meta_desc = page.locator('meta[property="og:description"]').get_attribute('content')
                    if meta_desc:
                        m = re.search(r":\s*['\"](.*?)['\"]$", meta_desc)
                        if m:
                            caption = m.group(1)
                        else:
                            parts = meta_desc.split(":", 1)
                            if len(parts) > 1:
                                caption = parts[1].strip()
                            else:
                                caption = meta_desc
                except Exception:
                    pass
                
                if not caption:
                    try:
                        spans = page.locator('span._ap3a._aaco._aacw._aacx._aad7._aade').all()
                        if spans:
                            caption = spans[0].inner_text()
                    except Exception:
                        pass
                        
                txt_path = post_folder / f"{sc}.txt"
                txt_path.write_text(caption, encoding="utf-8")
                print(f"  Legenda obtida e guardada ({len(caption)} chars).", flush=True)
                
                image_urls = set()
                
                try:
                    meta_img = page.locator('meta[property="og:image"]').get_attribute('content')
                    if meta_img:
                        image_urls.add(meta_img)
                except Exception:
                    pass
                
                try:
                    next_btn_selector = 'button:has(svg[aria-label*="Next"]), button:has(svg[aria-label*="Seguinte"]), button:has(svg[aria-label*="Avançar"]), button[aria-label*="Next"], button[aria-label*="Seguinte"], button[aria-label*="Avançar"]'
                    
                    carousel_images = set()
                    for slide_step in range(10):
                        imgs = page.locator('article img').all()
                        for img in imgs:
                            src = img.get_attribute('src')
                            if src and 'cdninstagram.com' in src:
                                carousel_images.add(src)
                                
                        next_btn = page.locator(next_btn_selector)
                        if next_btn.count() > 0 and next_btn.first.is_visible():
                            next_btn.first.click()
                            page.wait_for_timeout(1000)
                        else:
                            break
                            
                    if carousel_images:
                        image_urls.update(carousel_images)
                except Exception as ce:
                    print(f"  [Aviso] Erro a percorrer carrossel: {ce}", flush=True)
                    
                if not image_urls:
                    imgs = page.locator('img').all()
                    for img in imgs:
                        src = img.get_attribute('src')
                        if src and 'cdninstagram.com' in src:
                            image_urls.add(src)
                            
                img_count = 0
                for img_url in image_urls:
                    img_count += 1
                    img_name = f"{sc}_{img_count}.jpg"
                    img_path = post_folder / img_name
                    if download_file(img_url, img_path):
                        print(f"  Imagem descarregada: {img_name}", flush=True)
                        
                print(f"  Processamento concluído. {img_count} imagens descarregadas.", flush=True)
                
            except Exception as pe:
                print(f"  ❌ Erro ao abrir ou processar post {sc}: {pe}", flush=True)
                
    except Exception as e:
        print("Erro:", e, flush=True)
    finally:
        if context:
            context.close()
        if playwright_inst:
            playwright_inst.stop()
            
    print("\n✅ Todos os posts descarregados com sucesso por Playwright!", flush=True)

if __name__ == "__main__":
    main()
