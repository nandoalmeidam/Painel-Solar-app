import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as pl
from main import ia   # Importa a função ia do seu main.py

##############################################################
# PARA O CLIMA:
from Clima import geocode, consultar_api, lugares_cadastrados

##############################################################

# ----------------- IMPORTS / FUNÇÕES NECESSÁRIAS -----------------
import sys, asyncio, aiohttp, inspect, re

# Pacote SEMS (precisa estar instalado)
from sems_portal_api.sems_auth import login_to_sems
from sems_portal_api.sems_region import set_region
from sems_portal_api.sems_home_wrapper import get_collated_plant_details
from sems_portal_api import sems_plant_details, sems_charts
from sems_portal_api.sems_auth import login_to_sems, login_response_to_token


# Windows: evita problemas de event loop
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Helper: extrai token de diferentes respostas de forks
def _token_from_auth(auth):
    if isinstance(auth, str) and auth:
        return auth
    if isinstance(auth, dict):
        for path in [
            ("token",),
            ("data", "token"),
            ("result", "token"),
            ("Authorization",),
        ]:
            cur = auth
            for k in path:
                if not isinstance(cur, dict) or k not in cur:
                    cur = None
                    break
                cur = cur[k]
            if isinstance(cur, str) and cur:
                return cur
    return None

#Faz login e tenta listar plantas (forks usam nomes diferentes).
async def list_plants(region: str, account: str, password: str):
    set_region(region)
    async with aiohttp.ClientSession() as session:
        auth = await login_to_sems(session, account, password)
        token = login_response_to_token(auth)

        candidates = [
            (sems_plant_details, "get_station_list"),
            (sems_plant_details, "get_plant_list"),
            (sems_plant_details, "get_station_list_by_user"),
            (sems_charts,        "get_station_list"),
            (sems_charts,        "get_plant_list"),
        ]

        # Essa função tenta pegar o mesmo conteúdo (id, nome, capacidade) mesmo que as chaves mudem.
        def push(plants, d):
            pid  = d.get("powerStationId") or d.get("powerstation_id") or d.get("station_id") or d.get("id")
            name = d.get("stationname")    or d.get("plant_name")      or d.get("name")
            cap  = d.get("capacity")       or d.get("plant_capacity")
            if pid and name:
                plants.append({"name": name, "power_station_id": pid, "capacity": cap})

        # para cada candidato, getattr tenta obter a função pelo nome; se não existir, volta None
        for mod, fname in candidates:
            fn = getattr(mod, fname, None)
            if fn and inspect.iscoroutinefunction(fn):
                try:
                    resp = await fn(session=session, token=token)
                except TypeError:
                    continue
                # Normaliza a resposta
                plants = []
                if isinstance(resp, dict):
                    for v in resp.values():
                        if isinstance(v, list):
                            for it in v:
                                if isinstance(it, dict): push(plants, it)
                elif isinstance(resp, list):
                    for it in resp:
                        if isinstance(it, dict): push(plants, it)
                if plants:
                    return plants, token
        # se nenhum candidato funcionou, retorna lista vazia (mas com o token do login, que já foi obtido)
        return [], token

# Carrega o JSON consolidado de uma planta específica.
async def load_collated(region: str, account: str, password: str, plant_id: str):
    set_region(region)
    async with aiohttp.ClientSession() as session:
        auth = await login_to_sems(session, account, password)
        token = login_response_to_token(auth)

        data = await get_collated_plant_details(session, power_station_id=plant_id, token=token)
        return data, token
##############################################################

# Configurações da página
st.set_page_config(page_title="Painel Solar", layout="wide")
st.title("PAINEL SOLAR")

##############################################################
# função de logout
def do_logout(clear_creds: bool = False):
    ss = st.session_state
    for k in ("token", "plant_data", "plants", "plant_id"):
        ss.pop(k, None)
    ss.pop("messages", None)
    if clear_creds:
        ss["account"] = ""
        ss["password"] = ""
    st.toast("Sessão finalizada.")
    st.rerun()

##############################################################    
# Cria abas no app
tab1, tab2, tab3, tab4 = st.tabs([
    "Goodwe Assistant - MVP", 
    "Preferencias", 
    "Acesso de dados", 
    "Solar I.A."
])

