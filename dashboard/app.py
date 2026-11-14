import streamlit as st
import pandas as pd
import boto3
import os
import io
import yfinance as yf
from dotenv import load_dotenv

# 1. 로컬 .env 파일에서 AWS 암호 불러오기
load_dotenv()

# 2. 웹 페이지 기본 설정
st.set_page_config(page_title="Quant Dashboard", layout="wide")
st.title("📈 상록의 Quant 파이프라인 대시보드 (실제 일별 환율 반영 USD)")

# 3. AWS S3 연결
s3 = boto3.client(
    's3',
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY")
)
bucket_name = 'quant-portfolio-datalake-sr'
prefix = 'raw_data/'

# 4. S3 데이터 불러오기 + 일자별 실제 환율(KRW=X) 매칭 변환
@st.cache_data(ttl=3600)
def load_all_data():
    response = s3.list_objects_v2(Bucket=bucket_name, Prefix=prefix)
    if 'Contents' not in response:
        return None
    
    files = sorted(response['Contents'], key=lambda x: x['LastModified'])
    
    df_list = []
    for file in files:
        key = file['Key']
        if key.endswith('.parquet'):
            obj = s3.get_object(Bucket=bucket_name, Key=key)
            df_temp = pd.read_parquet(io.BytesIO(obj['Body'].read()))
            df_temp.columns = [col.lower() if col.lower() == 'timestamp' else col.upper() for col in df_temp.columns]
            df_list.append(df_temp)
            
    if not df_list:
        return None
        
    st.caption(f"총 {len(df_list)}개의 누적 데이터 파일을 불러왔습니다. (최신 파일: {files[-1]['Key']})")
    
    full_df = pd.concat(df_list, ignore_index=True)
    
    if 'timestamp' in full_df.columns:
        full_df['timestamp'] = pd.to_datetime(full_df['timestamp'])
        full_df = full_df.sort_values('timestamp').drop_duplicates(subset=['timestamp'], keep='last').reset_index(drop=True)
        
        # 💱 핵심: 데이터 시작일부터 종료일까지의 실제 원/달러 환율(KRW=X) 데이터 불러오기
        start_date = full_df['timestamp'].min().strftime('%Y-%m-%d')
        fx_df = yf.download('KRW=X', start=start_date, progress=False)
        
        if not fx_df.empty:
            # 멀티인덱스 방지 및 날짜 포맷 맞추기
            fx_close = fx_df['Close'].squeeze().reset_index()
            fx_close.columns = ['date', 'fx_rate']
            fx_close['date'] = pd.to_datetime(fx_close['date']).dt.tz_localize(None).dt.floor('D')
            
            # 원본 데이터의 날짜(연-월-일) 추출하여 환율과 병합
            full_df['date'] = full_df['timestamp'].dt.tz_localize(None).dt.floor('D')
            full_df = pd.merge(full_df, fx_close, on='date', how='left')
            
            # 주말/공휴일 등 환율 데이터가 비어있는 날은 직전 평일 환율로 채우기 (ffill/bfill)
            full_df['fx_rate'] = full_df['fx_rate'].ffill().bfill().fillna(1400.0)
            
            # 원화 데이터(BTC > 1,000,000, ETH > 50,000)만 그날의 실제 환율(fx_rate)로 나누기
            if 'BTC' in full_df.columns:
                full_df['BTC'] = full_df.apply(
                    lambda row: round(row['BTC'] / row['fx_rate'], 2) if pd.notnull(row['BTC']) and row['BTC'] > 1000000 else row['BTC'], axis=1
                )
            if 'ETH' in full_df.columns:
                full_df['ETH'] = full_df.apply(
                    lambda row: round(row['ETH'] / row['fx_rate'], 2) if pd.notnull(row['ETH']) and row['ETH'] > 50000 else row['ETH'], axis=1
                )
                
            # 계산에 사용한 임시 날짜 컬럼만 지우고 적용된 환율(FX_RATE)은 표에서 확인할 수 있게 남겨두기
            full_df.rename(columns={'fx_rate': 'USD_KRW(적용환율)'}, inplace=True)
            full_df.drop(columns=['date'], inplace=True)
            
    return full_df

# 5. 화면에 데이터 및 차트 뿌려주기
with st.spinner("AWS S3 데이터와 일자별 실제 환율 데이터를 매칭하는 중입니다..."):
    df = load_all_data()

if df is not None:
    st.success("일자별 실제 환율 매칭 및 달러($) 변환 완료!")
    
    st.subheader("수집 데이터 내역 (일자별 실제 환율 반영 USD)")
    st.dataframe(df, use_container_width=True)
    
    st.subheader("시장 주요 지수 트렌드 (시작점=100 기준 5개 종목 겹쳐보기)")
    target_cols = ['SPX', 'QQQ', 'VIX', 'BTC', 'ETH']
    available_cols = [col for col in target_cols if col in df.columns]
    
    if 'timestamp' in df.columns:
        chart_df = df.set_index('timestamp')[available_cols].dropna(how='all')
        normalized_df = chart_df.apply(lambda x: (x / x.dropna().iloc[0]) * 100 if len(x.dropna()) > 0 else x)
        st.line_chart(normalized_df)
else:
    st.warning("아직 S3 버킷에 저장된 데이터가 없습니다.")