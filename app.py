import streamlit as st
import pandas as pd
import numpy as np
import requests
import plotly.express as px
# 1. Configuração visual da página
st.set_page_config(page_title="Boletim Operacional", layout="wide")
st.title("🌊 Painel de Operações Hidrográficas")
st.markdown("Avaliação de Janela Meteorológica e Maré para Lançamento de Equipamentos")

# 2. Unificando nossas funções (com cache para não sobrecarregar a API)
@st.cache_data
def buscar_dados(lat, lon):
    # 1. Busca os dados Meteorológicos (Hora em hora)
    url_mar = f"https://marine-api.open-meteo.com/v1/marine?latitude={lat}&longitude={lon}&hourly=wave_height&timezone=America%2FSao_Paulo"
    url_vento = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=wind_speed_10m&timezone=America%2FSao_Paulo"
    
    resp_mar = requests.get(url_mar).json()
    resp_vento = requests.get(url_vento).json()
    
    df_clima = pd.DataFrame({
        'Data_Hora': pd.to_datetime(resp_mar['hourly']['time']),
        'Onda_Altura(m)': resp_mar['hourly']['wave_height'],
        'Vento_Nos': (np.array(resp_vento['hourly']['wind_speed_10m']) / 1.852).round(1)
    })
    
    # 2. Carrega a Maré Oficial da DHN via Upload na Tela ou Arquivo Padrão
    st.sidebar.markdown("---")
    st.sidebar.subheader("Dados de Maré (DHN)")
    arquivo_upload = st.sidebar.file_uploader("Envie o CSV de Maré da localidade (.csv)", type=["csv"])
    
    try:
        if arquivo_upload is not None:
            # Se o usuário arrastou um arquivo novo na tela, usa ele!
            df_mare = pd.read_csv(arquivo_upload, parse_dates=['Data_Hora'])
            st.sidebar.success("Tábua de maré personalizada carregada!")
        else:
            # Se não enviou nada, usa o arquivo padrão do GitHub
            df_mare = pd.read_csv('mare_dhn.csv', parse_dates=['Data_Hora'])
            
        df_mare.set_index('Data_Hora', inplace=True)
        
        # Interpolação para dados de 1 em 1 hora
        df_mare_horaria = df_mare.resample('1h').interpolate(method='time').round(2)
        df_mare_horaria.reset_index(inplace=True)
        
        df_final = pd.merge(df_clima, df_mare_horaria, on='Data_Hora', how='left')
        
    except Exception as e:
        st.error(f"Erro ao processar maré: {e}. Usando maré simulada.")
        horas = np.arange(len(df_clima))
        df_clima['Mare_Altura(m)'] = (0.8 + 0.6 * np.sin(horas * (2 * np.pi / 12.4))).round(2)
        df_final = df_clima

    return df_final.dropna()
        
        # 3. Cruza o Clima com a Maré baseando-se na Data/Hora
        df_final = pd.merge(df_clima, df_mare_horaria, on='Data_Hora', how='left')
        
    except FileNotFoundError:
        st.error("Arquivo 'mare_dhn.csv' não encontrado. Usando maré simulada.")
        horas = np.arange(len(df_clima))
        df_clima['Mare_Altura(m)'] = (0.8 + 0.6 * np.sin(horas * (2 * np.pi / 12.4))).round(2)
        df_final = df_clima

    return df_final.dropna()

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
        lat, lon = -22.18, -41.12
        
        df = buscar_dados(lat, lon)
        df[['Status', 'Avisos']] = df.apply(aplicar_regras, axis=1)
        
        st.subheader(f"Previsão Operacional: {local}")
        
        st.dataframe(df[['Data_Hora', 'Mare_Altura(m)', 'Onda_Altura(m)', 'Vento_Nos', 'Status', 'Avisos']], 
                     use_container_width=True, hide_index=True)
        
        st.subheader("Análise Gráfica: Maré vs Ondulação")
        
        # Criando um gráfico interativo com Plotly
        fig = px.line(
            df, 
            x='Data_Hora', 
            y=['Mare_Altura(m)', 'Onda_Altura(m)'],
            labels={'value': 'Altura (metros)', 'Data_Hora': 'Hora local', 'variable': 'Métrica'},
            color_discrete_map={
                'Mare_Altura(m)': '#1E88E5', # Azul marinho para a maré
                'Onda_Altura(m)': '#FFC107'  # Amarelo/Laranja para a onda
            }
        )
        
        # Efeitos visuais operacionais
        fig.data[0].update(fill='tozeroy', line_width=3)
        fig.data[1].update(line_width=3, line_dash='dot')
        
        # Exibe o gráfico interativo na tela
        st.plotly_chart(fig, use_container_width=True)
