import argparse
import calendar
import sys
import os
import json
import time
import subprocess
from datetime import datetime


sys.path.insert(0, os.getcwd())

from wikipedia_scraper import process_day
from web_sitemap_scraper import (
    process_web_sitemaps,
    get_sitemap_candidates,
    scrape_article,
    enrich_article_with_nvidia,
    save_article_to_block,
    extract_day_from_candidate,
    NvidiaLimitExceeded,
    is_article_already_in_block,
    build_article_shortcode
)

PROGRESS_FILE = "historical_progress.json"

def load_progress():
    from archive_storage import FileLock
    lock = FileLock(PROGRESS_FILE + ".lock")
    if lock.acquire():
        try:
            if os.path.exists(PROGRESS_FILE):
                with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        finally:
            lock.release()
    return {
        "wikipedia_completed_days": [],
        "web_completed_days": []
    }

def save_progress(progress, overwrite=False):
    from archive_storage import FileLock
    lock = FileLock(PROGRESS_FILE + ".lock")
    if lock.acquire():
        try:
            if overwrite:
                merged_progress = {
                    "wikipedia_completed_days": sorted(list(set(progress.get("wikipedia_completed_days", [])))),
                    "web_completed_days": sorted(list(set(progress.get("web_completed_days", []))))
                }
            else:

                disk_progress = {
                    "wikipedia_completed_days": [],
                    "web_completed_days": []
                }
                if os.path.exists(PROGRESS_FILE):
                    try:
                        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                            disk_progress = json.load(f)
                    except Exception:
                        pass
                
                wiki_merged = set(disk_progress.get("wikipedia_completed_days", [])) | set(progress.get("wikipedia_completed_days", []))
                web_merged = set(disk_progress.get("web_completed_days", [])) | set(progress.get("web_completed_days", []))
                
                merged_progress = {
                    "wikipedia_completed_days": sorted(list(wiki_merged)),
                    "web_completed_days": sorted(list(web_merged))
                }
            
            with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
                json.dump(merged_progress, f, ensure_ascii=False, indent=2)
                
            progress["wikipedia_completed_days"] = merged_progress["wikipedia_completed_days"]
            progress["web_completed_days"] = merged_progress["web_completed_days"]
        except Exception as e:
            print(f"[Erro] Falha ao guardar ficheiro de progresso: {e}")
        finally:
            lock.release()
    else:
        print("[Erro] Não foi possível adquirir lock para gravar progresso.")

