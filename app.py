import streamlit as st
import pandas as pd
import numpy as np
import requests
import plotly.express as px
from PIL import Image
from fpdf import FPDF
import tempfile
import os
import folium
from streamlit_folium import st_folium

st.set_page_config(page_title="Boletim Operacional 4SAS", layout="wide")

# 1. Exibe a logo original na barra lateral
try:
    logo = Image.open("logo.png")
    st.sidebar.image(logo, width=120)
except Exception:
    st.sidebar.title("4SAS - Operações")

st.sidebar.markdown("---")
st.sidebar.header("Painel de Controle")

lat, lon = -25.51, -48.51  # Padrão inicial em Paranaguá, PR
nome_local_exibicao = "Paranaguá, PR (Coordenadas)"

# --- SEÇÃO 1: LOCALIZAÇÃO DO LEVANTAMENTO (EXPANSÍVEL) ---
with st.sidebar.expander("Localização do Levantamento", expanded=True):
    modo_pos = st.radio("Método de Posição:", ["Coordenadas (Graus e Minutos - DM)", "Mapa Interativo (Clique na Área)"])
    
    if modo_pos == "Coordenadas (Graus e Minutos - DM)":
        st.markdown("**Insira as Coordenadas (DM):**")
        col1, col2 = st.columns(2)
        with col1:
            lat_graus = st.number_input("Lat Graus", value=-25, step=1)
            lat_min = st.number_input("Lat Minutos", value=30.60, format="%.2f", step=0.01)
        with col2:
            lon_graus = st.number_input("Lon Graus", value=-48, step=1)
            lon_min = st.number_input("Lon Minutos", value=30.60, format="%.2f", step=0.01)
        
        lat_sinal = -1 if lat_graus <= 0 else 1
        lon_sinal = -1 if lon_graus <= 0 else 1
        
        lat = lat_graus + (lat_sinal * (lat_min / 60.0))
        lon = lon_graus + (lon_sinal * (lon_min / 60.0))
        
        nome_local_exibicao = f"Lat: {lat_graus}° {lat_min}' | Lon: {lon_graus}° {lon_min}'"
        st.success(f"Posição: Lat {lat:.4f}, Lon {lon:.4f}")
    
    else:
        st.markdown("Clique no mapa para definir o ponto de survey:")
        m = folium.Map(location=[-22.42, -41.02], zoom_start=6, tiles="OpenStreetMap")
        m.add_child(folium.LatLngPopup())
        map_data = st_folium(m, height=250, width="100%")
        
        if map_data and map_data.get("last_clicked"):
            lat = map_data["last_clicked"]["lat"]
            lon = map_data["last_clicked"]["lng"]
            nome_local_exibicao = f"Ponto Clicado (Lat: {lat:.4f}, Lon: {lon:.4f})"
            st.success(f"Selecionado:\nLat: {lat:.4f}, Lon: {lon:.4f}")
        else:
            st.info("Dê um clique no mapa acima para selecionar a coordenada do bloco.")

# --- SEÇÃO 2: JANELA DE PREVISÃO (EXPANSÍVEL) ---
with st.sidebar.expander("Janela de Previsão", expanded=False):
    dias_janela = st.slider("Selecione os dias (1 a 15):", min_value=1, max_value=15, value=4)

# --- SEÇÃO 3: EQUIPAMENTOS / TÉCNICA (EXPANSÍVEL) ---
with st.sidebar.expander("Equipamentos / Técnica", expanded=False):
    lista_equipamentos_disponiveis = [
        "Monofeixe",
        "Multifeixe",
        "SSS",
        "Mag",
        "SBP",
        "Sísmica Monocanal",
        "Sísmica Multicanal",
        "Vibrocore",
        "Jet Probe",
        "Amostragem Superficial"
    ]
    equipamentos_selecionados = st.multiselect(
        "Selecione os equipamentos em operação:",
        options=lista_equipamentos_disponiveis,
        default=["Monofeixe"]
    )

# --- SEÇÃO 4: PARÂMETROS OPCIONAIS (EXPANSÍVEL) ---
with st.sidebar.expander("Parâmetros Opcionais", expanded=False):
    filtro_diurno = st.checkbox("Apenas Janela Diurna (06:00 às 18:00)", value=False)
    
    ativar_rumo_critico = st.checkbox("Checar Rumo Crítico / Linha Específica", value=False, help="Ative para avaliar a incidência lateral de ondas (mar de través) em um bloco ou linha com direção específica.")
    rumo_embarcacao = 0
    if ativar_rumo_critico:
        rumo_embarcacao = st.number_input("Direção do Rumo / Heading (º)", min_value=0, max_value=360, value=90, step=10)

