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
    
    # 2. Carrega a Maré Oficial da DHN (Horários quebrados)
    try:
        df_mare = pd.read_csv('mare_dhn.csv', parse_dates=['Data_Hora'])
        df_mare.set_index('Data_Hora', inplace=True)
        
        # A MÁGICA: Interpola a maré para gerar dados de 1 em 1 hora!
        # Ele cria a curva exata ligando a baixa-mar e a preamar.
        df_mare_horaria = df_mare.resample('1h').interpolate(method='time').round(2)
        df_mare_horaria.reset_index(inplace=True)
        
        # 3. Cruza o Clima com a Maré baseando-se na Data/Hora
        df_final = pd.merge(df_clima, df_mare_horaria, on='Data_Hora', how='left')
        
    except FileNotFoundError:
        st.error("Arquivo 'mare_dhn.csv' não encontrado. Usando maré simulada.")
        # Fallback de segurança (sua onda simulada antiga)
        horas = np.arange(len(df_clima))
        df_clima['Mare_Altura(m)'] = (0.8 + 0.6 * np.sin(horas * (2 * np.pi / 12.4))).round(2)
        df_final = df_clima

    return df_final.dropna() # Remove horas que ficaram sem dados no cruzamento