def run_historical(start_year, end_year, limit_per_day, lang, max_nvidia_calls=0, months=None, local_llm=None, use_nvidia=False, nvidia_model=None, nvidia_key_index=0):
    import web_sitemap_scraper
    web_sitemap_scraper.USE_NVIDIA = False
    
    if use_nvidia:
        web_sitemap_scraper.USE_NVIDIA = True
        if nvidia_model:
            web_sitemap_scraper.NVIDIA_MODEL = nvidia_model
            print(f"[NVIDIA] Modelo inicial configurado: {nvidia_model}")
        if nvidia_key_index > 0:
            web_sitemap_scraper.NVIDIA_KEY_INDEX = nvidia_key_index
            print(f"[NVIDIA] Índice de chave inicial configurado: {nvidia_key_index}")
        print("[NVIDIA] Modo NVIDIA ativado para a extração de notícias.")
    elif local_llm:
        web_sitemap_scraper.LOCAL_LLM = local_llm
        print(f"[Ollama] Modo Ollama local ativado ({local_llm}).")
        
    if max_nvidia_calls > 0:
        web_sitemap_scraper.NVIDIA_CALL_LIMIT = max_nvidia_calls
    else:
        web_sitemap_scraper.NVIDIA_CALL_LIMIT = 0
    progress = load_progress()
    last_status_time = 0
    
    wiki_done = set(progress.get("wikipedia_completed_days", []))
    web_done = set(progress.get("web_completed_days", []))
    
    if months:
        months_to_process = [int(m.strip()) for m in months.split(",") if m.strip()]
        months_str = ", ".join(str(m) for m in months_to_process)
    else:
        months_to_process = list(range(1, 13))
        months_str = "todos (1 a 12)"
        
    print("=" * 60)
    print("INICIANDO PROCESSAMENTO HISTÓRICO AUTOMÁTICO (V2)")
    print(f"Anos planeados: {start_year} a {end_year}")
    print(f"Meses planeados: {months_str}")
    print(f"Limite Web por dia: {'Sem limite (todas)' if limit_per_day <= 0 else limit_per_day}")
    print(f"Língua: {lang or 'pt'}")
    print(f"Progresso atual: {len(wiki_done)} dias Wikipedia, {len(web_done)} blocos diários de Web já processados.")
    if use_nvidia:
        print(f"API: NVIDIA (via nvidia_client.py)")
    elif local_llm:
        print(f"API: Ollama local ({local_llm})")
    else:
        print("API: Nenhuma (modo metadados básicos)")
    print("Pressiona Ctrl+C a qualquer momento para parar e guardar o estado atual.")
    print("=" * 60)
    
    try:
        for year in range(start_year, end_year + 1):
            print(f"\n" + "=" * 50)
            print(f"=== A PROCESSAR ANO: {year} ===")
            print("=" * 50)
            
            for month in months_to_process:

                web_langs = [lang] if lang else ["pt"]
                sitemaps_by_lang = {}
                
                num_days = calendar.monthrange(year, month)[1]
                
                for day in range(1, num_days + 1):

                    current_time = time.time()
                    if current_time - last_status_time > 30:
                        try:
                            web_sitemap_scraper.save_key_status_to_file()
                        except Exception:
                            pass
                        last_status_time = current_time
                        










                        

                    for wl in web_langs:
                        day_lang_str = f"{wl}-{year}-{month:02d}-{day:02d}"
                        
                        if day_lang_str not in web_done:

                            if wl not in sitemaps_by_lang:
                                print(f"\n[Web Sitemap] A carregar sitemaps ({wl.upper()}) para {year}-{month:02d}...")
                                candidates = get_sitemap_candidates(wl, year, month, day=None)
                                if candidates:
                                    from collections import defaultdict
                                    grouped = defaultdict(list)
                                    for cand in candidates:
                                        d = extract_day_from_candidate(cand, year, month)
                                        if d is not None:
                                            grouped[d].append(cand)
                                    sitemaps_by_lang[wl] = grouped
                                else:
                                    sitemaps_by_lang[wl] = {}
                                    
                            day_candidates = sitemaps_by_lang[wl].get(day, [])
                            if day_candidates:
                                print(f"\n[Web Sitemap][{wl.upper()}] {year}-{month:02d}-{day:02d}: A processar {len(day_candidates)} notícias...")

                                from urllib.parse import urlparse
                                from collections import defaultdict
                                
                                by_domain = defaultdict(list)
                                for cand in day_candidates:
                                    domain = urlparse(cand.get("url", "")).netloc
                                    by_domain[domain].append(cand)
                                
                                interleaved = []
                                max_len = max(len(lst) for lst in by_domain.values()) if by_domain else 0
                                for idx in range(max_len):
                                    for domain in sorted(by_domain.keys()):
                                        if idx < len(by_domain[domain]):
                                            interleaved.append(by_domain[domain][idx])
                                day_candidates = interleaved
                                
                                if limit_per_day > 0:
                                    day_candidates = day_candidates[:limit_per_day]
                                    
                                # Filtrar candidatos que já existem no arquivo diário do Drive
                                pending_candidates = []
                                for cand in day_candidates:
                                    url = cand["url"]
                                    if not is_article_already_in_block(wl, year, month, day, url):
                                        pending_candidates.append(cand)
                                        
                                day_processed = 0
                                
                                if pending_candidates:
                                    # Calcular totais apenas para as notícias que faltam processar
                                    from urllib.parse import urlparse
                                    domain_counts = {}
                                    domain_current = {}
                                    for cand in pending_candidates:
                                        dom = urlparse(cand.get("url", "")).netloc.replace("www.", "")
                                        domain_counts[dom] = domain_counts.get(dom, 0) + 1
                                        domain_current[dom] = 0

                                    friendly_names = {
                                        "publico.pt": "Público",
                                        "expresso.pt": "Expresso",
                                        "sicnoticias.pt": "SIC Notícias",
                                        "sabado.pt": "Sábado",
                                        "caras.pt": "Caras",
                                        "vip.pt": "VIP",
                                        "novagente.pt": "Nova Gente",
                                        "bbc.com": "BBC",
                                        "bbc.co.uk": "BBC",
                                        "cnn.com": "CNN",
                                        "edition.cnn.com": "CNN",
                                        "nytimes.com": "NY Times"
                                    }

                                    print(f"\n[Web Sitemap][{wl.upper()}] {year}-{month:02d}-{day:02d}: A processar {len(pending_candidates)} notícias pendentes...")

                                    for cand in pending_candidates:
                                        url = cand["url"]
                                        dom = urlparse(url).netloc.replace("www.", "")
                                        domain_current[dom] += 1
                                        jornal = friendly_names.get(dom, dom)

                                        import sys
                                        sys.stdout.write(f"\r [{wl.upper()}] A extrair... notícia {domain_current[dom]}/{domain_counts[dom]} [{jornal}]")
                                        sys.stdout.flush()

                                        article = scrape_article(url)
                                        if not article or not article["title"]:
                                            continue
                                        ai_payload = enrich_article_with_nvidia(article, wl)
                                        if ai_payload is None:
                                            print(f"\n [Aviso] IA falhou para '{article['title'][:60]}...'. Artigo não gravado, será reprocessado.")
                                            continue
                                        if save_article_to_block(wl, year, month, day, article, ai_payload, url):
                                            day_processed += 1
                                            
                                    print(f"\n[Web Sitemap][{wl.upper()}] {year}-{month:02d}-{day:02d} concluído: {day_processed} notícias adicionadas.")
                            else:
                                pass
                                
                            web_done.add(day_lang_str)
                            progress["web_completed_days"] = sorted(list(web_done))
                            save_progress(progress)
                        else:
                            pass
                            
        print("\n" + "=" * 60)
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] CONCLUÍDO! Todo o histórico planeado foi totalmente processado.")
        print("=" * 60)
        
    except KeyboardInterrupt:
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print("\n\n" + "=" * 60)
        print(f"[{now_str}] PROCESSAMENTO INTERROMPIDO PELO UTILIZADOR (Ctrl+C)")
        print("A guardar progresso no disco...")
        progress["wikipedia_completed_days"] = sorted(list(wiki_done))
        progress["web_completed_days"] = sorted(list(web_done))
        save_progress(progress)
        print("Progresso guardado com sucesso. Corre novamente o CMD para retomar.")
        print("=" * 60 + "\n")
        sys.exit(0)
        
    except NvidiaLimitExceeded:
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print("\n\n" + "=" * 60)
        print(f"[{now_str}] LIMITE DIÁRIO DE CHAMADAS AO NVIDIA ATINGIDO")
        print("A guardar progresso no disco...")
        progress["wikipedia_completed_days"] = sorted(list(wiki_done))
        progress["web_completed_days"] = sorted(list(web_done))
        save_progress(progress)
        print("Progresso guardado com sucesso. Podes correr novamente amanhã.")
        print("=" * 60 + "\n")
        sys.exit(2)

