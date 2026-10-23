import requests

# Recreated from breakoutprop HAR data

def place_buy_order(account_id, pair, volume, price):
    url = f"https://iapi.breakoutprop.com/api/internal/breakout/v1/trading/orders?account_id={account_id}"
    
    headers = {
    "accept": "application/json",
    "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
    "content-length": "141",
    "content-type": "application/json",
    "origin": "https://trade.breakoutprop.com",
    "priority": "u=1, i",
    "referer": "https://trade.breakoutprop.com/",
    "sec-ch-ua": "\"Chromium\";v=\"154\", \"Google Chrome\";v=\"154\", \"Not A(Brand\";v=\"99\"",
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": "\"Windows\"",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36",
    "x-csrf-token": ",Z,Ll3aJEIFDJhNCBrZIlsHYZow58L7zQpiqzwvs91oL9mmo_RqlHJJ_95oKsQDa_wEiGw6PZ32sYg--",
    "x-handler-environment": "stable",
    "x-korigin": "s081",
    "x-retry-attempt": "0"
}
    
    payload = {
        "order_type": {
            "limit": {
                "price": {
                    "absolute": str(price)
                }
            }
        },
        "pair": {
            "asset_class": "external_pair",
            "name": pair
        },
        "side": "buy",
        "volume": str(volume)
    }
    
    response = requests.post(url, headers=headers, json=payload)
    return response

def place_sell_order(account_id, pair, volume, price):
    url = f"https://iapi.breakoutprop.com/api/internal/breakout/v1/trading/orders?account_id={account_id}"
    
    headers = {
    "accept": "application/json",
    "accept-encoding": "gzip, deflate, br, zstd",
    "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
    "content-length": "141",
    "content-type": "application/json",
    "origin": "https://trade.breakoutprop.com",
    "priority": "u=1, i",
    "referer": "https://trade.breakoutprop.com/",
    "sec-ch-ua": "\"Chromium\";v=\"154\", \"Google Chrome\";v=\"154\", \"Not A(Brand\";v=\"99\"",
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": "\"Windows\"",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36",
    "x-csrf-token": ",Z,Ll3aJEIFDJhNCBrZIlsHYZow58L7zQpiqzwvs91oL9mmo_RqlHJJ_95oKsQDa_wEiGw6PZ32sYg--",
    "x-handler-environment": "stable",
    "x-korigin": "s081",
    "x-retry-attempt": "0"
}
    
    payload = {
        "order_type": {
            "limit": {
                "price": {
                    "absolute": str(price)
                }
            }
        },
        "pair": {
            "asset_class": "external_pair",
            "name": pair
        },
        "side": "sell",
        "volume": str(volume)
    }
    
    response = requests.post(url, headers=headers, json=payload)
    return response

def close_position(account_id, position_id):
    url = f"https://iapi.breakoutprop.com/api/internal/breakout/v1/trading/positions/{position_id}/close?account_id={account_id}"
    
    headers = {
    "accept": "application/json",
    "accept-encoding": "gzip, deflate, br, zstd",
    "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
    "origin": "https://trade.breakoutprop.com",
    "priority": "u=1, i",
    "referer": "https://trade.breakoutprop.com/",
    "sec-ch-ua": "\"Chromium\";v=\"154\", \"Google Chrome\";v=\"154\", \"Not A(Brand\";v=\"99\"",
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": "\"Windows\"",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36",
    "x-csrf-token": "dy1zDQFEEIFDJhNCBrZIlsHYZow58L7zQpiqzwvs91oL9mmo_RqqFZd7AKI6zyKVjVxQLeyf_JNPQg--",
    "x-handler-environment": "stable",
    "x-korigin": "s081",
    "x-retry-attempt": "0"
}
    
    response = requests.delete(url, headers=headers)
    return response

if __name__ == '__main__':
    print("These are the recreated functions to perform buy and sell actions.")
    # Example usage:
    # res = place_buy_order('WPYC-77BL-ULG8-F9AK', 'HYPE/USD', '1.7', '86.015')
    # print(res.text)
    # res = close_position('WPYC-77BL-ULG8-F9AK', 'XTU77AY-3V7VN-MVHLAO')
    # print(res.text)
