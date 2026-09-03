import os
import re
import requests


class NvidiaQuotaExceeded(Exception):
    pass


class NvidiaModelError(Exception):
    pass


DEFAULT_NVIDIA_MODEL = "meta/llama-3.1-8b-instruct"
NVIDIA_API_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
NVIDIA_KEY_FILE = "nvidia_api_key.local.txt"


def _append_unique_keys(target, raw_value):
    for line in (raw_value or "").splitlines():
        key = line.strip()
        if key and not key.startswith("#") and key not in target:
            target.append(key)


def load_nvidia_api_keys(key_file=NVIDIA_KEY_FILE):
    keys = []
    if os.path.exists(key_file):
        with open(key_file, "r", encoding="utf-8") as f:
            _append_unique_keys(keys, f.read())

    _append_unique_keys(keys, os.environ.get("NVIDIA_API_KEY", ""))
    return keys


class NvidiaKeyPool:
    def __init__(self, api_keys, starting_model=None, starting_key_index=0):
        raw_keys = list(api_keys)
        if starting_key_index > 0 and starting_key_index < len(raw_keys):
            self.api_keys = raw_keys[starting_key_index:] + raw_keys[:starting_key_index]
        else:
            self.api_keys = raw_keys
        self.exhausted = [False] * len(self.api_keys)
        self.current_index = 0
        default_models = [
            "meta/llama-3.1-8b-instruct",
            "meta/llama-3.3-70b-instruct",
            "google/gemma-2-2b-it"
        ]
        if starting_model and starting_model in default_models:
            idx = default_models.index(starting_model)
            self.models = default_models[idx:] + default_models[:idx]
        else:
            self.models = default_models
        self.current_model_index = 0

    def get_current_model(self):
        return self.models[self.current_model_index]

    def has_keys(self):
        return bool(self.api_keys)

    def get_current_key_info(self):
        if not self.api_keys:
            return "Nenhuma chave NVIDIA configurada."
        active_count = sum(1 for value in self.exhausted if not value)
        return f"Chave NVIDIA #{self.current_index + 1} de {len(self.api_keys)} (Ativas: {active_count}/{len(self.api_keys)})"

    def save_key_status_to_file(self):
        try:
            from archive_storage import get_auto_terminal_label, update_shared_api_status

            label = get_auto_terminal_label()
            self.exhausted = update_shared_api_status(
                label,
                self.current_index,
                len(self.api_keys),
                self.exhausted,
            )
        except Exception as exc:
            print(f"[Erro] Falha ao gravar estado da chave NVIDIA: {exc}")

    def mark_current_exhausted(self):
        if self.exhausted:
            self.exhausted[self.current_index] = True

    def rotate(self):
        total = len(self.api_keys)
        if total <= 1:
            return False

        start_index = self.current_index
        while True:
            self.current_index = (self.current_index + 1) % total
            if not self.exhausted[self.current_index]:
                break
            if self.current_index == start_index:
                return False

        self.save_key_status_to_file()
        print(f"Rotacao de API NVIDIA: {self.get_current_key_info()}")
        return True

    def chat_json(self, prompt, model=None, timeout=25):
        if not self.api_keys:
            return ""

        import time
        max_retries = 12
        
        use_pool_models = (model is None or model == DEFAULT_NVIDIA_MODEL)
        
        while True:
            if use_pool_models:
                model_to_use = self.models[self.current_model_index]
            else:
                model_to_use = model

            try:
                backoff = 3.0
                for attempt in range(max_retries):
                    try:
                        response = requests.post(
                            NVIDIA_API_URL,
                            headers={
                                "Authorization": f"Bearer {self.api_keys[self.current_index]}",
                                "Content-Type": "application/json",
                            },
                            json={
                                "model": model_to_use,
                                "messages": [
                                    {
                                        "role": "system",
                                        "content": "You are a careful editorial assistant. Return only valid JSON and no markdown.",
                                    },
                                    {"role": "user", "content": prompt},
                                ],
                                "temperature": 0.35,
                                "response_format": {"type": "json_object"},
                                "max_tokens": 2048,
                            },
                            timeout=timeout,
                        )
                    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as net_err:
                        print(f"\n[NVIDIA] Erro de rede/timeout ({net_err}) para {model_to_use} na chave #{self.current_index + 1}.")
                        raise NvidiaModelError(str(net_err))

                    if response.status_code >= 500:
                        print(f"\n[NVIDIA] Erro de servidor ({response.status_code}) para {model_to_use} na chave #{self.current_index + 1}.")
                        raise NvidiaModelError(f"HTTP {response.status_code}")

                    if response.status_code == 429:
                        err_msg = ""
                        try:
                            err_json = response.json()
                            err_msg = err_json.get("error", {}).get("message", "").lower()
                        except Exception:
                            err_msg = response.text.lower()
                        
                        is_daily = any(marker in err_msg for marker in ("requests per day", "tokens per day", "rpd", "tpd", "daily", "quota", "credit"))
                        if is_daily:

                            raise NvidiaQuotaExceeded(f"NVIDIA API quota exceeded: {err_msg}")


                        import random
                        jitter = random.uniform(3.0, 8.0)
                        sleep_seconds = backoff + jitter
                        print(f"\n[NVIDIA] Limite de 40 RPM atingido para {model_to_use}. A aguardar {sleep_seconds:.1f}s antes da tentativa {attempt + 1}/{max_retries}...")
                        time.sleep(sleep_seconds)
                        backoff = min(backoff * 2.0, 60.0)
                        continue

                    if response.status_code == 422:
                        print(f"\n[NVIDIA] Modelo {model_to_use} nao suporta response_format (HTTP 422).")
                        raise NvidiaModelError("HTTP 422: response_format not supported")

                    if response.status_code >= 400:
                        err_msg = ""
                        try:
                            err_json = response.json()
                            err_msg = err_json.get("error", {}).get("message", "").lower()
                        except Exception:
                            err_msg = response.text.lower()
                        
                        is_daily = any(marker in err_msg for marker in ("requests per day", "tokens per day", "rpd", "tpd", "daily", "quota", "credit"))
                        if is_daily:
                            raise NvidiaQuotaExceeded(f"NVIDIA API quota exceeded: {err_msg}")
                        
                        raise RuntimeError(f"NVIDIA API {response.status_code}: {response.text[:500]}")

                    data = response.json()
                    return data["choices"][0]["message"]["content"]
                    
                raise RuntimeError("NVIDIA API 429: Excedido o número de tentativas sob limite de rate limit (429).")

            except NvidiaQuotaExceeded as exc:
                if use_pool_models and self.current_model_index + 1 < len(self.models):
                    old_model = self.models[self.current_model_index]
                    self.current_model_index += 1
                    new_model = self.models[self.current_model_index]
                    print(f"\n[NVIDIA] Quota esgotada para o modelo {old_model} na chave #{self.current_index + 1}.")
                    print(f"[NVIDIA] A rodar para o modelo seguinte: {new_model}...")
                    continue
                else:
                    if use_pool_models:
                        self.current_model_index = 0
                    raise exc

            except NvidiaModelError as exc:
                if use_pool_models and self.current_model_index + 1 < len(self.models):
                    old_model = self.models[self.current_model_index]
                    self.current_model_index += 1
                    new_model = self.models[self.current_model_index]
                    print(f"\n[NVIDIA] Falha temporaria no modelo {old_model}. A rodar para o modelo seguinte: {new_model}...")
                    continue
                else:
                    if use_pool_models:
                        self.current_model_index = 0
                    raise exc
