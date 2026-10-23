import json

def get_headers():
    try:
        with open('trade.breakoutprop.com.har', 'r', encoding='utf-8') as f:
            har_data = json.load(f)
    except Exception as e:
        print(f"Error loading JSON: {e}")
        return

    for entry in har_data.get('log', {}).get('entries', []):
        request = entry.get('request', {})
        url = request.get('url', '')
        
        if 'api/internal/breakout/v1/trading/orders' in url and request.get('method') == 'POST':
            print("Found Order POST Request")
            print("URL:", url)
            print("Headers:")
            for h in request.get('headers', []):
                print(f"  {h['name']}: {h['value']}")
            print("Post Data:", request.get('postData', {}).get('text', ''))
            print("-" * 80)
            break

if __name__ == '__main__':
    get_headers()
