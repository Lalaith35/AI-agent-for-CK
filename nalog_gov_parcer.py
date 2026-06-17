import requests
import re
from datetime import datetime, timedelta
from urllib.parse import urlparse
import pandas as pd
from bs4 import BeautifulSoup
import time

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3',
}

search_keyword = 'банк'


def check_title_match(title):
    title_lower = title.lower()

    if search_keyword.lower() in title_lower:
        return True, [search_keyword], 'simple'

    return False, [], None


def parse_news_date(date_str):
    if not date_str:
        return None

    date_str = date_str.strip()

    if re.match(r'\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}', date_str):
        return datetime.strptime(date_str, '%d.%m.%Y %H:%M')

    if re.match(r'\d{2}\.\d{2}\.\d{4}', date_str):
        return datetime.strptime(date_str, '%d.%m.%Y')

    return None


def get_full_text_nalog(url):
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            return f"Ошибка доступа к странице: {response.status_code}"

        soup = BeautifulSoup(response.text, 'html.parser')
        full_text = ""

        text_block = soup.find('div', class_='text_block')
        if text_block:
            paragraphs = text_block.find_all('p')
            full_text = ' '.join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
            if not full_text:
                full_text = text_block.get_text(strip=True)

        if not full_text:
            page_content = soup.find('div', class_='page-content__center')
            if page_content:
                paragraphs = page_content.find_all('p')
                full_text = ' '.join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
                if not full_text:
                    full_text = page_content.get_text(strip=True)

        if not full_text:
            content_selectors = [
                ('div', 'news-detail__text'),
                ('div', 'article-text'),
                ('div', 'news-text'),
                ('div', 'content-text'),
                ('article', None),
            ]

            for tag, class_name in content_selectors:
                if class_name:
                    content_div = soup.find(tag, class_=class_name)
                else:
                    content_div = soup.find(tag)

                if content_div:
                    paragraphs = content_div.find_all('p')
                    full_text = ' '.join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
                    if full_text:
                        break

        if full_text:
            full_text = re.sub(r'Дата публикации:\s*\d{2}\.\d{2}\.\d{4}\s*', '', full_text)
            full_text = re.sub(r'Дата публикации:\s*\d{2}\.\d{2}\.\d{4}\s*\d{2}:\d{2}\s*', '', full_text)

            full_text = re.sub(r'Это архивная публикация - она может содержать устаревшую информацию\.\s*', '', full_text)

            full_text = re.sub(r'\s+', ' ', full_text).strip()
            full_text = re.sub(r'&nbsp;', ' ', full_text)
            full_text = re.sub(r'&[a-z]+;', '', full_text)

        return full_text if full_text else ""

    except Exception as e:
        print(f"Ошибка при получении текста новости {url}: {e}")
        return ""


