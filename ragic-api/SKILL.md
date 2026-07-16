---
name: ragic-api
description: 用程式(HTTP API)讀寫 Ragic 資料庫的完整實戰知識:讀取資料、不需設計權限就找出欄位編號、寫入含子表格的資料、doFormula 重算公式、附件上傳、刪除、以及「guest account / access right」權限錯誤的診斷。凡是要用 API 或寫程式對 Ragic 做任何事——讀資料、建單、查欄位編號、撈選單選項、做自動化機器人或排程寫入、診斷 Ragic API 錯誤——都務必先用此 skill,即使使用者只說「幫我把資料寫進 Ragic」「Ragic 欄位編號是多少」也適用。(用瀏覽器操作 Ragic 網頁則不適用,請用 yku-ragic-worktime 等瀏覽器類 skill。)
---

# Ragic HTTP API 實戰指南

以下全部是 2026/06 在真實環境(ap13.ragic.com/YKU)實測驗證過的行為,不是猜測。
本公司(衍古)的表單位置、欄位編號、既有工具,見 [references/yku-ragic.md](references/yku-ragic.md)——
**處理衍古的 Ragic 時先讀它**,通常欄位編號已經查好了,不必重查。

## 基本事實

- 端點:`https://{server}/{帳號}/{頁籤路徑}/{表單編號}`,加 query `?api&v=3`
  (例:`https://ap13.ragic.com/YKU/invoice-form/1?api&v=3`)
- 認證:HTTP header `Authorization: Basic {API金鑰}`——金鑰本身就是整個 credential,
  **不要**再做 base64(它已經是編碼過的形態)。
- 日期格式一律 `yyyy/MM/dd`。
- 回應是 JSON;建立/更新成功時 `status == "SUCCESS"`,失敗有 `status: INVALID/ERROR` 與 `msg`。

## 讀取資料

- `GET {端點}?api&v=3` 整張表;`GET {端點}/{ragicId}?api&v=3` 單筆。
- **讀取回應的鍵是「欄位名稱」,永遠拿不到數字欄位編號**(v=1、v=3、info=true 都一樣)。
- 子表格出現在 `_subtable_<群組編號>` 鍵下,一列一個 dict。
- 系統欄位以底線開頭:`_ragicId`、`_create_user`(建立者)、`_create_date`、`_subtable_*`。
- 回傳筆數受「該金鑰使用者的檢視權限」限制——一般使用者的金鑰只看得到自己的資料,
  管理者金鑰看得到全部。**讀得到幾筆是判斷金鑰權限的好線索。**

## 找欄位編號(關鍵技巧,不需「修改設計」權限)

寫入必須用數字欄位編號(欄位名稱無效,會被默默忽略然後報「必填欄位未填」)。
但讀取 API 拿不到編號。實測唯一可靠的 API 做法:

**對既有一筆資料送「空更新」,回應會以欄位編號為鍵回傳整筆:**

```python
r = requests.post(f"{BASE}/{某筆ragicId}", headers=H,
                  params={"api": "", "v": "3"}, json={}, timeout=60)
# r.json()["data"] 的鍵就是欄位編號,值是該筆現值 → 用已知值反查名稱↔編號對照
```

- 空 body `{}` 不會改任何欄位值,但會更新該筆的「最後修改時間」——挑一筆不敏感的資料做。
- 子表格群組編號也會在回應裡(`_subtable_1000110` 這種鍵)。
- 替代方案:F12 看表單 HTML、Data Dictionary(需 Professional 方案)、建一筆測試再刪。
  空更新法最乾淨,優先用。

## 寫入(建立資料)

- `POST {端點}?api&v=3`,JSON body,鍵=欄位編號字串。
- **子表格**:`{"_subtable_<群組編號>": {"-1": {欄位編號: 值}, "-2": {...}}}`
  ——負數是「新列暫時編號」,一列一個負數(-1、-2…)。
- **`&doFormula=true`**:建立時重算所有公式欄位(總計、連動欄位…)。不加的話公式欄位是空的。
  副作用:該頁的 JavaScript 工作流程腳本不會跑(官方防無限迴圈)。
- 必填欄位缺漏 → `status: INVALID`,`msg` 會**列出全部缺的欄位名稱**——這也是探索
  「哪些欄位必填」的好方法(故意送空 payload 看 msg)。
- 選單欄位實測接受自由文字(不會擋未知選項),但值要跟現有慣例一致;
  **撈該欄位實際用過的值**:GET 整張表,對該欄位做 Counter 統計。
- 連結欄位(link to 其他表單,例:專案名稱)**只吃完全正確的值**,送錯會被默默清空 → 寫入前先比對成正確全名。
- UI 的「選某連結值自動帶出其他欄位」(link-and-load,例:選專案自動帶接案團隊)是**網頁互動才觸發,
  API 建單不會觸發**,doFormula 也不做這件事 → 那些連動欄位要自己查出來源值後主動送。
- 自動產生欄位(單號等)會出現在建立回應的 `data`(以編號為鍵)→ 可直接讀回給使用者。

## 附件上傳

檔案/圖片欄位**只能用 multipart/form-data**(不能 JSON):一般欄位當 form field、
子表格欄位用平面鍵 `"<欄位編號>_-1"`、檔案當 file part。

```python
r = requests.post(BASE, headers=H, params={"api": "", "v": "3"},
                  data={"1000123": "一般欄位值",        # 一般欄位:form field
                        "1000456_-1": "子表格欄位值"},   # 子表格:平面鍵 <欄位編號>_-1
                  files={"1000789": open("附件.pdf", "rb")},  # 檔案欄位:file part
                  timeout=60)
# 注意:用 data=/files= 而非 json=,requests 才會送 multipart;headers 不要自己設 Content-Type
```

## 刪除

`DELETE {端點}/{ragicId}?api`,成功回 200。測試資料建完記得刪。

## 權限與「guest account」錯誤(重要陷阱)

錯誤訊息 `This sheet is access right protected ... You are currently accessing as: guest account`
代表**這把金鑰對該表單沒有「API 寫入」權限**。實測重點:

- **讀寫權限是分開的**:同一把金鑰可以 GET 成功(讀得到自己資料)、POST 卻被當 guest。
- 一般使用者能在 Ragic 網頁建單 ≠ 他的 API 金鑰能建單;API 寫入權要管理者另外開。
- 跟 doFormula 無關(實測有無都一樣失敗)。
- 根治:請管理者開該使用者在該表單的 API 寫入權。在此之前,程式有兩種策略,看需求選:
  - **退共用金鑰**:被擋就改用有完整權限的共用金鑰重試。優點:同仁馬上能用;
    缺點:系統「建立者」變成共用金鑰的帳號,該帳號(常是管理者)會看得到這筆
    (可能違反「各人資料獨立」的檢視權限);「申請人」等表單欄位不受影響。
  - **擋下不退**(保護共用帳號):被擋就回「請聯絡管理者開通 API 寫入權」,在開通前不建單,
    絕不會有別人的資料掛到共用帳號名下。優點:不洩漏;缺點:同仁要等開通才能用。

## Windows 上探查 Ragic 的編碼雷

- PowerShell 主控台印中文常變亂碼/cp950 錯誤:跑 Python 前設 `$env:PYTHONIOENCODING='utf-8'`,
  或把結果寫進 UTF-8 檔案再用 Read 工具讀。
- 探查用的一次性腳本寫完即刪,別留含真實資料的暫存檔。
