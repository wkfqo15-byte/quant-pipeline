import yfinance as yf
import requests
import json
import pandas as pd
import boto3
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

# === 환경 설정 (발급받은 정보로 변경하세요) ===
AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
BUCKET_NAME = "quant-portfolio-datalake-sr"
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")
# ==============================================

def get_us_stocks():
    tickers = {"SPX": "^GSPC", "QQQ": "QQQ", "VIX": "^VIX"}
    results = {}
    for name, ticker in tickers.items():
        try:
            data = yf.Ticker(ticker).history(period='1d')
            if not data.empty:
                results[name] = round(data['Close'].iloc[-1], 2)
            else:
                results[name] = None
        except Exception as e:
            print(f"[Error] {name} API 호출 실패: {e}")
            results[name] = None
    return results

def get_cryptos():
    url = "https://api.upbit.com/v1/ticker?markets=KRW-BTC,KRW-ETH"
    results = {"BTC": None, "ETH": None}
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        for item in data:
            symbol = item['market'].split('-')[1]
            results[symbol] = item['trade_price']
    except Exception as e:
        print(f"[Error] 암호화폐 API 통신 실패: {e}")
    return results

def send_slack_message(webhook_url, message):
    payload = {"text": message}
    try:
        requests.post(webhook_url, data=json.dumps(payload), headers={'Content-Type': 'application/json'})
        print("[Success] Slack 메시지 전송 완료")
    except Exception as e:
        print(f"[Error] Slack 통신 실패: {e}")

def upload_to_s3(dataframe, bucket_name):
    today = datetime.now().strftime('%Y%m%d_%H%M%S')
    file_name = f"market_data_{today}.parquet"
    
    # 1. 데이터프레임을 Parquet 파일로 로컬에 임시 저장
    dataframe.to_parquet(file_name, engine='pyarrow')
    
    # 2. AWS S3에 업로드
    try:
        s3_client = boto3.client(
            's3',
            aws_access_key_id=AWS_ACCESS_KEY,
            aws_secret_access_key=AWS_SECRET_KEY
        )
        # S3 버킷 내 raw_data 폴더 아래에 저장
        s3_client.upload_file(file_name, bucket_name, f"raw_data/{file_name}")
        print(f"[Success] S3 적재 완료: s3://{bucket_name}/raw_data/{file_name}")
        
        # 3. 임시 파일 삭제
        os.remove(file_name)
    except Exception as e:
        print(f"[Error] S3 업로드 실패: {e}")

if __name__ == "__main__":
    stocks = get_us_stocks()
    cryptos = get_cryptos()

    # 데이터 병합 및 타임스탬프 추가
    combined_data = {**stocks, **cryptos}
    combined_data['timestamp'] = datetime.now()
    
    # 딕셔너리를 Pandas DataFrame(1행)으로 변환
    df = pd.DataFrame([combined_data])
    print("=== 수집 데이터 (DataFrame) ===")
    print(df)
    
    # S3 업로드 실행
    if AWS_ACCESS_KEY != "발급받은_ACCESS_KEY":
        upload_to_s3(df, BUCKET_NAME)
    else:
        print("[Info] AWS 키가 입력되지 않아 S3 업로드를 건너뜁니다.")

    # Slack 알림 실행
    if "hooks.slack.com" in SLACK_WEBHOOK_URL:
        alert_msg = f"📊 *일일 파이프라인 적재 완료*\n• SPX: ${stocks.get('SPX')} | QQQ: ${stocks.get('QQQ')}\n• BTC: {cryptos.get('BTC'):,.0f} KRW | ETH: {cryptos.get('ETH'):,.0f} KRW"
        send_slack_message(SLACK_WEBHOOK_URL, alert_msg)