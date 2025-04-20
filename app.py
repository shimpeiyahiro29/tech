import streamlit as st
import time
from PIL import Image
import pandas as pd
import pydeck as pdk
import base64
import streamlit.components.v1 as components
import requests
import random

from supabase import create_client, Client
url: str = "https://pszefvosagdpzilocerq.supabase.co"
key: str = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBzemVmdm9zYWdkcHppbG9jZXJxIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDQ4ODU1NTIsImV4cCI6MjA2MDQ2MTU1Mn0.nRw_Ev8VGVf_PvnQZ5Lk10JPYg3jaJwUWkGCmNO03fA"

supabase: Client = create_client(url, key)
from openai import OpenAI

# Streamlit secrets から直接 API キーを渡して初期化
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# scraper.py から関数をインポート
from scraper import search_places, search_places_by_coords, gmaps

##############################バックエンド側関数##############################
##add_records("place","exp")を入れると、recordsに挿入される。→チェックインをする時に場所の情報とexpを載せたい
def add_records(place,exp,spell):
    data= {
        "place":place,
        "exp":exp,
        "spell":spell
    }
    response = supabase.table("records").insert(data).execute()
    return response

##shopDBからmoodとareaのカラムを参照して該当のデータを引っ張ってくる
##時間含めて条件分岐を作っている
def search_shops(time,mood,area):
    if time=="120分":
        response = supabase.table("place").select("*").eq("mood", mood).limit(10).execute()
    elif time=="60分" and (area=="天神駅" or area=="中洲川端駅"):
        response = supabase.table("place").select("*").in_("area", ["天神駅", "中洲川端駅"]).eq("mood", mood).limit(5).execute()
    else:
        response = supabase.table("place").select("*").eq("area", area).eq("mood", mood).limit(5).execute()
    return response.data 

##経験値の合計値をtotal_expに格納する
def exp_sum(spell):
    response = supabase.table("records").select("*").eq("spell", spell).execute()
    exp_values = [record['exp'] for record in response.data]
    total_exp = sum(exp_values)
    return total_exp

##recordsからチェックインした名前の場所と同じ場所を抽出する
def search_records(spell,place):
    response = supabase.table("records").select("*").eq("spell", spell).eq("place", place).execute()
    return response.data 

##recordsから復活の呪文を使ってチェックイン履歴を取得する
def get_records(spell):
    response = supabase.table("records").select("*").eq("spell", spell).execute()
    return response.data 

##recordsからチェックインした名前の場所と同じ場所がないかを調べ、経験値を計算する。
##経験値のロジックは、初めて行ったところは20で一回いくごとに-5される。最低が５。想定しうる経験値は20,25,10,5
def calc_exp(place):
    found_records=search_records(st.session_state.activated_spell,place)
    number_of_records = len(found_records)
    if number_of_records >3:
        exp =5
    else:
        exp = 20-5*(number_of_records)
    return exp

#--- supabase から呪文データを取得して辞書に格納する関数 ---
def build_spell_db_from_supabase():
    response = supabase.table("status").select("spell").execute()
    spell_list = response.data

    spell_db = {}
    for item in spell_list:
        spell_name = item["spell"]
        spell_db[spell_name] = {"level": 1, "exp": 0}
    return spell_db

################ベース設定####################

# 音楽ファイルを base64 に変換します

def get_audio_base64(file_path):
    with open(file_path, "rb") as f:
        data = f.read()
    return base64.b64encode(data).decode()

# BGM をモード選択時に再生する関数
def play_bgm_on_mode_selection(bgm):
    audio_base64 = get_audio_base64(bgm)
    audio_html = f"""
    <audio id="bgm" src="data:audio/mp3;base64,{audio_base64}" autoplay ></audio>
    <script>
        var audio = document.getElementById('bgm');
        if (audio) {{
            audio.volume = 0.1;
            audio.play();
        }}
    </script>
    """
    components.html(audio_html, height=0)