def get_nalog_news_dataframe(base_url = "https://www.nalog.gov.ru/rn77/news/news_fta/1.html?n=&fd=15.05.2025&td=15.06.2026&th=0,591527,591526,591528,591529,592228&chFederal=true&rbAllRegions=true&rbRegionSelected=false&ddlRegion=3288", days_back=31, max_pages=100):
    """
    Параметры:
    - base_url: полный URL первой страницы
    - days_back: количество дней для поиска новостей (по умолчанию 31)
    - max_pages: максимальное количество страниц для проверки

    Возвращает pandas DataFrame с колонками: date, title, full_text, url
    """
    found_news = []
    date_limit = datetime.now() - timedelta(days=days_back)

    parts = base_url.split('/')

    base_path_parts = []
    query_params = ""

    for i, part in enumerate(parts):
        if '.html' in part:
            html_part = part
            if '?' in html_part:
                html_file, query_params = html_part.split('?', 1)
                query_params = '?' + query_params
            else:
                html_file = html_part
                query_params = ""

            base_path_parts = parts[:i] + ['']
            break

    if not base_path_parts:
        print("Ошибка: Не удалось определить структуру URL")
        return pd.DataFrame()

    base_path = '/'.join(base_path_parts)
    if not base_path.endswith('/'):
        base_path += '/'

    print(f"Поиск новостей с ключевым словом '{search_keyword}'")
    print(f"Поиск новостей с {date_limit.strftime('%Y-%m-%d')}")
    print(f"Базовый путь: {base_path}")
    print(f"Параметры запроса: {query_params}")

    current_page = 1

    while current_page <= max_pages:
        page_url = f"{base_path}{current_page}.html{query_params}"
        print(f"\nОбработка страницы {current_page}: {page_url}")

        try:
            response = requests.get(page_url, headers=headers, timeout=15)

            if response.status_code == 404:
                print(f"Страница {current_page} не найдена (404), завершаем парсинг")
                break

            if response.status_code != 200:
                print(f"Ошибка {response.status_code} для страницы {current_page}")
                current_page += 1
                continue

            soup = BeautifulSoup(response.text, 'html.parser')

            news_blocks = soup.find_all('div', class_='news-block__text')

            if not news_blocks:
                news_blocks_alt = soup.find_all('div', class_='news-block')
                if news_blocks_alt:
                    extracted_blocks = []
                    for block in news_blocks_alt:
                        text_block = block.find('div', class_='news-block__text')
                        if text_block:
                            extracted_blocks.append(text_block)
                    news_blocks = extracted_blocks

            if not news_blocks:
                print(f"На странице {current_page} не найдено блоков новостей")
                pagination = soup.find('div', class_='pagination')
                if pagination:
                    next_link = pagination.find('a', string=re.compile(r'след|>|→', re.I))
                    if not next_link:
                        print("Достигнут конец списка новостей")
                        break
                current_page += 1
                continue

            print(f"Найдено {len(news_blocks)} блоков новостей")
            page_has_recent = False

            for block in news_blocks:
                try:
                    date_elem = block.find('div', class_='news__time')
                    if not date_elem:
                        continue

                    date_str = date_elem.get_text(strip=True)
                    news_date = parse_news_date(date_str)

                    if not news_date:
                        continue

                    if news_date < date_limit:
                        continue

                    page_has_recent = True

                    title_elem = block.find('div', class_='news-block__name')
                    if not title_elem:
                        continue

                    link_elem = title_elem.find('a')
                    if not link_elem:
                        continue

                    title = link_elem.get_text(strip=True)
                    href = link_elem.get('href', '')

                    if not title or not href:
                        continue

                    if href.startswith('/'):
                        parsed_base = urlparse(base_url)
                        news_url = f"{parsed_base.scheme}://{parsed_base.netloc}{href}"
                    else:
                        news_url = href

                    is_match, matched_keywords, match_type = check_title_match(title)

                    if is_match:
                        print(f"  Найдена релевантная новость: {title[:80]}...")
                        full_text = get_full_text_nalog(news_url)

                        found_news.append({
                            'date': news_date.strftime('%Y-%m-%d %H:%M:%S'),
                            'title': title,
                            'full_text': full_text,
                            'url': news_url
                        })

                        print(f"    Дата: {news_date.strftime('%Y-%m-%d %H:%M:%S')}")
                        print(f"    Ссылка: {news_url}")
                        print(f"    Текст: {full_text[:100]}..." if full_text else "    Текст: (пусто)")
                        print()

                        time.sleep(0.3)

                except Exception as e:
                    print(f"  Ошибка при обработке блока новости: {e}")
                    continue

            if not page_has_recent and current_page > 1:
                print("Нет свежих новостей на странице, завершаем парсинг")
                break

            pagination = soup.find('div', class_='pagination')
            has_next = False
            if pagination:
                next_link = pagination.find('a', string=re.compile(r'след|>|→', re.I))
                if not next_link:
                    next_link = pagination.find('a', class_='next')
                if not next_link:
                    next_page_num = current_page + 1
                    next_link = pagination.find('a', string=str(next_page_num))
                has_next = bool(next_link)

            if not has_next and current_page > 1:
                print("Достигнут конец списка новостей")
                break

            current_page += 1
            time.sleep(0.5)

        except requests.RequestException as e:
            print(f"Ошибка запроса для страницы {current_page}: {e}")
            current_page += 1
            continue

    if found_news:
        df = pd.DataFrame(found_news)
        df = df.drop_duplicates(subset=['url'])
        df = df.sort_values('date', ascending=False)
        print(f"\n{'='*60}")
        print(f"ИТОГО найдено новостей с ключевым словом '{search_keyword}': {len(df)}")
        return df
    else:
        print(f"\nНовости с ключевым словом '{search_keyword}' не найдены.")
        return pd.DataFrame(columns=['date', 'title', 'full_text', 'url'])