def recover_failed_days(start_year, end_year, threshold):
    progress = load_progress()
    web_done = progress.get("web_completed_days", [])
    
    new_web_done = []
    recovered_count = 0
    
    print(f"\nA escanear dias concluídos de {start_year} a {end_year} com limiar < {threshold} notícias...")
    
    loaded_blocks = {}
    
    for day_lang_str in web_done:
        parts = day_lang_str.split("-")
        if len(parts) == 4:
            wl, y_str, m_str, d_str = parts
            try:
                y, m, d = int(y_str), int(m_str), int(d_str)
                if start_year <= y <= end_year:
                    from archive_storage import block_id_for_month_day, load_block, parse_post_date
                    block_id = block_id_for_month_day(m, d)
                    
                    block_key = f"{wl}-{block_id}"
                    if block_key not in loaded_blocks:
                        loaded_blocks[block_key] = load_block(wl, block_id)
                        
                    posts = loaded_blocks[block_key]
                    day_posts_count = 0
                    for post in posts:
                        parsed = parse_post_date(post.get("date", ""))
                        if parsed and parsed.year == y and parsed.month == m and parsed.day == d:
                            day_posts_count += 1
                            
                    if day_posts_count < threshold:
                        print(f"  [Recuperado] {day_lang_str}: apenas {day_posts_count} notícias no arquivo JSON.")
                        recovered_count += 1
                        continue
            except Exception as e:
                print(f"Erro ao verificar {day_lang_str}: {e}")
                
        new_web_done.append(day_lang_str)
        
    if recovered_count > 0:
        progress["web_completed_days"] = new_web_done
        save_progress(progress, overwrite=True)
        print(f"\n[OK] Varredura concluída! {recovered_count} dias foram removidos e serão reprocessados na próxima execução.")
    else:
        print("\n[OK] Varredura concluída. Nenhum dia falhado encontrado.")

