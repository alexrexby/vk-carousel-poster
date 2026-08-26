#!/usr/bin/env python3
"""CLI-утилита для публикации каруселей во ВКонтакте."""

import argparse
import glob
import os
import sys
import time
from datetime import datetime, timedelta

from vk_carousel import VKCarouselPoster, VKAPIError


def load_env(env_path: str = ".env") -> dict:
    """Простая загрузка .env файла без сторонних библиотек."""
    config = {}
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                config[k.strip()] = v.strip().strip("'\"")
    return config


def main():
    parser = argparse.ArgumentParser(
        description="Автопостинг фото-каруселей во ВКонтакте (личная страница / группа)"
    )
    parser.add_argument(
        "--target",
        choices=["user", "group"],
        default="user",
        help="Куда публиковать: user (личная страница) или group (сообщество)",
    )
    parser.add_argument(
        "--group-id",
        type=int,
        help="ID сообщества без минуса (обязательно при --target group, если не указано в .env)",
    )
    parser.add_argument(
        "--token",
        help="VK User Access Token (если не указан, берется из .env или VK_ACCESS_TOKEN)",
    )
    parser.add_argument(
        "--images",
        nargs="+",
        help="Пути к изображениям (от 2 до 10 файлов, например: samples/*.png)",
    )
    parser.add_argument(
        "--folder",
        help="Папка с изображениями (будут взяты отсортированные файлы png/jpg)",
    )
    parser.add_argument(
        "--text",
        default="",
        help="Текст записи",
    )
    parser.add_argument(
        "--delay-minutes",
        type=int,
        default=0,
        help="Отложить публикацию на N минут вперед",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Проверить токен и права доступа без публикации",
    )

    args = parser.parse_args()

    # 1. Загрузка конфигурации из .env и аргументов
    env = load_env()
    token = args.token or os.environ.get("VK_ACCESS_TOKEN") or env.get("VK_ACCESS_TOKEN")
    group_id = args.group_id or os.environ.get("VK_GROUP_ID") or env.get("VK_GROUP_ID")

    if not token:
        print("❌ Ошибка: Не указан токен доступа VK!")
        print("💡 Получите токен на https://vkhost.github.io (выберите Kate Mobile)")
        print("   И укажите его в .env как VK_ACCESS_TOKEN=... или передайте через --token")
        sys.exit(1)

    poster = VKCarouselPoster(token)

    # Режим проверки
    if args.check:
        print("🔍 Проверка токена доступа...")
        try:
            user = poster.get_current_user()
            print(f"👤 Пользователь токена: {user.get('first_name')} {user.get('last_name')} (ID: {user.get('id')})")
            if group_id:
                grp = poster.get_group_info(int(group_id))
                print(f"👥 Сообщество: «{grp.get('name')}» (ID: {grp.get('id')})")
            print("✅ Токен валиден и готов к работе!")
        except VKAPIError as e:
            print(f"❌ Ошибка проверки токена: {e}")
            sys.exit(1)
        return

    # 2. Сбор изображений
    image_paths = []
    if args.images:
        # Раскрываем glob шаблоны, если переданы
        for item in args.images:
            matched = glob.glob(item)
            if matched:
                image_paths.extend(sorted(matched))
            elif os.path.exists(item):
                image_paths.append(item)
    elif args.folder:
        exts = ("*.png", "*.jpg", "*.jpeg", "*.PNG", "*.JPG", "*.JPEG")
        for ext in exts:
            image_paths.extend(glob.glob(os.path.join(args.folder, ext)))
        image_paths = sorted(list(set(image_paths)))
    else:
        # По умолчанию берем файлы из samples/
        sample_files = sorted(glob.glob("samples/*.png") + glob.glob("samples/*.jpg"))
        if sample_files:
            image_paths = sample_files[:6]

    if not (2 <= len(image_paths) <= 10):
        print(f"❌ Ошибка: Для карусели требуется от 2 до 10 изображений (найдено: {len(image_paths)})")
        print("Укажите файлы через --images file1.png file2.png или --folder path/to/slides")
        sys.exit(1)

    print(f"📦 Слайды для публикации ({len(image_paths)} шт.):")
    for idx, path in enumerate(image_paths, 1):
        print(f"   {idx}. {path}")

    # 3. Расчет времени отложки (если указано)
    publish_date = None
    if args.delay_minutes > 0:
        publish_date = int(time.time()) + (args.delay_minutes * 60)

    # 4. Публикация
    try:
        poster.post_carousel(
            image_paths=image_paths,
            message=args.text,
            target=args.target,
            group_id=int(group_id) if group_id else None,
            publish_date=publish_date,
        )
    except VKAPIError as e:
        print(f"\n❌ Ошибка VK API: {e}")
        if e.error_code == 15 or e.error_code == 1134:
            print("💡 Подсказка: ВК заблокировал wall.post, так как токен не является Standalone.")
            print("   Получите токен через https://vkhost.github.io выбрав 'Kate Mobile'.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
