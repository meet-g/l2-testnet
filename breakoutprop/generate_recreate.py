import json

def generate_python_script():
    try:
        with open('trade.breakoutprop.com.har', 'r', encoding='utf-8') as f:
            har_data = json.load(f)
    except Exception as e:
        print(f"Error loading JSON: {e}")
        return

    post_headers = {}
    delete_headers = {}

    for entry in har_data.get('log', {}).get('entries', []):
        request = entry.get('request', {})
        url = request.get('url', '')
        
        if 'api/internal/breakout/v1/trading' in url:
            method = request.get('method')
            
            headers = {}
            for h in request.get('headers', []):
                if not h['name'].startswith(':'):
                    headers[h['name']] = h['value']
                    
            if method == 'POST':
                post_headers = headers
            elif method == 'DELETE':
                delete_headers = headers

    script = f"""import requests

# Recreated from breakoutprop HAR data

def place_buy_order(account_id, pair, volume, price):
    url = f"https://iapi.breakoutprop.com/api/internal/breakout/v1/trading/orders?account_id={{account_id}}"
    
    headers = {json.dumps(post_headers, indent=4)}
    
    payload = {{
        "order_type": {{
            "limit": {{
                "price": {{
                    "absolute": str(price)
                }}
            }}
        }},
        "pair": {{
            "asset_class": "external_pair",
            "name": pair
        }},
        "side": "buy",
        "volume": str(volume)
    }}
    
    response = requests.post(url, headers=headers, json=payload)
    return response

def place_sell_order(account_id, pair, volume, price):
    url = f"https://iapi.breakoutprop.com/api/internal/breakout/v1/trading/orders?account_id={{account_id}}"
    
    headers = {json.dumps(post_headers, indent=4)}
    
    payload = {{
        "order_type": {{
            "limit": {{
                "price": {{
                    "absolute": str(price)
                }}
            }}
        }},
        "pair": {{
            "asset_class": "external_pair",
            "name": pair
        }},
        "side": "sell",
        "volume": str(volume)
    }}
    
    response = requests.post(url, headers=headers, json=payload)
    return response

def close_position(account_id, position_id):
    url = f"https://iapi.breakoutprop.com/api/internal/breakout/v1/trading/positions/{{position_id}}/close?account_id={{account_id}}"
    
    headers = {json.dumps(delete_headers, indent=4)}
    
    response = requests.delete(url, headers=headers)
    return response

if __name__ == '__main__':
    print("These are the recreated functions to perform buy and sell actions.")
    # Example usage:
    # res = place_buy_order('WPYC-77BL-ULG8-F9AK', 'HYPE/USD', '1.7', '86.015')
    # print(res.text)
    # res = close_position('WPYC-77BL-ULG8-F9AK', 'XTU77AY-3V7VN-MVHLAO')
    # print(res.text)
"""
    with open('recreate_requests.py', 'w') as out_f:
        out_f.write(script)
    print("recreate_requests.py generated successfully.")

if __name__ == '__main__':
    generate_python_script()
