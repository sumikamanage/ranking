import asyncio

import discord


# ===============================
# ログ送信用キュー(send_log / on_message のエラー通知が使う)
# ===============================
async def api_worker(bot):
    while True:
        coro = await bot.api_queue.get()

        try:
            await coro

        except discord.HTTPException as e:

            if e.status == 429:
                retry = getattr(e, "retry_after", 10)
                print(f"🚨 429検知 {retry:.2f}秒待機")
                await asyncio.sleep(retry)
            else:
                print(e)
                await asyncio.sleep(5)

        except Exception as e:
            print("API Worker Error:", e)

        finally:
            bot.api_queue.task_done()

            # ログチャンネルへの送信は 5件/5秒 程度が上限なので余裕を持たせる
            await asyncio.sleep(1.1)
