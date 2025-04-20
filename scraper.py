import os
import sys
import math
import requests
from dotenv import load_dotenv
from googlemaps import Client as GoogleMaps

# .env を読み込む
load_dotenv()
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
if not GOOGLE_MAPS_API_KEY:
    raise RuntimeError("ERROR: 環境変数 GOOGLE_MAPS_API_KEY が設定されていません。")

gmaps = GoogleMaps(key=GOOGLE_MAPS_API_KEY)

# サポートするキーワード
KEYWORDS = ["カフェ", "リラクゼーション", "エンタメ", "ショッピング"]


def haversine(lat1, lon1, lat2, lon2):
    """
    2点間の距離をメートルで返す（ハーサイン距離）
    """
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c


def search_places(mood: str, time_min: int, time_max: int, location_keyword: str) -> list:
    """
    mood: KEYWORDS のいずれか
    time_min, time_max: 検索距離の最小・最大値（メートル）
    location_keyword: 出発地キーワード（例: '博多駅'）
    戻り値: 場所情報リスト (最大5件)
    """
    # 1) 出発地の座標取得 (Places API Find Place)
    res = gmaps.find_place(
        input=location_keyword,
        input_type="textquery",
        fields=["geometry/location"],
        language="ja"
    )
    candidates = res.get("candidates", [])
    if not candidates:
        raise ValueError(f"場所 '{location_keyword}' が見つかりませんでした。")
    base = candidates[0]["geometry"]["location"]
    base_lat, base_lon = base['lat'], base['lng']

    # 2) 周辺検索 (Nearby Search)
    response = gmaps.places_nearby(
        location=(base_lat, base_lon),
        radius=time_max,
        keyword=mood,
        language="ja"
    )
    results = []
    for p in response.get('results', []):
        loc = p['geometry']['location']
        dist = haversine(base_lat, base_lon, loc['lat'], loc['lng'])
        if time_min <= dist <= time_max:
            results.append({
                'name': p.get('name'),
                'vicinity': p.get('vicinity'),
                'lat': loc['lat'],
                'lon': loc['lng'],
                'distance_m': int(dist)
            })
        if len(results) >= 5:
            break
    return results


# CLI テスト用
if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description="場所検索テスト")
    parser.add_argument('--mood', choices=KEYWORDS, required=True)
    parser.add_argument('--time', type=int, choices=[30,60,120], required=True,
                        help="30, 60, 120 のいずれかを指定")
    parser.add_argument('--location', required=True, help="例: '博多駅'")
    args = parser.parse_args()

    # time に応じた距離設定
    if args.time == 30:
        min_r, max_r = 0, 500
    elif args.time == 60:
        min_r, max_r = 500, 1000
    else:
        min_r, max_r = 1000, 2000

    places = search_places(args.mood, min_r, max_r, args.location)
    for i, spot in enumerate(places, start=1):
        print(f"{i}. {spot['name']} - {spot['vicinity']} ({spot['distance_m']}m)")