# ---------------- TAB 1 ----------------
with tab1:
    st.title("Goodwe Assistant - MVP")

    # estado da sessão (defaults)
    ss = st.session_state
    ss.setdefault("region", "eu")
    ss.setdefault("account", "demo@goodwe.com")
    ss.setdefault("password", "GoodweSems123!@#")
    ss.setdefault("plant_id", "")
    ss.setdefault("token", None)
    ss.setdefault("plant_data", None)

    # Credenciais + região (inputs para conta, senha e regiao)
    c1, c2, c3 = st.columns([2, 2, 1])

    with c1:
        ss.account = st.text_input("Conta (SEMS)", value=ss.account)

    with c2:
        ss.password = st.text_input("Senha", type="password", value=ss.password)

    with c3:
        ss.region = st.selectbox(
            "Região", ["eu", "na", "au"],
            index=["eu", "na", "au"].index(ss.region)
        )

    # campo do ID + botão  para colar o ID(fora do form)
    ss.plant_id = st.text_input(
        "Cole abaixo o seu ID (ex: 6ef62eb2-7959-4c49-ad0a-0ce75565023a)",
        value=ss.plant_id,
        key="plant_id_input",
    )

    # botão que dispara a chamada da API
    # (Carregar à esquerda | Logout à direita, na mesma linha)
    col_load, col_logout = st.columns([3, 1])
    with col_load:
        load_clicked = st.button("Carregar dados da planta")
    with col_logout:
        logout_clicked = st.button("Logout", type="secondary")
    if logout_clicked:
        do_logout(False)

    if load_clicked:
        if not ss.plant_id.strip():
            st.error("Cole o Power Station ID primeiro.")
        else:
            try:
                with st.spinner("Carregando dados da planta..."):
                    data, token = asyncio.run(
                        load_collated(ss.region, ss.account, ss.password, ss.plant_id.strip())
                    )
                # validação simples
                if not isinstance(data, dict) or "powerPlant" not in data:
                    st.error("Não foi possível carregar os detalhes. Verifique login, região e o ID.")
                else:
                    ss.plant_data, ss.token = data, token
                    st.success("Dados carregados com sucesso.")
            except Exception as e:
                st.error(f"Erro ao carregar dados: {e}")

    # Exibição dos dados
    plant_data = ss.get("plant_data")

    if isinstance(plant_data, dict) and plant_data:
        info = ((plant_data.get("powerPlant") or {}).get("info") or {})

        # helper para formatar números
        def fmt(v, nd=1, sep=False):
            try:
                x = float(v)
                return f"{x:,.{nd}f}" if sep else f"{x:.{nd}f}"
            except Exception:
                return "—"

        # mostra header com nome/ID, 4 métricas em cards
        st.markdown(
            f"**{info.get('stationname','(sem nome)')}** — "
            f"ID: `{info.get('powerstation_id','?')}`"
        )

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Geração hoje (kWh)", fmt(info.get("generationToday"), 1))
        c2.metric("Live (kW)",          fmt(info.get("generationLive"),   2))
        c3.metric("Mês (kWh)",          fmt(info.get("monthGeneration"),  1))
        c4.metric("SOC bateria (%)",    fmt(info.get("soc"),              0))

        # Inversores em tabela
        inverters = (plant_data.get("powerPlant") or {}).get("inverters") or []
        if inverters:
            import pandas as pd
            df = pd.DataFrame(inverters).rename(
                columns={"name": "SN", "model": "Modelo", "innerTemp": "Temp interna (°C)"}
            )
            st.subheader("Inversores")
            st.dataframe(df[["SN", "Modelo", "Temp interna (°C)"]], use_container_width=True)
        else:
            st.info("Nenhum inversor retornado pela API.")
    else:
        # qdo ainda não carregou nada, não mostra nada (só mantém o layout limpo)
        st.write("")  # ou st.empty()

# ---------------- TAB 2 ----------------
with tab2:
    st.write("Digite os itens que você usa em casa e classifique em importância.")

    # Usuário digita os itens separados por vírgula
    itens_input = st.text_input("Itens (separe por vírgula)", "Geladeira, TV, Computador")

    # Transforma o texto digitado em uma lista de itens
    itens = [i.strip() for i in itens_input.split(",") if i.strip()]

    if itens:
        st.write("Agora classifique os itens")

        # Usuário escolhe os itens mais importantes
        importantes = st.multiselect("Importante", itens, default=[itens[0]])

        # Remove da lista os que já foram escolhidos como importantes
        restantes = [i for i in itens if i not in importantes]

        # Usuário escolhe os itens médios
        medios = st.multiselect("Médio", restantes)

        # Remove da lista os que já foram escolhidos como médios
        restantes = [i for i in restantes if i not in medios]
        
        # Os itens restantes vão automaticamente para "menos importante"
        menos_importantes = restantes

        # Exibe um multiselect também para "menos importante"
        menos_importantes = st.multiselect("Menos importante", menos_importantes)


