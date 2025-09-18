import subprocess
import sys
import importlib
import os
import requests
import pandas as pd
from typing import Optional, Dict

# ------------------ INSTALAR PACOTES ------------------ #
def instalar_requisitos(arquivo_requisitos="requirements.txt"):
    """
    Instala pacotes listados em um arquivo requirements.txt.
    Retorna lista de pacotes instalados ou faltantes.
    """
    arquivo_requisitos = os.path.join(os.path.dirname(__file__), arquivo_requisitos)
    if not os.path.exists(arquivo_requisitos):
        return []

    with open(arquivo_requisitos, "r") as f:
        pacotes = [linha.strip() for linha in f if linha.strip() and not linha.startswith("#")]

    pacotes_faltando = []
    for pacote in pacotes:
        nome_pacote = pacote.split("==")[0].split(">=")[0].split("<=")[0]
        try:
            importlib.import_module(nome_pacote)
        except ImportError:
            pacotes_faltando.append(pacote)

    if pacotes_faltando:
        subprocess.check_call([sys.executable, "-m", "pip", "install"] + pacotes_faltando)

    return pacotes_faltando

# ------------------ API URLs ------------------ #
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# ------------------ FUNÇÕES DE API ------------------ #
def geocode(query: str) -> Optional[Dict]:
    """
    Faz geocodificação de uma cidade, retornando coordenadas.
    """
    try:
        parts = [p.strip() for p in query.split(",")]
        city = parts[0]
        country_hint = parts[1].lower() if len(parts) > 1 else None

        r = requests.get(GEOCODE_URL, params={
            "name": city,
            "count": 10,
            "language": "pt",
            "format": "json"
        }, timeout=10)
        r.raise_for_status()
        data = r.json()
        results = data.get("results") or []
        if not results:
            return None

        if country_hint:
            def match_country(res):
                cc = (res.get("country_code") or "").lower()
                nm = (res.get("country") or "").lower()
                return country_hint in (cc, nm)
            filtered = [res for res in results if match_country(res)]
            if filtered:
                return filtered[0]

        return results[0]
    except requests.exceptions.RequestException:
        return None

def get_forecast(lat: float, lon: float, tz: str = "auto") -> Optional[Dict]:
    """
    Consulta a API de previsão e retorna JSON bruto.
    """
    try:
        params = {
            "latitude": lat,
            "longitude": lon,
            "timezone": tz,
            "current": "temperature_2m,precipitation,weather_code",
            "hourly": "temperature_2m,precipitation",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum"
        }
        r = requests.get(FORECAST_URL, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.RequestException:
        return None

# ------------------ LISTA DE LUGARES ------------------ #
lugares_cadastrados = [
    {"nome": "São Paulo", "latitude": -23.5475, "longitude": -46.6361, "timezone": "America/Sao_Paulo"}
]

# ------------------ FUNÇÃO RESOLVER TIMEZONE ------------------ #
def resolver_timezone(lugar: Dict, wx: Dict) -> str:
    """
    Retorna um timezone válido com base no lugar ou nos dados da API.
    """
    tz = (lugar.get("timezone") or "").strip() if lugar else ""
    if tz.lower() in ("", "auto", "gmt0", "utc+0", "utc-0"):
        tz = (wx.get("timezone") or "").strip() if wx else ""
    if not tz:
        tz = "UTC"
    return tz

# ------------------ CONSULTAR API ------------------ #
def consultar_api(lugar):
    """
    Consulta a API e retorna apenas:
    - hourly_hoje: DataFrame com as 24h do dia atual no timezone correto
    - daily_df: DataFrame com previsões diárias
    """
    forecast = get_forecast(lugar["latitude"], lugar["longitude"], lugar.get("timezone", "auto"))
    if not forecast:
        return None, None

    hourly = forecast.get("hourly", {})
    daily = forecast.get("daily", {})

    if not hourly or not daily:
        return None, None

    # ---------- Processa dados horários ----------
    hourly_df = pd.DataFrame(hourly)

    # Descobre timezone válido
    tz = resolver_timezone(lugar, forecast)

    # Converte para datetime com fuso horário
    hourly_df["date"] = pd.to_datetime(hourly_df["time"], utc=True).dt.tz_convert(tz)
    hourly_df["temperature_2m"] = pd.to_numeric(hourly_df["temperature_2m"], errors="coerce")
    if "precipitation" in hourly_df.columns:
        hourly_df["precipitation"] = pd.to_numeric(hourly_df["precipitation"], errors="coerce")

    # Mantém somente as próximas 24h do dia atual no timezone local
    hoje_local = pd.Timestamp.now(tz=tz).normalize()
    amanha_local = hoje_local + pd.Timedelta(days=1)
    mask_hoje = (hourly_df["date"] >= hoje_local) & (hourly_df["date"] < amanha_local)
    hourly_hoje = hourly_df.loc[mask_hoje].reset_index(drop=True)

    if hourly_hoje.empty:
        hourly_hoje = hourly_df.head(24).reset_index(drop=True)

    # ---------- Processa dados diários ----------
    daily_df = pd.DataFrame(daily)
    daily_df["date"] = pd.to_datetime(daily_df["time"], utc=True).dt.tz_convert(tz)

    for col in ["temperature_2m_min", "temperature_2m_max", "precipitation_sum"]:
        if col in daily_df.columns:
            daily_df[col] = pd.to_numeric(daily_df[col], errors="coerce")

    return hourly_hoje, daily_df
