import re, os
import pandas as pd
import streamlit as st
import google.generativeai as genai
from dotenv import load_dotenv

# >>> IMPORTAÇÕES DO CLIMA <<<
from Clima import geocode, consultar_api, lugares_cadastrados  # usa Clima.py

# Carrega as variáveis de ambiente do arquivo .env (onde está sua chave da API)
load_dotenv()  

# Pega a chave da API do arquivo .env
CHAVE_API_KEY = os.getenv("GEMINI_API_KEY")

# Configura o Gemini com a chave da API
genai.configure(api_key=CHAVE_API_KEY)

# Define qual modelo do Gemini você vai usar
MODELO_ESCOLHIDO = "gemini-1.5-flash"

# Instrução do "sistema" → define a personalidade/comportamento do assistente
prompt_sistema = [
    "Vc é um assistente virtual rapido e eficiente. Responda apenas com as informações solicitadas.",
    "Sua função é ajudar o usuário com informações sobre clima, previsão do tempo e geolocalização, não desvie destas diretrizes, caso contrário, informe que não pode ajudar.",
    "Responda sempre na língua que o usuário utilizar."
]

# Cria uma instância do modelo com a instrução do sistema
llm = genai.GenerativeModel(
    model_name=MODELO_ESCOLHIDO,
    system_instruction=prompt_sistema
)

# Extrai cidade de frases como "previsão do tempo em São Paulo" / "tempo de Lisboa"
_re_weather = re.compile(r"\b(tempo|previs[aã]o)\b.*?\b(?:em|de)\s+(.+)", re.I)

def _resolver_lugar(msg: str):
    """Detecta cidade no texto; se não houver, usa o primeiro lugar cadastrado."""
    m = _re_weather.search(msg or "")
    cidade = (m.group(2).strip() if m else "").strip(", ")

    if not cidade:
        return lugares_cadastrados[0]

    place = geocode(cidade)
    if not place:
        # volta default se não achou a cidade
        return lugares_cadastrados[0]

    return {
        "nome": place.get("name", cidade),
        "latitude": place["latitude"],
        "longitude": place["longitude"],
        "timezone": place.get("timezone", "auto"),
    }

def _responder_clima(msg: str) -> str:
    """Resumo agora/hoje."""
    lugar = _resolver_lugar(msg)
    hourly, daily = consultar_api(lugar)
    if hourly is None or daily is None or daily.empty:
        return "Não consegui obter a previsão agora. Tente novamente em instantes."

    # Agora (hora mais próxima no fuso local retornado)
    now = pd.Timestamp.now(tz=hourly["date"].dt.tz)
    idx = (hourly["date"] - now).abs().idxmin()
    temp_now = float(hourly.loc[idx, "temperature_2m"])

    # Hoje (linha 0 do daily)
    hoje = daily.iloc[0]
    tmin = float(hoje.get("temperature_2m_min", float("nan")))
    tmax = float(hoje.get("temperature_2m_max", float("nan")))
    chuva = float(hoje.get("precipitation_sum", 0.0))

    nome_exib = lugar.get("nome", "local")
    return (
        f"**{nome_exib}**\n"
        f"- Agora: **{temp_now:.1f}°C**\n"
        f"- Hoje: **mín {tmin:.1f}°C / máx {tmax:.1f}°C**, chuva **{chuva:.1f} mm** nas 24h"
    )

# Nomes dos dias em PT (Segunda=0 ... Domingo=6)
_DIAS_PT = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]

