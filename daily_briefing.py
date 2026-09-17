import os
import asyncio
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
import edge_tts
from google import genai
from google.genai import types

# 1. 環境變數設定
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GMAIL_USER = os.environ.get("GMAIL_USER")          # 您的 Gmail: lala850307@gmail.com
GMAIL_APP_PASS = os.environ.get("GMAIL_APP_PASS")  # 16 位 Gmail 應用程式密碼
GITHUB_USER = os.environ.get("GITHUB_REPOSITORY_OWNER")
GITHUB_REPO = os.environ.get("GITHUB_REPOSITORY", "/").split("/")[-1]

today_str = datetime.now().strftime("%Y/%m/%d")
audio_filename = "today_briefing.mp3"
audio_public_url = f"https://{GITHUB_USER}.github.io/{GITHUB_REPO}/{audio_filename}"

# 2. 使用 Gemini 生成五大模組晨報
def generate_briefing():
    client = genai.Client(api_key=GEMINI_API_KEY)
    prompt = f"""
    你是跨領域 AI 戰略與系統思維分析導師。請檢索過去 24-48 小時內真實發生的全球重大 AI 科技突破或交集時事（嚴禁虛構），
    挑選 1 則最能展現打破舊體系規則的深度議題，嚴格依據以下結構撰寫，不可使用任何 Emoji：

    # [AI 每日跨域破局分析] {today_str}：[核心時事主題]
    ## 1. 【時事事實錨點（The Pivot）】
    * 報導出處 / 訪談對象：
    * 核心事實摘錄：
    * 本質定義：
    ## 2. 【回溯過去（The Past: 該領域原本卡死在哪裡？）】
    * 傳統運作模式：
    * 結構性死結（The Bottleneck）：
    ## 3. 【立足現在（The Present: 破局切入點與連鎖效應）】
    * 實質破局路徑：
    * 生態系連鎖效應：
    ## 4. 【推演未來（The Future: 已知限制與下一道深水區）】
    * 報導指出的後續方向：
    * 客觀遭遇的下一個壁壘：
    ## 5. 【跨界思維遷移題（Strategic Judgment）】
    """
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())]
        )
    )
    if not response.text:
        raise RuntimeError("Gemini 未回傳任何內容（可能被安全過濾攔截或無搜尋結果）")
    return response.text

# 3. 使用 Edge-TTS 生成台灣中文語音
async def text_to_speech(text, output_file):
    # 使用台灣繁中自然女聲 (也可替換為男聲 zh-TW-YunJheNeural)
    voice = "zh-TW-HsiaoChenNeural"
    # 過濾掉 Markdown 符號使朗讀更順暢
    clean_text = text.replace("#", "").replace("*", "").replace("-", "")
    communicate = edge_tts.Communicate(clean_text, voice, rate="+5%")
    await communicate.save(output_file)

# 4. 發送包含真實播放按鈕的 HTML 郵件
def send_email(briefing_text):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"【AI 破局晨報】{today_str} (含即點即聽語音)"
    msg["From"] = GMAIL_USER
    msg["To"] = GMAIL_USER

    # 純文字 fallback
    text_part = MIMEText(f"語音收聽連結：{audio_public_url}\n\n{briefing_text}", "plain", "utf-8")
    msg.attach(text_part)

    # 格式化為 HTML
    html_content = f"""
    <div style="background-color: #0b1120; padding: 24px; font-family: sans-serif;">
      <!-- 深色語音播放卡片（綁定真實當日音檔） -->
      <div style="background-color: #0f172a; padding: 20px; border-radius: 12px; color: #ffffff; max-width: 680px; margin: 0 auto 24px auto;">
        <div style="margin-bottom: 12px;">
          <p style="font-size: 16px; font-weight: bold; margin: 0 0 6px 0;">今日 AI 晨報 (語音串流版)</p>
          <span style="font-size: 11px; color: #38bdf8; background: rgba(56,189,248,0.15); padding: 3px 8px; border-radius: 4px;">當日真人級神經語音 • 0 空間佔用</span>
        </div>
        <div style="background-color: #1e293b; border-radius: 8px; padding: 12px 16px;">
          <a href="{audio_public_url}" target="_blank" style="display: inline-block; background-color: #3b82f6; color: #ffffff; text-decoration: none; padding: 8px 18px; border-radius: 20px; font-size: 13px; font-weight: bold;">
            立即播放今日晨報
          </a>
          <span style="font-size: 12px; color: #94a3b8; margin-left: 12px;">點擊直接呼叫系統播放器收聽</span>
        </div>
      </div>

      <!-- 晨報本文 -->
      <div style="background-color: #ffffff; padding: 28px; border-radius: 12px; max-width: 680px; margin: 0 auto; color: #1e293b; line-height: 1.7; white-space: pre-wrap;">
{briefing_text}
      </div>
    </div>
    """
    html_part = MIMEText(html_content, "html", "utf-8")
    msg.attach(html_part)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASS)
        server.sendmail(GMAIL_USER, GMAIL_USER, msg.as_string())

if __name__ == "__main__":
    print("正在檢索與生成晨報...")
    briefing = generate_briefing()

    print("正在合成繁體中文語音 (Edge-TTS)...")
    asyncio.run(text_to_speech(briefing, audio_filename))

    print("正在發送電子郵件...")
    send_email(briefing)
    print("執行完畢！")
