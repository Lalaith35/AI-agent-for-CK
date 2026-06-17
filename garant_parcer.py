import requests
import xml.etree.ElementTree as ET
import urllib3
import random
import time
from bs4 import BeautifulSoup

# --- 1. Настройка ---
SITEMAP_INDEX_URL = "https://www.garant.ru/sitemap.xml"
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Safari/605.1.15"
]
NAMESPACE = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}

TARGET_NEWS_COUNT = 1000 # максимум просмотренных статей
MAX_ATTEMPTS_PER_SITEMAP = 3
MAX_ATTEMPTS_PER_PAGE = 2
BASE_DELAY = 5 # Базовая задержка в секундах для экспоненциального бэкоффа
required_month = 5 # Месяц который нас интересует (если смотрим все месяцы ставим значение True)
# Отключаем предупреждения о небезопасных запросах (verify=False)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def fetch_url(url, attempt=1, max_attempts=MAX_ATTEMPTS_PER_SITEMAP):
    """
    Выполняет GET-запрос с умными повторами.
    Возвращает текст ответа или None в случае неудачи.
    """
    headers = {"User-Agent": random.choice(USER_AGENTS)}
    try:
        response = requests.get(url, headers=headers, timeout=25, verify=False)
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"  -> Ошибка при запросе {url}: {e}")
        if attempt < max_attempts:
            delay = BASE_DELAY * (2 ** (attempt - 1))
            print(f"  -> Попытка {attempt}/{max_attempts}. Повтор через {delay} сек...")
            time.sleep(delay)
            return fetch_url(url, attempt + 1, max_attempts)
        else:
            print(f"  -> Исчерпан лимит попыток ({max_attempts}). Пропускаем {url}.")
            return None


def get_sitemap_urls(index_url):
    """Получает список всех URL карт сайта из индекса."""
    sitemap_urls = []
    xml_text = fetch_url(index_url)
    if not xml_text:
        return sitemap_urls

    try:
        root = ET.fromstring(xml_text)
        for sitemap in root.findall('ns:sitemap', NAMESPACE):
            loc_elem = sitemap.find('ns:loc', NAMESPACE)
            if loc_elem is not None:
                sitemap_urls.append(loc_elem.text)
        print(f"Найдено {len(sitemap_urls)} карт сайта в индексе.")
    except Exception as e:
        print(f"Ошибка при парсинге индекса: {e}")
    return sitemap_urls


def find_archive_sitemap(sitemap_urls):
    """Ищет карту сайта, содержащую архив новостей."""
    for sitemap_url in sitemap_urls:
        xml_text = fetch_url(sitemap_url)
        if not xml_text:
            continue

        try:
            root = ET.fromstring(xml_text)
            # Проверяем, есть ли в этой карте ссылки на новости
            for url in root.findall('ns:url', NAMESPACE):
                loc_elem = url.find('ns:loc', NAMESPACE)
                if loc_elem is not None and '/news/' in loc_elem.text:
                    if 'archive' in sitemap_url.lower():
                        print(f"\nАрхивная карта сайта найдена: {sitemap_url}")
                        return sitemap_url
                    else:
                        # Если не нашли архивную, но нашли карту с новостями - используем её
                        return sitemap_url
        except Exception as e:
            print(f"Ошибка при парсинге карты {sitemap_url}: {e}")
    return None


def collect_news_links(sitemap_url, target_count):
    """Собирает ссылки на новости из указанной карты сайта."""
    news_links = []
    xml_text = fetch_url(sitemap_url)
    if not xml_text:
        return news_links

    try:
        root = ET.fromstring(xml_text)
        for url in root.findall('ns:url', NAMESPACE):
            if len(news_links) >= target_count:
                break
            loc_elem = url.find('ns:loc', NAMESPACE)
            if loc_elem is not None:
                link = loc_elem.text
                if '/news/' in link and '/company/' not in link:
                    news_links.append(link)
    except Exception as e:
        print(f"Ошибка при сборе ссылок из {sitemap_url}: {e}")
    return news_links


