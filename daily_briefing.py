import os
import re
import asyncio
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
import edge_tts
import markdown
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

# 1. 環境變數設定
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GMAIL_USER = os.environ.get("GMAIL_USER")          # 您的 Gmail: lala850307@gmail.com
GMAIL_APP_PASS = os.environ.get("GMAIL_APP_PASS")  # 16 位 Gmail 應用程式密碼
GITHUB_USER = os.environ.get("GITHUB_REPOSITORY_OWNER")
GITHUB_REPO = os.environ.get("GITHUB_REPOSITORY", "/").split("/")[-1]

today_str = datetime.now().strftime("%Y/%m/%d")
# 檔名帶時間戳記，確保每次執行的音檔都是獨立檔案，不會被下一次執行覆蓋掉
# （避免舊信件裡的播放連結，日後點開卻播到別次執行的內容）
audio_filename = f"briefing_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp3"
audio_public_url = f"https://{GITHUB_USER}.github.io/{GITHUB_REPO}/{audio_filename}"

# 2. 使用 Gemini 生成五大模組晨報
def generate_briefing():
    client = genai.Client(api_key=GEMINI_API_KEY)
    prompt = f"""
    你是跨領域 AI 戰略與系統思維分析導師。請檢索過去 24-48 小時內真實發生的全球重大 AI 科技突破或交集時事（嚴禁虛構），
    挑選 1 則最能展現打破舊體系規則的深度議題，嚴格依據以下結構撰寫，不可使用任何 Emoji：

    # [AI 每日跨域破局分析] {today_str}：[核心時事主題]
    ## 1. 最新即時新聞
    * **消息來源**：
    * **事件摘要**：
    * **深層意義**：
    ## 2. 過去
    * **過去做法**：
    * **核心困境**：
    ## 3. 現在
    * **突破方式**：
    * **影響層面**：
    ## 4. 未來
    * **後續發展**：
    * **未解難題**：
    ## 5. 延伸思考
    * **思考題**：
    ## 6. 每日英文單字
    請從本文內容中挑選 3-5 個關鍵英文術語（例如 misalignment、jailbreaking、agent swarm 這類報導中會出現的專業詞彙），依此格式條列：
    * **英文術語**（中文翻譯）：一句話白話解釋
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

# 3. 把完整分析文字轉換成口語化語音稿（只保留 1~4 段，第 5 段是留給讀者思考用的不唸）
def build_audio_script(text):
    body = re.split(r"##\s*5\.", text, maxsplit=1)[0]
    body = re.sub(r"^#+\s*", "", body, flags=re.MULTILINE)
    return body.replace("*", "").replace("-", "")

# 4. 使用 Edge-TTS 生成語音
#    （曾嘗試中英文分段切換不同語音，語氣不連貫、切換處會頓一下，聽感差，改用單一多語言語音模型，
#     同一個模型直接處理中英混合文字，英文發音清楚又不會有語氣斷層；中文腔調待實際試聽確認）
VOICE = "en-US-AvaMultilingualNeural"

async def synthesize_once(text, voice, output_file):
    communicate = edge_tts.Communicate(text, voice, rate="+5%")
    await communicate.save(output_file)

async def text_to_speech(text, output_file, retries=3):
    for attempt in range(retries):
        try:
            await synthesize_once(text, VOICE, output_file)
            return
        except edge_tts.exceptions.NoAudioReceived:
            if attempt == retries - 1:
                raise
            await asyncio.sleep(1 + attempt)  # 逐次拉長等待時間再重試

# 5. Gmail 會過濾信件內文中的 <style> 區塊，樣式一律改成內嵌 style=""
EMAIL_TAG_STYLES = {
    "<h1>": '<h1 style="font-size:22px;font-weight:700;color:#0f172a;border-bottom:1px solid #e2e8f0;padding-bottom:12px;margin:0 0 20px 0;">',
    "<h2>": '<h2 style="font-size:17px;font-weight:700;color:#2563eb;border-left:4px solid #2563eb;padding-left:10px;margin:24px 0 12px 0;">',
    "<ul>": '<ul style="padding-left:22px;margin:8px 0;">',
    "<ol>": '<ol style="padding-left:22px;margin:8px 0;">',
    "<li>": '<li style="margin-bottom:6px;">',
    "<strong>": '<strong style="color:#0f172a;">',
}

def inline_email_styles(html):
    for tag, styled_tag in EMAIL_TAG_STYLES.items():
        html = html.replace(tag, styled_tag)
    return html

# 6. 發送包含真實播放按鈕的 HTML 郵件
def send_email(briefing_text):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"『每日AI晨報』 {today_str}"
    msg["From"] = GMAIL_USER
    msg["To"] = GMAIL_USER

    # 純文字 fallback
    text_part = MIMEText(f"語音收聽連結：{audio_public_url}\n\n{briefing_text}", "plain", "utf-8")
    msg.attach(text_part)

    # 把 Gemini 產出的 Markdown 轉成真正的 HTML（標題、粗體、清單）
    briefing_html = markdown.markdown(briefing_text, extensions=["extra"])
    briefing_html = inline_email_styles(briefing_html)

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
      <div style="background-color: #ffffff; padding: 28px; border-radius: 12px; max-width: 680px; margin: 0 auto; color: #1e293b; line-height: 1.8;">
        {briefing_html}
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
    audio_script = build_audio_script(briefing)
    asyncio.run(text_to_speech(audio_script, audio_filename))

    print("正在發送電子郵件...")
    send_email(briefing)
    print("執行完畢！")