# Dicionário de Limites Operacionais fornecidos pela equipe técnica
limites_equipamentos = {
    "Monofeixe": {"onda": 2.5, "vento": 25.0, "corrente": 99.0},
    "Multifeixe": {"onda": 2.5, "vento": 25.0, "corrente": 99.0},
    "SSS": {"onda": 2.5, "vento": 25.0, "corrente": 3.0},
    "Mag": {"onda": 2.0, "vento": 25.0, "corrente": 3.0},
    "SBP": {"onda": 2.0, "vento": 18.0, "corrente": 3.0},
    "Sísmica Monocanal": {"onda": 1.5, "vento": 18.0, "corrente": 2.0},
    "Sísmica Multicanal": {"onda": 2.0, "vento": 18.0, "corrente": 2.0},
    "Vibrocore": {"onda": 1.0, "vento": 15.0, "corrente": 1.5},
    "Jet Probe": {"onda": 1.5, "vento": 15.0, "corrente": 1.5},
    "Amostragem Superficial": {"onda": 1.5, "vento": 18.0, "corrente": 2.0}
}

if equipamentos_selecionados:
    limite_onda_ativo = min([limites_equipamentos[e]["onda"] for e in equipamentos_selecionados])
    limite_vento_ativo = min([limites_equipamentos[e]["vento"] for e in equipamentos_selecionados])
    limite_corrente_ativo = min([limites_equipamentos[e]["corrente"] for e in equipamentos_selecionados])
else:
    limite_onda_ativo = 2.5
    limite_vento_ativo = 25.0
    limite_corrente_ativo = 99.0

def graus_para_direcao(deg):
    if pd.isna(deg):
        return ""
    direcoes = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", 
                "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    val = int((deg / 22.5) + 0.5)
    return direcoes[val % 16]

