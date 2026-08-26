"""Модуль для публикации фото-каруселей во ВКонтакте (VK API).

Поддерживает:
- Публикацию на личную страницу (owner_id = user_id, from_group = 0)
- Публикацию от имени группы (owner_id = -group_id, from_group = 1)
- Отложенный постинг (publish_date)
- Загрузку от 2 до 10 изображений в карусель
- Работу без сторонних зависимостей (только стандартная библиотека Python)
"""

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

        boundary = uuid.uuid4().hex
        filename = os.path.basename(file_path)
        mime_type, _ = mimetypes.guess_type(file_path)
        mime_type = mime_type or "image/png"

        with open(file_path, "rb") as f:
            file_bytes = f.read()

        # Формирование multipart тела
        body = []
        body.append(f"--{boundary}\r\n".encode("utf-8"))
        body.append(
            f'Content-Disposition: form-data; name="photo"; filename="{filename}"\r\n'.encode("utf-8")
        )
        body.append(f"Content-Type: {mime_type}\r\n\r\n".encode("utf-8"))
        body.append(file_bytes)
        body.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))
        payload_data = b"".join(body)

        req = urllib.request.Request(
            upload_url,
            data=payload_data,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Content-Length": str(len(payload_data)),
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw_resp = resp.read().decode("utf-8")
                return json.loads(raw_resp)
        except Exception as e:
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

    def upload_wall_photo(self, file_path: str, group_id: Optional[int] = None) -> str:
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

        saved_photos = self._api_call("photos.saveWallPhoto", save_params)
        if not saved_photos:
            raise VKAPIError("Ошибка сохранения фото через photos.saveWallPhoto")

        photo_data = saved_photos[0]
        return f"photo{photo_data['owner_id']}_{photo_data['id']}"

    def upload_carousel_photos(self, image_paths: List[str], group_id: Optional[int] = None) -> List[str]:
        """
        Загрузка списка изображений карусели (до 10 шт).
        Возвращает список attachments.
        """
        if not (2 <= len(image_paths) <= 10):
            raise ValueError(f"Количество слайдов в карусели должно быть от 2 до 10 (передано: {len(image_paths)})")

        attachments = []
        for idx, path in enumerate(image_paths, start=1):
            print(f"  [↑] Загрузка слайда {idx}/{len(image_paths)}: {os.path.basename(path)}...")
            att = self.upload_wall_photo(path, group_id=group_id)
            attachments.append(att)
            time.sleep(0.35)

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

        :param image_paths: список путей к картинкам (2..10)
        :param message: текст поста
        :param target: 'user' (личная страница) или 'group' (сообщество)
        :param group_id: ID группы (обязателен, если target='group')
        :param publish_date: Unix timestamp для отложенной публикации
        :return: ответ VK API с post_id
        """
        target = target.lower().strip()
        if target == "group":
            if not group_id:
                raise ValueError("Для публикации в группу необходимо указать group_id")
            clean_group_id = abs(int(group_id))
            owner_id = -clean_group_id
            from_group = 1
            upload_group_id = clean_group_id
            group_info = self.get_group_info(clean_group_id)
            print(f"🚀 Публикация карусели в сообщество: «{group_info.get('name', 'ID ' + str(clean_group_id))}» (ID: {clean_group_id})")
        elif target == "user":
            user_info = self.get_current_user()
            owner_id = user_info["id"]
            from_group = 0
            upload_group_id = None
            print(f"🚀 Публикация карусели на личную страницу: {user_info.get('first_name')} {user_info.get('last_name')} (ID: {owner_id})")
        else:
            raise ValueError("Параметр target должен быть 'user' или 'group'")

        # 1. Загрузка фото
        attachments = self.upload_carousel_photos(image_paths, group_id=upload_group_id)
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
            print(f"⏰ Запланировано на: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(publish_date))}")

        result = self._api_call("wall.post", post_params)
        post_id = result.get("post_id")
        print(f"✅ Успешно! ID записи: {post_id}")
        if target == "group":
            print(f"🔗 Ссылка на пост: https://vk.com/wall-{clean_group_id}_{post_id}")
        else:
            print(f"🔗 Ссылка на пост: https://vk.com/wall{owner_id}_{post_id}")

        return result
