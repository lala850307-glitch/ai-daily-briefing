import os
import re
import asyncio
import smtplib
import tempfile
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
audio_filename = "today_briefing.mp3"
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

# 4. 使用 Edge-TTS 生成語音：中英文分段用各自語言的語音合成再接起來，
#    英文專有名詞（OpenAI、GPT-6 等）才不會被台灣腔語音唸得不清楚
ZH_VOICE = "zh-TW-HsiaoChenNeural"  # 台灣繁中自然女聲 (也可替換為男聲 zh-TW-YunJheNeural)
EN_VOICE = "en-US-JennyNeural"

def split_language_segments(text):
    pattern = re.compile(r"[A-Za-z][A-Za-z0-9\-]*(?:[ \t]+[A-Za-z][A-Za-z0-9\-]*)*")
    segments = []
    last_end = 0
    for m in pattern.finditer(text):
        if m.start() > last_end:
            segments.append((ZH_VOICE, text[last_end:m.start()]))
        segments.append((EN_VOICE, m.group()))
        last_end = m.end()
    if last_end < len(text):
        segments.append((ZH_VOICE, text[last_end:]))
    return [(voice, seg) for voice, seg in segments if seg.strip()]

async def text_to_speech(text, output_file):
    segments = split_language_segments(text)
    audio_bytes = bytearray()
    for voice, segment_text in segments:
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = tmp.name
        communicate = edge_tts.Communicate(segment_text, voice, rate="+5%")
        await communicate.save(tmp_path)
        with open(tmp_path, "rb") as f:
            audio_bytes += f.read()
        os.remove(tmp_path)
    with open(output_file, "wb") as f:
        f.write(audio_bytes)

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