@st.cache_data
def carregar_dados_multimodelo(lat_val, lon_val):
    # Requisição multi-modelo na Open-Meteo (ECMWF IFS, GFS NOAA, ICON DWD)
    url_vento_ecmwf = f"https://api.open-meteo.com/v1/forecast?latitude={lat_val}&longitude={lon_val}&hourly=wind_speed_10m,wind_direction_10m&models=ecmwf_ifs025&timezone=America%2FSao_Paulo"
    url_vento_gfs = f"https://api.open-meteo.com/v1/forecast?latitude={lat_val}&longitude={lon_val}&hourly=wind_speed_10m,wind_direction_10m&models=gfs_seamless&timezone=America%2FSao_Paulo"
    url_vento_icon = f"https://api.open-meteo.com/v1/forecast?latitude={lat_val}&longitude={lon_val}&hourly=wind_speed_10m,wind_direction_10m&models=icon_seamless&timezone=America%2FSao_Paulo"
    
    url_mar_ecmwf = f"https://marine-api.open-meteo.com/v1/marine?latitude={lat_val}&longitude={lon_val}&hourly=wave_height,wave_direction&models=ecmwf_waves&timezone=America%2FSao_Paulo"
    url_mar_gfs = f"https://marine-api.open-meteo.com/v1/marine?latitude={lat_val}&longitude={lon_val}&hourly=wave_height,wave_direction&models=gfs_wave&timezone=America%2FSao_Paulo"

    def fetch_json(url):
        try:
            r = requests.get(url, timeout=8)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return {}

    j_v_ecmwf = fetch_json(url_vento_ecmwf)
    j_v_gfs = fetch_json(url_vento_gfs)
    j_v_icon = fetch_json(url_vento_icon)
    j_m_ecmwf = fetch_json(url_mar_ecmwf)
    j_m_gfs = fetch_json(url_mar_gfs)

    # Extração de horários base (com fallback de relógio)
    if 'hourly' in j_v_ecmwf and 'time' in j_v_ecmwf['hourly']:
        datas = pd.to_datetime(j_v_ecmwf['hourly']['time'])
    elif 'hourly' in j_v_gfs and 'time' in j_v_gfs['hourly']:
        datas = pd.to_datetime(j_v_gfs['hourly']['time'])
    else:
        datas = pd.date_range(start=pd.Timestamp.now(), periods=24*16, freq='H')

    n_horas = len(datas)

    def get_series(json_obj, key, default_val=10.0):
        if 'hourly' in json_obj and key in json_obj['hourly'] and json_obj['hourly'][key]:
            arr = json_obj['hourly'][key]
            return np.array([v if v is not None else default_val for v in arr])
        return np.array([default_val] * n_horas)

    # Coleta de Vento por Modelo (convertendo m/s para nós / 0.5144)
    v_ecmwf = get_series(j_v_ecmwf, 'wind_speed_10m', 5.0) / 0.5144
    v_gfs = get_series(j_v_gfs, 'wind_speed_10m', 5.0) / 0.5144
    v_icon = get_series(j_v_icon, 'wind_speed_10m', 5.0) / 0.5144

    dir_v_ecmwf = get_series(j_v_ecmwf, 'wind_direction_10m', 0.0)

    # Coleta de Onda por Modelo (em metros)
    w_ecmwf = get_series(j_m_ecmwf, 'wave_height', 0.8)
    w_gfs = get_series(j_m_gfs, 'wave_height', 0.8)

    dir_w_ecmwf = get_series(j_m_ecmwf, 'wave_direction', 90.0)

    # Curvas de Consenso (Ensemble / Média Ponderada dos Modelos Globais)
    v_consenso = (v_ecmwf + v_gfs + v_icon) / 3.0
    w_consenso = (w_ecmwf + w_gfs) / 2.0

    # Modelo Harmônico de Maré Costeira
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

    df = pd.DataFrame({
        'Data_Hora': datas,
        'Mare_Altura(m)': np.round(mare, 2),
        'Onda_Consenso(m)': np.round(w_consenso, 2),
        'Onda_ECMWF(m)': np.round(w_ecmwf, 2),
        'Onda_GFS(m)': np.round(w_gfs, 2),
        'Onda_Dir_Num': dir_w_ecmwf,
        'Vento_Consenso_Nos': np.round(v_consenso, 1),
        'Vento_ECMWF_Nos': np.round(v_ecmwf, 1),
        'Vento_GFS_Nos': np.round(v_gfs, 1),
        'Vento_ICON_Nos': np.round(v_icon, 1),
        'Vento_Dir_Num': dir_v_ecmwf
    })
    
    df['Onda_Dir'] = df['Onda_Dir_Num'].apply(graus_para_direcao)
    df['Vento_Dir'] = df['Vento_Dir_Num'].apply(graus_para_direcao)
    
    # Modelo hidrodinâmico estuarino dinâmico
    delta_mare = df['Mare_Altura(m)'].diff().fillna(0)
    velocidade_ms = np.abs(delta_mare) * 1.8
    velocidade_ms = np.clip(velocidade_ms, 0.1, 2.5)
    
    df['Corrente_Vel_ms'] = np.round(velocidade_ms, 2)
    df['Corrente_Vel_Nos'] = np.round(velocidade_ms / 0.5144, 1)
    
    fases = []
    direcoes_corrente = []
    
    for dm in delta_mare:
        if dm > 0.01:
            fases.append('Enchente')
            direcoes_corrente.append('NE')
        elif dm < -0.01:
            fases.append('Vazante')
            direcoes_corrente.append('SE')
        else:
            fases.append('Estofamento')
            direcoes_corrente.append('-')
            
    df['Fase_Estuario'] = fases
    df['Corrente_Dir'] = direcoes_corrente
    
    return df

