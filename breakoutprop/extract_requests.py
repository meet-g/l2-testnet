import json
from urllib.parse import urlparse

def find_trade_api():
    try:
        with open('trade.breakoutprop.com.har', 'r', encoding='utf-8') as f:
            har_data = json.load(f)
    except Exception as e:
        print(f"Error loading JSON: {e}")
        return

    print("Searching for trade API requests...")
    count = 0
    for entry in har_data.get('log', {}).get('entries', []):
        request = entry.get('request', {})
        url = request.get('url', '')
        method = request.get('method', '')
        
        parsed_url = urlparse(url)
        # Skip analytics/tracking
        if 'seg.kraken.com' in parsed_url.netloc or 'segment' in url:
            continue
            
        if method in ['POST', 'PUT', 'PATCH']:
            post_data = request.get('postData', {}).get('text', '')
            post_data_lower = post_data.lower()
            url_lower = url.lower()
            
            # Look for order-related terms
            if 'buy' in post_data_lower or 'sell' in post_data_lower or 'order' in url_lower or 'order' in post_data_lower:
                print(f"--- Trade Request {count + 1} ---")
                print(f"URL: {url}")
                print(f"Method: {method}")
                print(f"Post Data: {post_data}")
                
                # Try to pretty print post data if it's JSON
                try:
                    js = json.loads(post_data)
                    print("Parsed JSON Payload:")
                    print(json.dumps(js, indent=2))
                except:
                    pass
                print("-" * 80)
                count += 1
                
                if count >= 15:
                    break

if __name__ == '__main__':
    find_trade_api()
