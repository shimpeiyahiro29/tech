import streamlit as st
import time
from PIL import Image
import pandas as pd
import pydeck as pdk
import base64
import streamlit.components.v1 as components
import random
from supabase import create_client, Client
url: str = "https://pszefvosagdpzilocerq.supabase.co"
key: str = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBzemVmdm9zYWdkcHppbG9jZXJxIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDQ4ODU1NTIsImV4cCI6MjA2MDQ2MTU1Mn0.nRw_Ev8VGVf_PvnQZ5Lk10JPYg3jaJwUWkGCmNO03fA"

supabase: Client = create_client(url, key)
from openai import OpenAI

# Streamlit secrets から直接 API キーを渡して初期化
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

##############################バックエンド側関数##############################
##add_records("place","exp")を入れると、recordsに挿入される。→チェックインをする時に場所の情報とexpを載せたい
def add_records(place,exp):
    data= {
        "place":place,
        "exp":exp
    }
    response = supabase.table("records").insert(data).execute()
    return response

##サンプル
add_records("komeda",20)

##recordsテーブルのplaceカラムから引数の内容で検索し、add_recordsに格納する
def search_records(place):
    response = supabase.table("records").select("*").eq("place", place).execute()
    return response.data 

##shopDBからmoodとtimeのカラムを参照して該当のデータを引っ張ってくる
def search_shops(mood,time):
    response = supabase.table("place").select("*").eq("mood", mood).eq("time", time).execute()
    return response.data 

##shopDBからsearch_shopを使って店名を抽出する。
search_mood = "カフェ" # 検索したい場所
search_time = 30 # 検索したい時間
found_records = search_shops(search_mood,search_time)
names = found_records[0]['name']
url =  found_records[0]['url']
lat =  found_records[0]['lat']
lon =  found_records[0]['lon']
print(names)


##経験値の合計値をtotal_expに格納する
def exp_sum():
    response = supabase.table("records").select("*").execute()
    exp_values = [record['exp'] for record in response.data]
    total_exp = sum(exp_values)
    return total_exp
total_exp =exp_sum()

#経験値が100溜まるとレベルが貯まる。100-余りで残りの経験値を算出する。
now_lv= total_exp//100
last_exp=100-(total_exp%100)

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
def play_bgm_on_mode_selection():
    audio_base64 = get_audio_base64("bgm1.mp3")
    audio_html = f"""
    <audio id="bgm" src="data:audio/mp3;base64,{audio_base64}" autoplay loop></audio>
    <script>
        var audio = document.getElementById('bgm');
        if (audio) {{
            audio.volume = 0.2;
            audio.play();
        }}
    </script>
    """
    components.html(audio_html, height=0)


# --- 勇者の画像＋ステータス表示（共通） ---
def show_hero_status():
    if st.session_state.activated_spell and st.session_state.user_data:
        data = st.session_state.user_data
        col1, col2 = st.columns([1, 2])
        with col1:
            image = Image.open("yu-sya_image2.png")
            st.image(image, width=200)
        with col2:
            st.markdown(f"### レベル：{data['level']}")
            st.markdown(f"レベルアップまであと **{data['exp']} EXP**")
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
        "new_spell_ready": False
    }
    for key, default in keys_and_defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default

init_session_state()

# --- UI表示系 ---
st.title("テック勇者リョヤカアプリ")
st.caption("気分と時間に合わせて冒険の旅を提案します。まちを旅して勇者を育てよう！")

if st.session_state.show_awakening_message:
    st.success(st.session_state.awakening_message)
    st.session_state.show_awakening_message = False

# --- 仮の候補地DB（緯度・経度含む） ---
def get_candidate_places_from_db():
    return pd.DataFrame([
        {"name": names, "lat": lat, "lon": lon},#データベースからかmood：カフェ、時間；30で直接指定したDBの結果が表示される。
        {"name": "キャナルシティ", "lat": 33.5896, "lon": 130.4119},
        {"name": "天神地下街", "lat": 33.5903, "lon": 130.4017},
        {"name": "中洲のスパ", "lat": 33.5931, "lon": 130.4094},
        {"name": "リバーウォーク", "lat": 33.8859, "lon": 130.8753},
    ])

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
    play_bgm_on_mode_selection()
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
        st.session_state.new_spell_ready = True
        st.success(f"『{new_spell}』 勇者は　うまれた！")
        st.stop()

    else:
        st.markdown("### あなたの ふっかつのじゅもん を入力してください")
        new_spell = st.text_input("新しいじゅもん", placeholder="例：ほいみ", key="new_spell")

        if st.button("このじゅもんで冒険を始める"):
            if new_spell:
                def add_spell_to_status(new_spell):
                    data = {"spell": new_spell}
                    response = supabase.table("status").insert(data).execute()
                    return response
                add_spell_to_status(new_spell)

                spell_db[new_spell] = {"level": 1, "exp": 0}
                st.session_state.activated_spell = new_spell
                st.session_state.user_data = spell_db[new_spell]
                st.session_state.new_spell_ready = True
                st.success(f"『{new_spell}』 勇者は　うまれた！")
                st.session_state.mode = "ready"
                st.rerun() 
                st.stop()
            else:
                st.error("じゅもんを入力してください")
        st.stop()
    
