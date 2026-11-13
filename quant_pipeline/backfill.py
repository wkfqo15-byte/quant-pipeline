import yfinance as yf
import pandas as pd
import pyupbit
import warnings
warnings.filterwarnings('ignore') # 보기 싫은 경고문 숨기기

print("데이터를 다시 수집합니다. 이번엔 확실하게 합칩니다...")

# 1. 미국 주식 수집 (시간 떼고 'YYYY-MM-DD' 날짜 글자만 남김)
tickers_us = {"spx": "^GSPC", "qqq": "QQQ", "vix": "^VIX"}
df_us_list = []
for name, ticker in tickers_us.items():
    data = yf.Ticker(ticker).history(period="3y")[['Close']]
    data = data.rename(columns={'Close': name})
    data.index = data.index.strftime('%Y-%m-%d') 
    df_us_list.append(data)

df_us = pd.concat(df_us_list, axis=1)

# 2. 암호화폐 수집 (시간 떼고 날짜 글자만 남김)
df_btc = pyupbit.get_ohlcv("KRW-BTC", count=1095)[['close']]
df_btc = df_btc.rename(columns={'close': 'btc'})
df_btc.index = df_btc.index.strftime('%Y-%m-%d')

df_eth = pyupbit.get_ohlcv("KRW-ETH", count=1095)[['close']]
df_eth = df_eth.rename(columns={'close': 'eth'})
df_eth.index = df_eth.index.strftime('%Y-%m-%d')

df_crypto = pd.concat([df_btc, df_eth], axis=1)

# 3. 데이터 완벽 병합 (글자 기준) 및 결측치 채우기
df_merged = df_crypto.join(df_us, how='outer')

# 주말 등 비어있는 미국 주식 가격은 전날(금요일) 가격으로 채움
df_merged = df_merged.ffill()
# 맨 앞단에 비어있는 데이터가 있다면 다음날 가격으로 당겨서 채움
df_merged = df_merged.bfill()

# 4. 저장 (Athena가 읽을 수 있도록 시간 ' 00:00:00' 강제 부착)
df_merged = df_merged.reset_index().rename(columns={'index': 'timestamp'})
df_merged['timestamp'] = df_merged['timestamp'] + " 00:00:00"

df_merged.to_parquet("historical_data.parquet", index=False)
print(f"완료! 데이터 {len(df_merged)}줄이 정상적으로 꽉 채워졌습니다.")