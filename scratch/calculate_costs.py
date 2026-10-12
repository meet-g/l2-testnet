uncached_input = 32_877_728
cached_input = 207_126_181
output_tokens = 1_215_528
total_tokens = uncached_input + cached_input + output_tokens

pricing_models = {
    "Gemini Pro (Standard Tier: $1.25 in / $0.3125 cache / $5.00 out)": {
        "input_rate": 1.25 / 1_000_000,
        "cached_rate": 0.3125 / 1_000_000,
        "output_rate": 5.00 / 1_000_000,
    },
    "Gemini Pro (>128k Tier: $2.50 in / $0.625 cache / $10.00 out)": {
        "input_rate": 2.50 / 1_000_000,
        "cached_rate": 0.625 / 1_000_000,
        "output_rate": 10.00 / 1_000_000,
    },
    "Gemini Flash ($0.075 in / $0.01875 cache / $0.30 out)": {
        "input_rate": 0.075 / 1_000_000,
        "cached_rate": 0.01875 / 1_000_000,
        "output_rate": 0.30 / 1_000_000,
    },
    "Claude 3.5 / 3.7 Sonnet ($3.00 in / $0.30 cache / $15.00 out)": {
        "input_rate": 3.00 / 1_000_000,
        "cached_rate": 0.30 / 1_000_000,
        "output_rate": 15.00 / 1_000_000,
    },
    "OpenAI GPT-4o ($2.50 in / $1.25 cache / $10.00 out)": {
        "input_rate": 2.50 / 1_000_000,
        "cached_rate": 1.25 / 1_000_000,
        "output_rate": 10.00 / 1_000_000,
    }
}

print(f"Token Counts:")
print(f"  Uncached Input: {uncached_input:,}")
print(f"  Cached Input:   {cached_input:,}")
print(f"  Output Tokens:  {output_tokens:,}")
print(f"  Total Tokens:   {total_tokens:,}\n")

for name, rates in pricing_models.items():
    cost_in = uncached_input * rates["input_rate"]
    cost_cached = cached_input * rates["cached_rate"]
    cost_out = output_tokens * rates["output_rate"]
    total_cost = cost_in + cost_cached + cost_out
    
    # Cost if there was NO caching (all 240M as uncached input)
    cost_no_cache = (uncached_input + cached_input) * rates["input_rate"] + cost_out
    savings = cost_no_cache - total_cost
    
    print(f"=== {name} ===")
    print(f"  Uncached Input Cost: ${cost_in:,.2f}")
    print(f"  Cached Input Cost:   ${cost_cached:,.2f}")
    print(f"  Output Cost:         ${cost_out:,.2f}")
    print(f"  TOTAL ACTUAL COST:   ${total_cost:,.2f}")
    print(f"  (Without Caching:    ${cost_no_cache:,.2f} -> Caching Saved: ${savings:,.2f})\n")
