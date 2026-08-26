# VK Carousel Autoposter

Легковесный модуль и CLI-утилита для автопостинга **фото-каруселей** (слайдеров от 2 до 10 изображений) во ВКонтакте:
* 👤 **На личную страницу** (`owner_id = user_id`, `from_group = 0`)
* 👥 **От имени сообщества / группы** (`owner_id = -group_id`, `from_group = 1`)
* ⏰ **С отложенной публикацией** (`publish_date`)
* 🚀 **Zero-dependency**: работает на стандартной библиотеке Python без необходимости устанавливать сторонние пакеты.

---

## 🔑 Быстрый старт: получение токена

Для работы скрипта требуется Standalone User Token (бессрочный):
1. Откройте **[vkhost.github.io](https://vkhost.github.io/)**.
2. Нажмите на **Kate Mobile** (или **VK Admin**).
3. Разрешите доступ и скопируйте токен из адресной строки браузера после `access_token=`.

---

## ⚙️ Настройка

Создайте файл `.env` на основе `.env.example`:

```bash
cp .env.example .env
```

Заполните ваши данные в `.env`:
```env
VK_ACCESS_TOKEN=vk1.a.your_token_from_vkhost...
VK_GROUP_ID=123456789   # ID вашей группы без минуса
```

---

## 🚀 Использование через CLI

### 1. Проверка токена и прав:
```bash
python3 main.py --check
```

### 2. Публикация на личную страницу (тестовые слайды из `samples/`):
```bash
python3 main.py --target user --text "Тестовая карусель на личной странице 🔥"
```

### 3. Публикация от имени группы:
```bash
python3 main.py --target group --text "Полезный гайд в карусели 👇"
```

### 4. Публикация своей папки со слайдами:
```bash
python3 main.py --target group --folder "/path/to/my_slides" --text "Текст поста"
```

### 5. Отложенная публикация (например, через 60 минут):
```bash
python3 main.py --target group --delay-minutes 60 --text "Запланированный пост"
```

---

## 📦 Использование как Python-модуля

Вы можете легко подключить модуль `VKCarouselPoster` к проекту генератора каруселей (например, `CoureselText`):

```python
from vk_carousel import VKCarouselPoster

poster = VKCarouselPoster(access_token="vk1.a...")

# Публикация на личную страницу:
poster.post_carousel(
    image_paths=["slide_1.png", "slide_2.png", "slide_3.png"],
    message="Текст поста",
    target="user"
)

# Публикация в сообщество:
poster.post_carousel(
    image_paths=["slide_1.png", "slide_2.png", "slide_3.png"],
    message="Пост от имени сообщества",
    target="group",
    group_id=123456789
)
```