def run_cdxj_update(args):
    cmd = [
        sys.executable,
        "-u",
        "build_arquivo_cdxj_index.py",
        "--start-year",
        str(args.start_year),
        "--end-year",
        str(args.end_year),
    ]
    if args.cdxj_input_dir:
        cmd.extend(["--input-dir", args.cdxj_input_dir])
    elif args.cdxj_collections:
        cmd.extend(["--collections", *[item.strip() for item in args.cdxj_collections.split(",") if item.strip()]])
    else:
        cmd.append("--all-remote")
    if args.cdxj_force:
        cmd.append("--force")

    print("\n" + "=" * 60)
    print("[CDXJ] A atualizar indice local apos recolha historica...")
    print(" ".join(cmd))
    print("=" * 60)
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Recolha histórica completa de Janeiro a Dezembro de forma automática e resumível.")
    parser.add_argument("--start-year", type=int, default=1990, help="Ano de início da recolha. Padrão: 1990.")
    parser.add_argument("--end-year", type=int, default=2026, help="Ano de fim da recolha. Padrão: 2026.")
    parser.add_argument("--limit-per-day", "--limit", type=int, default=0, help="Número máximo de notícias por dia (0 para ilimitado). Padrão: 0 (todas).")
    parser.add_argument("--lang", choices=["pt", "en"], help="Processa apenas este idioma. Padrão: processa ambos.")
    parser.add_argument("--max-nvidia-calls", type=int, default=0, help="Número máximo de chamadas ao NVIDIA nesta execução.")
    parser.add_argument("--recover-failed", action="store_true", help="Faz scan aos blocos diários de dados e remove os dias com menos notícias do que o limiar do progresso para os reprocessar.")
    parser.add_argument("--recovery-threshold", type=int, default=1, help="Limiar de notícias para o scan de recuperação. Dias com menos do que este número de notícias serão reprocessados. Padrão: 1.")
    parser.add_argument("--months", type=str, help="Meses a processar separados por vírgula (ex: 1,2). Padrão: todos.")
    parser.add_argument("--local-llm", type=str, help="Usa um modelo local via Ollama (ex: gemma2:2b) para a extração.")
    parser.add_argument("--use-nvidia", action="store_true", help="Usa a API da NVIDIA em vez do Ollama para a extração.")
    parser.add_argument("--nvidia-model", type=str, default="meta/llama-3.3-70b-instruct", help="Define o modelo NVIDIA inicial a usar na rotação.")
    parser.add_argument("--nvidia-key-index", type=int, default=0, help="Define o índice da chave API NVIDIA inicial a usar.")
    parser.add_argument("--update-cdxj", action="store_true", help="Depois da recolha local, atualiza tambem o indice CDXJ filtrado do Arquivo.pt.")
    parser.add_argument("--cdxj-input-dir", type=str, help="Pasta local com CDXJ brutos para usar com --update-cdxj.")
    parser.add_argument("--cdxj-collections", type=str, help="Colecoes remotas separadas por virgula para usar com --update-cdxj.")
    parser.add_argument("--cdxj-force", action="store_true", help="Forca reprocessamento de fontes CDXJ ja registadas.")
    args = parser.parse_args()
    
    if args.recover_failed:
        recover_failed_days(args.start_year, args.end_year, args.recovery_threshold)
    else:
        run_historical(args.start_year, args.end_year, args.limit_per_day, args.lang, args.max_nvidia_calls, args.months, args.local_llm, args.use_nvidia, args.nvidia_model, args.nvidia_key_index)
        if args.update_cdxj:
            run_cdxj_update(args)