# --- 勇者の画像＋ステータス表示（共通） ---
def show_hero_status(spell):
    if st.session_state.activated_spell and st.session_state.user_data:
        data = st.session_state.user_data
        col1, col2 = st.columns([1, 2])
        with col1:
            image = Image.open("yu-sya_image3.png")
            st.image(image, width=200)
        with col2:
            total_exp =exp_sum(spell)
            now_lv= total_exp//100
            last_exp=100-(total_exp%100)
            #st.session_state.user_lv=now_lv
            st.markdown(f"### レベル：{now_lv}")
            st.markdown(f"レベルアップまであと **{last_exp} EXP**")
            st.markdown("🗺️ 新しい冒険に出発しよう！")

# --- データベース（ふっかつのじゅもん） ---
spell_db = build_spell_db_from_supabase()


# --- セッションステート初期化 ---
def init_session_state():
    keys_and_defaults = {
        "mode": None,
        "activated_spell": None,
        "user_data": None,
        "awakening_message": "",
        "show_awakening_message": False,
        "spell_checked": False,
        "spell_valid": False,
        "spell_last_input": "",
        "selected_time": None,
        "selected_mood": None,
        "selected_location": None,
        "place_chosen": False,
        "checkin_done": False,
        "checkin_history": [],
        "new_spell_ready": False,
        "user_lv":None,
    }
    for key, default in keys_and_defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default

init_session_state()


# 背景画像を設定する関数
def set_background(image_file):
    with open(image_file, "rb") as f:
        encoded = base64.b64encode(f.read()).decode()
    page_bg_img = f"""
    <style>
    [data-testid="stApp"] {{
        background-image: url("data:image/png;base64,{encoded}");
        background-size: cover;
        background-position: center;
        background-repeat: no-repeat;
        background-attachment: fixed;
    }}
    </style>
    """
    st.markdown(page_bg_img, unsafe_allow_html=True)

# ✅ 共通のメッセージ表示関数（くっきり表示用）
def custom_message(message, color="green"):
    if color == "green":
        st.markdown(
            f"""
            <div style="
                background-color: #c8facc;
                border: 2px solid #2e8b57;
                border-radius: 10px;
                padding: 1em 1.2em;
                margin: 1em 0;
                font-weight: bold;
                font-size: 18px;
                color: #155724;
                box-shadow: 3px 3px 10px rgba(0, 100, 0, 0.2);
                line-height: 1.6;
                text-align: center;
            ">
            {message}
            </div>
            """,
            unsafe_allow_html=True
        )
    elif color == "red":
        st.markdown(
            f"""
            <div style="
                background-color: #ffe5e5;
                border: 2px solid #ff0000;
                border-radius: 8px;
                padding: 1em;
                margin-top: 1em;
                font-weight: bold;
                color: #900;
                box-shadow: 2px 2px 6px rgba(255, 0, 0, 0.2);
            ">
            {message}
            </div>
            """,
            unsafe_allow_html=True
        )
    elif color == "blue":
        st.markdown(
            f"""
            <div style="
                background-color: #e0f0ff;
                border: 2px solid #3399ff;
                border-radius: 8px;
                padding: 1em;
                margin-top: 0.5em;
                margin-bottom: 1em;
                font-weight: normal;
                color: #003366;
                box-shadow: 1px 1px 4px rgba(0, 0, 255, 0.1);
            ">
            {message}
            </div>
            """,
            unsafe_allow_html=True
        )


# --- UI表示系 ----
set_background("backimage2.png") 

st.title("まちクエ!!")
st.markdown("気分と時間に合わせて冒険の旅を提案します。まちを旅して勇者を育てよう！")

if st.session_state.show_awakening_message:
    st.success(st.session_state.awakening_message)
    st.session_state.show_awakening_message = False

