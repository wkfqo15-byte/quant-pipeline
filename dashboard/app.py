import streamlit as st
import pandas as pd
from pyathena import connect
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="Quant Dashboard", layout="wide")
st.title("📈 퀀트 포트폴리오 데이터 조회")

st.sidebar.header("AWS 접속 정보")
aws_access_key = st.sidebar.text_input("Access Key", type="password")
aws_secret_key = st.sidebar.text_input("Secret Key", type="password")
s3_staging = "s3://quant-portfolio-datalake-sr/athena-results/" 

if st.button("데이터 조회하기"):
    if aws_access_key and aws_secret_key:
        with st.spinner("Athena에서 데이터를 가져오는 중..."):
            try:
                conn = connect(
                    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
                    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
                    region_name="ap-southeast-2", 
                    s3_staging_dir="s3://quant-portfolio-datalake-sr/athena-results/"
                )
                
                # 수정 전: df = pd.read_sql('SELECT * FROM "quant_db"."raw_data" LIMIT 1000', conn)
                # 수정 후 (아래 코드로 변경)
                df = pd.read_sql('SELECT * FROM "quant_db"."raw_data"', conn)
                df.columns = df.columns.str.lower() # 컬럼명 소문자 통일

                df = df.rename(columns={'^gspc': 'spx', 'btc-usd': 'btc'})
                st.success("데이터 로딩 완료!")
                st.dataframe(df)
                
                st.markdown("### 📊 자산 가격 트렌드 및 퀀트 지표")
                
                if 'timestamp' in df.columns and 'spx' in df.columns and 'btc' in df.columns:
                    df['timestamp'] = pd.to_datetime(df['timestamp'])
                    df = df.sort_values('timestamp')
                    
                    # 퀀트 지표 계산 (SPX 기준)
                    df['MA200'] = df['spx'].rolling(window=200).mean() # 200일 이평선
                    df['MA20'] = df['spx'].rolling(window=20).mean()   # 20일 이평선(볼린저 중심)
                    df['STD20'] = df['spx'].rolling(window=20).std()   # 20일 표준편차
                    df['Upper_BB'] = df['MA20'] + (df['STD20'] * 2)    # 볼린저 밴드 상단
                    df['Lower_BB'] = df['MA20'] - (df['STD20'] * 2)    # 볼린저 밴드 하단

                    # 매수 시그널 로직: SPX 가격이 볼린저 밴드 하단보다 낮을 때
                    df['Buy_Signal'] = df.apply(lambda row: row['spx'] if row['spx'] < row['Lower_BB'] else None, axis=1)
                    
                    # 이중 Y축 서브플롯 생성
                    fig = make_subplots(specs=[[{"secondary_y": True}]])
                    
                    # 1. 왼쪽 Y축 (SPX 및 지표)
                    fig.add_trace(go.Scatter(x=df['timestamp'], y=df['spx'], mode='lines', name='SPX', line=dict(color='#1f77b4')), secondary_y=False)
                    fig.add_trace(go.Scatter(x=df['timestamp'], y=df['MA200'], mode='lines', name='SPX 200일 이평선', line=dict(color='#ff7f0e', dash='dash')), secondary_y=False)
                    fig.add_trace(go.Scatter(x=df['timestamp'], y=df['Upper_BB'], mode='lines', name='SPX BB 상단', line=dict(color='gray', dash='dot')), secondary_y=False)
                    fig.add_trace(go.Scatter(x=df['timestamp'], y=df['Lower_BB'], mode='lines', name='SPX BB 하단', line=dict(color='gray', dash='dot')), secondary_y=False)

                    fig.add_trace(go.Scatter(x=df['timestamp'], y=df['Buy_Signal'], mode='markers', name='매수 시그널', marker=dict(symbol='triangle-up', size=10, color='red')), secondary_y=False)
                    
                    # 2. 오른쪽 Y축 (BTC)
                    fig.add_trace(go.Scatter(x=df['timestamp'], y=df['btc'], mode='lines', name='BTC (비트코인)', line=dict(color='#2ca02c')), secondary_y=True)
                    
                    fig.update_layout(title="SPX (볼린저 밴드) 및 BTC 가격 이중축 추이", template="plotly_white", hovermode="x unified")
                    fig.update_yaxes(title_text="SPX 가격", secondary_y=False)
                    fig.update_yaxes(title_text="BTC 가격", showgrid=False, secondary_y=True)
                    
                    st.plotly_chart(fig, use_container_width=True)
                    # 백테스트 기본 지표 계산 (SPX 기준)
                    df['Return'] = df['spx'].pct_change()
                    df['Cumulative_Return'] = (1 + df['Return']).cumprod() - 1
                    
                    rolling_max = (1 + df['Return']).cumprod().rolling(window=252, min_periods=1).max()
                    df['Drawdown'] = (1 + df['Return']).cumprod() / rolling_max - 1
                    mdd = df['Drawdown'].min() * 100
                    
                    total_return = df['Cumulative_Return'].iloc[-1] * 100
                    signal_count = df['Buy_Signal'].count()
    
                    # 대시보드 위젯 출력
                    st.markdown("### 📊 백테스트 성과 요약")
                    col1, col2, col3 = st.columns(3)
                    col1.metric("단순 보유 누적 수익률", f"{total_return:.2f}%")
                    col2.metric("최대 낙폭 (MDD)", f"{mdd:.2f}%")
                    col3.metric("볼린저 밴드 이탈(매수) 횟수", f"{signal_count}회")
                else:
                    st.warning("데이터베이스에 'timestamp', 'spx', 'btc' 컬럼이 모두 존재해야 합니다.")
                    
            except Exception as e:
                st.error(f"에러 발생: {e}")
    else:
        st.warning("왼쪽 사이드바에 AWS 키를 입력해주세요.")