from airflow.decorators import dag, task
from pendulum import timezone
from datetime import datetime
import yfinance as yf
import requests
import json
import pandas as pd
import boto3
import os

# === 환경 설정 ===
AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
BUCKET_NAME = "quant-portfolio-datalake-sr"
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")# ================

KST = timezone("Asia/Seoul")

@dag(
    dag_id="quant_monitoring_pipeline",
    schedule="0 9 * * 1-5", # 평일 오전 9시 (한국시간) 매일 실행
    start_date=datetime(2026, 10, 20, tzinfo=KST),
    catchup=False,
    tags=["portfolio", "DE"]
)
def quant_pipeline():

    @task
    def run_extract_and_load():
        # 1. 데이터 수집
        tickers = {"SPX": "^GSPC", "QQQ": "QQQ"}
        stocks = {}
        for name, ticker in tickers.items():
            data = yf.Ticker(ticker).history(period='1d')
            stocks[name] = round(data['Close'].iloc[-1], 2) if not data.empty else None

        cryptos = {"BTC": None, "ETH": None}
        res = requests.get("https://api.upbit.com/v1/ticker?markets=KRW-BTC,KRW-ETH", timeout=5)
        for item in res.json():
            cryptos[item['market'].split('-')[1]] = item['trade_price']

        # 2. DataFrame 변환 및 S3 적재
        combined = {**stocks, **cryptos, 'timestamp': datetime.now()}
        df = pd.DataFrame([combined])
        
        file_name = f"market_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.parquet"
        df.to_parquet(file_name, engine='pyarrow')
        
        s3_client = boto3.client('s3', aws_access_key_id=AWS_ACCESS_KEY, aws_secret_access_key=AWS_SECRET_KEY)
        s3_client.upload_file(file_name, BUCKET_NAME, f"raw_data/{file_name}")
        os.remove(file_name)

        # 3. Slack 알림
        alert_msg = f"✅ *Airflow 파이프라인 자동 적재 완료*\n• SPX: ${stocks.get('SPX')} | QQQ: ${stocks.get('QQQ')}\n• BTC: {cryptos.get('BTC'):,.0f} KRW"
        requests.post(SLACK_WEBHOOK_URL, data=json.dumps({"text": alert_msg}), headers={'Content-Type': 'application/json'})

    # 태스크 실행 순서 정의
    run_extract_and_load()

# DAG 인스턴스화
quant_pipeline()