# --- AIコメント生成関数 ---
@st.cache_data(show_spinner=False)
def get_ai_recommendation(place: str) -> str:
    """
    place の名称を受け取り、ChatGPT に推薦コメントを生成させる。
    キャッシュ付きなので連続呼び出しのコストを抑えられます。
    """
    messages = [
        {"role": "system", "content": "あなたは旅行好きユーザー向けのレコメンドアシスタントです。"},
        {"role": "user", "content": f"目的地「{place}」を訪れたくなる、日本語の短い推薦コメントを100文字以内でください。"}
    ]
    res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.8,
        max_tokens=120,
    )
    return res.choices[0].message.content.strip()


# --- モード選択(初回) ---
if st.session_state.mode is None:
    st.markdown("## あなたの冒険を選んでください")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("\U0001F331 新しい冒険をはじめる"):
            st.session_state.mode = "new"
            st.session_state.bgm_triggered = True
            st.rerun()  # 画面再描画して音再生へ
    with col2:

        if st.button("\U0001F501 自分の冒険を思い出す"):
            st.session_state.mode = "returning"
            st.session_state.bgm_triggered = True
            st.rerun() # 画面再描画して音再生へ
    st.stop()


# モードが選ばれて、bgm_triggered が True のときのみ再生
if st.session_state.bgm_triggered:
    play_bgm_on_mode_selection("bgm2.mp4")
    st.session_state.bgm_triggered = False  # 一度だけ再生

# --- 新しい冒険 ---
if st.session_state.mode == "new" and not st.session_state.new_spell_ready:

    if st.session_state.activated_spell:
        # 再入力を省略して自動登録
        new_spell = st.session_state.activated_spell

        def add_spell_to_status(new_spell):
            data = {"spell": new_spell}
            response = supabase.table("status").insert(data).execute()
            return response
        add_spell_to_status(new_spell)

        spell_db[new_spell] = {"level": 1, "exp": 0}
        st.session_state.user_data = spell_db[new_spell]


        # ✅ ここでメッセージを保存しておく！
        st.session_state.awakening_message = f"『{new_spell}』 勇者は　うまれた！"
        st.session_state.show_awakening_message = True
        
        # 次の表示へ
#        st.session_state.new_spell_ready = False  # 念のためリセット
        st.session_state.mode = "ready"
        st.rerun()

    else:
        st.markdown("### あなたの ふっかつのじゅもん を入力してください")
        new_spell = st.text_input("新しいじゅもん", placeholder="例：ほいみ", key="new_spell")

        if st.button("このじゅもんで冒険を始める"):
            if new_spell:
                def add_spell_to_status(new_spell):
                    data = {"spell": new_spell}
                    # spellをDBに入れようとする。
                    try: 
                        response = supabase.table("status").insert(data).execute()
                        return response
                    # エラーが出た場合の分岐
                    except Exception as e:
                        # すでに存在している場合のエラー処理
                        if hasattr(e, "args") and "duplicate key value violates unique constraint" in str(e.args[0]):
                            custom_message(f"じゅもん『{new_spell}』は すでに使われています。<br>別のじゅもんを考えてみてください。", color="red")
                            st.session_state.reset_spell = True
                        else:
                            custom_message("じゅもんの登録中に予期せぬエラーが発生しました。<br>もう一度試してみてください。", color="red")
                            st.session_state.reset_spell = True
                        return None
                
                response = add_spell_to_status(new_spell)

                if response:
                    spell_db[new_spell] = {"level": 1, "exp": 0}
                    st.session_state.activated_spell = new_spell
                    st.session_state.user_data = spell_db[new_spell]
                    st.session_state.awakening_message = f"『{new_spell}』 勇者は　うまれた！" # ✅ 次の画面で表示するために保存
                    st.session_state.show_awakening_message = True
                    st.session_state.mode = "ready"
                    st.rerun()
                    st.stop()
            else:
                custom_message("じゅもんを入力してください", color="red")
        st.stop()
    
