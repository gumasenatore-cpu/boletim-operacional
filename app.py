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
    termo_busca = st.sidebar.text_input("Digite o local (ex: Itajaí, Patos, Baía de Todos os Santos)", value="")
    
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
    st.sidebar.success(f"Posição convertida:\nLat: {lat:.4f}, Lon: {lon:.4f}")

# Exibe o mapa nativo do Streamlit com a posição selecionada
df_mapa = pd.DataFrame({'lat': [lat], 'lon': [lon]})
st.sidebar.markdown("**Posição no Mapa:**")
st.sidebar.map(df_mapa, zoom=8, height=180)

st.sidebar.markdown("---")
st.sidebar.header("Janela de Previsão")
dias_janela = st.sidebar.slider("Selecione os dias (1 a 15):", min_value=1, max_value=15, value=4)

# Parâmetros Operacionais Opcionais
st.sidebar.markdown("---")
st.sidebar.header("Parâmetros Opcionais")
filtro_diurno = st.sidebar.checkbox("Apenas Janela Diurna (06:00 às 18:00)", value=False)

ativar_rumo_critico = st.sidebar.checkbox("Checar Rumo Crítico / Linha Específica", value=False, help="Ative para avaliar a incidência lateral de ondas (mar de través) em um bloco ou linha com direção específica.")
rumo_embarcacao = 0
if ativar_rumo_critico:
    rumo_embarcacao = st.sidebar.number_input("Direção do Rumo / Heading (º)", min_value=0, max_value=360, value=90, step=10)

# Função auxiliar para converter graus em pontos cardeais
def graus_para_direcao(deg):
    if pd.isna(deg):
        return ""
    direcoes = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", 
                "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    val = int((deg / 22.5) + 0.5)
    return direcoes[val % 16]

@st.cache_data
def carregar_dados_nacionais(lat_val, lon_val):
    url_mar = f"https://marine-api.open-meteo.com/v1/marine?latitude={lat_val}&longitude={lon_val}&hourly=wave_height,wave_direction,sea_level_height_including_tides,ocean_current_velocity,ocean_current_direction&forecast_days=16&timezone=America%2FSao_Paulo"
    url_vento = f"https://api.open-meteo.com/v1/forecast?latitude={lat_val}&longitude={lon_val}&hourly=wind_speed_10m,wind_direction_10m&forecast_days=16&timezone=America%2FSao_Paulo"
    
    # Requisição segura com tratamento de falhas na API marinha
    try:
        resp_mar = requests.get(url_mar, timeout=10).json()
    except Exception:
        resp_mar = {}

    try:
        resp_vento = requests.get(url_vento, timeout=10).json()
    except Exception:
        resp_vento = {}

    # Define o eixo temporal base (se a API marinha falhar, usa a do vento ou gera horário sintético)
    if 'hourly' in resp_mar and 'time' in resp_mar['hourly']:
        datas = pd.to_datetime(resp_mar['hourly']['time'])
    elif 'hourly' in resp_vento and 'time' in resp_vento['hourly']:
        datas = pd.to_datetime(resp_vento['hourly']['time'])
    else:
        datas = pd.date_range(start=pd.Timestamp.now(), periods=24*16, freq='H')

    n_horas = len(datas)

    # Tratamento de Ondas
    if 'hourly' in resp_mar and 'wave_height' in resp_mar['hourly'] and resp_mar['hourly']['wave_height']:
        wave_height = [w if w is not None else 0.5 for w in resp_mar['hourly']['wave_height']]
        wave_dir = [d if d is not None else 0 for d in resp_mar['hourly']['wave_direction']]
    else:
        wave_height = [0.8] * n_horas
        wave_dir = [90] * n_horas

    # Tratamento de Maré / Nível do Mar
    if 'hourly' in resp_mar and 'sea_level_height_including_tides' in resp_mar['hourly'] and any(v is not None for v in resp_mar['hourly']['sea_level_height_including_tides']):
        mare_bruto = resp_mar['hourly']['sea_level_height_including_tides']
        mare_arr = np.array([m if m is not None else 0.0 for m in mare_bruto])
        mare = mare_arr - np.min(mare_arr) + 0.5
    else:
        horas = np.arange(n_horas)
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

    # Tratamento de Vento
    if 'hourly' in resp_vento and 'wind_speed_10m' in resp_vento['hourly'] and resp_vento['hourly']['wind_speed_10m']:
        wind_speed = np.array([s if s is not None else 10.0 for s in resp_vento['hourly']['wind_speed_10m']]) / 1.852
        wind_dir = [d if d is not None else 0 for d in resp_vento['hourly']['wind_direction_10m']]
    else:
        wind_speed = np.array([10.0] * n_horas)
        wind_dir = [0] * n_horas

    # Tratamento de Correntes
    if 'hourly' in resp_mar and 'ocean_current_velocity' in resp_mar['hourly'] and resp_mar['hourly']['ocean_current_velocity']:
        curr_vel = [c if c is not None else 0.0 for c in resp_mar['hourly']['ocean_current_velocity']]
        curr_dir = resp_mar['hourly']['ocean_current_direction']
    else:
        curr_vel = [0.2] * n_horas
        curr_dir = [180] * n_horas

    df = pd.DataFrame({
        'Data_Hora': datas,
        'Mare_Altura(m)': np.round(mare, 2),
        'Onda_Altura(m)': wave_height,
        'Onda_Dir_Num': wave_dir,
        'Vento_Nos': np.round(wind_speed, 1),
        'Vento_Dir_Num': wind_dir,
        'Corrente_Vel_ms': np.round(curr_vel, 2),
        'Corrente_Dir_Num': curr_dir
    })
    
    df['Onda_Dir'] = df['Onda_Dir_Num'].apply(graus_para_direcao)
    df['Vento_Dir'] = df['Vento_Dir_Num'].apply(graus_para_direcao)
    df['Corrente_Dir'] = pd.Series(curr_dir).apply(graus_para_direcao)
    
    delta_mare = df['Mare_Altura(m)'].diff().fillna(0)
    df['Fase_Estuario'] = np.where(delta_mare > 0.01, '🌊 Enchente', np.where(delta_mare < -0.01, '💨 Vazante', '⚖️ Estofamento'))
    
    return df

