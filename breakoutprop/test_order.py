from recreate_requests import place_buy_order

def test_buy():
    print("Testing buy order for HYPE/USD at price 90...")
    
    response = place_buy_order(
        account_id='WPYC-77BL-ULG8-F9AK',
        pair='HYPE/USD',
        volume='1.0',
        price='90'
    )
    
    print(f"Status Code: {response.status_code}")
    print(f"Response Text: {response.text}")

if __name__ == '__main__':
    test_buy()