# --- 「うまれた」あとの処理 --- 不要
#if st.session_state.mode == "new" and st.session_state.new_spell_ready:
#    st.session_state.awakening_message = f"『{st.session_state.activated_spell}』 勇者は　うまれた！"
#    st.session_state.show_awakening_message = True
#    st.session_state.new_spell_ready = False
#    st.session_state.mode = "ready"
#    st.rerun()



# --- 自分の冒険を思い出す(ふっかつのじゅもん) ---
if st.session_state.mode == "returning":
    st.markdown("### ふっかつのじゅもん")
    spell = st.text_input(" ", placeholder="じゅもんを入力してください", label_visibility="collapsed", key="spell_input_returning")

    if st.button("唱える"):
        if not spell.strip():
            custom_message("じゅもんを入力してください", color="red")
        else:
            spell_db = build_spell_db_from_supabase()

            st.session_state.spell_checked = True
            st.session_state.spell_last_input = spell

            if spell in spell_db:
                st.session_state.spell_valid = True
                st.session_state.activated_spell = spell
                st.session_state.user_data = spell_db[spell]
                st.session_state.awakening_message = f"『{spell}』勇者は　めをさました！"
                st.session_state.show_awakening_message = True
                st.session_state.mode = "ready"
                st.rerun()
            else:
                st.session_state.spell_valid = False
                st.session_state.activated_spell = None
                st.session_state.user_data = None
                custom_message("その　じゅもんは　まちがっております", color="red")

    if st.session_state.spell_checked and not st.session_state.spell_valid:
        st.markdown("<br>", unsafe_allow_html=True)  # ← ここでスペース追加
        if st.button("このじゅもんで新しい冒険を始める"):
            # Supabaseに追加
            def add_spell_to_status(new_spell):
                data = {"spell": new_spell}
                response = supabase.table("status").insert(data).execute()
                return response

            add_spell_to_status(st.session_state.spell_last_input)

            st.session_state.mode = "ready"
            st.session_state.activated_spell = st.session_state.spell_last_input
            st.session_state.user_data = {"level": 1, "exp": 0}
            st.session_state.awakening_message = f"『{st.session_state.activated_spell}』勇者は　うまれた！"
            st.session_state.show_awakening_message = True
            st.rerun()

# --- モード選択前（最初の画面）のときだけ表示したい部分を条件で囲う ---
if st.session_state.mode is None:
    st.markdown("### ふっかつのじゅもん")
    spell = st.text_input(" ", placeholder="じゅもんを入力してください", label_visibility="collapsed", key="spell_input_main")

    if st.button("唱える"):
        if spell in spell_db:
            st.session_state.activated_spell = spell
            st.session_state.user_data = spell_db[spell]
            st.session_state.awakening_message = f"『{spell}』勇者は　めをさました！"
            st.session_state.show_awakening_message = True
            st.session_state.mode = "ready"
            st.rerun()
        else:
            st.session_state.activated_spell = None
            st.session_state.user_data = None
            custom_message("その　じゅもんは　まちがっております", color="red")

#################################################################################################    
# --- 冒険フロー（readyモード） ---
#if st.session_state.mode == "ready" and st.session_state.activated_spell:
#
#    # 🟢 表示したいメッセージ（うまれた／めをさました）をここで表示
#    if st.session_state.show_awakening_message:
#        st.success(st.session_state.awakening_message)
#        st.session_state.show_awakening_message = False


#    if not st.session_state.place_chosen:
#        show_hero_status(st.session_state.activated_spell)  # 勇者ステータス
#        st.markdown("---")
#        st.markdown("### ⏳ 冒険の時間")
#        time_choice = st.radio("時間を選んでください", ["30分", "60分", "120分"], horizontal=True, key="time_choice")

#        st.markdown("### 💫 冒険の気分")
#        mood_choice = st.radio("気分を選んでください", ["カフェ", "リラクゼーション", "エンタメ", "ショッピング"], horizontal=True, key="mood_choice")

