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
def add_records(place,exp,spell):
    data= {
        "place":place,
        "exp":exp,
        "spell":spell
    }
    response = supabase.table("records").insert(data).execute()
    return response


##shopDBからmoodとtimeのカラムを参照して該当のデータを引っ張ってくる
def search_shops(mood,time):
    response = supabase.table("place").select("*").eq("mood", mood).eq("time", time).execute()
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
    found_records=search_records(spell,place)
    number_of_records = len(found_records)
    if number_of_records >3:
        exp =5
    else:
        exp = 20-5*(number_of_records)
    return exp



##########################################################################################
# 音楽ファイルを base64 に変換
def get_audio_base64(file_path):
    with open(file_path, "rb") as f:
        data = f.read()
    return base64.b64encode(data).decode()

# 再生ボタンだけのHTMLを構築
audio_base64 = get_audio_base64("bgm1.mp3")
audio_html = f"""
<audio id="bgm" src="data:audio/mp3;base64,{audio_base64}"></audio>
<button onclick="document.getElementById('bgm').play()" style="font-size:18px; padding:5px 15px;">▶️ BGM再生</button>
"""
components.html(audio_html, height=50)

# --- 仮のデータベース（ふっかつのじゅもん） ---
spell_db = {
    "ほいみ": {"level": 5, "exp": 5},#LVと経験値が正しく表示される。ユーザーの識別はできていない。
    "ぱるぷんて": {"level": 5, "exp": 72},
    "べホイミ": {"level": 8, "exp": 3}
}

# --- セッションステート初期化 ---
def init_state():
    st.session_state.setdefault("activated_spell", None)
    st.session_state.setdefault("user_data", None)
    st.session_state.setdefault("selected_time", None)
    st.session_state.setdefault("selected_mood", None)
    st.session_state.setdefault("selected_location", None)
    st.session_state.setdefault("selected_place", None)
    st.session_state.setdefault("place_chosen", False)
    st.session_state.setdefault("checkin_done", False)
    st.session_state.setdefault("checkin_history", [])

init_state()

############################################################削除して良さそう############################################################
# --- 仮の候補地DB（緯度・経度含む） ---
# def get_candidate_places_from_db():
#     return pd.DataFrame([
#         {"name": names, "lat": lat, "lon": lon},#データベースからかmood：カフェ、時間；30で直接指定したDBの結果が表示される。
#         {"name": "キャナルシティ", "lat": 33.5896, "lon": 130.4119},
#         {"name": "天神地下街", "lat": 33.5903, "lon": 130.4017},
#         {"name": "中洲のスパ", "lat": 33.5931, "lon": 130.4094},
#         {"name": "リバーウォーク", "lat": 33.8859, "lon": 130.8753},
#     ])
########################################################################################################################
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


# --- タイトルと説明 ---
st.title("テック勇者リョヤカアプリ")
st.caption("テック勇者リョヤカアプリは、あなたの質問に答えるためのアプリです。")

# --- ふっかつのじゅもん入力 ---
st.markdown("### ふっかつのじゅもん")
spell = st.text_input(" ", placeholder="じゅもんを入力してください", label_visibility="collapsed")

if st.button("唱える"):
    if spell in spell_db:
        st.session_state.activated_spell = spell
        st.session_state.user_data = spell_db[spell]
        st.success(f"『{spell}』勇者は　めをさました！")
    else:
        st.session_state.activated_spell = None
        st.session_state.user_data = None
        st.error("その　じゅもんは　まちがっております")