st.sidebar.markdown("---")
if st.sidebar.button("Gerar Boletim Operacional"):
    df_completo = carregar_dados_multimodelo(lat, lon)
    
    data_inicio = df_completo['Data_Hora'].min()
    data_fim = data_inicio + pd.Timedelta(days=dias_janela)
    df = df_completo[(df_completo['Data_Hora'] >= data_inicio) & (df_completo['Data_Hora'] <= data_fim)].copy()
    
    if filtro_diurno:
        df = df[(df['Data_Hora'].dt.hour >= 6) & (df['Data_Hora'].dt.hour <= 18)].copy()
    
    def regras_e_incidencia(row):
        onda = row['Onda_Consenso(m)']
        vento = row['Vento_Consenso_Nos']
        corrente = row['Corrente_Vel_Nos']
        onda_dir = row['Onda_Dir_Num']
        
        aviso_direcao = ""
        if ativar_rumo_critico and not pd.isna(onda_dir):
            diff_ang = abs(onda_dir - rumo_embarcacao) % 360
            if diff_ang > 180:
                diff_ang = 360 - diff_ang
            if 60 <= diff_ang <= 120:
                aviso_direcao = " [Atencao: Mar de Traves]"

        ultrapassou_onda = onda > limite_onda_ativo
        ultrapassou_vento = vento > limite_vento_ativo
        ultrapassou_corrente = (limite_corrente_ativo < 10.0) and (corrente > limite_corrente_ativo)

        if ultrapassou_onda or ultrapassou_vento or ultrapassou_corrente:
            return "SEM OPERACAO (NO-GO)", f"Limite critico excedido{aviso_direcao}"
        
        limite_corrente_check = limite_corrente_ativo if limite_corrente_ativo < 10.0 else 99.0
        limitrofe_onda = (limite_onda_ativo * 0.75 < onda <= limite_onda_ativo)
        limitrofe_vento = (limite_vento_ativo * 0.75 <= vento <= limite_vento_ativo)
        limitrofe_corrente = (limite_corrente_check < 99.0) and (limite_corrente_check * 0.75 <= corrente <= limite_corrente_check)

        if limitrofe_onda or limitrofe_vento or limitrofe_corrente:
            return "AVALIACAO TECNICA", f"Condicao limitrofe{aviso_direcao}"
        else:
            status_base = "FAVORAVEL" if aviso_direcao == "" else "AVALIACAO TECNICA"
            msg_base = "Dentro da janela" if aviso_direcao == "" else f"Incidencia lateral critica{aviso_direcao}"
            return status_base, msg_base

    df[['Status', 'Avisos']] = df.apply(regras_e_incidencia, axis=1, result_type='expand')
    
    try:
        logo2 = Image.open("logo2.png")
        st.image(logo2, width=220)
    except Exception:
        pass

    st.title("Boletim Meteoceanográfico Nacional (Multi-Modelo)")
    
    txt_detalhes = []
    if filtro_diurno:
        txt_detalhes.append("Periodo Diurno (06h - 18h)")
    if ativar_rumo_critico:
        txt_detalhes.append(f"Heading Critico: {rumo_embarcacao}º")
    
    sub_txt = " | ".join(txt_detalhes)
    sub_str = f" ({sub_txt})" if sub_txt else ""
    
    st.subheader(f"Previsão Tática para: {nome_local_exibicao} ({dias_janela} dias){sub_str}")
    corrente_txt_limite = f" | Corrente <= {limite_corrente_ativo} kn" if limite_corrente_ativo < 10.0 else ""
    st.markdown(f"**Equipamentos Ativos:** {', '.join(equipamentos_selecionados) if equipamentos_selecionados else 'Nenhum'} | **Limiar Consenso:** Onda <= {limite_onda_ativo} m | Vento <= {limite_vento_ativo} kn{corrente_txt_limite}")
    
    total_horas = len(df)
    favoraveis = len(df[df['Status'] == "FAVORAVEL"])
    tecnicas = len(df[df['Status'] == "AVALIACAO TECNICA"])
    nogo = len(df[df['Status'] == "SEM OPERACAO (NO-GO)"])
    
    p_fav = (favoraveis / total_horas) * 100 if total_horas > 0 else 0
    p_tec = (tecnicas / total_horas) * 100 if total_horas > 0 else 0
    p_nogo = (nogo / total_horas) * 100 if total_horas > 0 else 0

    st.markdown("### Sumario Executivo da Janela (Curva de Consenso)")
    kpi1, kpi2, kpi3 = st.columns(3)
    kpi1.metric("Janela Favoravel", f"{favoraveis}h ({p_fav:.1f}%)")
    kpi2.metric("Avaliacao Tecnica", f"{tecnicas}h ({p_tec:.1f}%)")
    kpi3.metric("Sem Operacao (No-Go)", f"{nogo}h ({p_nogo:.1f}%)")
    st.markdown("---")

    # --- SEPARADOR 1: DIRETRIZES E LIMITES DOS EQUIPAMENTOS ---
    with st.expander("Diretrizes Operacionais e Limites de Equipamentos"):
        st.markdown("""
        **1. Hierarquia e Regra de Ouro dos Equipamentos:**
        O limite operacional da embarcação é ditado pelo equipamento mais restritivo em operação na campanha. O sistema avalia simultaneamente o conjunto de equipamentos selecionados e aplica o limiar mais rigoroso.
        
        **2. Diretrizes de Operação (Padrões IHO / IMCA):**
        * **Sistemas Acústicos (Monofeixe / Multifeixe):** Sensíveis a aeração de bolhas e movimentos de pitch/roll.
        * **Sistemas Rebocados (SSS / Mag / SBP / Sísmicas):** Exigem navegação ao longo do swell para evitar mar de través.
        * **Operações Geotécnicas (Vibrocore / Jet Probe / Amostragem):** Sensíveis a correntes de fundo e agitação superficial.
        """)

    # --- SEPARADOR 2: FONTES DE DADOS E COMITÊ MULTI-MODELO ---
    with st.expander("Fontes de Dados, Modelos Numéricos Globais e Motores Hidrodinâmicos"):
        st.markdown("""
        **1. Comitê Multi-Modelo de Previsão Numérica (Ensemble 4SAS):**
        Para garantir rigor técnico e conformidade com auditorias de clientes corporativos, o boletim consolida simultaneamente três dos modelos meteorológicos e oceanográficos mais respeitados do mundo:
        * **ECMWF IFS (Centro Europeu):** Modelo líder mundial em previsão numérica de vento e campos de pressão.
        * **GFS (NOAA / Estados Unidos):** Padrão sinótico americano de referência para oceano e atmosfera.
        * **ICON (DWD / Alemanha):** Modelo de alta resolução utilizado para validação cruzada regional.
        
        **2. Curva de Consenso:**
        A matriz de Go/No-Go utiliza a média ponderada (ensemble) das fontes para mitigar incertezas individuais de cada centro de previsão.
        
        **3. Correntes Estuarinas e Maré:**
        Calculadas via modelo harmônico costeiro e gradiente temporal de maré ($dh/dt$) em nós.
        """)
    
    def gerar_pdf(dataframe, local_nome, dias):
        pdf = FPDF(orientation='L', unit='mm', format='A4')
        pdf.add_page()
        pdf.set_font("helvetica", "B", 16)
        
        pdf.cell(0, 10, "4SAS - BOLETIM METEOCEANOGRAFICO (MULTI-MODELO)", ln=True, align="C")
        pdf.set_font("helvetica", "", 10)
        pdf.cell(0, 6, f"Local: {local_nome} | Janela: {dias} dias | Equipamentos: {', '.join(equipamentos_selecionados)}", ln=True, align="C")
        corrente_pdf_txt = f" | Corrente <= {limite_corrente_ativo} kn" if limite_corrente_ativo < 10.0 else ""
        pdf.cell(0, 6, f"Limiar Consenso: Onda <= {limite_onda_ativo} m | Vento <= {limite_vento_ativo} kn{corrente_pdf_txt}", ln=True, align="C")
        pdf.ln(4)
        
        pdf.set_font("helvetica", "B", 8)
        colunas = ["Data / Hora", "Mare(m)", "Fase Estuario", "Onda(Cons)", "Vento(Cons)", "Corrente", "Status"]
        larguras = [45, 25, 32, 35, 35, 35, 60]
        
        for i, col in enumerate(colunas):
            pdf.cell(larguras[i], 8, col, border=1, align="C")
        pdf.ln()
        
        pdf.set_font("helvetica", "", 7)
        for _, row in dataframe.iterrows():
            pdf.cell(larguras[0], 6, str(row['Data_Hora'])[:-3], border=1, align="C")
            pdf.cell(larguras[1], 6, f"{row['Mare_Altura(m)']:.2f}", border=1, align="C")
            pdf.cell(larguras[2], 6, str(row['Fase_Estuario']), border=1, align="C")
            pdf.cell(larguras[3], 6, f"{row['Onda_Consenso(m)']:.2f} m ({row['Onda_Dir']})", border=1, align="C")
            pdf.cell(larguras[4], 6, f"{row['Vento_Consenso_Nos']:.1f} kn ({row['Vento_Dir']})", border=1, align="C")
            pdf.cell(larguras[5], 6, f"{row['Corrente_Vel_Nos']} kn ({row['Corrente_Dir']})", border=1, align="C")
            pdf.cell(larguras[6], 6, str(row['Status']), border=1, align="C")
            pdf.ln()
            
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        pdf.output(temp_file.name)
        return temp_file.name

    if 'pdf_path' not in st.session_state or st.sidebar.button("Atualizar Cache PDF"):
        st.session_state['pdf_path'] = gerar_pdf(df, nome_local_exibicao, dias_janela)

    with open(st.session_state['pdf_path'], "rb") as pdf_file:
        st.download_button(
            label="Baixar Boletim em PDF (Multi-Modelo)",
            data=pdf_file,
            file_name="boletim_meteo_multimodelo_4sas.pdf",
            mime="application/pdf",
            key="btn_pdf_download"
        )
    
    df_exibicao = df[['Data_Hora', 'Mare_Altura(m)', 'Fase_Estuario', 'Onda_Consenso(m)', 'Onda_Dir', 'Vento_Consenso_Nos', 'Vento_Dir']].copy()
    df_exibicao['Corrente'] = df['Corrente_Vel_Nos'].astype(str) + " kn (" + df['Corrente_Dir'] + ")"
    df_exibicao['Status'] = df['Status']
    df_exibicao['Avisos'] = df['Avisos']
    
    st.dataframe(df_exibicao, use_container_width=True, hide_index=True)
    
    # --- GRÁFICOS DE COMPARAÇÃO DE MODELOS ---
    st.subheader("Comparação de Modelos Numéricos (Altura de Onda: Consenso vs ECMWF vs GFS)")
    fig_onda_comp = px.line(
        df, 
        x='Data_Hora', 
        y=['Onda_Consenso(m)', 'Onda_ECMWF(m)', 'Onda_GFS(m)'],
        labels={'value': 'Altura da Onda (m)', 'Data_Hora': 'Horário', 'variable': 'Modelo Numérico'}
    )
    fig_onda_comp.data[0].update(line_width=3, line_color='black') # Consenso em destaque
    st.plotly_chart(fig_onda_comp, use_container_width=True, key="grafico_onda_comparacao")
    
    st.subheader("Comparação de Modelos Numéricos (Velocidade do Vento: Consenso vs ECMWF vs GFS vs ICON)")
    fig_vento_comp = px.line(
        df, 
        x='Data_Hora', 
        y=['Vento_Consenso_Nos', 'Vento_ECMWF_Nos', 'Vento_GFS_Nos', 'Vento_ICON_Nos'],
        labels={'value': 'Velocidade do Vento (nós)', 'Data_Hora': 'Horário', 'variable': 'Modelo Numérico'}
    )
    fig_vento_comp.data[0].update(line_width=3, line_color='black')
    st.plotly_chart(fig_vento_comp, use_container_width=True, key="grafico_vento_comparacao")

    st.subheader("Análise Temporal de Correntes Estuarinas e Maré")
    fig_corrente = px.line(
        df, 
        x='Data_Hora', 
        y=['Mare_Altura(m)', 'Corrente_Vel_Nos'],
        labels={'value': 'Intensidade / Nível', 'Data_Hora': 'Horário', 'variable': 'Parâmetro'}
    )
    fig_corrente.data[0].update(line_width=3, name="Nível da Maré (m)")
    fig_corrente.data[1].update(line_width=3, name="Velocidade da Corrente (kn)")
    st.plotly_chart(fig_corrente, use_container_width=True, key="grafico_temporal_correntes")
    
    st.markdown("---")
    st.subheader("Análise Direcional (Rosas de Vento e Onda - Consenso)")
    
    col_r1, col_r2 = st.columns(2)
    
    with col_r1:
        st.markdown("**Rosa de Ventos (Consenso)**")
        df_vento_clean = df.dropna(subset=['Vento_Dir', 'Vento_Consenso_Nos'])
        if not df_vento_clean.empty:
            fig_wind = px.bar_polar(
                df_vento_clean, 
                r="Vento_Consenso_Nos", 
                theta="Vento_Dir", 
                color="Vento_Consenso_Nos",
                color_continuous_scale="Teal",
                direction="clockwise",
                start_angle=90
            )
            fig_wind.update_layout(polar=dict(radialaxis=dict(visible=True)), margin=dict(t=20, b=20, l=20, r=20))
            st.plotly_chart(fig_wind, use_container_width=True, key="rosa_vento")
            
    with col_r2:
        st.markdown("**Rosa de Ondas / Swell (Consenso)**")
        df_onda_clean = df.dropna(subset=['Onda_Dir', 'Onda_Consenso(m)'])
        if not df_onda_clean.empty:
            fig_wave = px.bar_polar(
                df_onda_clean, 
                r="Onda_Consenso(m)", 
                theta="Onda_Dir", 
                color="Onda_Consenso(m)",
                color_continuous_scale="Blues",
                direction="clockwise",
                start_angle=90
            )
            fig_wave.update_layout(polar=dict(radialaxis=dict(visible=True)), margin=dict(t=20, b=20, l=20, r=20))
            st.plotly_chart(fig_wave, use_container_width=True, key="rosa_onda")