#        st.markdown("### 🏘️ 旅立ちの村")
#        location_choice = st.radio("出発地を選んでください", ["博多駅", "天神駅", "中洲川端駅"], horizontal=True, key="location_choice")

#        if st.button("🧭 冒険に出る"):
#            with st.spinner("冒険先を探索中..."):
#                time.sleep(1.5)
#            st.session_state.selected_time = time_choice
#            st.session_state.selected_mood = mood_choice
#            st.session_state.selected_location = location_choice
#            st.session_state.place_chosen = True
#            st.success("冒険スタート！")
#            st.rerun()
#            search_mood = st.session_state.selected_mood # 検索したい場所
#            search_time = 30
#################################################################################################

# --- 冒険フロー（readyモード） ---
if st.session_state.mode == "ready" and st.session_state.activated_spell:
    # 🟢 表示したいメッセージ（うまれた／めをさました）をここで表示
    if st.session_state.show_awakening_message:
        custom_message(st.session_state.awakening_message, color="green")
        st.session_state.show_awakening_message = False
#        st.stop()

    show_hero_status(st.session_state.activated_spell)  # 勇者ステータス

# ★ここから先は show_awakening_message の内側ではなく、
#  mode=="ready" のトップレベルで常に実行されるUIにする
    if not st.session_state.place_chosen:
        st.markdown("---")
        st.markdown("### ⏳ 冒険の時間")
        time_choice = st.radio("時間を選んでください", ["30分", "60分", "120分"], horizontal=True, key="time_choice")

        st.markdown("### 💫 冒険の気分")
        mood_choice = st.radio("気分を選んでください", ["カフェ", "リラクゼーション", "エンタメ", "ショッピング"], horizontal=True, key="mood_choice")

        st.markdown("### 🏘️ 旅立ちの村")
        loc_method = st.radio(
            "出発地を選んでください",
            ["現在地を取得 (IP-API)", "手動で入力"],
            horizontal=True,
            key="location_method"
        )
        use_coords = False
        location_keyword = None

        if loc_method == "現在地を取得 (IP-API)":
            # IP-APIを使用して現在の位置を取得
            try:
                ipres = requests.get("http://ip-api.com/json/").json()
                base_lat, base_lon = ipres["lat"], ipres["lon"]
                st.write(f"取得した現在地: ({base_lat:.4f}, {base_lon:.4f})")
                use_coords = True
#                location_keyword = None
            except Exception as e:
                st.error(f"現在地の取得に失敗しました: {e}")
#                use_coords = False
                location_keyword = st.text_input("出発地を入力してください (例: 博多駅)", key="location_input")
        else:
            # 手動入力
#           use_coords = False
            location_keyword = st.text_input("出発地を入力してください (例: 博多駅)", key="location_input")
        

        if st.button("🧭 冒険に出る"):
            with st.spinner("冒険先を探索中..."):
                time.sleep(1.5)


            if use_coords:
                st.session_state.base_lat = base_lat #現在地の緯度・経度をセッションに保存
                st.session_state.base_lon = base_lon #現在地の緯度・経度をセッションに保存
                st.session_state.selected_location = f"現在地 ({base_lat:.4f}, {base_lon:.4f})" #これいるかな？
            else:
                # 手動入力モード: 入力キーワードをジオコーディング
                if not location_keyword:
                    st.error("出発地を入力してください")
                    st.stop()
                # ジオコーディングを実行
                geocode_result = gmaps.geocode(location_keyword, language="ja")
                if not geocode_result:
                    st.error("ジオコーディングに失敗しました")
                    st.stop()
                loc = geocode_result[0]["geometry"]["location"]
                st.session_state.base_lat = loc["lat"]
                st.session_state.base_lon = loc["lng"]
                st.session_state.selected_location = location_keyword

