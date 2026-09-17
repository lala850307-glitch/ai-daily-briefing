# ai-daily-briefing

每天早上 08:00（台灣時間）自動產生一份 AI 跨域時事晨報，寄到 Gmail，信件裡同時有文字內容與可直接播放的語音檔連結。

## 流程

1. **GitHub Actions**（`.github/workflows/daily.yml`）依排程觸發，也可以手動執行
2. **Gemini API**（含 Google Search grounding）檢索近 24-48 小時的真實 AI 時事並產生分析文字
3. **edge-tts** 將文字合成為台灣繁中語音（`zh-TW-HsiaoChenNeural`）
4. 語音檔 commit 回 repo，透過 **GitHub Pages** 取得公開播放連結
5. 用 Gmail SMTP 寄出信件，內含文字全文與語音播放連結

全部使用免費額度，沒有付費服務。

## 設定步驟

1. **啟用 GitHub Pages**
   Settings → Pages → Source 選 `Deploy from a branch`，分支選 `main`

2. **新增 Secrets**（Settings → Secrets and variables → Actions）
   - `GEMINI_API_KEY`：Google AI Studio 申請的 API Key
   - `GMAIL_USER`：寄件與收件用的 Gmail 帳號
   - `GMAIL_APP_PASS`：Google 帳戶「安全性」頁面產生的應用程式密碼（16 碼）

3. **手動測試**
   Actions 頁籤 → 選擇 workflow → `Run workflow`

## 本機開發

`.env` 用於本機測試環境變數，已加入 `.gitignore`，不會被提交。

```
pip install google-genai edge-tts python-dotenv markdown
python daily_briefing.py
```
