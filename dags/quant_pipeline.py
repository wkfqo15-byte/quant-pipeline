from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
import yfinance as yf
import pandas as pd
import boto3
import io
import os

def fetch_and_upload_data():
    # 1. 5년 치 과거 데이터 수집 (티커 매핑)
    tickers = {"^GSPC": "spx", "QQQ": "qqq", "BTC-USD": "btc", "ETH-USD": "eth"}
    df_list = []
    
    for ticker, col_name in tickers.items():
        # yfinance로 5년 치 일봉 데이터 종가(Close) 가져오기
        data = yf.download(ticker, period="5y", interval="1d")['Close']
        data.name = col_name
        df_list.append(data)
        
    # 2. 데이터 병합 및 정제
    df = pd.concat(df_list, axis=1).reset_index()
    df.rename(columns={'Date': 'timestamp'}, inplace=True) # Athena 스키마에 맞춤
    df.fillna(method='ffill', inplace=True) # 휴일 등으로 비어있는 가격은 전일 종가로 채움
    
    # 3. CSV 변환 및 S3 업로드
    csv_buffer = io.StringIO()
    df.to_csv(csv_buffer, index=False)
    
    s3_client = boto3.client('s3',
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        region_name="ap-southeast-2"
    )
    bucket_name = "quant-portfolio-datalake-sr"
    # Athena가 raw_data 테이블로 인식할 수 있는 S3 경로에 저장
    file_key = f"raw_data/historical_{datetime.now().strftime('%Y%m%d')}.csv"
    
    s3_client.put_object(Bucket=bucket_name, Key=file_key, Body=csv_buffer.getvalue())
    print(f"데이터 적재 완료: s3://{bucket_name}/{file_key}")

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2026, 11, 1),
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

with DAG(
    'quant_data_pipeline',
    default_args=default_args,
    description='S&P 500 및 코인 과거 데이터 S3 적재',
    schedule_interval='@daily', # 매일 1회 실행
    catchup=False
) as dag:

    task_fetch_upload = PythonOperator(
        task_id='fetch_and_upload_to_s3',
        python_callable=fetch_and_upload_data
    )