#            # セッションに保存
            st.session_state.selected_time = time_choice
            st.session_state.selected_mood = mood_choice
            st.session_state.selected_location = (
                f"現在地 ({base_lat:.4f}, {base_lon:.4f})"
                if use_coords else location_keyword
            )

            # 出発地情報を格納
            if use_coords:
                # 現在地取得の場合は緯度・経度を文字列化して保存する、あるいは任意のラベル
                st.session_state.selected_location = f"現在地 ({base_lat:.4f}, {base_lon:.4f})"
            else:
                # 手動入力の場合はそのまま保存
                st.session_state.selected_location = location_keyword
#            st.session_state.place_chosen = True




            # search_places を呼び出し
            # 距離レンジの計算
            minutes = int(time_choice.replace("分", ""))

            if minutes == 30:
                min_r, max_r = 0, 500
            elif minutes == 60:
                min_r, max_r = 500, 1000
            else:
                min_r, max_r = 1000, 2000

            # 検索実行：IP‐APIで取った緯度経度なら search_places_by_coords を
            # それ以外はキーワード検索用の search_places を呼ぶ
            if use_coords:
                spots = search_places_by_coords(
                    mood=mood_choice,
                    time_min=min_r,
                    time_max=max_r,
                    base_lat=base_lat,
                    base_lon=base_lon
                )
            else:
                # 手動入力モードならキーワード必須
                if not location_keyword:
                    st.error("出発地を入力してください")
                    st.stop()
                spots = search_places(
                    mood=mood_choice,
                    time_min=min_r,
                    time_max=max_r,
                    location_keyword=location_keyword
                )


            # DataFrame 化してセッションに保持
            st.session_state.df_places = pd.DataFrame(spots)
            st.session_state.place_chosen = True
            custom_message("冒険スタート！", color="green")
            st.rerun()


# --- 候補地表示 ---
if st.session_state.place_chosen and not st.session_state.checkin_done:
    df_places = st.session_state.df_places
    # AI コメントを列に追加
    df_places["recommendation"] = df_places["name"].apply(get_ai_recommendation)

    #セッションに保存されている現在地の緯度・経度を取得
    base_lat = st.session_state.base_lat
    base_lon = st.session_state.base_lon

    # 初期ビュー
    initial_view_state = pdk.ViewState(
        latitude=base_lat,
        longitude=base_lon,
        zoom=14,
        pitch=30
    )

    # 現在地レイヤー (青ピン)
    user_layer = pdk.Layer(
        "ScatterplotLayer",
        data=[{"lat": base_lat, "lon": base_lon}],
        get_position='[lon, lat]',
        get_color='[0, 0, 255, 200]',
        get_radius=100,
        pickable=False,
    )

    # 目的地候補レイヤー (赤ピン)
    place_layer = pdk.Layer(
        "ScatterplotLayer",
        data=df_places,
        get_position='[lon, lat]',
        get_color='[200, 30, 0, 160]',
        get_radius=100,
        pickable=True,
    )

    # 吹き出し設定
    tooltip = {
        "html": "<b>{name}</b><br>{recommendation}",
        "style": {
            "backgroundColor": "white",
            "color": "black",
        },
    }

    

    st.markdown("### 🌟 目的地候補とAIコメント")
    for i, row in df_places.iterrows():
        place = row["name"]
        st.markdown(f"**🏞️ {place}**")
        custom_message(get_ai_recommendation(place), color="blue")  # コメントくっきり表示に変更（からちゃん）

# マップ描画
    st.pydeck_chart(
        pdk.Deck(
            map_style='mapbox://styles/mapbox/streets-v12',
            initial_view_state=initial_view_state,
            layers=[user_layer, place_layer],
            tooltip=tooltip,
        )
    )
    st.markdown("### ✅ 上から目的地を選んでください")
    selected_place = st.radio("目的地を選択", df_places["name"].tolist(), key="selected_place", label_visibility="collapsed")

