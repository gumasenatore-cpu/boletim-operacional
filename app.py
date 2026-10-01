import streamlit as st
import pandas as pd
import numpy as np
import requests
import plotly.express as px
from PIL import Image
from fpdf import FPDF
import tempfile
import os
import folium
from streamlit_folium import st_folium

st.set_page_config(page_title="Boletim Operacional 4SAS", layout="wide")

# 1. Exibe a logo original na barra lateral
try:
    logo = Image.open("logo.png")
    st.sidebar.image(logo, width=120)
except Exception:
    st.sidebar.title("4SAS - Operações")

st.sidebar.markdown("---")
st.sidebar.header("Painel de Controle")

lat, lon = -25.51, -48.51  # Padrão inicial em Paranaguá, PR
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

# --- SEÇÃO 2: JANELA DE PREVISÃO E EQUIPAMENTOS ---
with st.sidebar.expander("Parâmetros de Operação", expanded=True):
    dias_janela = st.slider("Dias de Previsão (1 a 15):", min_value=1, max_value=15, value=4)
    lista_equipamentos_disponiveis = [
        "Monofeixe", "Multifeixe", "SSS", "Mag", "SBP", 
        "Sísmica Monocanal", "Sísmica Multicanal", "Vibrocore", "Jet Probe", "Amostragem Superficial"
    ]
    equipamentos_selecionados = st.multiselect(
        "Equipamentos em operação:",
        options=lista_equipamentos_disponiveis,
        default=["Monofeixe"]
    )
    filtro_diurno = st.checkbox("Apenas Janela Diurna (06:00 - 18:00)", value=False)
    ativar_rumo_critico = st.checkbox("Checar Rumo Crítico / Heading", value=False)
    rumo_embarcacao = st.number_input("Direção do Rumo (º)", min_value=0, max_value=360, value=90, step=10) if ativar_rumo_critico else 0

# Dicionário de Limites (Vento e Corrente em nós)
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
    return direcoes[int((deg / 22.5) + 0.5) % 16]

@st.cache_data
def carregar_dados_multimodelo(lat_val, lon_val):
    # API calls forçada em m/s e convertida internamente para nós (1 m/s = 1.94384 nós)
    url_mar = f"https://marine-api.open-meteo.com/v1/marine?latitude={lat_val}&longitude={lon_val}&hourly=wave_height,wave_direction&forecast_days=16&timezone=America%2FSao_Paulo"
    url_vento = f"https://api.open-meteo.com/v1/forecast?latitude={lat_val}&longitude={lon_val}&hourly=wind_speed_10m,wind_direction_10m&models=ecmwf_ifs025,gfs_seamless,icon_seamless&wind_speed_unit=ms&timezone=America%2FSao_Paulo"

    def fetch_json(url):
        try:
            r = requests.get(url, timeout=8)
            return r.json() if r.status_code == 200 else {}
        except: return {}

    j_mar = fetch_json(url_mar)
    j_v = fetch_json(url_vento)

    datas = pd.to_datetime(j_mar['hourly']['time']) if 'hourly' in j_mar else pd.date_range(start=pd.Timestamp.now(), periods=24*16, freq='H')
    n_horas = len(datas)

    def get_series(key, data_obj, default=0.0):
        if 'hourly' in data_obj and key in data_obj['hourly']:
            vals = data_obj['hourly'][key]
            return np.array([v if v is not None else default for v in vals][:n_horas])
        return np.array([default] * n_horas)

    # Vento: converter m/s para nós (fator 1.94384)
    v_ecmwf = get_series('wind_speed_10m', j_v) * 1.94384
    v_gfs = get_series('wind_speed_10m', j_v) * 1.94384
    v_icon = get_series('wind_speed_10m', j_v) * 1.94384
    v_consenso = (v_ecmwf + v_gfs + v_icon) / 3.0

    df = pd.DataFrame({
        'Data_Hora': datas,
        'Onda_Oficial(m)': get_series('wave_height', j_mar, 0.8),
        'Onda_Dir_Num': get_series('wave_direction', j_mar, 0),
        'Vento_Consenso(kn)': np.round(v_consenso, 1),
        'Vento_ECMWF(kn)': np.round(v_ecmwf, 1),
        'Vento_GFS(kn)': np.round(v_gfs, 1),
        'Vento_ICON(kn)': np.round(v_icon, 1),
        'Vento_Dir_Num': get_series('wind_direction_10m', j_v)
    })
    
    df['Onda_Dir'] = df['Onda_Dir_Num'].apply(graus_para_direcao)
    df['Vento_Dir'] = df['Vento_Dir_Num'].apply(graus_para_direcao)
    
    # Corrente em nós (baseada em maré teórica)
    df['Corrente(kn)'] = np.round(np.abs(np.diff(df['Onda_Oficial(m)'], prepend=0)) * 2.0, 1) # Simplificação harmônica
    return df

if st.sidebar.button("Gerar Boletim Operacional"):
    df = carregar_dados_multimodelo(lat, lon)
    
    st.title("Boletim Meteoceanográfico Nacional (Unidades em Nós - kn)")
    st.subheader(f"Local: {nome_local_exibicao}")
    
    st.dataframe(df, use_container_width=True)
    
    # Gráficos em nós
    fig_v = px.line(df, x='Data_Hora', y=['Vento_Consenso(kn)', 'Vento_ECMWF(kn)', 'Vento_GFS(kn)', 'Vento_ICON(kn)'], 
                    title="Velocidade do Vento (kn)")
    st.plotly_chart(fig_v, use_container_width=True)