# previsão da semana (OPÇÃO B – lista Markdown, a partir de amanhã)
def _previsao_semana(msg: str) -> str:
    lugar = _resolver_lugar(msg)  # sua função que resolve "São Paulo, Brasil" etc.
    hourly, daily = consultar_api(lugar)
    if daily is None or daily.empty:
        return "Não consegui obter a previsão da semana agora."

    # Começa a contar da MEIA-NOITE DE AMANHÃ no fuso do dataset
    tz = daily["date"].dt.tz
    now = pd.Timestamp.now(tz=tz)
    amanha = (now + pd.Timedelta(days=1)).normalize()

    semana = daily.loc[daily["date"] >= amanha].head(7).copy()
    if semana.empty:
        semana = daily.head(7).copy()

    linhas = []
    for _, row in semana.iterrows():
        d = row["date"]
        nome = _DIAS_PT[d.weekday()]
        data_fmt = d.strftime("%d/%m")
        tmin  = float(row.get("temperature_2m_min", float("nan")))
        tmax  = float(row.get("temperature_2m_max", float("nan")))
        chuva = float(row.get("precipitation_sum", 0) or 0)
        # • Opção B: cada dia em uma linha Markdown (com " - ")
        linhas.append(f"- {nome} {data_fmt}: {tmin:.0f}–{tmax:.0f} °C, chuva {chuva:.0f} mm")

    dias_com_chuva = int(
        (semana.get("precipitation_sum", pd.Series(0, index=semana.index)).fillna(0) > 0.2).sum()
    )

    return (
        f"Previsão para **{lugar['nome']}** (próx. 7 dias):\n\n"
        + "\n".join(linhas)
        + f"\n\nResumo: chuva em ~{dias_com_chuva} dia(s)."
    )

# “vai chover?” hoje/amanhã/semana
def _vai_chover(msg: str) -> str:
    texto = (msg or "").lower()
    lugar = _resolver_lugar(msg)
    hourly, daily = consultar_api(lugar)
    if (hourly is None) and (daily is None):
        return "Não consegui verificar a chuva agora."
    limiar = 0.2  # mm

    if "amanhã" in texto or "amanha" in texto:
        if daily is None or len(daily) < 2:
            return "Não consegui calcular para amanhã."
        chuva = float((daily.iloc[1].get("precipitation_sum") or 0))
        return f"{'Sim' if chuva > limiar else 'Não'} deve chover **amanhã** em {lugar['nome']}."
    elif "semana" in texto:
        if daily is None or daily.empty:
            return "Não consegui calcular para esta semana."
        tz = daily["date"].dt.tz
        now = pd.Timestamp.now(tz=tz)
        amanha = (now + pd.Timedelta(days=1)).normalize()
        semana = daily.loc[daily["date"] >= amanha].head(7)
        dias_com = int((semana.get("precipitation_sum", pd.Series(0)).fillna(0) > limiar).sum())
        return f"Na próxima semana, há sinal de chuva em ~{dias_com} dia(s) em {lugar['nome']}."
    else:
        # hoje: soma precipitação das próximas 24h
        if hourly is None or "precipitation" not in hourly.columns:
            return "Não consegui calcular para hoje."
        chuva = float(hourly["precipitation"].fillna(0).sum())
        return f"{'Sim' if chuva > limiar else 'Não'} deve chover **hoje** em {lugar['nome']}."

# ---- regex simples para detectar intenção de "semana"
_re_semana = re.compile(r"\b(?:esta|essa|pr[oó]xima)?\s*semana\b", re.I)

# Função que recebe uma mensagem (msg) e retorna a resposta do Gemini
def ia(msg: str) -> str:
    try:
        txt = msg.lower()

        # 1) "semana" → mostra PREVISÃO A PARTIR DE AMANHÃ (7 dias)
        if _re_semana.search(txt) and any(w in txt for w in ["tempo", "temperatura", "previs", "clima", "chuva"]):
            return _previsao_semana(msg)

        # 2) Perguntas de chuva
        if re.search(r"\bvai chover\b|\bchoverá\b|\bchuverá\b", txt):
            return _vai_chover(msg)

        # 3) Pedidos gerais de clima/temperatura (hoje/agora)
        if re.search(r"\b(tempo|previs[aã]o|clima|temperatura)\b", txt):
            return _responder_clima(msg)

        # 4) Caso não seja clima, delega ao Gemini
        resposta = llm.generate_content(msg)
        return resposta.text

    except Exception as e:
        return f"Desculpe, ocorreu um erro ao processar sua solicitação: {e}"