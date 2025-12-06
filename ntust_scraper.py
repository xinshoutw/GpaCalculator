import json
import re

import httpx
from bs4 import BeautifulSoup


class NtustGradeScraper:
    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.base_headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "zh-TW,zh;q=0.9",
            "Upgrade-Insecure-Requests": "1"
        }
        self.client = httpx.Client(
            headers=self.base_headers,
            verify=False,
            http2=True,
            follow_redirects=True,
            timeout=30.0
        )

        # 相關 URL 定義
        self.urls = {
            "entry": "https://stuinfosys.ntust.edu.tw/StuScoreQueryServ/StuScoreQuery",
            "sso_login": "https://ssoam.ntust.edu.tw/nidp/app/login?sid=0&sid=0",
            "grades_display": "https://stuinfosys.ntust.edu.tw/StuScoreQueryServ/StuScoreQuery/DisplayAll"
        }

    def login(self) -> bool:
        """
        執行登入流程，成功後 Client 內會包含有效的 .ASPXAUTH Cookie
        """
        try:
            # 1. 訪問入口，觸發 Redirect 到 SSO
            self.client.get(self.urls["entry"])

            # 2. 準備登入 Payload
            payload = {
                "option": "credential",
                "Ecom_User_ID": self.username,
                "Ecom_Password": self.password,
                "loginButton2": ""
            }

            # 3. 發送帳密到 SSO
            r_login = self.client.post(self.urls["sso_login"], data=payload)

            if r_login.status_code != 200:
                return False

            # 4. 解析 Javascript Redirect 網址
            match = re.search(r"window\.location\.href='([^']+)'", r_login.text)
            if not match:
                return False

            redirect_url = match.group(1)

            # 5. 訪問授權連結，這會自動 Redirect 回成績系統並設定 Cookie
            self.client.get(redirect_url)

            # 6. 檢查是否取得關鍵 Cookie
            if ".ASPXAUTH" in self.client.cookies:
                return True
            else:
                return False

        except Exception as e:
            return False

    def fetch_grades(self) -> list:
        """
        抓取並解析成績，回傳 list of dict
        """
        try:
            r = self.client.get(self.urls["grades_display"])
            r.raise_for_status()

            soup = BeautifulSoup(r.text, "html.parser")
            courses = []

            tables = soup.find_all("table")
            grade_table = None
            for table in tables:
                if "課程名稱" in table.get_text():
                    grade_table = table
                    break

            if not grade_table:
                # 若找不到表格，回傳空清單或拋出錯誤
                return []

            # 解析表格內容
            rows = grade_table.find_all("tr")
            for row in rows:
                cols = row.find_all("td")
                if len(cols) > 5:
                    semester = cols[1].get_text(strip=True)
                    course_id = cols[2].get_text(strip=True)
                    course_name = cols[3].get_text(strip=True)
                    credits = cols[4].get_text(strip=True)
                    grade = cols[5].get_text(strip=True)

                    if course_name:  # 確保有名稱
                        courses.append({
                            "semester": semester,
                            "course_id": course_id,
                            "course_name": course_name,
                            "credits": credits,
                            "grade": grade
                        })

            return courses

        except Exception as e:
            return []

    def close(self):
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        sys.exit("Usage: python ntust_scraper.py <username> <password>")
    else:
        USERNAME, PASSWORD = sys.argv[1:3]

    with NtustGradeScraper(USERNAME, PASSWORD) as scraper:
        if scraper.login():
            grades = scraper.fetch_grades()
            print(json.dumps(grades))
        else:
            print(json.dumps({"error": "Login failed"}, ensure_ascii=False))
