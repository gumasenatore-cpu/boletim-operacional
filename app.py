import streamlit as st
import pandas as pd
import numpy as np
import requests
import plotly.express as px

st.set_page_config(page_title="Boletim Operacional 4SAS", layout="wide")
st.title("🌊 Painel de Operações Hidrográficas (Harmônico)")
st.markdown("Avaliação de Janela Meteorológica e Maré Harmônica para Lançamento de Equipamentos")

# 1. Configuração de Localidades e Coordenadas
st.sidebar.header("📍 Localização do Levantamento")

locais_dict = {
    "Barra do Furado, RJ": {"lat": -22.42, "lon": -41.02},
    "Porto do Açu, RJ": {"lat": -21.85, "lon": -41.03},
    "Bacia de Campos (Offshore)": {"lat": -22.18, "lon": -40.50},
    "Personalizado (Digitar Coordenadas)": {"lat": -22.18, "lon": -41.12}
}

escolha_local = st.sidebar.selectbox("Selecione a Área", list(locais_dict.keys()))

if escolha_local == "Personalizado (Digitar Coordenadas)":
    lat = st.sidebar.number_input("Latitude", value=-22.18, format="%.4f")
    lon = st.sidebar.number_input("Longitude", value=-41.12, format="%.4f")
else:
    lat = locais_dict[escolha_local]["lat"]
    lon = locais_dict[escolha_local]["lon"]
    st.sidebar.info(f"Coordenadas fixas: **{lat}, {lon}**")

df_mapa = pd.DataFrame({'lat': [lat], 'lon': [lon]})
st.sidebar.map(df_mapa, zoom=8, height=180)

@st.cache_data
def carregar_dados(lat_val, lon_val):
    url_mar = f"https://marine-api.open-meteo.com/v1/marine?latitude={lat_val}&longitude={lon_val}&hourly=wave_height&timezone=America%2FSao_Paulo"
    url_vento = f"https://api.open-meteo.com/v1/forecast?latitude={lat_val}&longitude={lon_val}&hourly=wind_speed_10m&timezone=America%2FSao_Paulo"
    
    resp_mar = requests.get(url_mar).json()
    resp_vento = requests.get(url_vento).json()
    
    datas = pd.to_datetime(resp_mar['hourly']['time'])
    
    df = pd.DataFrame({
        'Data_Hora': datas,
        'Onda_Altura(m)': resp_mar['hourly']['wave_height'],
        'Vento_Nos': (np.array(resp_vento['hourly']['wind_speed_10m']) / 1.852).round(1)
    })
    
    # Cálculo Harmônico Nativo (Componentes M2, S2, K1, O1)
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
        if row['Onda_Altura(m)'] > 1.5 and row['Mare_Altura(m)'] < 0.6:
            return "🔴 ALTO RISCO", "Risco p/ reboque"
        elif row['Vento_Nos'] > 15:
            return "🟡 ATENÇÃO", "Deriva alta"
        return "🟢 NORMAL", "Janela favorável"

    df[['Status', 'Avisos']] = df.apply(regras, axis=1, result_type='expand')
    
    st.subheader(f"Previsão para: {escolha_local} (Lat: {lat}, Lon: {lon})")
    
    # Exibe a tabela completa de dados
    st.dataframe(df, use_container_width=True, hide_index=True)
    
    st.subheader("Análise Gráfica: Janela Operacional de 4 Dias")
    
    # FILTRO DE 4 DIAS (96 horas a partir do início da previsão)
    data_inicio = df['Data_Hora'].min()
    data_fim = data_inicio + pd.Timedelta(days=4)
    df_4dias = df[(df['Data_Hora'] >= data_inicio) & (df['Data_Hora'] <= data_fim)]
    
    fig = px.line(
        df_4dias, 
        x='Data_Hora', 
        y=['Mare_Altura(m)', 'Onda_Altura(m)'],
        labels={'value': 'Altura (m)', 'Data_Hora': 'Horário', 'variable': 'Parâmetro'}
    )
    
    # Ajuste visual para destacar as linhas no gráfico de 4 dias
    fig.data[0].update(line_width=3)
    fig.data[1].update(line_width=3)
    
    st.plotly_chart(fig, use_container_width=True)
