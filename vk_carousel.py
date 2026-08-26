"""Модуль для публикации фото-каруселей во ВКонтакте (VK API)."""

import json
import mimetypes
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import List, Optional, Dict, Any


class VKAPIError(Exception):
    """Исключение при ошибках VK API."""
    def __init__(self, message: str, error_code: Optional[int] = None, raw_response: Optional[dict] = None):
        super().__init__(message)
        self.error_code = error_code
        self.raw_response = raw_response


class VKCarouselPoster:
    API_URL = "https://api.vk.com/method/"
    API_VERSION = "5.199"

    def __init__(self, access_token: str):
        if not access_token:
            raise ValueError("Требуется VK Access Token (получите на vkhost.github.io)")
        self.access_token = access_token.strip()

    def _api_call(self, method: str, params: Dict[str, Any], timeout: int = 30) -> dict:
        """Вызов метода VK API."""
        url = f"{self.API_URL}{method}"
        payload = {
            "v": self.API_VERSION,
            "access_token": self.access_token,
            **params
        }
        data = urllib.parse.urlencode(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data)

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                result = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise VKAPIError(f"HTTP ошибка сети: {e.code} ({e.reason})")
        except Exception as e:
            raise VKAPIError(f"Сетевой сбой при вызове {method}: {e}")

        if "error" in result:
            err = result["error"]
            code = err.get("error_code")
            msg = err.get("error_msg", "Неизвестная ошибка")
            raise VKAPIError(f"VK API Error [{code}]: {msg}", error_code=code, raw_response=err)

        return result.get("response")

    def _upload_file_multipart(self, upload_url: str, file_path: str, timeout: int = 60) -> dict:
        """Загрузка файла методом multipart/form-data на upload_url."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Файл не найден: {file_path}")

        boundary = f"----WebKitFormBoundary{uuid.uuid4().hex[:16]}"
        filename = os.path.basename(file_path)
        mime_type, _ = mimetypes.guess_type(file_path)
        mime_type = mime_type or "image/png"

        with open(file_path, "rb") as f:
            file_bytes = f.read()

        # Формирование multipart тела
        body = bytearray()
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(
            f'Content-Disposition: form-data; name="photo"; filename="{filename}"\r\n'.encode("utf-8")
        )
        body.extend(f"Content-Type: {mime_type}\r\n\r\n".encode("utf-8"))
        body.extend(file_bytes)
        body.extend(f"\r\n--{boundary}--\r\n".encode("utf-8"))
        payload_data = bytes(body)

        req = urllib.request.Request(
            upload_url,
            data=payload_data,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Content-Length": str(len(payload_data)),
                "User-Agent": "VKAndroidApp/8.0 (Android 12; SDK 31; arm64-v8a; Xiaomi Redmi Note 10; ru)",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw_resp = resp.read().decode("utf-8")
                res = json.loads(raw_resp)
                if not res.get("photo") or res.get("photo") == "[]":
                    # Если upload server вернул пустой результат photo
                    raise VKAPIError(f"Сервер загрузки вернул пустой результат: {raw_resp}")
                return res
        except Exception as e:
            if isinstance(e, VKAPIError):
                raise
            raise VKAPIError(f"Не удалось загрузить фото на сервер ВК: {e}")

    def get_current_user(self) -> dict:
        """Получить информацию о текущем пользователе токена."""
        users = self._api_call("users.get", {"fields": "screen_name"})
        if users:
            return users[0]
        raise VKAPIError("Не удалось получить данные пользователя")

    def get_group_info(self, group_id: int) -> dict:
        """Получить информацию о группе."""
        clean_id = abs(int(group_id))
        groups = self._api_call("groups.getById", {"group_id": clean_id})
        if groups:
            if isinstance(groups, dict) and "groups" in groups:
                return groups["groups"][0]
            if isinstance(groups, list):
                return groups[0]
        raise VKAPIError(f"Группа с ID {group_id} не найдена")

    def upload_wall_photo(self, file_path: str, group_id: Optional[int] = None, user_id: Optional[int] = None) -> str:
        """
        Загрузка одного фото для стены.
        Возвращает строку attachment: 'photo{owner_id}_{id}'
        """
        params = {}
        if group_id:
            params["group_id"] = abs(int(group_id))

        # 1. Получаем сервер загрузки
        server_info = self._api_call("photos.getWallUploadServer", params)
        upload_url = server_info.get("upload_url")
        if not upload_url:
            raise VKAPIError("Не получен upload_url от photos.getWallUploadServer")

        # 2. Отправляем файл
        upload_res = self._upload_file_multipart(upload_url, file_path)

        # 3. Сохраняем фото в альбом стены
        save_params = {
            "server": upload_res.get("server"),
            "photo": upload_res.get("photo"),
            "hash": upload_res.get("hash"),
        }
        if group_id:
            save_params["group_id"] = abs(int(group_id))
        elif user_id:
            save_params["user_id"] = abs(int(user_id))

        saved_photos = self._api_call("photos.saveWallPhoto", save_params)
        if not saved_photos:
            raise VKAPIError("Ошибка сохранения фото через photos.saveWallPhoto: пустой ответ")

        photo_data = saved_photos[0]
        return f"photo{photo_data['owner_id']}_{photo_data['id']}"

    def upload_carousel_photos(
        self, 
        image_paths: List[str], 
        group_id: Optional[int] = None, 
        user_id: Optional[int] = None
    ) -> List[str]:
        """
        Загрузка списка изображений карусели (до 10 шт).
        Возвращает список attachments.
        """
        if not (2 <= len(image_paths) <= 10):
            raise ValueError(f"Количество слайдов в карусели должно быть от 2 до 10 (передано: {len(image_paths)})")

        attachments = []
        for idx, path in enumerate(image_paths, start=1):
            print(f"  [↑] Загрузка слайда {idx}/{len(image_paths)}: {os.path.basename(path)}...", flush=True)
            # До 3 попыток на случай временного сбоя upload-сервера ВК
            att = None
            last_err = None
            for attempt in range(1, 4):
                try:
                    att = self.upload_wall_photo(path, group_id=group_id, user_id=user_id)
                    break
                except Exception as e:
                    last_err = e
                    time.sleep(1.0 * attempt)

            if not att:
                raise VKAPIError(f"Не удалось загрузить слайд {path} после 3 попыток: {last_err}")

            attachments.append(att)
            time.sleep(0.5)

        return attachments

    def post_carousel(
        self,
        image_paths: List[str],
        message: str = "",
        target: str = "user",  # "user" или "group"
        group_id: Optional[int] = None,
        publish_date: Optional[int] = None,
    ) -> dict:
        """
        Публикация поста-карусели.
        """
        target = target.lower().strip()
        if target == "group":
            if not group_id:
                raise ValueError("Для публикации в группу необходимо указать group_id")
            clean_group_id = abs(int(group_id))
            owner_id = -clean_group_id
            from_group = 1
            upload_group_id = clean_group_id
            upload_user_id = None
            group_info = self.get_group_info(clean_group_id)
            print(f"🚀 Публикация карусели в сообщество: «{group_info.get('name', 'ID ' + str(clean_group_id))}» (ID: {clean_group_id})", flush=True)
        elif target == "user":
            user_info = self.get_current_user()
            owner_id = user_info["id"]
            from_group = 0
            upload_group_id = None
            upload_user_id = owner_id
            print(f"🚀 Публикация карусели на личную страницу: {user_info.get('first_name')} {user_info.get('last_name')} (ID: {owner_id})", flush=True)
        else:
            raise ValueError("Параметр target должен быть 'user' или 'group'")

        # 1. Загрузка фото
        attachments = self.upload_carousel_photos(
            image_paths, 
            group_id=upload_group_id, 
            user_id=upload_user_id
        )
        attachments_str = ",".join(attachments)

        # 2. Публикация
        post_params = {
            "owner_id": owner_id,
            "from_group": from_group,
            "message": message,
            "attachments": attachments_str,
        }

        if publish_date:
            post_params["publish_date"] = int(publish_date)
            print(f"⏰ Запланировано на: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(publish_date))}", flush=True)

        result = self._api_call("wall.post", post_params)
        post_id = result.get("post_id")
        print(f"✅ Успешно! ID записи: {post_id}", flush=True)
        if target == "group":
            print(f"🔗 Ссылка на пост: https://vk.com/wall-{clean_group_id}_{post_id}", flush=True)
        else:
            print(f"🔗 Ссылка на пост: https://vk.com/wall{owner_id}_{post_id}", flush=True)

        return result