def parse_news_page(url):
    """
    Парсит страницу новости с учетом сложной структуры и фильтрацией по дате.
    Возвращает словарь с данными или None, если страница не соответствует критериям.
    """
    html_text = fetch_url(url, max_attempts=MAX_ATTEMPTS_PER_PAGE)
    if not html_text:
        return None

    try:
        soup = BeautifulSoup(html_text, 'html.parser')

        # --- 1. Поиск заголовка ---
        title_tag = soup.find('h1') # Часто у h1 есть класс "title"
        title = title_tag.get_text(strip=True) if title_tag else "Заголовок не найден"


        # --- 2. Поиск даты публикации (по вашему селектору) ---
        # Ищем элемент <time> по сложному пути от body
        date_obj = soup.select_one('body > div.container-xxxl.my-8.my-sm-10 > div > div.col-12.col-lg-9.col-xxl-8 > div:nth-child(7) > div.text-secondary.text-opacity-50.small.d-flex.align-items-center.flex-wrap.gap-4.mb-7 > time')

        news_date = None
        if date_obj and date_obj.has_attr('datetime'):
            datetime_str = date_obj['datetime']
            # Извлекаем год из строки формата "2026-06-10T18:27:00+03:00"
            year = int(datetime_str[:4])
            day =  date_obj['datetime'][8:10]
            month =  date_obj['datetime'][5:7]
            news_date = f'{day}.{month}.{year}'

            print(f"  -> Найдена дата: {date_obj.text} ({datetime_str})")

            # Фильтрация по дате: пропускаем все новости до 2026 года включительно
            if year < 2026 or int(month) != required_month:
                print(f"  -> Новости за {news_date} нас не интересуют. Пропускаем.")
                return None
        else:
            print("  -> ВНИМАНИЕ: Дата публикации не найдена по указанному селектору!")
            # Можно либо пропустить новость без даты, либо продолжить парсинг текста
            # return None # <-- Раскомментируйте эту строку, чтобы пропускать новости без даты

        # --- 3. Поиск основного текста статьи ---
        text_blocks = soup.find_all('div', class_='clearfix')

        # Создаем единый список со всеми <p> и всеми <li> из найденных блоков
        paragraphs = []
        clearfix_elements = soup.select('.clearfix ul, .clearfix p')
        paragraphs.extend(clearfix_elements)

        # Теперь склеиваем всё вместе
        if paragraphs:
            # Используем рекомендуемый метод с separator для красивого форматирования
            text = "\n\n".join([p.get_text(strip=True) for p in paragraphs])
        else:
            text = "Текст статьи не найден"
        # print(text +'!!@')
        # --- 4. Проверка на ключевое слово "налог" ---
        if 'налог' not in text.lower():
            print("  -> Слово 'налог' в тексте не найдено. Пропускаем.")
            return None

        return {
            'year': news_date,
            'title': title,
            'text': text if text else "Текст статьи не найден",
            'url': url
        }

    except Exception as e:
        print(f"  -> Ошибка при парсинге страницы {url}: {e}")
        return None


# --- Основной скрипт ---
print("=== Запуск парсинга новостей ===")
print("Этап 1: Получаем список карт сайта из индекса...")
all_sitemaps = get_sitemap_urls(SITEMAP_INDEX_URL)

if all_sitemaps:
    print("\nЭтап 2: Поиск карты сайта с новостями...")
    archive_sitemap = find_archive_sitemap(all_sitemaps)

    if archive_sitemap:
        print("\nЭтап 3: Сбор ссылок на новости из найденной карты...")
        collected_links = collect_news_links(archive_sitemap, TARGET_NEWS_COUNT)

        # --- Этап 4: Парсинг страниц новостей и сохранение в датафрейм ---
news_data_list = [] # Список для сбора словарей с данными о новостях

for i, news_link in enumerate(collected_links, 1):
    print(f"\n--- Парсим новость {i}/{len(collected_links)} ---")
    print(f"Ссылка: {news_link}")

    news_data = parse_news_page(news_link)

    if news_data:
        # Слово "налог" уже проверено внутри функции parse_news_page,
        # поэтому сюда попадают только подходящие статьи.
        news_data_list.append(news_data)

        print(f"Заголовок: {news_data['title']}")
        print("Статья соответствует критериям (дата > 2026 и есть слово 'налог'). Сохранена.")

    # Проверяем условие остановки после каждой найденной новости
    if len(news_data_list) >= TARGET_NEWS_COUNT:
        print(f"\nДостигнут лимит в {TARGET_NEWS_COUNT} новостей. Останавливаем поиск.")
        break

# --- Создание DataFrame из собранных данных ---
if news_data_list:
    import pandas as pd
    df = pd.DataFrame(news_data_list)
    print("\nПарсинг завершен. Данные собраны:")
    print(df.head())

    # --- Сохранение в Excel ---
    filename = "parsed_garant_news.xlsx"
    df.to_excel(filename, index=False)
    print(f"\nФайл '{filename}' успешно создан!")
else:
    print("\nНе удалось найти новости, соответствующие заданным критериям.")
