import streamlit as st
import pandas as pd
import numpy as np
import requests

# 1. Configuração visual da página
st.set_page_config(page_title="Boletim Operacional", layout="wide")
st.title("🌊 Painel de Operações Hidrográficas")
st.markdown("Avaliação de Janela Meteorológica e Maré para Lançamento de Equipamentos")

# 2. Unificando nossas funções (com cache para não sobrecarregar a API)
@st.cache_data
def buscar_dados(lat, lon):
    url_mar = f"https://marine-api.open-meteo.com/v1/marine?latitude={lat}&longitude={lon}&hourly=wave_height&timezone=America%2FSao_Paulo"
    url_vento = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=wind_speed_10m&timezone=America%2FSao_Paulo"
    
    resp_mar = requests.get(url_mar).json()
    resp_vento = requests.get(url_vento).json()
    
    df = pd.DataFrame({
        'Data_Hora': pd.to_datetime(resp_mar['hourly']['time']),
        'Onda_Altura(m)': resp_mar['hourly']['wave_height'],
        'Vento_Nos': (np.array(resp_vento['hourly']['wind_speed_10m']) / 1.852).round(1)
    })
    
    # Maré simulada do Passo 3
    horas = np.arange(len(df))
    df['Mare_Altura(m)'] = (0.8 + 0.6 * np.sin(horas * (2 * np.pi / 12.4))).round(2)
    return df

def aplicar_regras(linha):
    onda = linha['Onda_Altura(m)']
    vento = linha['Vento_Nos']
    mare = linha['Mare_Altura(m)']
    avisos = []
    
    # Regras customizadas para os equipamentos
    if vento > 15:
        avisos.append("Deriva alta (Atenção ao line planning)")
    if onda > 1.5:
        avisos.append("Ruído acústico (Atenção ao Kongsberg EA440)")
    
    if onda > 1.5 and mare < 0.6:
        return pd.Series(["🔴 ALTO RISCO", "Risco p/ reboque de magnetômetro"])
    elif onda > 2.0 or vento > 20:
        return pd.Series(["⛔ NO GO", "Condição extrema"])
    elif avisos:
        return pd.Series(["🟡 ATENÇÃO", " + ".join(avisos)])
    else:
        return pd.Series(["🟢 NORMAL", "Janela favorável"])

# 3. Construindo a Interface (Menu Lateral e Tela Principal)
st.sidebar.header("Configuração do Levantamento")
local = st.sidebar.selectbox("Área de Navegação", ["Barra do Furado, RJ", "Porto do Açu, RJ"])

# Botão de ação
if st.sidebar.button("Gerar Boletim"):
    with st.spinner("Cruzando dados atmosféricos e oceanográficos..."):
        # Coordenadas fixas para o teste
        lat, lon = -22.18, -41.12
        
        df = buscar_dados(lat, lon)
        df[['Status', 'Avisos']] = df.apply(aplicar_regras, axis=1)
        
        st.subheader(f"Previsão Operacional: {local}")
        
        # Mostra a tabela bonita
        st.dataframe(df[['Data_Hora', 'Mare_Altura(m)', 'Onda_Altura(m)', 'Vento_Nos', 'Status', 'Avisos']], 
                     use_container_width=True, hide_index=True)
        
        # Cria um gráfico cruzando Onda e Maré
        st.subheader("Tendência: Altura de Onda vs Nível da Maré")
        df_grafico = df.set_index('Data_Hora')[['Onda_Altura(m)', 'Mare_Altura(m)']]
        st.line_chart(df_grafico)