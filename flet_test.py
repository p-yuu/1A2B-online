import flet as ft

def main(page: ft.Page):
    page.title = "1A2B 猜數字遊戲"
    page.theme_mode = ft.ThemeMode.DARK # 滿足黑底白字要求

    # 建立一個文字元件
    welcome_text = ft.Text("歡迎來到 1A2B 遊戲！", size=24, color="white")

    # 將元件加到畫面上
    page.add(welcome_text)

ft.app(target=main)