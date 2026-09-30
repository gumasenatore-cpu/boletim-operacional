import streamlit as st
import pandas as pd
import numpy as np
import requests
import plotly.express as px

st.set_page_config(page_title="Boletim Operacional 4SAS", layout="wide")
st.title("🌊 Painel de Operações Hidrográficas")
st.markdown("Avaliação de Janela Meteorológica e Maré para Lançamento de Equipamentos")

st.sidebar.header("Configuração")
local = st.sidebar.selectbox("Área de Navegação", ["Barra do Furado, RJ", "Porto do Açu, RJ"])
arquivo_upload = st.sidebar.file_uploader("Envie o CSV de Maré (.csv)", type=["csv"])

@st.cache_data
def carregar_dados(lat, lon):
    url_mar = f"https://marine-api.open-meteo.com/v1/marine?latitude={lat}&longitude={lon}&hourly=wave_height&timezone=America%2FSao_Paulo"
    url_vento = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=wind_speed_10m&timezone=America%2FSao_Paulo"
    
    resp_mar = requests.get(url_mar).json()
    resp_vento = requests.get(url_vento).json()
    
    df = pd.DataFrame({
        'Data_Hora': pd.to_datetime(resp_mar['hourly']['time']),
        'Onda_Altura(m)': resp_mar['hourly']['wave_height'],
        'Vento_Nos': (np.array(resp_vento['hourly']['wind_speed_10m']) / 1.852).round(1)
    })
    
    horas = np.arange(len(df))
    df['Mare_Altura(m)'] = (0.8 + 0.6 * np.sin(horas * (2 * np.pi / 12.4))).round(2)
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
    
    st.subheader(f"Previsão: {local}")
    st.dataframe(df, use_container_width=True, hide_index=True)
    
    fig = px.line(df, x='Data_Hora', y=['Mare_Altura(m)', 'Onda_Altura(m)'])
    st.plotly_chart(fig, use_container_width=True)
