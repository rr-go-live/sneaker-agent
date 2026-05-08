# =============================================================================
# STATIC SNEAKER DATA
# Sourced from:
# https://github.com/purplebugs/sneakers-game/blob/main/data/sneakersFromDatabase.json
#
# In a production app this would come from a live database or API.
# Hard-coded here so every agent can see exactly what it is working with.
# =============================================================================

# How much money each user has to spend
USER_BUDGETS = {
    "John": 300.00,
    "Alice": 500.00,
}

# What sneakers each user already owns
USER_SNEAKER_COLLECTION = {
    "John": [
        "Nike Air Max 90 White",
        "Adidas Stan Smith Green",
        "Vans Old Skool Black/White",
        "Nike Air Force 1 Low Triple White",
    ],
    "Alice": [
        "Nike Dunk Low Panda",
        "Jordan 1 Low White Cement",
        "New Balance 574 Grey",
        "Adidas Superstar Shell Toe",
    ],
}

# The sneaker catalog — brand, colorway, retail price, resale market value,
# whether it is in stock, and a StockX purchase link
SNEAKER_CATALOG = {
    "New Balance 550 Triple Black": {
        "brand": "New Balance",
        "colorway": "Black/Black/Black",
        "retail_price": 110.00,
        "market_value": 146.00,
        "gender": "Men",
        "in_stock": True,
        "link": "https://stockx.com/new-balance-550-triple-black",
    },
    "Adidas Busenitz Vintage Focus Orange": {
        "brand": "Adidas",
        "colorway": "Focus Orange/Cloud White/Gum",
        "retail_price": 85.00,
        "market_value": 100.00,
        "gender": "Men",
        "in_stock": True,
        "link": "https://stockx.com/adidas-busenitz-vintage-focus-orange",
    },
    "Nike Air Force 1 Mid Berlin": {
        "brand": "Nike",
        "colorway": "Cave Stone/White-Off Noir-Washed Teal",
        "retail_price": 130.00,
        "market_value": 130.00,
        "gender": "Men",
        "in_stock": True,
        "link": "https://stockx.com/nike-air-force-1-mid-berlin",
    },
    "Nike Air Force 1 Low LX Off Noir Black": {
        "brand": "Nike",
        "colorway": "Off Noir/Off Noir-Black",
        "retail_price": 130.00,
        "market_value": 130.00,
        "gender": "Men",
        "in_stock": True,
        "link": "https://stockx.com/nike-air-force-1-low-lx-off-noir-black",
    },
    "Adidas Stan Smith South Park Stan Marsh": {
        "brand": "Adidas",
        "colorway": "Blue/Red/White",
        "retail_price": 100.00,
        "market_value": 187.00,
        "gender": "Men",
        "in_stock": True,
        "link": "https://stockx.com/adidas-stan-smith-southpark-stan-marsh",
    },
    "Nike SB Dunk High Oski Great White": {
        "brand": "Nike",
        "colorway": "White/Cool Grey-White-White",
        "retail_price": 100.00,
        "market_value": 364.00,
        "gender": "Men",
        "in_stock": True,
        "link": "https://stockx.com/nike-sb-dunk-high-oski-great-white",
    },
    "Jordan 13 Retro Del Sol": {
        "brand": "Jordan",
        "colorway": "White/University Red-Del Sol-Black",
        "retail_price": 200.00,
        "market_value": 300.00,
        "gender": "Men",
        "in_stock": True,
        "link": "https://stockx.com/air-jordan-13-retro-del-sol",
    },
    "Jordan 6 Retro UNC White": {
        "brand": "Jordan",
        "colorway": "University Blue/White/College Navy/Black",
        "retail_price": 210.00,
        "market_value": 295.00,
        "gender": "Men",
        "in_stock": True,
        "link": "https://stockx.com/air-jordan-6-retro-unc-white",
    },
    "Adidas Yeezy 450 Cinder": {
        "brand": "Adidas",
        "colorway": "Cinder/Cinder/Cinder",
        "retail_price": 200.00,
        "market_value": 200.00,
        "gender": "Men",
        "in_stock": True,
        "link": "https://stockx.com/adidas-yeezy-450-cinder",
    },
    "Nike Dunk Low Essential Paisley Pack Green": {
        "brand": "Nike",
        "colorway": "White/Malachite-White-Malachite",
        "retail_price": 120.00,
        "market_value": 254.00,
        "gender": "Women",
        "in_stock": True,
        "link": "https://stockx.com/nike-dunk-low-essential-paisley-pack-green-w",
    },
    "Jordan 6 Retro Mint Foam": {
        "brand": "Jordan",
        "colorway": "White/Pure Platinum-Mint Foam",
        "retail_price": 200.00,
        "market_value": 340.00,
        "gender": "Women",
        "in_stock": True,
        "link": "https://stockx.com/air-jordan-6-retro-mint-foam-w",
    },
    "Jordan 4 Retro Infrared": {
        "brand": "Jordan",
        "colorway": "Dark Grey/Infrared 23-Black-Cement Grey",
        "retail_price": 200.00,
        "market_value": 650.00,
        "gender": "Men",
        "in_stock": False,
        "link": "https://stockx.com/air-jordan-4-retro-infrared",
    },
    "Jordan 1 Retro High OG Stage Haze": {
        "brand": "Jordan",
        "colorway": "White/Black-Grey Fog-Bleached Coral",
        "retail_price": 170.00,
        "market_value": 556.00,
        "gender": "Men",
        "in_stock": False,
        "link": "https://stockx.com/air-jordan-1-retro-high-og-stage-haze",
    },
    "Jordan 1 Retro High OG Heritage": {
        "brand": "Jordan",
        "colorway": "White/University Red-Black",
        "retail_price": 170.00,
        "market_value": 551.00,
        "gender": "Men",
        "in_stock": False,
        "link": "https://stockx.com/air-jordan-1-retro-high-og-heritage",
    },
    "Adidas Yeezy Boost 350 V2 MX Frost Blue": {
        "brand": "Adidas",
        "colorway": "MX Frost Blue/MX Frost Blue/MX Frost Blue",
        "retail_price": 230.00,
        "market_value": 669.00,
        "gender": "Men",
        "in_stock": False,
        "link": "https://stockx.com/adidas-yeezy-boost-350-v2-mx-frost-blue",
    },
}
