import requests
import urllib3
from datetime import datetime, timedelta
import pandas as pd
from bs4 import BeautifulSoup
import time

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Referer': 'https://www.rbc.ru/short_news',
}

simple_keywords = [
    'платежные системы',
    'международные переводы',
    'ЦФА',
    'цифровые активы',
    'цифровой рубль',
    'QR-код',
    'СБП',
    'налог',
    'налогообложение'
]

law_terms = ['цфа', 'стейблкоин', 'криптовалюта', 'цифровые активы', 'цифровой рубль']
law_keywords = ['закон', 'законопроект']


def get_full_text(url):
    try:
        response = requests.get(url, headers=headers, verify=False, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')

            article_body = soup.find('div', class_='article__text')
            if article_body:
                paragraphs = article_body.find_all('p')
                full_text = ' '.join([p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)])
                if full_text:
                    return full_text

            paragraphs = soup.find_all('p', class_='paragraph')
            full_text = ' '.join([p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)])
            if full_text:
                return full_text

            anons_span = soup.find('span', class_='js-article-pro-anons-text')
            if anons_span:
                full_text = anons_span.get_text(strip=True)
                if full_text:
                    return full_text

            return ''
    except Exception as e:
        print(f"Ошибка при получении текста: {e}")
        return ''


def check_title_match(title):
    title_lower = title.lower()
    matched_keywords = []
    match_type = None

    for kw in simple_keywords:
        if kw.lower() in title_lower:
            matched_keywords.append(kw)
            if not match_type:
                match_type = 'simple'

    has_law_word = any(law_word in title_lower for law_word in law_keywords)
    has_law_term = any(term in title_lower for term in law_terms)

    if has_law_word and has_law_term:
        found_law_words = [lw for lw in law_keywords if lw in title_lower]
        found_law_terms = [lt for lt in law_terms if lt in title_lower]
        combined_match = f"{'+'.join(found_law_words)} + {'/'.join(found_law_terms)}"
        matched_keywords.append(combined_match)
        if not match_type:
            match_type = 'complex_law'

    return bool(matched_keywords), matched_keywords, match_type


def get_rbc_news_dataframe(days_back=31):
    """
    Главная функция, которая возвращает DataFrame с новостями

    Параметры days_back: количество дней назад для поиска (по умолчанию 31)

    Возвращает pandas DataFrame с колонками: date, title, full_text, url
    """
    base_url = 'https://www.rbc.ru/api/rbcnews/v1/newsfeed'
    found_news = []
    end_cursor = None
    request_count = 0
    max_requests = 100

    date_limit = int((datetime.now() - timedelta(days=days_back)).timestamp())

    print(f"Фильтруем новости за период с {datetime.fromtimestamp(date_limit).strftime('%Y-%m-%d')}")

    while request_count < max_requests:
        params = {'limit': 20}
        if end_cursor:
            params['endCursor'] = end_cursor

        response = requests.get(base_url, headers=headers, params=params, verify=False)

        if response.status_code == 429:
            retry_after = response.headers.get('Retry-After')
            wait_time = int(retry_after) if retry_after and retry_after.isdigit() else 10
            print(f"Получен статус 429 (Too Many Requests). Ожидание {wait_time} секунд перед повтором...")
            time.sleep(wait_time)
            continue

        if response.status_code != 200:
            print(f"Ошибка API: {response.status_code}")
            break

        data = response.json()
        items = data.get('items', [])

        if not items:
            break

        oldest_date = min(item.get('publishDateT', 0) for item in items)
        if oldest_date < date_limit:
            items = [item for item in items if item.get('publishDateT', 0) >= date_limit]
            if not items:
                break

        for item in items:
            title = item.get('title', '')
            publish_date = datetime.fromtimestamp(item.get('publishDateT', 0))
            url = item.get('url', '')

            is_match, _, _ = check_title_match(title)

            if is_match:
                full_text = get_full_text(url)

                found_news.append({
                    'date': publish_date.strftime('%Y-%m-%d %H:%M:%S'),
                    'title': title,
                    'full_text': full_text,
                    'url': url
                })

        if not data.get('moreExists', False):
            break

        end_cursor = data.get('endCursor')
        request_count += 1

        print(f"Запрос {request_count} выполнен. Пауза перед следующим")
        time.sleep(0.3)

    if found_news:
        df = pd.DataFrame(found_news)
        print(f"\nИТОГО найдено новостей: {len(df)}")
        return df
    else:
        print("Новости по заданным критериям не найдены.")
        return pd.DataFrame(columns=['date', 'title', 'full_text', 'url'])
