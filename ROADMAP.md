# AutoPassWiFi 未來發展藍圖 (Roadmap)

此文件記錄了 AutoPassWiFi 適合拓展與升級的新功能提案，分為四個主要維度。

## 1. 強化認證能力與安全性 (Authentication & Security)

*   **整合作業系統的密碼管理員 (Credential Manager Integration)**
    *   **目標**：解決目前以明文記錄於 JSON 檔案中的密碼安全問題。
    *   **實作方向**：整合 Windows Credential Manager (例如使用 `keyring` 套件)。遇到需要帳號密碼的 Portal（如 eduroam 或企業網路），將密碼加密儲存於系統憑證庫，重播時動態注入。
*   **光學字元辨識 (OCR) 與簡單驗證碼自動化**
    *   **目標**：減少因驗證碼 (Captcha) 而中斷自動化，被迫轉為互動模式的情況。
    *   **實作方向**：整合輕量級的 OCR 引擎（如 Tesseract）或透過 API。當辨識到簡單圖形驗證碼時，自動截圖並進行文字辨識填寫。

## 2. 跨平台與社群共享 (Cross-Platform & Community)

*   **跨平台支援 (macOS / Linux)**
    *   **目標**：打破目前僅限 Windows 系統的限制。
    *   **實作方向**：採用抽象工廠模式 (Abstract Factory Pattern)，將底層的 `connection_monitor.py` 抽離。為 macOS 實作 `CoreWLAN` 監聽，為 Linux 實作 `NetworkManager` (`DBus`) 監聽。
*   **社群共享設定檔 (Crowdsourced Profiles)**
    *   **目標**：實現「一人示範，萬人乘涼」，讓使用者不需要每次遇到新 Portal 都親自手動教學。
    *   **實作方向**：建立輕量雲端資料庫。使用者可匿名上傳特定 SSID 的解析腳本（過濾敏感資訊）。連上未知 SSID 時，優先從雲端拉取社群貢獻的腳本執行。

## 3. 進階網路管理 (Advanced Networking)

*   **自動更換 MAC 位址 (MAC Address Spoofing)**
    *   **目標**：突破公共 Wi-Fi 常見的「每日免費使用時數限制」。
    *   **實作方向**：當偵測到免費時數耗盡被踢下線時，背景自動隨機產生並修改網卡的 MAC 位址，接著觸發重新連線與自動登入，實現無縫的無限上網。
*   **連線品質監控與智能切換 (Smart Roaming)**
    *   **目標**：避免連上訊號極差或無實際頻寬的「假」免費 Wi-Fi。
    *   **實作方向**：在背景定期進行小型 Ping 測試或頻寬測速。若判定品質低於閾值，自動將該 SSID 列入暫時黑名單並斷開連線，切回行動網路或其他穩定的 Wi-Fi。

## 4. 使用者體驗 (User Experience)

*   **本地端管理介面 (Local Web Dashboard)**
    *   **目標**：提供比純文字 JSON 更直觀的設定與歷史檢視方式。
    *   **實作方向**：內建輕量級的 HTTP 伺服器 (如 FastAPI) 或前端 GUI (Tkinter/PyQt)。透過 System Tray 開啟網頁介面，讓使用者可以輕鬆地刪除過期的腳本設定檔、檢視成功登入的次數與網路狀態紀錄。
