import streamlit as st
import pandas as pd
import numpy as np
import requests
import plotly.express as px
from PIL import Image

st.set_page_config(page_title="Boletim Operacional 4SAS", layout="wide")

# 1. Exibe a logo da 4SAS no topo da barra lateral
# Exibe a logo da 4SAS no topo da barra lateral com tamanho reduzido
try:
    logo = Image.open("logo.png")
    # O parâmetro width controla a largura da imagem em pixels. 
    # Você pode alterar o número 180 para deixar maior ou menor conforme preferir!
    st.sidebar.image(logo, width=140)
except Exception:
    st.sidebar.title("4SAS - Operações")

# Escolha do método de entrada de posição
modo_pos = st.sidebar.radio("Método de Posição:", ["Busca por Nome", "Coordenadas (Graus e Minutos - DM)"])

lat, lon = -22.42, -41.02  # Padrão inicial
nome_local_exibicao = "Barra do Furado, RJ"

if modo_pos == "Busca por Nome":
    # Campo iniciado vazio conforme solicitado
    termo_busca = st.sidebar.text_input("Digite o local (ex: Itajaí, Porto do Açu)", value="")
    
    if termo_busca.strip() != "":
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
                st.sidebar.error("Local não encontrado.")
        except Exception:
            st.sidebar.error("Erro na busca.")
    else:
        st.sidebar.info("Digite um nome de localidade acima.")
        nome_local_exibicao = "Local Personalizado"
else:
    st.sidebar.markdown("**Insira as Coordenadas (DM):**")
    st.sidebar.markdown("Ex: Lat: -22 e 25.2' | Lon: -41 e 1.2'")
    
    # Entradas em Graus e Minutos Decimais
    col1, col2 = st.sidebar.columns(2)
    with col1:
        lat_graus = st.number_input("Lat Graus", value=-22, step=1)
        lat_min = st.number_input("Lat Minutos", value=25.20, format="%.2f", step=0.01)
    with col2:
        lon_graus = st.number_input("Lon Graus", value=-41, step=1)
        lon_min = st.number_input("Lon Minutos", value=1.20, format="%.2f", step=0.01)
    
    # Conversão de Graus e Minutos Decimais (DM) para Graus Decimais (Decimal Degrees)
    # Lógica considerando sinais negativos para o hemisfério sul/oeste
    lat_sinal = -1 if lat_graus <= 0 else 1
    lon_sinal = -1 if lon_graus <= 0 else 1
    
    lat = lat_graus + (lat_sinal * (lat_min / 60.0))
    lon = lon_graus + (lon_sinal * (lon_min / 60.0))
    
    nome_local_exibicao = f"Lat: {lat_graus}° {lat_min}' | Lon: {lon_graus}° {lon_min}'"
    st.sidebar.success(f"Posição convertida:\nLat: {lat:.4f}, Lon: {lon:.4f}")

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
    
    st.plotly_chart(fig, use_container_width=True, key="grafico_previsao_4dias_v3")
