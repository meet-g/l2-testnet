import json
from urllib.parse import urlparse

def find_trade_api():
    try:
        with open('trade.breakoutprop.com.har', 'r', encoding='utf-8') as f:
            har_data = json.load(f)
    except Exception as e:
        print(f"Error loading JSON: {e}")
        return

    print("Searching for unique trade API requests...")
    seen_urls = set()
    count = 0
    for entry in har_data.get('log', {}).get('entries', []):
        request = entry.get('request', {})
        url = request.get('url', '')
        method = request.get('method', '')
        
        parsed_url = urlparse(url)
        # Skip analytics/tracking
        if 'seg.kraken.com' in parsed_url.netloc or 'segment' in url:
            continue
            
        if method in ['POST', 'PUT']:
            if url not in seen_urls:
                if 'order' in url.lower() or 'trade' in url.lower():
                    seen_urls.add(url)
                    print(f"--- Trade Request {count + 1} ---")
                    print(f"URL: {url}")
                    print(f"Method: {method}")
                    
                    print("Headers:")
                    for h in request.get('headers', []):
                        if h['name'].lower() in ['authorization', 'content-type', 'user-agent', 'origin']:
                            print(f"  {h['name']}: {h['value'][:100]}")
                            
                    post_data = request.get('postData', {}).get('text', '')
                    print(f"Post Data: {post_data}")
                    print("-" * 80)
                    count += 1
                    
                    if count >= 3:
                        break

if __name__ == '__main__':
    find_trade_api()
