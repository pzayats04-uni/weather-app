from fastapi import FastAPI, Request, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from datetime import datetime, timedelta
import csv
import aiohttp
import asyncio
from typing import Optional

#БАЗА ДАННЫХ
Base = declarative_base()

class City(Base):
    __tablename__ = "cities"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    temperature = Column(Float, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow)

class DefaultCity(Base):
    __tablename__ = "default_cities"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)

DATABASE_URL = "sqlite:///./cities.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

#FASTAPI
app = FastAPI()
templates = Jinja2Templates(directory="templates")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

#ФУНКЦИЯ ДЛЯ ПОГОДЫ
async def fetch_weather(latitude: float, longitude: float) -> Optional[float]:
    """Получает температуру из Open-Meteo"""
    url = f"https://api.open-meteo.com/v1/forecast?latitude={latitude}&longitude={longitude}&current_weather=true"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('current_weather', {}).get('temperature')
    except Exception as e:
        print(f"Ошибка получения погоды: {e}")
    return None

#ЗАГРУЗКА CSV
@app.on_event("startup")
def startup_event():
    print("=" * 50)
    print("ПРИЛОЖЕНИЕ ЗАПУСКАЕТСЯ")
    print("=" * 50)
    
    db = SessionLocal()
    try:
        if not db.query(City).first():
            with open("cities.csv", "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    default_city = DefaultCity(
                        name=row["city"],
                        latitude=float(row["latitude"]),
                        longitude=float(row["longitude"])
                    )
                    db.add(default_city)
                    city = City(
                        name=row["city"],
                        latitude=float(row["latitude"]),
                        longitude=float(row["longitude"]),
                        temperature=None,  
                        updated_at=datetime(2000, 1, 1) 
                    )
                    db.add(city)
            
            db.commit()
            print("CSV файл загружен, города добавлены в базу")
            print(f"Добавлено городов: {db.query(City).count()}")
        else:
            print("Города уже загружены")
            
    except Exception as e:
        print(f"Ошибка загрузки CSV: {e}")
        db.rollback()
    finally:
        db.close()

#МАРШРУТЫ
@app.get("/")
async def read_root(request: Request, db: Session = Depends(get_db)):
    cities = db.query(City).order_by(City.temperature.desc()).all()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "cities": cities,
        "now": datetime.utcnow()
    })

@app.post("/cities/remove/{city_id}")
async def remove_city(city_id: int, db: Session = Depends(get_db)):
    city = db.query(City).filter(City.id == city_id).first()
    if city:
        db.delete(city)
        db.commit()
    return RedirectResponse("/", status_code=303)

@app.post("/cities/reset")
async def reset_cities(db: Session = Depends(get_db)):
    db.query(City).delete()
    default_cities = db.query(DefaultCity).all()
    for dc in default_cities:
        city = City(
            name=dc.name,
            latitude=dc.latitude,
            longitude=dc.longitude,
            temperature=None,  
            updated_at=datetime(2000, 1, 1)  
        )
        db.add(city)
    
    db.commit()
    return RedirectResponse("/", status_code=303)

@app.post("/cities/update")
async def update_weather(db: Session = Depends(get_db)):
    print("\n" + "="*50)
    print("НАЧАЛО ОБНОВЛЕНИЯ ПОГОДЫ")
    print("="*50)
    
    cities = db.query(City).all()
    print(f"Городов для обновления: {len(cities)}")
    
    updated_count = 0
    
    # Используем asyncio для параллельных запросов
    async def update_single_city(city: City):
        nonlocal updated_count
        
        print(f"\n Город: {city.name}")
        print(f" Координаты: {city.latitude}, {city.longitude}")
        if city.temperature is None:
            print(f"  Нет температуры - запрашиваем...")
            temp = await fetch_weather(city.latitude, city.longitude)
            
            if temp is not None:
                city.temperature = temp
                city.updated_at = datetime.utcnow()
                updated_count += 1
                print(f" Получена температура: {temp}°C")
                return True
            else:
                print(f"  Не удалось получить данные")
                return False
        time_passed = datetime.utcnow() - city.updated_at
        minutes_passed = time_passed.total_seconds() / 60
        
        if minutes_passed < 15:
            print(f"   Пропускаем (обновляли {minutes_passed:.1f} мин назад)")
            return False
        
        print(f" Прошло {minutes_passed:.1f} мин - запрашиваем...")
        temp = await fetch_weather(city.latitude, city.longitude)
        
        if temp is not None:
            city.temperature = temp
            city.updated_at = datetime.utcnow()
            updated_count += 1
            print(f"  Новая температура: {temp}°C")
            return True
        else:
            print(f"  Не удалось получить данные")
            return False
    
    # Параллельно обновляем все города
    tasks = [update_single_city(city) for city in cities]
    results = await asyncio.gather(*tasks)
    
    if updated_count > 0:
        db.commit()
        print(f"\n Сохранено обновлений: {updated_count}")
    else:
        print(f"\n Нет новых обновлений")
    print("="*50)
    return RedirectResponse("/", status_code=303)

#ТЕСТОВЫЙ ЭНДПОИНТ
@app.get("/test-api")
async def test_api():
    """Тестируем API прямо из браузера"""
    test_url = "https://api.open-meteo.com/v1/forecast?latitude=55.7558&longitude=37.6173&current_weather=true"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(test_url, timeout=10) as response:
                data = await response.json()
                return {
                    "status": response.status,
                    "data": data,
                    "temperature": data.get('current_weather', {}).get('temperature')
                }
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=True)