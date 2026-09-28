import os
import asyncio
from threading import Thread
from config import TOKEN

import discord
from waitress import serve

# 自作モジュール
# botインスタンス読み込み
from bot import bot
import ranking
import messages_scan
# flask起動
from web_app import app


# bot落ち防止のためのuptimerobot用,起動に必要
port = int(os.environ.get("PORT", 8080))


def run():
    try:
        print(f"✅ Flaskサーバーを {port} ポートで起動")
        serve(app, host="0.0.0.0", port=port)
    except Exception as e:
        print("❌ Flaskサーバーエラー:", e)


def keep_alive():
    t = Thread(target=run)
    t.daemon = True
    t.start()


print("🔄 サーバーを定義完了")


# 実行部
async def main():
    async with bot:
        while True:
            try:
                await bot.start(TOKEN)
                break
            except discord.HTTPException as e:
                # ログイン時の429(CloudflareによるIP制限を含む)。
                # 落ちるとRenderが即再起動して試行が増えるので、プロセス内で長く待つ。
                if e.status == 429:
                    print("🚨 429: 15分待って再試行します")
                    await asyncio.sleep(900)
                else:
                    raise


# --- 実行セクション ---
if __name__ == "__main__":
    keep_alive()
    asyncio.run(main())
