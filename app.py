import streamlit as st
import pandas as pd
import numpy as np
import requests
import plotly.express as px

st.set_page_config(page_title="Boletim Operacional 4SAS", layout="wide")
st.title("🌊 Painel de Operações Hidrográficas (Harmônico)")
st.markdown("Avaliação de Janela Meteorológica e Maré Harmônica para Lançamento de Equipamentos")

st.sidebar.header("Configuração")
local = st.sidebar.selectbox("Área de Navegação", ["Barra do Furado, RJ", "Porto do Açu, RJ"])

@st.cache_data
def carregar_dados(lat, lon):
    # 1. Pega os dados de vento e onda da Open-Meteo
    url_mar = f"https://marine-api.open-meteo.com/v1/marine?latitude={lat}&longitude={lon}&hourly=wave_height&timezone=America%2FSao_Paulo"
    url_vento = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=wind_speed_10m&timezone=America%2FSao_Paulo"
    
    resp_mar = requests.get(url_mar).json()
    resp_vento = requests.get(url_vento).json()
    
    datas = pd.to_datetime(resp_mar['hourly']['time'])
    
    df = pd.DataFrame({
        'Data_Hora': datas,
        'Onda_Altura(m)': resp_mar['hourly']['wave_height'],
        'Vento_Nos': (np.array(resp_vento['hourly']['wind_speed_10m']) / 1.852).round(1)
    })
    
    # 2. Cálculo Harmônico Nativo (Simulação baseada nas principais componentes: M2, S2, K1, O1)
    # Frequências angulares das principais marés oceânicas
    horas = np.arange(len(datas))
    omega_m2 = 2 * np.pi / 12.4206  # Principal lunar semidiurna
    omega_s2 = 2 * np.pi / 12.0000  # Principal solar semidiurna
    omega_k1 = 2 * np.pi / 23.9345  # Lunar-solar diurna
    omega_o1 = 2 * np.pi / 25.8193  # Principal lunar diurna
    
    # Composição harmônica com amplitudes e fases típicas da costa sudeste
    mare = (
        0.45 * np.cos(omega_m2 * horas - 1.2) +
        0.15 * np.cos(omega_s2 * horas - 0.5) +
        0.20 * np.cos(omega_k1 * horas - 0.8) +
        0.10 * np.cos(omega_o1 * horas - 0.3) +
        0.80  # Nível médio de referência (1.0m)
    )
    
    df['Mare_Altura(m)'] = np.round(mare, 2)
    return df

if st.sidebar.button("Gerar Boletim"):
    lat, lon = -22.18, -41.12
    df = carregar_dados(lat, lon)
    
    def regras(row):
        if row['Onda_Altura(m)'] > 1.5 and row['Mare_Altura(m)'] < 0.6:
            return "🔴 ALTO RISCO", "Risco p/ reboque"
        elif row['Vento_Nos'] > 15:
            return "🟡 ATENÇÃO", "Deriva alta"
        return "🟢 NORMAL", "Janela favorável"

    df[['Status', 'Avisos']] = df.apply(regras, axis=1, result_type='expand')
    
    st.subheader(f"Previsão Harmônica: {local}")
    st.dataframe(df, use_container_width=True, hide_index=True)
    
    fig = px.line(
        df, 
        x='Data_Hora', 
        y=['Mare_Altura(m)', 'Onda_Altura(m)'],
        labels={'value': 'Altura (m)', 'Data_Hora': 'Horário', 'variable': 'Parâmetro'}
    )
    st.plotly_chart(fig, use_container_width=True)
