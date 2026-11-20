
import asyncio
import json
import logging
import os

from telethon import TelegramClient, errors, types
from telethon.tl.functions.payments import GetSavedStarGiftsRequest

from config import API_ID, API_HASH, SESSION_NAME


INPUT_FILE = "usernames.txt"
OUTPUT_FILE = "results.txt"
PROGRESS_FILE = "progress.json"

PAGE_SIZE = 100
DELAY = 1.5


logging.basicConfig(
    filename="scanner.log",
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    encoding="utf-8"
)


def load_usernames():
    if not os.path.exists(INPUT_FILE):
        raise FileNotFoundError(
            f"Не найден файл {INPUT_FILE}"
        )

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        usernames = [
            line.strip().lstrip("@")
            for line in f
            if line.strip()
        ]

    # Убираем дубликаты, сохраняя порядок
    return list(dict.fromkeys(usernames))


def load_progress():
    if not os.path.exists(PROGRESS_FILE):
        return {}

    try:
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_progress(progress):
    temp_file = PROGRESS_FILE + ".tmp"

    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=4)

    os.replace(temp_file, PROGRESS_FILE)


def save_results(progress):
    results = [
        (username, data["count"])
        for username, data in progress.items()
        if data.get("status") == "done"
        and data.get("count", 0) > 0
    ]

    # Сначала больше подарков, затем юзернейм
    results.sort(key=lambda x: (-x[1], x[0].lower()))

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for username, count in results:
            f.write(f"@{username} | NFT: {count}\n")


async def request_with_retry(client, request):
    while True:
        try:
            return await client(request)

        except errors.FloodWaitError as e:
            wait_time = e.seconds + 1

            print(
                f"\n[!] FloodWait: ожидание {wait_time} секунд"
            )

            await asyncio.sleep(wait_time)


async def count_nft_gifts(client, username):
    peer = await client.get_input_entity(username)

    offset = ""
    nft_count = 0

    while True:
        request = GetSavedStarGiftsRequest(
            peer=peer,
            offset=offset,
            limit=PAGE_SIZE,
            exclude_hosted=True
        )

        response = await request_with_retry(client, request)

        for saved_gift in response.gifts:
            gift = getattr(saved_gift, "gift", None)

            if isinstance(gift, types.StarGiftUnique):
                nft_count += 1

        next_offset = getattr(response, "next_offset", None)

        if not next_offset:
            break

        offset = next_offset

    return nft_count


async def main():
    usernames = load_usernames()
    progress = load_progress()

    total = len(usernames)

    if not usernames:
        print("Список usernames.txt пуст!")
        return

    print("=" * 45)
    print("       TELEGRAM NFT SCANNER")
    print("=" * 45)

    completed = sum(
        1 for u in usernames
        if progress.get(u, {}).get("status") == "done"
    )

    print(f"Всего аккаунтов: {total}")
    print(f"Уже проверено: {completed}")
    print(f"Осталось: {total - completed}")
    print("=" * 45)

    async with TelegramClient(
        SESSION_NAME,
        API_ID,
        API_HASH
    ) as client:

        for index, username in enumerate(usernames, 1):

            if progress.get(username, {}).get("status") == "done":
                continue

            print(
                f"\n[{index}/{total}] Проверка @{username}"
            )

            try:
                count = await count_nft_gifts(
                    client,
                    username
                )

                progress[username] = {
                    "status": "done",
                    "count": count
                }

                if count > 0:
                    print(f"[+] Найдено NFT: {count}")
                else:
                    print("[-] Коллекционных подарков не найдено")

                logging.info(
                    "%s | NFT: %s",
                    username,
                    count
                )

            except errors.FloodWaitError as e:
                # При ограничении на разрешение аккаунта
                # сохраняем прогресс и прекращаем запуск.
                print(
                    f"[!] FloodWait при обработке @{username}: "
                    f"{e.seconds} секунд"
                )
                logging.warning(
                    "FloodWait при обработке %s",
                    username
                )
                break

            except errors.RPCError as e:
                print(f"[!] Telegram API: {username}: {e}")
                logging.warning("%s | %s", username, e)

                progress[username] = {
                    "status": "error",
                    "count": 0
                }

            except Exception as e:
                print(f"[!] Ошибка @{username}: {e}")
                logging.exception("Ошибка обработки %s", username)

                progress[username] = {
                    "status": "error",
                    "count": 0
                }

            finally:
                save_progress(progress)
                save_results(progress)

            await asyncio.sleep(DELAY)

    print("\n" + "=" * 45)
    print("ПРОВЕРКА ЗАВЕРШЕНА")
    print("=" * 45)

    found = sum(
        1 for data in progress.values()
        if data.get("status") == "done"
        and data.get("count", 0) > 0
    )

    print(f"Аккаунтов с NFT: {found}")
    print(f"Результат: {OUTPUT_FILE}")
    print(f"Прогресс: {PROGRESS_FILE}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nОстановка сканера.")
        print("Ранее сохранённые результаты остались на диске.")
