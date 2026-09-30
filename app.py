import streamlit as st
import pandas as pd
import numpy as np
import requests
import plotly.express as px
from PIL import Image

st.set_page_config(page_title="Boletim Operacional 4SAS", layout="wide")

# 1. Exibe a logo da 4SAS no topo da barra lateral
try:
    logo = Image.open("logo.png")
    st.sidebar.image(logo, use_container_width=True)
except Exception:
    st.sidebar.title("4SAS - Operações")

st.sidebar.markdown("---")
# Removido o ícone do pino vermelho conforme solicitado
st.sidebar.header("Localização do Levantamento")

# Escolha do método de entrada de posição
modo_pos = st.sidebar.radio("Método de Posição:", ["Busca por Nome", "Coordenadas Manuais"])

lat, lon = -22.42, -41.02  # Padrão inicial (Barra do Furado)
nome_local_exibicao = "Barra do Furado, RJ"

if modo_pos == "Busca por Nome":
    termo_busca = st.sidebar.text_input("Digite o local (ex: Itajaí, Porto do Açu)", value="Barra do Furado")
    try:
        url = f"https://geocoding-api.open-meteo.com/v1/search?name={termo_busca}&count=1&language=pt&format=json"
        resp = requests.get(url).json()
        if "results" in resp and len(resp["results"]) > 0:
            lat = resp["results"][0]["latitude"]
            lon = resp["results"][0]["longitude"]
            cidade = resp["results"][0].get("name", termo_busca)
            pais = resp["results"][0].get("country", "")
            nome_local_exibicao = f"{cidade} ({pais})"
            st.sidebar.success(f"Encontrado: **{nome_local_exibicao}**\nLat: {lat:.4f}, Lon: {lon:.4f}")
        else:
            st.sidebar.error("Local não encontrado. Usando padrão.")
    except Exception:
        st.sidebar.error("Erro na busca. Usando padrão.")
else:
    st.sidebar.markdown("**Insira sua coordenada aqui:**")
    tipo_coord = st.sidebar.selectbox("Sistema de Coordenadas", ["Latitude / Longitude (Decimais)", "UTM (X e Y)"])
    
    if tipo_coord == "Latitude / Longitude (Decimais)":
        lat = st.sidebar.number_input("Latitude", value=-22.4200, format="%.4f")
        lon = st.sidebar.number_input("Longitude", value=-41.0200, format="%.4f")
        nome_local_exibicao = f"Lat: {lat}, Lon: {lon}"
    else:
        st.sidebar.info("Conversor básico UTM para WGS84 (Aproximado)")
        x_utm = st.sidebar.number_input("Coordenada X (Easting)", value=300000.0)
        y_utm = st.sidebar.number_input("Coordenada Y (Northing)", value=7500000.0)
        zona = st.sidebar.number_input("Fuso / Zona UTM", value=23, min_value=1, max_value=60)
        
        # Conversão aproximada de UTM simples para fins de demonstração no app
        # (Para cálculos rigorosos embarcados, usa-se pyproj, mantido leve aqui)
        lat = -22.0 - ((y_utm - 7000000) / 111000)
        lon = -43.0 + ((x_utm - 500000) / 100000)
        nome_local_exibicao = f"UTM X:{x_utm} Y:{y_utm} (Zona {zona})"
        st.sidebar.success(f"Convertido p/ Lat/Lon: {lat:.4f}, {lon:.4f}")

# Exibe o mapa nativo do Streamlit com a posição selecionada
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
    
    # Título alterado para Boletim Meteoceanográfico sem o ícone de onda
    st.title("Boletim Meteoceanográfico")
    st.subheader(f"Previsão Tática para: {nome_local_exibicao}")
    
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
    
    st.plotly_chart(fig, use_container_width=True, key="grafico_previsao_4dias_v2")