#マップブロックを丸ごと削除
#    if selected_place:
#        st.session_state.place_chosen = True
#        
#
#        selected_df = df_places[df_places["name"] == selected_place]
#        st.pydeck_chart(pdk.Deck(
#            map_style='mapbox://styles/mapbox/streets-v12',
#            initial_view_state=pdk.ViewState(
#                latitude=float(selected_df["lat"].values[0]),
#                longitude=float(selected_df["lon"].values[0]),
#                zoom=14,
#                pitch=30,
#           ),

#            
#            layers=[
#                pdk.Layer(
#                    'ScatterplotLayer',
#                    data=selected_df,
#                    get_position='[lon, lat]',
#                    get_color='[200, 30, 0, 160]',
#                    get_radius=100,
#                ),
#           ]
#        ))

    st.markdown("冒険を終えたら、チェックインしてください！")

    if st.button("✅ チェックイン"):
        gained_exp = 20
        current_exp = st.session_state.user_data["exp"]
        current_level = st.session_state.user_data["level"]
        new_exp = current_exp + gained_exp
        new_level = current_level
        level_up = False
        while new_exp >= 100:
            new_exp -= 100
            new_level += 1
            level_up = True

        # 経験値とレベルを更新　
        st.session_state.user_data["exp"] = new_exp
        st.session_state.user_data["level"] = new_level
        st.session_state.checkin_done = True

        # チェックイン履歴保存
        st.session_state.checkin_history.append({
            "place": selected_place,
            "time": st.session_state.selected_time,
            "mood": st.session_state.selected_mood,
            "location": st.session_state.selected_location,
            "exp_gained": gained_exp
        })

        st.balloons()  # 🎈 風船を上げる
        custom_message(f"🎉 {selected_place} にチェックインしました！", color="green")
        st.session_state.user_lv =exp_sum(st.session_state.activated_spell)//100
        #経験値が100溜まるとレベルが貯まる。100-余りで残りの経験値を算出する。
        get_exp=calc_exp(selected_place)#チェックインした店の名前から獲得経験値を計算
        add_records(selected_place,get_exp,st.session_state.activated_spell)#recordsにチェックインで選んだ店名,経験値,ふっかつの呪文を入れる
        update_now_lv= exp_sum(st.session_state.activated_spell)//100#チェックインした後の更新したレベルを計算
        last_exp=(exp_sum(st.session_state.activated_spell)%100)#チェックインした後の更新した経験値を計算
            
        st.markdown(f"🧪 経験値 +{get_exp} EXP（現在の経験値 {last_exp} EXP）")####DBを参照して、チェックイン後のレベルを表示する

            # if level_up:
            #     st.markdown(f"🌟 レベルアップ！ 新しいレベル：**{new_level}**")
            # else:
            #     st.markdown(f"📊 現在のレベル：{now_lv}")####DBを参照して、チェックイン後のレベルを表示する

            
        if st.session_state.user_lv == update_now_lv: # ふっかつのじゅもんを唱えた時と、チェックインをした後のレベルが違ったらレベルアップ
            st.markdown(f"📊 現在のレベル：{update_now_lv}")  
        else:                    
            st.balloons()  # 🎈 この1行をここに追加！
            st.markdown(f"🌟 レベルアップ！ 新しいレベル：**{st.session_state.user_lv}**→**{update_now_lv}**")
            st.session_state.level_up = True  # ← レベルアップ検知
            play_bgm_on_mode_selection("levelup.mp3")
            
            # # 🔊 レベルアップ音を鳴らす（1回だけ）
            # if st.session_state.get("level_up"):
                
            #     st.session_state.level_up = False

# --- 履歴表示 ---
if st.session_state.checkin_history:
    st.markdown("---")
    st.markdown("### 📚 チェックイン履歴")
    df_history = pd.DataFrame(get_records (st.session_state.activated_spell))
    st.dataframe(df_history[["created_at","place"]])