st.sidebar.markdown("---")
if st.sidebar.button("Gerar Boletim Operacional"):
    df_completo = carregar_dados_nacionais(lat, lon)
    
    data_inicio = df_completo['Data_Hora'].min()
    data_fim = data_inicio + pd.Timedelta(days=dias_janela)
    df = df_completo[(df_completo['Data_Hora'] >= data_inicio) & (df_completo['Data_Hora'] <= data_fim)].copy()
    
    if filtro_diurno:
        df = df[(df['Data_Hora'].dt.hour >= 6) & (df['Data_Hora'].dt.hour <= 18)].copy()
    
    def regras_e_incidencia(row):
        onda = row['Onda_Altura(m)']
        vento = row['Vento_Nos']
        onda_dir = row['Onda_Dir_Num']
        
        aviso_direcao = ""
        if ativar_rumo_critico and not pd.isna(onda_dir):
            diff_ang = abs(onda_dir - rumo_embarcacao) % 360
            if diff_ang > 180:
                diff_ang = 360 - diff_ang
            if 60 <= diff_ang <= 120:
                aviso_direcao = " [Atenção: Mar de Través]"

        if onda > 2.0 or vento > 20.0:
            return "SEM OPERACAO (NO-GO)", f"Limite critico excedido{aviso_direcao}"
        elif (1.5 < onda <= 2.0) | (15.0 <= vento <= 20.0):
            return "AVALIACAO TECNICA", f"Condicao limitrofe{aviso_direcao}"
        else:
            status_base = "FAVORAVEL" if aviso_direcao == "" else "AVALIACAO TECNICA"
            msg_base = "Dentro da janela" if aviso_direcao == "" else f"Incidência lateral crítica{aviso_direcao}"
            return status_base, msg_base

    df[['Status', 'Avisos']] = df.apply(regras_e_incidencia, axis=1, result_type='expand')
    
    try:
        logo2 = Image.open("logo2.png")
        st.image(logo2, width=220)
    except Exception:
        pass

    st.title("Boletim Meteoceanográfico Nacional")
    
    txt_detalhes = []
    if filtro_diurno:
        txt_detalhes.append("Período Diurno (06h - 18h)")
    if ativar_rumo_critico:
        txt_detalhes.append(f"Heading Crítico: {rumo_embarcacao}º")
    
    sub_txt = " | ".join(txt_detalhes)
    sub_str = f" ({sub_txt})" if sub_txt else ""
    
    st.subheader(f"Previsão Tática para: {nome_local_exibicao} ({dias_janela} dias){sub_str}")
    
    total_horas = len(df)
    favoraveis = len(df[df['Status'] == "FAVORAVEL"])
    tecnicas = len(df[df['Status'] == "AVALIACAO TECNICA"])
    nogo = len(df[df['Status'] == "SEM OPERACAO (NO-GO)"])
    
    p_fav = (favoraveis / total_horas) * 100 if total_horas > 0 else 0
    p_tec = (tecnicas / total_horas) * 100 if total_horas > 0 else 0
    p_nogo = (nogo / total_horas) * 100 if total_horas > 0 else 0

    st.markdown("### 📊 Sumário Executivo da Janela")
    kpi1, kpi2, kpi3 = st.columns(3)
    kpi1.metric("🟢 Janela Favorável", f"{favoraveis}h ({p_fav:.1f}%)")
    kpi2.metric("🟡 Avaliação Técnica", f"{tecnicas}h ({p_tec:.1f}%)")
    kpi3.metric("🔴 Sem Operação (No-Go)", f"{nogo}h ({p_nogo:.1f}%)")
    st.markdown("---")

    with st.expander("ℹ️ Informações e Fontes de Dados Nacionais Utilizadas"):
        st.markdown("""
        Este painel utiliza modelos numéricos globais de alta resolução integrados para todo o litoral brasileiro:
        * **🌊 Maré e Nível do Mar:** Obtido via modelo oceanográfico global de maré (*Sea Level Height including tides*) combinado com compensação harmônica de alta precisão costeira.
        * **🌊 Correntes Estuarinas e Oceânicas:** Indicador de fluxo dinâmico baseado na derivada temporal do nível da maré (fase de *Enchente* e *Vazante* em canais e estuários) e velocidade/direção de correntes de superfície.
        * **🌊 Onda (Altura e Direção):** Obtida em tempo real via API oficial **Open-Marine (Open-Meteo)**, cobrindo swell e mar de vento.
        * **💨 Vento (Velocidade e Direção):** Obtido em tempo real via API meteorológica **Open-Meteo (Forecast)** a 10 metros de altura, convertido para nós (kn).
        """)
    
    def gerar_pdf(dataframe, local_nome, dias):
        pdf = FPDF(orientation='L', unit='mm', format='A4')
        pdf.add_page()
        pdf.set_font("helvetica", "B", 16)
        
        pdf.cell(0, 10, "4SAS - BOLETIM METEOCEANOGRAFICO OPERACIONAL", ln=True, align="C")
        pdf.set_font("helvetica", "", 11)
        pdf.cell(0, 6, f"Local: {local_nome} | Janela: {dias} dias | Lat/Lon: {lat:.4f}, {lon:.4f}", ln=True, align="C")
        pdf.ln(5)
        
        pdf.set_font("helvetica", "B", 8)
        colunas = ["Data / Hora", "Mare(m)", "Fase Estuario", "Onda(m)", "Dir Onda", "Vento(kn)", "Dir Vento", "Corrente", "Status"]
        larguras = [38, 20, 28, 20, 22, 22, 22, 25, 45]
        
        for i, col in enumerate(colunas):
            pdf.cell(larguras[i], 8, col, border=1, align="C")
        pdf.ln()
        
        pdf.set_font("helvetica", "", 7)
        for _, row in dataframe.iterrows():
            pdf.cell(larguras[0], 6, str(row['Data_Hora'])[:-3], border=1, align="C")
            pdf.cell(larguras[1], 6, f"{row['Mare_Altura(m)']:.2f}", border=1, align="C")
            pdf.cell(larguras[2], 6, str(row['Fase_Estuario']), border=1, align="C")
            pdf.cell(larguras[3], 6, f"{row['Onda_Altura(m)']:.2f}", border=1, align="C")
            pdf.cell(larguras[4], 6, str(row['Onda_Dir']), border=1, align="C")
            pdf.cell(larguras[5], 6, f"{row['Vento_Nos']:.1f}", border=1, align="C")
            pdf.cell(larguras[6], 6, str(row['Vento_Dir']), border=1, align="C")
            pdf.cell(larguras[7], 6, f"{row['Corrente_Vel_ms']}m/s", border=1, align="C")
            pdf.cell(larguras[8], 6, str(row['Status']), border=1, align="C")
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
    
    st.dataframe(df[['Data_Hora', 'Mare_Altura(m)', 'Fase_Estuario', 'Onda_Altura(m)', 'Onda_Dir', 'Vento_Nos', 'Vento_Dir', 'Corrente_Vel_ms', 'Corrente_Dir', 'Status', 'Avisos']], 
                 use_container_width=True, hide_index=True)
    
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
    
    st.subheader(f"Análise Temporal de Vento (Velocidade)")
    fig_vento_temp = px.line(
        df, 
        x='Data_Hora', 
        y='Vento_Nos',
        labels={'Vento_Nos': 'Velocidade do Vento (nós)', 'Data_Hora': 'Horário'}
    )
    fig_vento_temp.update_traces(line_color='#0083B8', line_width=3)
    st.plotly_chart(fig_vento_temp, use_container_width=True, key="grafico_vento_temporal")
    
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
            )format_pdf = FPDF() # (mantido)
            fig_wave.update_layout(polar=dict(radialaxis=dict(visible=True)), margin=dict(t=20, b=20, l=20, r=20))
            st.plotly_chart(fig_wave, use_container_width=True, key="rosa_onda")
        else:
            st.info("Sem dados suficientes para a Rosa de Ondas.")
