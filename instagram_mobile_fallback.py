import os
import pickle
import json
from datetime import datetime
from instagrapi import Client

_client = None

def get_fallback_client():
    global _client
    if _client is not None:
        return _client
        
    cl = Client()
    settings_file = "instagrapi_settings.json"
    session_file = "instaloader.session"
    

    if os.path.exists(settings_file):
        try:
            print(f"A carregar sessão do Instagrapi a partir de {settings_file}...")
            cl.load_settings(settings_file)
            cl.get_timeline_feed()
            _client = cl
            print("Sessão do Instagrapi ativa e carregada com sucesso.")
            return _client
        except Exception as e:
            print("Sessão guardada do Instagrapi expirada ou inválida:", e)
            

    if os.path.exists(session_file):
        try:
            print(f"A ler cookies de {session_file} para o Instagrapi...")
            with open(session_file, "rb") as f:
                cookies = pickle.load(f)
            
            sessionid = cookies.get("sessionid")
            if sessionid:
                print("A iniciar sessão do Instagrapi com sessionid...")
                cl.login_by_sessionid(sessionid)
                cl.dump_settings(settings_file)
                _client = cl
                print("Login do Instagrapi com sessionid concluído com sucesso.")
                return _client
        except Exception as e:
            print("Erro ao fazer login no Instagrapi com cookies:", e)
            

    username = os.environ.get("INSTA_USERNAME")
    password = os.environ.get("INSTA_PASSWORD")
    if username and password:
        try:
            print(f"A tentar login no Instagrapi com credenciais ({username})...")
            cl.login(username, password)
            cl.dump_settings(settings_file)
            _client = cl
            print("Login do Instagrapi com credenciais concluído.")
            return _client
        except Exception as e:
            print("Erro ao fazer login no Instagrapi com credenciais:", e)
            
    print("Aviso: Instagrapi não conseguiu autenticar. Fallback indisponível.")
    return None

class InstagrapiPostWrapper:
    def __init__(self, media):
        self.shortcode = media.code
        self.date_utc = media.taken_at
        

        if self.date_utc and self.date_utc.tzinfo is not None:
            self.date_utc = self.date_utc.replace(tzinfo=None)
            
        self.caption = media.caption_text or ""
        self.url = media.thumbnail_url
        self.video_url = media.video_url or ""
        self.is_video = media.media_type == 2
        self.mediacount = len(media.resources) if media.media_type == 8 else 1
        self.typename = "GraphSidecar" if media.media_type == 8 else ""
        self.owner_username = media.user.username
        self._resources = media.resources or []

    def get_sidecar_nodes(self):
        class Node:
            def __init__(self, res):
                self.display_url = res.thumbnail_url
                self.video_url = res.video_url or ""
                self.is_video = res.media_type == 2
        return [Node(r) for r in self._resources]
