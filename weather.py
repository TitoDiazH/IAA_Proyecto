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


def normalize_condition(condition):
    cond = (condition or "").lower()

    if "sunny" in cond or "clear" in cond:
        return "Soleado"
    if "cloud" in cond or "overcast" in cond:
        return "Nublado"
    if "fog" in cond or "mist" in cond:
        return "Niebla"
    if (
        "snow" in cond
        or "sleet" in cond
        or "blizzard" in cond
        or "hail" in cond
        or "ice pellet" in cond
    ):
        return "Nieve"
    if "rain" in cond or "drizzle" in cond or "thunder" in cond:
        return "Lluvia"
    return "Otro"


def fetch_day(date_str):
    weather_api = f"https://api.weatherapi.com/v1/history.json?key={API_KEY}&q={CITY}&dt={date_str}"
    response = session.get(weather_api, timeout=20)
    response.raise_for_status()
    return response.json()


def calculate_pressure(data):
    sum_pressure = 0
    for hour in data["forecast"]["forecastday"][0]["hour"]:
        sum_pressure += hour["pressure_mb"]
    avg_pressure = sum_pressure / 24
    return round(avg_pressure, 2)

def pressure_difference(data):
    pressures = [hour["pressure_mb"] for hour in data["forecast"]["forecastday"][0]["hour"]]
    return max(pressures) - min(pressures)

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
    condition_raw = data["forecast"]["forecastday"][0]["day"]["condition"]["text"]
    condition = normalize_condition(condition_raw)
    visibility = data["forecast"]["forecastday"][0]["day"]["avgvis_km"]
    sunrise = data["forecast"]["forecastday"][0]["astro"]["sunrise"]
    sunset = data["forecast"]["forecastday"][0]["astro"]["sunset"]
    pressure_mb = calculate_pressure(data)
    return {
        "city": city,
        "date": forecast_date,
        "max_temp_c": max_temp,
        "min_temp_c": min_temp,
        "avg_temp_c": avg_temp,
        "max_wind_kph": max_wind,
        "total_precip_mm": total_precip,
        "total_snow_cm": total_snow,
        "avg_humidity": avg_humidity,
        "uv": uv,
        "chance_of_rain": chance_of_rain,
        "chance_of_snow": chance_of_snow,
        "condition": condition,
        "visibility_km": visibility,
        "sunrise": sunrise,
        "sunset": sunset,
        "pressure_mb": pressure_mb,
        "pressure_diff_mb": pressure_difference(data),
    }


fieldnames = [
    "city",
    "date",
    "max_temp_c",
    "min_temp_c",
    "avg_temp_c",
    "max_wind_kph",
    "total_precip_mm",
    "total_snow_cm",
    "avg_humidity",
    "uv",
    "chance_of_rain",
    "chance_of_snow",
    "condition",
    "yd_condition",
    "visibility_km",
    "sunrise",
    "sunset",
    "pressure_mb",
    "pressure_diff_mb",
]

rows = []
failed_dates = []

for i in range(8):
    year = 2018 + i
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

            rows.append(parse_data(data))

if failed_dates:
    print("Reintentando fechas fallidas...")
for date_str in failed_dates:
    try:
        data = fetch_day(date_str)
        rows.append(parse_data(data))
    except requests.RequestException as e:
        print(f"Error persistente {date_str}: {e}")

rows.sort(key=lambda row: (row["city"], row["date"]))
last_condition_by_city = {}
for row in rows:
    city = row["city"]
    row["yd_condition"] = last_condition_by_city.get(city, "")
    last_condition_by_city[city] = row["condition"]

with open("clima_historico.csv", "w", newline="", encoding="utf-8") as file:
    writer = csv.DictWriter(file, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)


