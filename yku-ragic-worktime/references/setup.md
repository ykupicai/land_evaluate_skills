# Chrome 免登入常駐設定與每月排程（一次性環境設定）

## Chrome 免登入常駐

靠**保持已登入的 session**，不是自動打密碼（密碼/登入是紅線，Claude 不做）。

- 捷徑 `開Ragic工時(已登入).lnk`（專案根＋Windows 啟動資料夾各一份）：
  `chrome.exe --profile-directory="Default" https://ap13.ragic.com/YKU/invoice-form/6`
  用 **Default** 設定檔（Claude 擴充與登入 session 都在這）。開機自動開好、停在 Ragic。
- 一次性（本人做）：登入時勾「**在這台電腦記得我**」延長 session；過期才手動登入一次。
- 連線：`list_connected_browsers` → 若空，跑捷徑把 Chrome 開起來等幾秒再試；
  `select_browser` 選 device "yku" → `navigate` 到草稿 → 操作。
- 取消開機自動開：刪 `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\開Ragic工時(已登入).lnk`。

## 排程（每月最後工作日自動建草稿）

`ragic_reminder.ps1`（Windows 排程「Ragic工時提醒」每天 09:00 跑，僅最後工作日動作）：
跑 `ragic_fill_api.py <當月> --auto` 建表頭+比例草稿、開表單+通知，提醒本人到 UI 完成 UI 段與簽核。
`.ps1` 需存成 **UTF-8 BOM**（否則 PowerShell 5.1 讀中文會壞）。
