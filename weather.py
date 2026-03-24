import requests
import os
import csv
from dotenv import load_dotenv
from datetime import date
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
load_dotenv()

API_KEY = os.getenv("API_KEY")
CITY = "Valdivia Chile"
current_day = date.today()

session = requests.Session()
retries = Retry(
    total=3,
    connect=3,
    read=3,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"],
)
session.mount("https://", HTTPAdapter(max_retries=retries))
session.mount("http://", HTTPAdapter(max_retries=retries))

def fetch_day(date_str):
    weather_api = f"https://api.weatherapi.com/v1/history.json?key={API_KEY}&q={CITY}&dt={date_str}"
    response = session.get(weather_api, timeout=20)
    response.raise_for_status()
    return response.json()

def parse_data(data):
    city = data["location"]["name"]
    forecast_date = data["forecast"]["forecastday"][0]["date"]
    max_temp = data["forecast"]["forecastday"][0]["day"]["maxtemp_c"]
    min_temp = data["forecast"]["forecastday"][0]["day"]["mintemp_c"]
    avg_temp = data["forecast"]["forecastday"][0]["day"]["avgtemp_c"]
    max_wind = data["forecast"]["forecastday"][0]["day"]["maxwind_kph"]
    total_precip = data["forecast"]["forecastday"][0]["day"]["totalprecip_mm"]
    total_snow = data["forecast"]["forecastday"][0]["day"]["totalsnow_cm"]
    avg_humidity = data["forecast"]["forecastday"][0]["day"]["avghumidity"]
    uv = data["forecast"]["forecastday"][0]["day"]["uv"]
    chance_of_rain = data["forecast"]["forecastday"][0]["day"]["daily_chance_of_rain"]
    chance_of_snow = data["forecast"]["forecastday"][0]["day"]["daily_chance_of_snow"]
    condition = data["forecast"]["forecastday"][0]["day"]["condition"]["text"]
    visibility = data["forecast"]["forecastday"][0]["day"]["avgvis_km"]
    sunrise = data["forecast"]["forecastday"][0]["astro"]["sunrise"]
    sunset = data["forecast"]["forecastday"][0]["astro"]["sunset"]

    return [
        city, forecast_date, max_temp, min_temp, avg_temp, max_wind,
        total_precip, total_snow, avg_humidity, uv,
        chance_of_rain, chance_of_snow, condition, visibility,
        sunrise, sunset
    ]

with open("clima_historico.csv", "w", newline="", encoding="utf-8") as file:
    writer = csv.writer(file)
    failed_dates = []
    writer.writerow([
        "city", "date", "max_temp_c", "min_temp_c", "avg_temp_c", "max_wind_kph",
        "total_precip_mm", "total_snow_cm", "avg_humidity", "uv",
        "chance_of_rain", "chance_of_snow", "condition", "visibility_km",
        "sunrise", "sunset"
    ])

    for i in range(14):
        year = 2013 + i
        if year == 2024 or year == 2020 or year == 2016:
            bisiesto = 1
        else:
            bisiesto = 0
        
        for j in range(12):
            month = j + 1
            print(f"{year}-{month:02d}")

            if month == 2:
                days = 28 + bisiesto
            elif month in [1, 3, 5, 7, 8, 10, 12]:
                days = 31
            else:
                days = 30

            for k in range(days):
                day = k + 1
                date_str = f"{year}-{month:02d}-{day:02d}"

                if date_str > current_day.strftime("%Y-%m-%d"):
                    break

                try:
                    data = fetch_day(date_str)

                except requests.RequestException as e:
                    print(f"Error {date_str}: {e}")
                    failed_dates.append(date_str)
                    continue

                parsed_data = parse_data(data)
                writer.writerow(parsed_data)

    if failed_dates:
        print(f"Reintentando fechas fallidas...")
    for date_str in failed_dates:
        try:
            data = fetch_day(date_str)
            parsed_data = parse_data(data)
            writer.writerow(parsed_data)
        except requests.RequestException as e:
            print(f"Error persistente {date_str}: {e}")


