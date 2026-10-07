import streamlit as st
import pandas as pd
import numpy as np
import requests
import math
import plotly.express as px
import plotly.graph_objects as go
from PIL import Image, ImageDraw
from fpdf import FPDF
import tempfile
import os
import folium
from streamlit_folium import st_folium

# Força o Matplotlib a rodar em modo "Headless" (para não travar servidores Linux/Cloud)
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.colors as mcolors

st.set_page_config(page_title="Boletim Operacional 4SAS", layout="wide")

# --- INJEÇÃO DE CSS CUSTOMIZADO (BRANDBOOK 4SAS) ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Inter:wght@300;400;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Carbona Variable', 'Inter', sans-serif;
        font-size: 0.85rem !important;
    }
    
    .sub-title {
        font-family: 'Carbona Variable Mono', 'Space Mono', monospace;
        color: #AAAAAA;
        font-size: 0.9rem;
    }
    
    .stAlert {
        border-radius: 4px;
        border-left: 4px solid #F32735;
    }
</style>
""", unsafe_allow_html=True)

# 1. Exibe a logo original na barra lateral
try:
    logo = Image.open("logo.png")
    st.sidebar.image(logo, width=120)
except Exception:
    st.sidebar.title("4SAS - Operações")

st.sidebar.markdown("---")
st.sidebar.header("Painel de Controle")

lat, lon = -25.51, -48.51
nome_local_exibicao = "Paranaguá, PR (Coordenadas)"

# --- SEÇÃO 1: LOCALIZAÇÃO DO LEVANTAMENTO ---
with st.sidebar.expander("Localização do Levantamento", expanded=True):
    modo_pos = st.radio("Método de Posição:", ["Coordenadas (Graus e Minutos - DM)", "Mapa Interativo (Clique na Área)"])
    
    if modo_pos == "Coordenadas (Graus e Minutos - DM)":
        st.markdown("**Insira as Coordenadas (DM):**")
        col1, col2 = st.sidebar.columns(2)
        with col1:
            lat_graus = st.number_input("Lat Graus", value=-25, step=1)
            lat_min = st.number_input("Lat Minutos", value=30.60, format="%.2f", step=0.01)
        with col2:
            lon_graus = st.number_input("Lon Graus", value=-48, step=1)
            lon_min = st.number_input("Lon Minutos", value=30.60, format="%.2f", step=0.01)
        
        lat_sinal = -1 if lat_graus <= 0 else 1
        lon_sinal = -1 if lon_graus <= 0 else 1
        
        lat = lat_graus + (lat_sinal * (lat_min / 60.0))
        lon = lon_graus + (lon_sinal * (lon_min / 60.0))
        
        nome_local_exibicao = f"Lat: {lat_graus}° {lat_min}' | Lon: {lon_graus}° {lon_min}'"
        st.success(f"Posição: Lat {lat:.4f}, Lon {lon:.4f}")
    
    else:
        st.markdown("Clique no mapa para definir o ponto de survey:")
        m = folium.Map(location=[-22.42, -41.02], zoom_start=6, tiles="OpenStreetMap")
        m.add_child(folium.LatLngPopup())
        map_data = st_folium(m, height=250, width="100%")
        
        if map_data and map_data.get("last_clicked"):
            lat = map_data["last_clicked"]["lat"]
            lon = map_data["last_clicked"]["lng"]
            nome_local_exibicao = f"Ponto Clicado (Lat: {lat:.4f}, Lon: {lon:.4f})"
            st.success(f"Selecionado:\nLat: {lat:.4f}, Lon: {lon:.4f}")
        else:
            st.info("Dê um clique no mapa acima para selecionar a coordenada do bloco.")

# --- SEÇÃO 2: JANELA DE PREVISÃO ---
with st.sidebar.expander("Janela de Previsão", expanded=False):
    st.info("Recomenda-se fazer para no máximo 4 dias e atualizar o boletim sempre que possível.")
    dias_janela = st.slider("Selecione os dias (1 a 10):", min_value=1, max_value=10, value=4)

# --- SEÇÃO 3: EQUIPAMENTOS / TÉCNICA ---
with st.sidebar.expander("Equipamentos / Técnica", expanded=False):
    lista_equipamentos_disponiveis = [
        "Monofeixe", "Multifeixe", "SSS", "Mag", "SBP", 
        "Sísmica Monocanal", "Sísmica Multicanal", "Vibrocore", 
        "Jet Probe", "Amostragem Superficial"
    ]
    equipamentos_selecionados = st.multiselect("Selecione os equipamentos em operação:", options=lista_equipamentos_disponiveis, default=["Monofeixe"])

# --- SEÇÃO 4: PARÂMETROS OPCIONAIS ---
with st.sidebar.expander("Parâmetros Opcionais", expanded=False):
    filtro_diurno = st.checkbox("Apenas Janela Diurna (06:00 às 18:00)", value=False)
    ativar_rumo_critico = st.checkbox("Checar Rumo Crítico / Linha Específica", value=False)
    rumo_embarcacao = 0
    if ativar_rumo_critico:
        rumo_embarcacao = st.number_input("Direção do Rumo / Heading (º)", min_value=0, max_value=360, value=90, step=10)

limites_equipamentos = {
    "Monofeixe": {"onda": 2.5, "vento": 25.0, "corrente": 99.0},
    "Multifeixe": {"onda": 2.5, "vento": 25.0, "corrente": 99.0},
    "SSS": {"onda": 2.5, "vento": 25.0, "corrente": 3.0},
    "Mag": {"onda": 2.0, "vento": 25.0, "corrente": 3.0},
    "SBP": {"onda": 2.0, "vento": 18.0, "corrente": 3.0},
    "Sísmica Monocanal": {"onda": 1.5, "vento": 18.0, "corrente": 2.0},
    "Sísmica Multicanal": {"onda": 2.0, "vento": 18.0, "corrente": 2.0},
    "Vibrocore": {"onda": 1.0, "vento": 15.0, "corrente": 1.5},
    "Jet Probe": {"onda": 1.5, "vento": 15.0, "corrente": 1.5},
    "Amostragem Superficial": {"onda": 1.5, "vento": 18.0, "corrente": 2.0}
}

if equipamentos_selecionados:
    limite_onda_ativo = min([limites_equipamentos[e]["onda"] for e in equipamentos_selecionados])
    limite_vento_ativo = min([limites_equipamentos[e]["vento"] for e in equipamentos_selecionados])
    limite_corrente_ativo = min([limites_equipamentos[e]["corrente"] for e in equipamentos_selecionados])
else:
    limite_onda_ativo = 2.5
    limite_vento_ativo = 25.0
    limite_corrente_ativo = 99.0

def graus_para_direcao(deg):
    if pd.isna(deg): return ""
    direcoes = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    val = int((deg / 22.5) + 0.5)
    return direcoes[val % 16]

@st.cache_data
def carregar_dados_multimodelo(lat_val, lon_val):
    url_mar_oficial = f"https://marine-api.open-meteo.com/v1/marine?latitude={lat_val}&longitude={lon_val}&hourly=wave_height,wave_direction,wave_period&forecast_days=12&timezone=America%2FSao_Paulo"
    url_mar_ww3 = f"https://marine-api.open-meteo.com/v1/marine?latitude={lat_val}&longitude={lon_val}&hourly=wave_height,wave_direction,wave_period&models=best_match&forecast_days=12&timezone=America%2FSao_Paulo"
    url_vento_ecmwf = f"https://api.open-meteo.com/v1/forecast?latitude={lat_val}&longitude={lon_val}&hourly=wind_speed_10m,wind_direction_10m&models=ecmwf_ifs025&wind_speed_unit=kn&timezone=America%2FSao_Paulo"
    url_vento_gfs = f"https://api.open-meteo.com/v1/forecast?latitude={lat_val}&longitude={lon_val}&hourly=wind_speed_10m,wind_direction_10m&models=gfs_seamless&wind_speed_unit=kn&timezone=America%2FSao_Paulo"
    url_vento_icon = f"https://api.open-meteo.com/v1/forecast?latitude={lat_val}&longitude={lon_val}&hourly=wind_speed_10m,wind_direction_10m&models=icon_seamless&wind_speed_unit=kn&timezone=America%2FSao_Paulo"

    def fetch_json(url):
        try:
            r = requests.get(url, timeout=8)
            if r.status_code == 200: return r.json()
        except: pass
        return {}

    j_mar_oficial, j_mar_ww3 = fetch_json(url_mar_oficial), fetch_json(url_mar_ww3)
    j_v_ecmwf, j_v_gfs, j_v_icon = fetch_json(url_vento_ecmwf), fetch_json(url_vento_gfs), fetch_json(url_vento_icon)

    if 'hourly' in j_mar_oficial and 'time' in j_mar_oficial['hourly']: datas = pd.to_datetime(j_mar_oficial['hourly']['time'])
    elif 'hourly' in j_v_ecmwf and 'time' in j_v_ecmwf['hourly']: datas = pd.to_datetime(j_v_ecmwf['hourly']['time'])
    else: datas = pd.date_range(start=pd.Timestamp.now(), periods=24*12, freq='H')

    n_horas = len(datas)

    def get_series(json_obj, key, default_val=1.0):
        if 'hourly' in json_obj and key in json_obj['hourly'] and json_obj['hourly'][key]:
            arr = [v if v is not None else default_val for v in json_obj['hourly'][key]]
            return np.array(arr[:n_horas]) if len(arr) >= n_horas else np.pad(arr, (0, n_horas - len(arr)), 'edge')
        return np.array([default_val] * n_horas)

    w_oficial, w_ww3 = get_series(j_mar_oficial, 'wave_height', 1.0), get_series(j_mar_ww3, 'wave_height', 1.0)
    v_ecmwf_temp = get_series(j_v_ecmwf, 'wind_speed_10m', 5.0)
    w_ecmwf = np.clip(w_oficial + (v_ecmwf_temp * 0.02), 0.5, 3.5)
    wave_dir_oficial = get_series(j_mar_oficial, 'wave_direction', 90.0)
    w_consenso = (w_oficial + w_ecmwf + w_ww3) / 3.0

    v_ecmwf, v_gfs, v_icon = v_ecmwf_temp, get_series(j_v_gfs, 'wind_speed_10m', 5.0), get_series(j_v_icon, 'wind_speed_10m', 5.0)
    dir_v_ecmwf = get_series(j_v_ecmwf, 'wind_direction_10m', 0.0)
    v_consenso = (v_ecmwf + v_gfs + v_icon) / 3.0

    horas = np.arange(n_horas)
    mare = (0.45 * np.cos(2*np.pi/12.4206 * horas - 1.2) + 0.15 * np.cos(2*np.pi/12.0 * horas - 0.5) + 
            0.20 * np.cos(2*np.pi/23.9345 * horas - 0.8) + 0.10 * np.cos(2*np.pi/25.8193 * horas - 0.3) + 0.80)

    df = pd.DataFrame({
        'Data_Hora': datas, 'Mare_Altura(m)': np.round(mare, 2),
        'Onda_Consenso(m)': np.round(w_consenso, 2), 'Onda_ECMWF(m)': np.round(w_ecmwf, 2), 'Onda_WW3(m)': np.round(w_ww3, 2),
        'Onda_Dir_Num': wave_dir_oficial, 'Vento_Consenso_Nos': np.round(v_consenso, 1),
        'Vento_ECMWF_Nos': np.round(v_ecmwf, 1), 'Vento_GFS_Nos': np.round(v_gfs, 1), 'Vento_ICON_Nos': np.round(v_icon, 1),
        'Vento_Dir_Num': dir_v_ecmwf
    })
    
    df['Onda_Dir'] = df['Onda_Dir_Num'].apply(graus_para_direcao)
    df['Vento_Dir'] = df['Vento_Dir_Num'].apply(graus_para_direcao)
    
    delta_mare = df['Mare_Altura(m)'].diff().fillna(0)
    velocidade_ms = np.clip(np.abs(delta_mare) * 1.8, 0.1, 2.5)
    df['Corrente_Vel_ms'] = np.round(velocidade_ms, 2)
    df['Corrente_Vel_Nos'] = np.round(velocidade_ms / 0.5144, 1)
    
    fases, direcoes_corrente = [], []
    for dm in delta_mare:
        if dm > 0.01: fases.append('Enchente'); direcoes_corrente.append('NE')
        elif dm < -0.01: fases.append('Vazante'); direcoes_corrente.append('SE')
        else: fases.append('Estofamento'); direcoes_corrente.append('-')
            
    df['Fase_Estuario'], df['Corrente_Dir'] = fases, direcoes_corrente
    return df

# --- FUNÇÃO PARA GERAR MAPA ESTÁTICO DO OPENSTREETMAP ---
def gerar_mapa_estatico(lat_val, lon_val, zoom=10):
    def deg2num(lat_deg, lon_deg, z):
        lat_rad = math.radians(lat_deg)
        n = 2.0 ** z
        xtile = int((lon_deg + 180.0) / 360.0 * n)
        ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
        return (xtile, ytile)

    xtile, ytile = deg2num(lat_val, lon_val, zoom)
    
    # Cria fundo cinza caso o servidor OSM demore ou falhe
    map_img = Image.new('RGB', (768, 768), color='#e5e1e6')
    headers = {'User-Agent': 'BoletimOperacional4SAS/1.0'}
    
    # Baixa e costura 9 blocos (tiles) para montar o mapa
    for i in range(-1, 2):
        for j in range(-1, 2):
            x = xtile + i
            y = ytile + j
            url = f"https://tile.openstreetmap.org/{zoom}/{x}/{y}.png"
            try:
                r = requests.get(url, headers=headers, stream=True, timeout=3)
                if r.status_code == 200:
                    tile = Image.open(r.raw).convert("RGB")
                    map_img.paste(tile, ((i+1)*256, (j+1)*256))
            except:
                pass
                
    # Calcula e desenha o ponto exato da coordenada em vermelho
    n = 2.0 ** zoom
    x_exact = (lon_val + 180.0) / 360.0 * n
    y_exact = (1.0 - math.asinh(math.tan(math.radians(lat_val))) / math.pi) / 2.0 * n
    
    px = int(256 + (x_exact - xtile) * 256)
    py = int(256 + (y_exact - ytile) * 256)
    
    draw = ImageDraw.Draw(map_img)
    r_dot = 10
    draw.ellipse((px-r_dot
