import json

def get_cookies():
    try:
        with open('trade.breakoutprop.com.har', 'r', encoding='utf-8') as f:
            har_data = json.load(f)
    except Exception as e:
        print(f"Error loading JSON: {e}")
        return

    for entry in har_data.get('log', {}).get('entries', []):
        request = entry.get('request', {})
        url = request.get('url', '')
        
        if 'api/internal/breakout/v1/trading' in url:
            method = request.get('method')
            if method == 'POST':
                for h in request.get('headers', []):
                    if h['name'].lower() == 'cookie':
                        print("Found Cookie Header:")
                        print(h['value'][:100] + "...")
                        
                        # Let's save it to a file
                        with open('cookie.txt', 'w') as cf:
                            cf.write(h['value'])
                break

if __name__ == '__main__':
    get_cookies()
