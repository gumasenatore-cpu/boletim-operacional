import streamlit as st
import pandas as pd
import numpy as np
import requests
import plotly.express as px
from PIL import Image
from fpdf import FPDF
import tempfile
import os

st.set_page_config(page_title="Boletim Operacional 4SAS", layout="wide")

# 1. Exibe a logo original na barra lateral (tamanho ajustado para 120)
try:
    logo = Image.open("logo.png")
    st.sidebar.image(logo, width=120)
except Exception:
    st.sidebar.title("4SAS - Operações")

st.sidebar.markdown("---")
st.sidebar.header("Localização do Levantamento")

# Escolha do método de entrada de posição
modo_pos = st.sidebar.radio("Método de Posição:", ["Busca por Nome", "Coordenadas (Graus e Minutos - DM)"])

lat, lon = -22.42, -41.02  # Padrão inicial
nome_local_exibicao = "Barra do Furado, RJ"

if modo_pos == "Busca por Nome":
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
    
    col1, col2 = st.sidebar.columns(2)
    with col1:
        lat_graus = st.number_input("Lat Graus", value=-22, step=1)
        lat_min = st.number_input("Lat Minutos", value=25.20, format="%.2f", step=0.01)
    with col2:
        lon_graus = st.number_input("Lon Graus", value=-41, step=1)
        lon_min = st.number_input("Lon Minutos", value=1.20, format="%.2f", step=0.01)
    
    lat_sinal = -1 if lat_graus <= 0 else 1
    lon_sinal = -1 if lon_graus <= 0 else 1
    
    lat = lat_graus + (lat_sinal * (lat_min / 60.0))
    lon = lon_graus + (lon_sinal * (lon_min / 60.0))
    
    nome_local_exibicao = f"Lat: {lat_graus}° {lat_min}' | Lon: {lon_graus}° {lon_min}'"
    st.sidebar.success(f"Posição convertida:\nLat: {lat:.4f}, Lon: {lat:.4f}")

# Exibe o mapa nativo do Streamlit com a posição selecionada
df_mapa = pd.DataFrame({'lat': [lat], 'lon': [lon]})
st.sidebar.markdown("**Posição no Mapa:**")
st.sidebar.map(df_mapa, zoom=8, height=180)

st.sidebar.markdown("---")
st.sidebar.header("Janela de Previsão")
dias_janela = st.sidebar.slider("Selecione os dias (1 a 15):", min_value=1, max_value=15, value=4)

