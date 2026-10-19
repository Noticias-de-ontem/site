import json
import sys

sys.stdout.reconfigure(encoding="utf-8")

posts = json.load(open("pending_posts.json", encoding="utf-8"))
posts_by_id = {p["id"]: p for p in posts}

candidate_ids_26 = [
    "pt_2026-01-01_1", # Lula toma posse como Presidente do Brasil (User: Sim)
    "pt_2026-01-02_1", # Velório de Pelé no Vila Belmiro (User: Talvez, importante sim)
    "pt_2026-01-04_2", # Benfica conquista a Liga Portuguesa (User: Sim)
    "pt_2026-01-05_1", # Fernanda Torres vence Globo de Ouro (User: Sim, FB)
    "pt_2026-01-06_2", # Sporting e Benfica perdem pontos (User: Talvez próximo de sim)
    "pt_2026-01-07_1", # Sporting vs FC Porto clássico (User: Sim)
    "pt_2026-01-08_1", # Cristiano Ronaldo ruma ao Al-Nassr (User: Sim)
    "pt_2026-01-08_2", # António Costa pode deixar Conselho Europeu (User: Sim)
    "pt_2026-01-10_1", # Ronaldo ganha 200M promover Mundial (User: Sim)
    "pt_2026-01-13_1", # Governo espanhol limita alojamento turístico (User: Sim)
    "pt_2026-01-18_1", # Israel aprova cessar-fogo em Gaza (User: Sim)
    "pt_2026-01-20_2", # Messi e Ronaldo revelam amizade na UEFA (User: Sim)
    "pt_2026-01-21_2", # Messi supera Ronaldo na eleição da Marca (User: Sim)
    "pt_2026-01-24_1", # Ronaldo quebra recorde de likes no Instagram (User: Sim)
    "pt_2026-01-25_2", # Alerta sobre filtros de IA e crianças (User: Sim)
    "pt_2026-01-27_2", # Crise do Banco Comercial Português (User: Talvez)
    "pt_2026-01-30_1", # Portugal vai a votos para Primeiro-Ministro (User: Sim)
    "pt_2026-02-01_1", # Portugal com maior crescimento UE e dívida < 99% (User: Sim)
    "pt_2026-02-02_1", # Rui Rocha reeleito na IL (User: Sim)
    "pt_2026-02-03_1", # Netanyahu recebido por Trump na Casa Branca (User: Sim)
    "pt_2026-02-04_1", # Trump volta ao Facebook e Instagram (User: Sim)
    "pt_2026-02-06_1", # Estátua de Ronaldo na Times Square (User: Sim)
    "pt_2026-02-07_1", # Cristiano Ronaldo celebra 39 anos (User: Sim, FB)
    "pt_2026-02-07_2", # SpaceX Falcon Heavy com carro no espaço (User: Talvez se não houver mais nada / Sim)
    "pt_2026-02-11_1", # Portugal conquista o Euro de Futsal (User: Sim)
    "pt_2026-02-11_2", # Barack Obama vence primárias democratas (User: Sim)
]

print(f"Total candidate 26: {len(candidate_ids_26)}")
for i, pid in enumerate(candidate_ids_26, 1):
    p = posts_by_id.get(pid)
    opt = p["options"][int(p.get("selected_option", 0) or 0)]
    print(f"{i:2d}. [{pid}] ({opt.get('original_year')}) [{opt.get('category')}] {opt.get('title')}")
