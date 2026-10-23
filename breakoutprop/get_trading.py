import json

def get_trading():
    try:
        with open('trade.breakoutprop.com.har', 'r', encoding='utf-8') as f:
            har_data = json.load(f)
    except Exception as e:
        print(f"Error loading JSON: {e}")
        return

    count = 1
    for entry in har_data.get('log', {}).get('entries', []):
        request = entry.get('request', {})
        url = request.get('url', '')
        
        if 'api/internal/breakout/v1/trading' in url:
            if request.get('method') in ['POST', 'PUT', 'DELETE', 'PATCH']:
                print(f"--- Trading Request {count} ---")
                print("Method:", request.get('method'))
                print("URL:", url)
                print("Post Data:", request.get('postData', {}).get('text', ''))
                count += 1

if __name__ == '__main__':
    get_trading()
