from airflow import DAG
from airflow.providers.http.sensors.http import HttpSensor
from airflow.providers.http.operators.http import SimpleHttpOperator
from airflow.operators.python_operator import PythonOperator
from airflow.hooks.base import BaseHook
from datetime import datetime, timedelta
import json
import pandas as pd
import os

# Daftar kota-kota yang ingin Anda ambil data cuacanya
CITIES = ['Jakarta', 'Surabaya', 'Bandung', 'Medan', 'Semarang']

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 1),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
}

def _process_weather_data(ti):
    """
    Memproses data cuaca yang diambil dari API
    """
    weather_data=[]
    for city in CITIES:
        data = ti.xcom_pull(task_ids=f'extract_weather_{city.lower()}')
        if data:
            weather_data.append(data)

    if not weather_data:
        raise ValueError("Data cuaca tidak tersedia. Periksa task sebelumnya.")

    # Menyiapkan list untuk menyimpan data cuaca
    processed_data = []
    
    for city_data in weather_data:
        if city_data and 'main' in city_data and 'weather' in city_data:
            processed_data.append({
                'city': city_data['name'],
                'temperature': city_data['main']['temp'],
                'feels_like': city_data['main']['feels_like'],
                'humidity': city_data['main']['humidity'],
                'description': city_data['weather'][0]['description'],
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })

    df = pd.DataFrame(processed_data)
    output_path = f'/opt/airflow/data/weather_data_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    df.to_csv(output_path, index=False)
    
    print(f"Data cuaca telah disimpan di {output_path}")
    print(df)

with DAG(
    dag_id='openweathermap_weather_dag',
    default_args=default_args,
    schedule_interval='@daily',  # Jalankan setiap hari
    catchup=False
) as dag:
    
    # Sensor untuk memeriksa koneksi ke OpenWeatherMap API
    is_api_available = HttpSensor(
        task_id='is_api_available',
        http_conn_id='openweathermap_api',
        endpoint='/data/2.5/weather',
        request_params={
            'q': 'Jakarta',
            'appid': '{{ var.value.openweathermap_api_key }}'
        }
    )
    
    # Task untuk mengekstrak data cuaca untuk setiap kota
    def extract_weather_for_city(city):
        return SimpleHttpOperator(
            task_id=f'extract_weather_{city.lower()}',
            method='GET',
            http_conn_id='openweathermap_api',
            endpoint='/data/2.5/weather',
            data={
                'q': city,
                'appid': '{{ var.value.openweathermap_api_key }}',
                'units': 'metric'  # Menggunakan suhu dalam Celsius
            },
            response_filter=lambda response: response.json(),
            log_response=True
        )
    
    # Membuat list task untuk ekstraksi data cuaca
    extract_weather_tasks = [extract_weather_for_city(city) for city in CITIES]
    
    # Task untuk memproses data cuaca
    process_weather_data = PythonOperator(
        task_id='process_weather_data',
        python_callable=_process_weather_data,
        provide_context=True
    )

    # Menentukan urutan task
    is_api_available >> extract_weather_tasks >> process_weather_data

# Catatan Penting:
# 1. Anda perlu membuat connection di Airflow dengan ID 'openweathermap_api'
#    dengan base URL: https://api.openweathermap.org
# 2. Tambahkan variabel 'openweathermap_api_key' di Airflow Variables
#    dengan API key Anda dari OpenWeatherMap
# 3. Pastikan Anda telah menginstal provider HTTP dan pandas di Airflow