# ---------------- TAB 3 ----------------
with tab3:
    st.title("Clima / Previsão")

    ss = st.session_state
    # 1) Inicializa a lista de lugares na sessão a partir do seed do Clima.py
    if "wx_places" not in ss:
        ss.wx_places = list(lugares_cadastrados)  # cópia para poder editar no app
    ss.setdefault("wx_hourly", None)
    ss.setdefault("wx_daily", None)
    ss.setdefault("wx_selected_idx", 0)

    # 2) Linha para adicionar um novo lugar por geocode
    c1, c2 = st.columns([3, 1])
    with c1:
        nova_cidade = st.text_input("Adicionar cidade (ex.: Paris, França)", "")
    with c2:
        if st.button("Adicionar"):
            q = (nova_cidade or "").strip()
            if not q:
                st.error("Digite cidade e país, ex.: 'Paris, França'.")
            else:
                with st.spinner("Buscando coordenadas..."):
                    place = geocode(q)
                if not place:
                    st.error("Local não encontrado. Tente outro nome.")
                else:
                    nome = place.get("name") or q
                    # evita duplicado por nome
                    if any(p["nome"].lower() == nome.lower() for p in ss.wx_places):
                        st.warning("Lugar já cadastrado.")
                    else:
                        ss.wx_places.append({
                            "nome": nome,
                            "latitude": place.get("latitude"),
                            "longitude": place.get("longitude"),
                            "timezone": place.get("timezone", "auto"),
                        })
                        st.success(f"'{nome}' adicionado.")
                        st.rerun()

    # 3) Seletor do lugar cadastrado
    if not ss.wx_places:
        st.info("Nenhum lugar cadastrado ainda. Adicione um acima.")
        st.stop()

    options = [
        f"{p['nome']} ({p['latitude']:.3f}, {p['longitude']:.3f}) [{p.get('timezone','auto')}]"
        for p in ss.wx_places
    ]
    ss.wx_selected_idx = st.selectbox("Lugares", range(len(options)), 
                                      format_func=lambda i: options[i], 
                                      index=min(ss.wx_selected_idx, len(options)-1))

    # 4) Linha de ações (mesma da Tab1: botão principal à esquerda)
    a1, a2 = st.columns([2, 1])
    with a1:
        consultar_clicked = st.button("Consultar previsão")
    with a2:
        remover_clicked = st.button("Remover lugar", type="secondary")

    if remover_clicked:
        if 0 <= ss.wx_selected_idx < len(ss.wx_places):
            removido = ss.wx_places.pop(ss.wx_selected_idx)
            st.toast(f"Removido: {removido['nome']}")
            ss.wx_hourly, ss.wx_daily = None, None
            ss.wx_selected_idx = 0
            st.rerun()

    # 5) Consulta à API e armazenamento na sessão
    if consultar_clicked:
        lugar = ss.wx_places[ss.wx_selected_idx]
        with st.spinner("Consultando previsão..."):
            hourly, daily = consultar_api(lugar)
        if hourly is None or daily is None:
            st.error("Não foi possível obter a previsão agora.")
        else:
            ss.wx_hourly, ss.wx_daily = hourly, daily
            st.success(f"Previsão atualizada para {lugar['nome']}.")

    # 6) Exibição (métricas + tabelas + gráficos)
    hourly = ss.get("wx_hourly")
    daily  = ss.get("wx_daily")

    if hourly is not None and daily is not None:
        lugar = ss.wx_places[ss.wx_selected_idx]
        st.markdown(f"**{lugar['nome']}** — ({lugar['latitude']:.3f}, {lugar['longitude']:.3f})")

        # --- Métricas de hoje (a partir de hourly das próximas 24h) ---
        try:
            tmin = float(hourly["temperature_2m"].min())
            tmax = float(hourly["temperature_2m"].max())
            chuva = float(hourly["precipitation"].sum()) if "precipitation" in hourly.columns else 0.0
        except Exception:
            tmin = tmax = chuva = None

        m1, m2, m3 = st.columns(3)
        m1.metric("Mín (hoje) °C", f"{tmin:.1f}" if tmin is not None else "—")
        m2.metric("Máx (hoje) °C", f"{tmax:.1f}" if tmax is not None else "—")
        m3.metric("Chuva (hoje) mm", f"{chuva:.1f}" if chuva is not None else "—")

        # --- Tabelas ---
        st.subheader("Tabela — próximas 24h (hora local)")
        st.dataframe(hourly[["date", "temperature_2m"] + (["precipitation"] if "precipitation" in hourly.columns else [])],
                     use_container_width=True)

        st.subheader("Tabela — próximos dias")
        cols = ["date"] + [c for c in ["temperature_2m_min","temperature_2m_max","precipitation_sum"] if c in daily.columns]
        st.dataframe(daily[cols], use_container_width=True)

        # --- Gráficos (matplotlib) ---
        import matplotlib.pyplot as plt
        import numpy as np

        st.subheader("Gráficos")
        
        # Tamanho reduzido dos gráficos
        FIG_w, FIG_H, DPI = 6, 2.8, 120

        def grafico_temp_horaria():
            fig, ax = plt.subplots(figsize=(7, 3))
            x = hourly["date"].dt.strftime("%Hh")
            y = hourly["temperature_2m"]
            ax.plot(x, y, marker=".", linewidth=1.6)
            ax.set_title(f"Temperatura — hoje — {lugar['nome']}")
            ax.set_xlabel("Hora"); ax.set_ylabel("°C")
            # reduz número de rótulos para não poluir
            step = max(1, len(x)//8)
            ax.set_xticks(np.arange(0, len(x), step))
            ax.grid(True, linestyle="--", alpha=0.35)
            plt.tight_layout()
            st.pyplot(fig, clear_figure=True)

        def grafico_semana_min_max():
            if {"temperature_2m_min","temperature_2m_max"}.issubset(daily.columns):
                fig, ax = plt.subplots(figsize=(7, 3))
                xd = daily["date"].dt.strftime("%d/%m")
                ax.plot(xd, daily["temperature_2m_min"], marker="o", label="Mín")
                ax.plot(xd, daily["temperature_2m_max"], marker="o", label="Máx")
                ax.fill_between(xd, daily["temperature_2m_min"], daily["temperature_2m_max"], alpha=0.15)
                ax.set_title(f"Temperaturas — semana — {lugar['nome']}")
                ax.set_xlabel("Data"); ax.set_ylabel("°C"); ax.legend(loc="upper left")
                ax.grid(True, linestyle="--", alpha=0.35)
                plt.tight_layout()
                st.pyplot(fig, clear_figure=True)

        def grafico_semana_chuva():
            if "precipitation_sum" in daily.columns:
                fig, ax = plt.subplots(figsize=(7, 3))
                xd = daily["date"].dt.strftime("%d/%m")
                yb = daily["precipitation_sum"].clip(lower=0)
                ax.bar(xd, yb)
                ax.set_ylim(0, max(5.0, float(yb.max()) + 2.0))
                ax.set_title(f"Precipitação — semana — {lugar['nome']}")
                ax.set_xlabel("Data"); ax.set_ylabel("mm")
                ax.grid(axis="y", linestyle="--", alpha=0.5)
                plt.tight_layout()
                st.pyplot(fig, clear_figure=True)

        # --- layout ---
        c1, c2 = st.columns(2, gap="medium")
        with c1: grafico_temp_horaria()
        with c2: grafico_semana_min_max()

        c3, c4 = st.columns(2, gap="medium")
        with c3: grafico_semana_chuva()
        with c4: st.empty()



# ---------------- TAB 4 ----------------
with tab4:
    st.subheader("SOLAR I.A.")
    st.markdown(
        "<h3 style='text-align: center;'>Faça a sua pergunta: </h3>",
        unsafe_allow_html=True
    )

    # Inicializa o histórico de mensagens se ainda não existir
    if "messages" not in st.session_state:
        st.session_state.messages = []
    
    # Mostra o histórico de mensagens na tela
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):  # Pode ser "user" ou "assistant"
            st.markdown(message["content"])

    # Input do usuário (chat)
    if msg := st.chat_input("Digite sua pergunta aqui..."):
        # Mostra a mensagem do usuário no chat
        st.chat_message("user").markdown(msg)

        # Salva no histórico
        st.session_state.messages.append({"role": "user", "content": msg})

        # Gera resposta usando sua função ia()
        resposta = ia(msg)

        # Mostra a resposta do assistente no chat
        st.chat_message("assistant").markdown(resposta, unsafe_allow_html=True)

        # Salva a resposta no histórico
        st.session_state.messages.append({"role": "assistant", "content": resposta})