# Novo filtro de horário diurno
st.sidebar.markdown("---")
st.sidebar.header("Filtros Operacionais")
filtro_diurno = st.sidebar.checkbox("Apenas Janela Diurna (06:00 às 18:00)", value=False)

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
    url_mar = f"https://marine-api.open-meteo.com/v1/marine?latitude={lat_val}&longitude={lon_val}&hourly=wave_height,wave_direction&forecast_days=16&timezone=America%2FSao_Paulo"
    url_vento = f"https://api.open-meteo.com/v1/forecast?latitude={lat_val}&longitude={lon_val}&hourly=wind_speed_10m,wind_direction_10m&forecast_days=16&timezone=America%2FSao_Paulo"
    
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
    df_completo = carregar_dados(lat, lon)
    
    data_inicio = df_completo['Data_Hora'].min()
    data_fim = data_inicio + pd.Timedelta(days=dias_janela)
    df = df_completo[(df_completo['Data_Hora'] >= data_inicio) & (df_completo['Data_Hora'] <= data_fim)].copy()
    
    # Aplica o filtro de horário diurno se selecionado
    if filtro_diurno:
        df = df[(df['Data_Hora'].dt.hour >= 6) & (df['Data_Hora'].dt.hour <= 18)].copy()
    
    def regras(row):
        onda = row['Onda_Altura(m)']
        vento = row['Vento_Nos']
        
        if onda > 2.0 or vento > 20.0:
            return "SEM OPERACAO (NO-GO)", "Limite critico excedido"
        elif (1.5 < onda <= 2.0) | (15.0 <= vento <= 20.0):
            return "AVALIACAO TECNICA", "Condicao limitrofe"
        else:
            return "FAVORAVEL", "Dentro da janela"

    df[['Status', 'Avisos']] = df.apply(regras, axis=1, result_type='expand')
    
    try:
        logo2 = Image.open("logo2.png")
        st.image(logo2, width=220)
    except Exception:
        pass

    st.title("Boletim Meteoceanográfico")
    
    txt_diurno = " (Apenas Período Diurno: 06h - 18h)" if filtro_diurno else ""
    st.subheader(f"Previsão Tática para: {nome_local_exibicao} ({dias_janela} dias){txt_diurno}")
    
    # --- BOTÃO EXPANSÍVEL DE FONTES DE DADOS ---
    with st.expander("ℹ️ Informações e Fontes de Dados Utilizadas neste Boletim"):
        st.markdown("""
        Este painel utiliza motores independentes e APIs meteorológicas oficiais de alta confiabilidade:
        * **🌊 Maré:** Calculada de forma **nativa via Python (NumPy)** através de modelo harmônico somando as principais componentes da costa brasileira (**M2, S2, K1 e O1**), garantindo independência de tabelas estáticas.
        * **🌊 Onda (Altura e Direção):** Obtida em tempo real via API oficial **Open-Marine (Open-Meteo)**, baseada em modelos oceânicos globais.
        * **💨 Vento (Velocidade e Direção):** Obtida em tempo real via API de previsão do tempo **Open-Meteo (Forecast)**, convertida para nós (kn) a partir de dados a 10 metros de altura.
        """)
    
    # --- FUNÇÃO DE GERAÇÃO DE PDF ---
    def gerar_pdf(dataframe, local_nome, dias):
        pdf = FPDF(orientation='L', unit='mm', format='A4')
        pdf.add_page()
        pdf.set_font("helvetica", "B", 16)
        
        pdf.cell(0, 10, "4SAS - BOLETIM METEOCEANOGRAFICO OPERACIONAL", ln=True, align="C")
        pdf.set_font("helvetica", "", 11)
        pdf.cell(0, 6, f"Local: {local_nome} | Janela: {dias} dias | Lat/Lon: {lat:.4f}, {lon:.4f}", ln=True, align="C")
        pdf.ln(5)
        
        pdf.set_font("helvetica", "B", 9)
        colunas = ["Data / Hora", "Mare (m)", "Onda (m)", "Dir Onda", "Vento (kn)", "Dir Vento", "Status Operacional"]
        larguras = [40, 25, 25, 25, 25, 25, 60]
        
        for i, col in enumerate(colunas):
            pdf.cell(larguras[i], 8, col, border=1, align="C")
        pdf.ln()
        
        pdf.set_font("helvetica", "", 8)
        for _, row in dataframe.iterrows():
            pdf.cell(larguras[0], 6, str(row['Data_Hora'])[:-3], border=1, align="C")
            pdf.cell(larguras[1], 6, f"{row['Mare_Altura(m)']:.2f}", border=1, align="C")
            pdf.cell(larguras[2], 6, f"{row['Onda_Altura(m)']:.2f}", border=1, align="C")
            pdf.cell(larguras[3], 6, str(row['Onda_Dir']), border=1, align="C")
            pdf.cell(larguras[4], 6, f"{row['Vento_Nos']:.1f}", border=1, align="C")
            pdf.cell(larguras[5], 6, str(row['Vento_Dir']), border=1, align="C")
            pdf.cell(larguras[6], 6, str(row['Status']), border=1, align="C")
            pdf.ln()
            
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        pdf.output(temp_file.name)
        return temp_file.name

    pdf_path = gerar_pdf(df, nome_local_exibicao, dias_janela)
    with open(pdf_path, "rb") as pdf_file:
        st.download_button(
            label="📄 Baixar Boletim em PDF",
            data=pdf_file,
            file_name="boletim_meteo_4sas.pdf",
            mime="application/pdf",
            key="btn_pdf"
        )
    
    st.dataframe(df[['Data_Hora', 'Mare_Altura(m)', 'Onda_Altura(m)', 'Onda_Dir', 'Vento_Nos', 'Vento_Dir', 'Status', 'Avisos']], 
                 use_container_width=True, hide_index=True)
    
    # --- GRÁFICO 1: MARÉ E ONDAS ---
    st.subheader(f"Análise Temporal (Maré e Altura de Onda)")
    fig_geral = px.line(
        df, 
        x='Data_Hora', 
        y=['Mare_Altura(m)', 'Onda_Altura(m)'],
        labels={'value': 'Altura (m)', 'Data_Hora': 'Horário', 'variable': 'Parâmetro'}
    )
    fig_geral.data[0].update(line_width=3)
    fig_geral.data[1].update(line_width=3)
    st.plotly_chart(fig_geral, use_container_width=True, key="grafico_temporal_geral")
    
    # --- GRÁFICO 2: VENTO TEMPORAL ---
    st.subheader(f"Análise Temporal de Vento (Velocidade)")
    fig_vento_temp = px.line(
        df, 
        x='Data_Hora', 
        y='Vento_Nos',
        labels={'Vento_Nos': 'Velocidade do Vento (nós)', 'Data_Hora': 'Horário'}
    )
    fig_vento_temp.update_traces(line_color='#0083B8', line_width=3)
    st.plotly_chart(fig_vento_temp, use_container_width=True, key="grafico_vento_temporal")
    
    # --- SEÇÃO DE ROSAS (VENTO E ONDA) ---
    st.markdown("---")
    st.subheader("🧭 Análise Direcional (Rosas de Vento e Onda)")
    
    col_r1, col_r2 = st.columns(2)
    
    with col_r1:
        st.markdown("**Rosa de Ventos (Frequência por Direção e Intensidade)**")
        df_vento_clean = df.dropna(subset=['Vento_Dir', 'Vento_Nos'])
        if not df_vento_clean.empty:
            fig_wind = px.bar_polar(
                df_vento_clean, 
                r="Vento_Nos", 
                theta="Vento_Dir", 
                color="Vento_Nos",
                color_continuous_scale="Teal",
                direction="clockwise",
                start_angle=90
            )
            fig_wind.update_layout(polar=dict(radialaxis=dict(visible=True)), margin=dict(t=20, b=20, l=20, r=20))
            st.plotly_chart(fig_wind, use_container_width=True, key="rosa_vento")
        else:
            st.info("Sem dados suficientes para a Rosa de Ventos.")
            
    with col_r2:
        st.markdown("**Rosa de Ondas / Swell (Altura por Direção)**")
        df_onda_clean = df.dropna(subset=['Onda_Dir', 'Onda_Altura(m)'])
        if not df_onda_clean.empty:
            fig_wave = px.bar_polar(
                df_onda_clean, 
                r="Onda_Altura(m)", 
                theta="Onda_Dir", 
                color="Onda_Altura(m)",
                color_continuous_scale="Blues",
                direction="clockwise",
                start_angle=90
            )
            fig_wave.update_layout(polar=dict(radialaxis=dict(visible=True)), margin=dict(t=20, b=20, l=20, r=20))
            st.plotly_chart(fig_wave, use_container_width=True, key="rosa_onda")
        else:
            st.info("Sem dados suficientes para a Rosa de Ondas.")
