# test_api.py
import aiohttp
import asyncio

async def test():
    print("🔍 Тестируем API Open-Meteo...")
    
    cities = [
        ("Москва", 55.7558, 37.6173),
        ("Казань", 55.8304, 49.0661)
    ]
    
    async with aiohttp.ClientSession() as session:
        for name, lat, lon in cities:
            url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
            print(f"\n📍 {name}: {url}")
            
            try:
                async with session.get(url, timeout=5) as response:
                    print(f"   Статус: {response.status}")
                    data = await response.json()
                    
                    if 'current_weather' in data:
                        temp = data['current_weather'].get('temperature')
                        print(f"   🌡️  Температура: {temp}°C")
                    else:
                        print(f"   ❌ Нет данных о погоде")
                        print(f"   Ответ: {data}")
            except Exception as e:
                print(f"   ❌ Ошибка: {e}")

if __name__ == "__main__":
    asyncio.run(test())
    input("\nНажмите Enter для выхода...")