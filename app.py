import streamlit as st
import pandas as pd
import numpy as np
import requests
import plotly.express as px

# 1. Configuração visual da página
st.set_page_config(page_title="Boletim Operacional 4SAS", layout="wide")
st.title("🌊 Painel de Operações Hidrográficas")
st.markdown("Avaliação de Janela Meteorológica e Maré para Lançamento de Equipamentos")

# 2. Configuração do Menu Lateral
st.sidebar.header("Configuração do Levantamento")
local = st.sidebar.selectbox("Área de Navegação", ["Barra do Furado, RJ", "Porto do Açu, RJ", "Outra Localidade"])

st.sidebar.markdown("---")
st.sidebar.subheader("Dados de Maré (DHN)")
arquivo_upload = st.sidebar.file_uploader("Envie o CSV de Maré da localidade (.csv)", type=["csv"])

# 3. Função principal de busca de dados
@st.cache_data
def buscar_dados(lat, lon, uploaded_file):
    # Busca os dados Meteorológicos (Hora em hora)
    url_mar = f"https://marine-api.open-meteo.com/v1/marine?latitude={lat}&longitude={lon}&hourly=wave_height&timezone=America%2FSao_Paulo"
    url_vento = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=wind_speed_10m&timezone=America%2FSao_Paulo"
    
    resp_mar = requests.get(url_mar).json()
    resp_vento = requests.get(url_vento).json()
    
    df_clima = pd.DataFrame({
        'Data_Hora': pd.to_datetime(resp_mar['hourly']['time']),
        'Onda_Altura(m)': resp_mar['hourly']['wave_height'],
        'Vento_Nos': (np.array(resp_vento['hourly']['wind_speed_10m']) / 1.852).round(1)
    })
    
    try:
        if uploaded_file is not None:
            df_mare = pd.read_csv(uploaded_file, parse_dates=['Data_Hora'])
        else:
            df_mare = pd.read_csv('mare_dhn.csv', parse_dates=['Data_Hora'])
            
        df_mare.set_index('Data_Hora', inplace=True)
        df_mare_horaria = df_mare.resample('1h').interpolate(method='time').round(2)
        df_mare_horaria.reset_index(inplace=True)
        
        df_final = pd.merge(df_clima, df_mare_horaria, on='Data_Hora', how='left')
        
    except Exception as e:
        st.error(f"Aviso: Usando maré simulada. Detalhe: {e}")
        horas = np.arange(len(df_clima))
        df_clima['Mare_Altura(m)'] = (0.8 + 0.6 * np.sin(horas * (2 * np.pi / 12.4))).round(2)
        df_final = df_clima

    return df_final.dropna()

def aplicar_regras(linha):
    onda = linha['Onda_Altura(m)']
    vento = linha['Vento_Nos']
    mare = linha['Mare_Altura(m)']
    avisos = []
    
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

# 4. Botão de ação na interface
if st.sidebar.button("Gerar Boletim"):
    with st.spinner("Cruzando dados atmosféricos e oceanográficos..."):
        lat, lon = -22.18, -41.12
        
        df = buscar_dados(lat, lon, arquivo_upload)
        df[['Status', 'Avisos']] = df.apply(aplicar_regras, axis=1)
        
        st.subheader(f"Previsão Operacional: {local}")
        
        st.dataframe(df[['Data_Hora', 'Mare_Altura(m)', 'Onda_Altura(m)', 'Vento_Nos', 'Status', 'Avisos']], 
                     use_container_width=True, hide_index=True)
        
        st.subheader("Análise Gráfica: Maré vs Ondulação")
        
        fig = px.line(
            df, 
            x='Data_Hora', 
            y=['Mare_Altura(m)', 'Onda_Altura(m)'],
            labels={'value': 'Altura (metros)', 'Data_Hora': 'Hora local', 'variable': 'Métrica'},
            color_discrete_map={
                'Mare_Altura(m)': '#1E88E5',
                'Onda_Altura(m)': '#FFC107'
            }
        )
        
        fig.data[0].update(fill='tozeroy', line_width=3)
        fig.data[1].update(line_width=3, line_dash='dot')
        
        st.plotly_chart(fig, use_container_width=True)
