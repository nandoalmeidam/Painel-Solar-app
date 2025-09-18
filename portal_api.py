import sys, asyncio, aiohttp, inspect
import streamlit as st

# Pacote SEMS (precisa estar instalado/local)
from sems_portal_api.sems_auth import login_to_sems
from sems_portal_api.sems_region import set_region
from sems_portal_api.sems_home_wrapper import get_collated_plant_details
from sems_portal_api import sems_plant_details, sems_charts

def _token_from_auth(auth):
    """Extrai o token retornado por forks diferentes do sems_portal_api."""
    # Pode vir como string já pronta
    if isinstance(auth, str) and auth:
        return auth

    # Pode vir como dict em estruturas diferentes
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

# Evita problemas de event loop no Windows (Streamlit/asyncio)
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

def do_logout(clear_creds: bool = False):
    """Limpa o estado da sessão e recarrega o app."""
    ss = st.session_state

    # chaves do seu fluxo SEMS
    for k in ["token", "plant_data", "plants", "plant_id"]:
        ss.pop(k, None)

    # opcional: também limpar conta/senha digitadas
    if clear_creds:
        ss["account"] = ""
        ss["password"] = ""

    # se estiver usando caches:
    try:
        st.cache_data.clear()
        st.cache_resource.clear()
    except Exception:
        pass

    st.toast("Sessão finalizada.")
    st.rerun()

async def list_plants(region: str, account: str, password: str):
    """
    Loga e tenta listar as plantas do usuário.
    Existem forks diferentes da lib com nomes de função distintos,
    então tentamos várias opções até achar uma que funcione.
    """
    set_region(region)  # seleciona a região (altera base URL)
    async with aiohttp.ClientSession() as session:
        # obter e validar token de forma robusta ---
        auth = await login_to_sems(session, account, password)
        if not auth:
            raise ValueError("Falha no login: verifique Conta/Senha e Região.")

        token = _token_from_auth(auth)
        if not token:
            raise ValueError("Falha no login: token ausente na resposta do SEMS.")

        # candidatos de funções de listagem (variam entre forks)
        candidates = [
            (sems_plant_details, "get_station_list"),
            (sems_plant_details, "get_plant_list"),
            (sems_plant_details, "get_station_list_by_user"),
            (sems_charts,        "get_station_list"),
            (sems_charts,        "get_plant_list"),
        ]

        # helper para normalizar um item de planta
        def push(plants, d):
            pid  = d.get("powerStationId") or d.get("powerstation_id") or d.get("station_id") or d.get("id")
            name = d.get("stationname")    or d.get("plant_name")      or d.get("name")
            cap  = d.get("capacity")       or d.get("plant_capacity")
            if pid and name:
                plants.append({"name": name, "power_station_id": pid, "capacity": cap})

        # tenta cada candidato até um funcionar
        for mod, fname in candidates:
            fn = getattr(mod, fname, None)  # procura a função pelo nome
            if fn and inspect.iscoroutinefunction(fn):  # garante que é async
                try:
                    # alguns forks aceitam (session=, token=); outros não
                    resp = await fn(session=session, token=token)
                except TypeError:
                    # assinatura diferente → tenta o próximo candidato
                    continue

                # normaliza a resposta para uma lista de plantas
                plants = []
                if isinstance(resp, dict):
                    for v in resp.values():
                        if isinstance(v, list):
                            for it in v:
                                if isinstance(it, dict): push(plants, it)
                elif isinstance(resp, list):
                    for it in resp:
                        if isinstance(it, dict): push(plants, it)

                # se conseguiu algo, retorna
                if plants:
                    return plants, token

        # nenhum candidato funcionou → retorna vazio (mas com token)
        return [], token

async def load_collated(region: str, account: str, password: str, plant_id: str):
    """
    Carrega o JSON consolidado de uma planta específica (info + powerflow + inversores).
    """
    set_region(region)
    async with aiohttp.ClientSession() as session:
        auth = await login_to_sems(session, account, password)
        if not auth:
            raise ValueError("Falha no login: verifique Conta/Senha e Região.")

        token = _token_from_auth(auth)
        if not token:
            raise ValueError("Falha no login: token ausente na resposta do SEMS.")

        data = await get_collated_plant_details(session, power_station_id=plant_id, token=token)
        return data, token