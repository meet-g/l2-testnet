import json

def get_orders():
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
        
        if 'api/internal/breakout/v1/trading/orders' in url and request.get('method') == 'POST':
            print(f"--- Order Request {count} ---")
            print("URL:", url)
            print("Post Data:", request.get('postData', {}).get('text', ''))
            count += 1

if __name__ == '__main__':
    get_orders()