# --- 呪文が唱えられた後の処理 ---
if st.session_state.activated_spell and st.session_state.user_data:
    data = st.session_state.user_data
    col1, col2 = st.columns([1, 2])
    with col1:
        image = Image.open("yu-sya_image2.png")
        st.image(image, width=200)
    with col2:
        total_exp =exp_sum(spell)
        now_lv= total_exp//100
        last_exp=100-(total_exp%100)

        st.markdown(f"### レベル：{now_lv}")
        st.markdown(f"レベルアップまであと **{last_exp} EXP**")
        st.markdown("🗺️ 新しい冒険に出発しよう！")

    st.markdown("---")
    st.markdown("### 🕒 冒険の時間")
    time_choice = st.radio("時間を選んでください", ["30分", "60分", "120分"], horizontal=True, label_visibility="collapsed")

    st.markdown("### 🎭 冒険の気分")
    mood_choice = st.radio("気分を選んでください", ["カフェ", "リラクゼーション", "エンタメ", "ショッピング"], horizontal=True, label_visibility="collapsed")

    st.markdown("### 🏘️ 旅立ちの村")
    location_choice = st.radio("出発地を選んでください", ["博多駅", "天神駅", "中洲川端駅"], horizontal=True, label_visibility="collapsed")

    if st.button("🚀 冒険に出る"):
        with st.spinner("冒険先を探索中..."):
            time.sleep(1.5)
        st.session_state.selected_time = time_choice###時間
        st.session_state.selected_mood = mood_choice###ムード
        st.session_state.selected_location = location_choice
        st.session_state.place_chosen = False
        st.session_state.checkin_done = False
        ##shopDBからsearch_shopを使って店名を抽出する。
    
    search_mood = mood_choice # 検索したい場所
    search_time = 30
    # found_records = pd.DataFrame(search_shops(search_mood,search_time))
    # names = found_records["name"].values[0]
    # url =  found_records['url'].values[0]
    # lat =  found_records['lat'].values[0]
    # lon =  found_records['lon'].values[0]

# --- 候補地表示 ---
if st.session_state.selected_time and not st.session_state.checkin_done:
    df_places = pd.DataFrame(search_shops(search_mood,search_time)) 

    st.markdown("### 🌟 目的地候補とAIコメント")
    for i, row in df_places.iterrows():
        place = row["name"]
        st.markdown(f"**🏞️ {place}**")
        st.info(get_ai_recommendation(place))

    st.markdown("### ✅ 上から目的地を選んでください")
    selected_place = st.radio("目的地を選択", df_places["name"].tolist(), key="selected_place", label_visibility="collapsed")

    if selected_place:
        st.session_state.place_chosen = True
        st.markdown("🏃 がんばって目的地までいこう！")

        selected_df = df_places[df_places["name"] == selected_place]
        st.pydeck_chart(pdk.Deck(
            map_style='mapbox://styles/mapbox/streets-v12',
            initial_view_state=pdk.ViewState(
                latitude=float(selected_df["lat"].values[0]),
                longitude=float(selected_df["lon"].values[0]),
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
            #経験値が100溜まるとレベルが貯まる。100-余りで残りの経験値を算出する。
            get_exp=calc_exp(selected_place)#チェックインした店の名前から獲得経験値を計算
            add_records(selected_place,get_exp,spell)#recordsにチェックインで選んだ店名,経験値,ふっかつの呪文を入れる
            update_now_lv= exp_sum(spell)//100#チェックインした後の更新したレベルを計算
            last_exp=(total_exp%100)#チェックインした後の更新した経験値を計算
            
            st.markdown(f"🧪 経験値 +{get_exp} EXP（現在の経験値 {last_exp} EXP）")####DBを参照して、チェックイン後のレベルを表示する

            # if level_up:
            #     st.markdown(f"🌟 レベルアップ！ 新しいレベル：**{new_level}**")
            # else:
            #     st.markdown(f"📊 現在のレベル：{now_lv}")####DBを参照して、チェックイン後のレベルを表示する

            if now_lv == update_now_lv: # ふっかつのじゅもんを唱えた時と、チェックインをした後のレベルが違ったらレベルアップ
                st.markdown(f"📊 現在のレベル：{update_now_lv}")
                
            else:                    
                st.balloons()  # 🎈 この1行をここに追加！
                st.markdown(f"🌟 レベルアップ！ 新しいレベル：**{update_now_lv}**")

# --- 履歴表示 ---
if st.session_state.checkin_history:
    st.markdown("---")
    st.markdown("### 📚 チェックイン履歴")
    df_history = pd.DataFrame(get_records (spell))
    st.dataframe(df_history[["created_at","place"]])