# --- 「うまれた」あとの処理 ---
if st.session_state.mode == "new" and st.session_state.new_spell_ready:
    st.session_state.awakening_message = f"『{st.session_state.activated_spell}』 勇者は　うまれた！"
    st.session_state.show_awakening_message = True
    st.session_state.new_spell_ready = False
    st.session_state.mode = "ready"
    st.rerun()


# --- 冒険フロー（readyモード） ---
if st.session_state.mode == "ready" and st.session_state.activated_spell:

    # 🟢 表示したいメッセージ（うまれた／めをさました）をここで表示
    if st.session_state.show_awakening_message:
        st.success(st.session_state.awakening_message)
        st.session_state.show_awakening_message = False

    show_hero_status()  # 勇者ステータス

    if not st.session_state.place_chosen:
        st.markdown("---")
        st.markdown("### 🕒 冒険の時間")
        time_choice = st.radio("時間を選んでください", ["30分", "60分", "120分"], horizontal=True, key="time_choice")

        st.markdown("### 🎭 冒険の気分")
        mood_choice = st.radio("気分を選んでください", ["カフェ", "リラクゼーション", "エンタメ", "ショッピング"], horizontal=True, key="mood_choice")

        st.markdown("### 🏘️ 旅立ちの村")
        location_choice = st.radio("出発地を選んでください", ["博多駅", "天神駅", "中洲川端駅"], horizontal=True, key="location_choice")

        if st.button("🚀 冒険に出る"):
            with st.spinner("冒険先を探索中..."):
                time.sleep(1.5)
            st.session_state.selected_time = time_choice
            st.session_state.selected_mood = mood_choice
            st.session_state.selected_location = location_choice
            st.session_state.place_chosen = True
            st.success("冒険スタート！")
            st.rerun()


# --- 自分の冒険を思い出す(ふっかつのじゅもん) ---
if st.session_state.mode == "returning":
    st.markdown("### ふっかつのじゅもん")
    spell = st.text_input(" ", placeholder="じゅもんを入力してください", label_visibility="collapsed", key="spell_input_returning")

    if st.button("唱える"):
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
            st.error("その　じゅもんは　まちがっております")

    if st.session_state.spell_checked and not st.session_state.spell_valid:
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
            st.session_state.awakening_message = f"『{st.session_state.activated_spell}』勇者は　めをさました！"
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
            st.success(f"『{spell}』勇者は　めをさました！")
        else:
            st.session_state.activated_spell = None
            st.session_state.user_data = None
            st.error("その　じゅもんは　まちがっております")


# --- 候補地表示 ---
if st.session_state.selected_time and not st.session_state.checkin_done:
    df_places = get_candidate_places_from_db()

    st.markdown("### 🌟 目的地候補とAIコメント")
    for i, row in df_places.iterrows():
        place = row["name"]
        st.markdown(f"**🏞️ {place}**")
        st.info(get_ai_recommendation(place))

    st.markdown("### ✅ 上から目的地を選んでください")
    selected_place = st.radio("目的地を選択", df_places["name"].tolist(), key="selected_place", label_visibility="collapsed")

    if selected_place:
        st.session_state.place_chosen = True
        

        selected_df = df_places[df_places["name"] == selected_place]
        st.pydeck_chart(pdk.Deck(
            map_style='mapbox://styles/mapbox/streets-v12',
            initial_view_state=pdk.ViewState(
                latitude=selected_df["lat"].values[0],
                longitude=selected_df["lon"].values[0],
                zoom=14,
                pitch=30,
            ),
            layers=[
                pdk.Layer(
                    'ScatterplotLayer',
                    data=selected_df,
                    get_position='[lon, lat]',
                    get_color='[200, 30, 0, 160]',
                    get_radius=100,
                ),
            ]
        ))

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

            st.success(f"🎉 {selected_place} にチェックインしました！")
            st.markdown(f"🧪 経験値 +{gained_exp} EXP（現在 {new_exp} EXP）")

            if level_up:
                st.markdown(f"🌟 レベルアップ！ 新しいレベル：**{new_level}**")
            else:
                st.markdown(f"📊 現在のレベル：{new_level}")

            if level_up:
                st.balloons()  # 🎈 この1行をここに追加！
                st.markdown(f"🌟 レベルアップ！ 新しいレベル：**{new_level}**")
            else:                    
                st.markdown(f"📊 現在のレベル：{new_level}")

# --- 履歴表示 ---
if st.session_state.checkin_history:
    st.markdown("---")
    st.markdown("### 📚 チェックイン履歴")
    df_history = pd.DataFrame(st.session_state.checkin_history)
    st.dataframe(df_history)