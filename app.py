import streamlit as st
import pandas as pd
import numpy as np
import requests
import plotly.express as px
from PIL import Image

st.set_page_config(page_title="Boletim Operacional 4SAS", layout="wide")

# Exibe a logo da 4SAS no topo da barra lateral
try:
    logo = Image.open("logo.png")
    st.sidebar.image(logo, use_container_width=True)
except Exception:
    st.sidebar.title("4SAS - Operações")

st.sidebar.markdown("---")
st.sidebar.header("📍 Localização do Levantamento")

# Função para buscar coordenadas digitando o nome do local (Geocoding API)
def buscar_coordenadas(nome_local):
    try:
        url = f"https://geocoding-api.open-meteo.com/v1/search?name={nome_local}&count=1&language=pt&format=json"
        resp = requests.get(url).json()
        if "results" in resp and len(resp["results"]) > 0:
            lat = resp["results"][0]["latitude"]
            lon = resp["results"][0]["longitude"]
            nome_encontrado = resp["results"][0].get("name", nome_local)
            pais = resp["results"][0].get("country", "")
            return lat, lon, f"{nome_encontrado} ({pais})"
    except Exception:
        pass
    return None, None, None

# Campo de digitação livre para o local
termo_busca = st.sidebar.text_input("Buscar Localidade (ex: Barra do Furado)", value="Barra do Furado")

# Se o usuário digitou algo, busca a coordenada na API
lat, lon, nome_formatado = buscar_coordenadas(termo_busca)

if lat is not None and lon is not None:
    st.sidebar.success(f"Encontrado: **{nome_formatado}**\nLat: {lat:.4f}, Lon: {lon:.4f}")
else:
    st.sidebar.error("Local não encontrado. Usando coordenadas padrão.")
    lat, lon = -22.42, -41.02 # Padrão Barra do Furado

# Exibe o mapa nativo do Streamlit com a posição encontrada
df_mapa = pd.DataFrame({'lat': [lat], 'lon': [lon]})
st.sidebar.markdown("**Posição no Mapa:**")
st.sidebar.map(df_mapa, zoom=8, height=180)

# Função auxiliar para converter graus em pontos cardeais
def graus_para_direcao(deg):
    if pd.isna(deg):
        return ""
    direcoes = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", 
                "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    val = int((deg / 22.5) + 0.5)
    return direcoes[val % 16]

@st.cache_data
def carregar_dados(lat_val, lon_val):
    url_mar = f"https://marine-api.open-meteo.com/v1/marine?latitude={lat_val}&longitude={lon_val}&hourly=wave_height,wave_direction&timezone=America%2FSao_Paulo"
    url_vento = f"https://api.open-meteo.com/v1/forecast?latitude={lat_val}&longitude={lon_val}&hourly=wind_speed_10m,wind_direction_10m&timezone=America%2FSao_Paulo"
    
    resp_mar = requests.get(url_mar).json()
    resp_vento = requests.get(url_vento).json()
    
    datas = pd.to_datetime(resp_mar['hourly']['time'])
    
    df = pd.DataFrame({
        'Data_Hora': datas,
        'Onda_Altura(m)': resp_mar['hourly']['wave_height'],
        'Onda_Dir_Num': resp_mar['hourly']['wave_direction'],
        'Vento_Nos': (np.array(resp_vento['hourly']['wind_speed_10m']) / 1.852).round(1),
        'Vento_Dir_Num': resp_vento['hourly']['wind_direction_10m']
    })
    
    df['Onda_Dir'] = df['Onda_Dir_Num'].apply(graus_para_direcao)
    df['Vento_Dir'] = df['Vento_Dir_Num'].apply(graus_para_direcao)
    
    # Cálculo Harmônico Nativo de Maré (Componentes M2, S2, K1, O1)
    horas = np.arange(len(datas))
    omega_m2 = 2 * np.pi / 12.4206
    omega_s2 = 2 * np.pi / 12.0000
    omega_k1 = 2 * np.pi / 23.9345
    omega_o1 = 2 * np.pi / 25.8193
    
    mare = (
        0.45 * np.cos(omega_m2 * horas - 1.2) +
        0.15 * np.cos(omega_s2 * horas - 0.5) +
        0.20 * np.cos(omega_k1 * horas - 0.8) +
        0.10 * np.cos(omega_o1 * horas - 0.3) +
        0.80
    )
    
    df['Mare_Altura(m)'] = np.round(mare, 2)
    return df

st.sidebar.markdown("---")
if st.sidebar.button("Gerar Boletim Operacional"):
    df = carregar_dados(lat, lon)
    
    def regras(row):
        onda = row['Onda_Altura(m)']
        vento = row['Vento_Nos']
        
        if onda > 2.0 or vento > 20.0:
            return "🔴 SEM OPERAÇÃO (NO-GO)", "Limite crítico excedido"
        elif (1.5 < onda <= 2.0) or (15.0 <= vento <= 20.0):
            return "🟡 AVALIAÇÃO TÉCNICA", "Condição limítrofe"
        else:
            return "🟢 FAVORÁVEL", "Dentro da janela"

    df[['Status', 'Avisos']] = df.apply(regras, axis=1, result_type='expand')
    
    st.title("🌊 Painel de Operações Hidrográficas")
    st.subheader(f"Previsão Tática para: {termo_busca.capitalize()} (Lat: {lat:.4f}, Lon: {lon:.4f})")
    
    st.dataframe(df[['Data_Hora', 'Mare_Altura(m)', 'Onda_Altura(m)', 'Onda_Dir', 'Vento_Nos', 'Vento_Dir', 'Status', 'Avisos']], 
                 use_container_width=True, hide_index=True)
    
    st.subheader("Análise Gráfica: Janela Operacional de 4 Dias")
    
    data_inicio = df['Data_Hora'].min()
    data_fim = data_inicio + pd.Timedelta(days=4)
    df_4dias = df[(df['Data_Hora'] >= data_inicio) & (df['Data_Hora'] <= data_fim)]
    
    fig = px.line(
        df_4dias, 
        x='Data_Hora', 
        y=['Mare_Altura(m)', 'Onda_Altura(m)'],
        labels={'value': 'Altura (m)', 'Data_Hora': 'Horário', 'variable': 'Parâmetro'}
    )
    
    fig.data[0].update(line_width=3)
    fig.data[1].update(line_width=3)
    
    st.plotly_chart(fig, use_container_width=True)
    fig.data[0].update(line_width=3)
    fig.data[1].update(line_width=3)
    
    st.plotly_chart(fig, use_container_width=True)
