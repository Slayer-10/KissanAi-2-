"""
FarmAI Weather Service
Fetches live weather data from Open-Meteo or returns mock fallback data.
"""

import requests
import os
import logging

logger = logging.getLogger(__name__)


def get_live_weather(latitude: float, longitude: float) -> dict:
    """
    Fetch current live weather and 48h forecast from Open-Meteo API using coordinate inputs.
    """
    try:
        base_url = os.getenv("OPEN_METEO_BASE_URL", "https://api.open-meteo.com/v1/forecast").strip()
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,relative_humidity_2m,rain,precipitation,wind_speed_10m",
            "hourly": "temperature_2m,relative_humidity_2m,precipitation_probability,precipitation,wind_speed_10m",
            "forecast_days": 2
        }
        res = requests.get(base_url, params=params, timeout=5)
        if res.status_code == 200:
            data = res.json()
            current = data.get("current", {})
            hourly = data.get("hourly", {})
            
            temp = current.get("temperature_2m", 32)
            humidity = current.get("relative_humidity_2m", 55)
            rain = current.get("rain", 0.0)
            precipitation = current.get("precipitation", 0.0)
            
            # Check rain expected: if it's currently raining, or if any of the next 6 hours has > 30% rain probability
            rain_probs = hourly.get("precipitation_probability", [])
            next_6_hours_probs = rain_probs[:6] if rain_probs else []
            max_prob = max(next_6_hours_probs) if next_6_hours_probs else 0
            
            rain_expected = (rain > 0 or precipitation > 0 or max_prob > 30)
            
            # Extract 24h/48h arrays
            probs_24h = rain_probs[:24] if rain_probs else []
            probs_48h = rain_probs[:48] if rain_probs else []
            
            max_rain_probability_24h = max(probs_24h) if probs_24h else 0
            max_rain_probability_48h = max(probs_48h) if probs_48h else 0
            
            precip_hourly = hourly.get("precipitation", [])
            rain_24h = precip_hourly[:24] if precip_hourly else []
            rain_48h = precip_hourly[:48] if precip_hourly else []
            
            rain_expected_24h = any(r > 0.1 for r in rain_24h) or (max_rain_probability_24h > 30)
            rain_expected_48h = any(r > 0.1 for r in rain_48h) or (max_rain_probability_48h > 30)
            
            humidity_hourly = hourly.get("relative_humidity_2m", [])
            humidity_24h = humidity_hourly[:24] if humidity_hourly else []
            max_humidity_24h = int(round(max(humidity_24h))) if humidity_24h else int(round(humidity))
            
            wind_hourly = hourly.get("wind_speed_10m", [])
            wind_24h = wind_hourly[:24] if wind_hourly else []
            max_wind_24h = float(max(wind_24h)) if wind_24h else 0.0
            
            temp_hourly = hourly.get("temperature_2m", [])
            temp_48h = temp_hourly[:48] if temp_hourly else []
            max_temp_48h = int(round(max(temp_48h))) if temp_48h else int(round(temp))
            
            # Spray advice
            spray_safe = True
            if max_rain_probability_24h > 30:
                spray_msg = f"اگلے 24 گھنٹوں میں بارش کا امکان زیادہ ({max_rain_probability_24h}٪) ہے، اس لیے آج سپرے نہ کریں۔ بارش کے بعد خشک وقت کا انتظار کریں۔"
                spray_safe = False
            elif max_rain_probability_48h > 30:
                spray_msg = f"اگلے 48 گھنٹوں میں بارش کا امکان زیادہ ({max_rain_probability_48h}٪) ہے، اس لیے سپرے مؤخر کریں یا خشک وقت کا انتخاب کریں۔"
                spray_safe = False
            elif max_wind_24h > 15:
                spray_msg = f"ہوا کی رفتار تیز ({max_wind_24h} کلومیٹر فی گھنٹہ) ہونے کا امکان ہے، جس سے سپرے ضائع ہونے کا خطرہ ہے۔ اس لیے ابھی سپرے نہ کریں۔"
                spray_safe = False
            elif max_humidity_24h > 85:
                spray_msg = f"ہوا میں نمی بہت زیادہ ({max_humidity_24h}٪) ہے، جس کی وجہ سے سپرے زیادہ موثر نہیں رہے گا۔ احتیاط برتیں۔"
            else:
                spray_msg = "اگلے 24 گھنٹوں میں بارش کا امکان کم ہے، اس لیے اگر فصل کو ضرورت ہو تو صبح یا شام کے وقت سپرے کیا جا سکتا ہے۔"
                
            # Irrigation advice
            if max_rain_probability_24h > 30:
                irrigation_msg = f"اگلے 24 گھنٹوں میں بارش کا امکان ({max_rain_probability_24h}٪) ہے، اس لیے ابھی پانی روک دیں اور زمین کی نمی چیک کریں۔"
            elif max_rain_probability_48h > 30:
                irrigation_msg = f"اگلے 48 گھنٹوں میں بارش کا امکان ({max_rain_probability_48h}٪) ہے۔ اگر زمین بہت زیادہ خشک ہے تو صرف ہلکا پانی دیں، ورنہ بارش کا انتظار کریں۔"
            elif max_humidity_24h > 80 and max_rain_probability_48h > 15:
                irrigation_msg = "ہوا میں نمی زیادہ ہے اور بارش کا ہلکا امکان بھی موجود ہے، اس لیے اضافی پانی دینے سے پرہیز کریں۔"
            elif max_temp_48h > 35:
                irrigation_msg = f"اگلے 2 دن میں درجہ حرارت تیز ({max_temp_48h}°C) اور موسم خشک رہنے کا امکان ہے۔ زمین کی نمی چیک کر کے ہلکی آبپاشی کریں۔"
            else:
                irrigation_msg = "اگلے 48 گھنٹے موسم خشک رہنے کا امکان ہے۔ اگر زمین خشک ہے تو ہلکا پانی دیا جا سکتا ہے۔ آبپاشی سے پہلے مٹی کی نمی ضرور چیک کریں۔"
                
            forecast_48h = []
            if temp_hourly and humidity_hourly and rain_probs:
                for idx in range(min(48, len(temp_hourly))):
                    forecast_48h.append({
                        "hour": idx,
                        "temperature": temp_hourly[idx],
                        "humidity": humidity_hourly[idx],
                        "precipitation_probability": rain_probs[idx] if idx < len(rain_probs) else 0
                    })

            return {
                "temperature": int(round(temp)) if temp is not None else 32,
                "humidity": int(round(humidity)) if humidity is not None else 55,
                "rain_expected": bool(rain_expected),
                "rain_probability": int(max_prob),
                "spray_safe": bool(spray_safe),
                "location": "منتقل مقام",
                "source": "open_meteo",
                "forecast_48h": forecast_48h,
                "max_rain_probability_24h": int(max_rain_probability_24h),
                "max_rain_probability_48h": int(max_rain_probability_48h),
                "rain_expected_24h": bool(rain_expected_24h),
                "rain_expected_48h": bool(rain_expected_48h),
                "max_humidity_24h": int(max_humidity_24h),
                "max_wind_24h": float(max_wind_24h),
                "max_temp_48h": int(max_temp_48h),
                "spray_advice": {"message": spray_msg},
                "irrigation_advice": {"message": irrigation_msg}
            }
        else:
            logger.error(f"Open-Meteo API returned status code {res.status_code}")
    except Exception as e:
        logger.error(f"Error fetching live weather: {e}")
        
    return {
        "temperature": 32,
        "humidity": 55,
        "rain_expected": False,
        "rain_probability": 20,
        "spray_safe": True,
        "location": "مقام دستیاب نہیں (Fallback)",
        "source": "fallback",
        "forecast_48h": [],
        "max_rain_probability_24h": 20,
        "max_rain_probability_48h": 20,
        "rain_expected_24h": False,
        "rain_expected_48h": False,
        "max_humidity_24h": 55,
        "max_wind_24h": 5.0,
        "max_temp_48h": 32,
        "spray_advice": {"message": "اگلے 24 گھنٹوں میں بارش کا امکان کم ہے، اس لیے اگر فصل کو ضرورت ہو تو صبح یا شام کے وقت سپرے کیا جا سکتا ہے۔"},
        "irrigation_advice": {"message": "اگلے 48 گھنٹے موسم خشک رہنے کا امکان ہے۔ اگر زمین خشک ہے تو ہلکا پانی دیا جا سکتا ہے۔"}
    }


def get_mock_weather(latitude: float = None, longitude: float = None) -> dict:
    """
    Return weather data. If coordinates exist, fetch live data.
    """
    if latitude is not None and longitude is not None:
        return get_live_weather(latitude, longitude)
        
    return {
        "temperature": 32,
        "humidity": 55,
        "rain_expected": False,
        "rain_probability": 20,
        "spray_safe": True,
        "location": "مقام دستیاب نہیں",
        "source": "mock_weather_no_location",
        "forecast_48h": [],
        "max_rain_probability_24h": 20,
        "max_rain_probability_48h": 20,
        "rain_expected_24h": False,
        "rain_expected_48h": False,
        "max_humidity_24h": 55,
        "max_wind_24h": 5.0,
        "max_temp_48h": 32,
        "spray_advice": {"message": "اگلے 24 گھنٹوں میں بارش کا امکان کم ہے، اس لیے اگر فصل کو ضرورت ہو تو صبح یا شام کے وقت سپرے کیا جا سکتا ہے۔"},
        "irrigation_advice": {"message": "اگلے 48 گھنٹے موسم خشک رہنے کا امکان ہے۔ اگر زمین خشک ہے تو ہلکا پانی دیا جا سکتا ہے۔"}
    }
