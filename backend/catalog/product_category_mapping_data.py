"""ProductCategory → LocalCategory 映射数据（2026-11-23 批次 A）。

来源：`var/category_misclass_20261123/findings.md` §8.3、
`pc_mapping_analysis.json`（240 行 = catalog joybuy_uk 全部商品类目）。
用户拍板（Q9/Q12）：回填 206 条（67 高置信 + 139 归父级），其余 34 条
（22 词集合包含 + 1 跨父级 + 11 无对应根）只出清单、不填。

键是 `ProductCategory.source_id`（纯数字，catalog=joybuy_uk）；值是本地
`LocalCategory.slug`。由 `backfill_product_category_local_category` 消费。
"""

LOCAL_CATEGORY_BY_SOURCE_ID = {
    "4": "beauty-personal-care",  # Beauty | root
    "5": "makeup",  # Makeup | Beauty
    "59": "beauty-personal-care",  # Skin Care | Beauty
    "159": "beauty-personal-care",  # Personal Care Devices | root
    "167": "beauty-personal-care",  # Dental Care Appliances | Personal Care Devices
    "183": "home-living",  # Decorative Accents | Home Décor
    "187": "beauty-personal-care",  # Beauty Appliances | Personal Care Devices
    "192": "beauty-personal-care",  # Hair Care Appliances | Personal Care Devices
    "199": "small-home-appliances",  # Home Appliances | root
    "200": "small-home-appliances",  # Cleaning Appliances | Home Appliances
    "253": "small-home-appliances",  # Ironing Appliances | Home Appliances
    "264": "small-home-appliances",  # Environmental Appliances | Home Appliances
    "275": "small-home-appliances",  # Small Kitchen Appliances | Home Appliances
    "288": "home-living",  # Cooking & Dining | root
    "289": "home-living",  # Bakeware | Cooking & Dining
    "296": "home-living",  # Kitchen Gadgets | Cooking & Dining
    "308": "home-living",  # Tableware | Cooking & Dining
    "321": "home-living",  # Kitchen Consumables | Cooking & Dining
    "330": "home-living",  # Home Textiles | root
    "361": "home-living",  # Cookware | Cooking & Dining
    "425": "home-living",  # Home Décor | root
    "441": "home-living",  # Furniture | root
    "442": "home-living",  # Living Room Furniture | Furniture
    "445": "home-living",  # Bathroom Furniture | Furniture
    "492": "home-living",  # Frozen Food | root
    "805": "health-wellness",  # Health Wellness | root
    "872": "beauty-personal-care",  # Personal Care | root
    "873": "beauty-personal-care",  # Dental care | Personal Care
    "876": "beauty-personal-care",  # Intimate and Period Care | Personal Care
    "897": "beauty-personal-care",  # Deodorants and Antiperspirants | Personal Care
    "919": "beauty-personal-care",  # Massage, Recovery and Wellness | Personal Care
    "926": "home-living",  # Household Laundry | root
    "927": "home-living",  # Household Cleaners | Household Laundry
    "942": "home-living",  # Cleaning Tools | Household Laundry
    "953": "home-living",  # Laundry Supplies | Household Laundry
    "964": "dishwashing",  # Dishwashing | Household Laundry
    "969": "kitchen-toilet-roll",  # Kitchen Roll, Toilet Roll Tissues | Household Laundry
    "978": "home-living",  # Papers, Wraps & Bags | Household Laundry
    "999": "baby-toddler",  # Baby | root
    "1021": "baby-feeding",  # Nursing Feeding | Baby
    "1068": "safety-equipment",  # Safety Equipment | Baby
    "1119": "baby-toddler",  # Health Baby Care | Baby
    "1171": "home-living",  # Fresh & Chilled Food | root
    "1481": "pet-supplies",  # Pet | root
    "1482": "pet-supplies",  # Dogs | Pet
    "1537": "pet-supplies",  # Cats | Pet
    "1801": "electronics-accessories",  # Accessories | Electronics
    "1819": "outdoor-sports",  # Sports & Outdoor | root
    "1849": "electronics",  # Electronics | root
    "1858": "cameras-photo",  # Camera & Photo | Electronics
    "1984": "wearables",  # Wearables | Electronics
    "1989": "computers-accessories",  # Computing | root
    "2017": "monitors",  # Monitors | Computing
    "2049": "games-accessories",  # Gaming | root
    "2050": "consoles",  # Consoles | Gaming
    "2053": "controllers",  # Controllers | Gaming
    "2056": "console-games",  # Console Games | Gaming
    "2059": "gaming-gear",  # Gaming Accessories | Gaming
    "2062": "home-living",  # Stationery & Office Supplies | root
    "2063": "home-living",  # Art Craft Supplies | Stationery & Office Supplies
    "2082": "home-living",  # Calendars, Planners Personal Organisers | Stationery & Office Supplies
    "2103": "home-living",  # Envelopes Mailing Supplies | Stationery & Office Supplies
    "2172": "home-living",  # Office Paper Products | Stationery & Office Supplies
    "2179": "home-living",  # Office Supplies | Stationery & Office Supplies
    "2210": "home-living",  # Pens, Pencils Writing Supplies | Stationery & Office Supplies
    "2227": "home-living",  # School Educational Supplies | Stationery & Office Supplies
    "2646": "home-living",  # Tobacco, Vapes & Alternatives | root
    "2647": "tobacco",  # Tobacco | Tobacco, Vapes & Alternatives
    "2661": "home-living",  # E Ciggaretts and Vapes | Tobacco, Vapes & Alternatives
    "2672": "tobacco-alternatives",  # Tobacco Alternatives | Tobacco, Vapes & Alternatives
    "2685": "health-wellness",  # Cold Flu | Health Wellness
    "2687": "health-wellness",  # Pain Relief | Health Wellness
    "2691": "home-living",  # Coffee Tea Making | Cooking & Dining
    "2693": "small-home-appliances",  # Laundry Appliances | Home Appliances
    "2701": "outdoor-sports",  # Sports Equipment | Sports & Outdoor
    "3102": "baby-toddler",  # Toy | root
    "3178": "baby-toddler",  # Baby Toddler Toys | Toy
    "3209": "baby-toddler",  # Dress Up Pretend Play | Toy
    "3343": "soft-toys",  # Soft Toys | Toy
    "3769": "home-living",  # Bedroom Furniture | Furniture
    "3796": "home-living",  # Office Furniture | Furniture
    "3815": "home-living",  # Housewares | root
    "3999": "baby-toddler",  # Building Toys | Toy
    "4029": "baby-toddler",  # Dolls Doll Accessories | Toy
    "4057": "games-puzzles",  # Games & Puzzles | Toy
    "4073": "baby-toddler",  # Learning Development | Toy
    "4090": "outdoor-toys",  # Outdoor Toys | Toy
    "4198": "beauty-personal-care",  # Personal Care Consumables | Personal Care
    "4268": "baby-toddler",  # Nappy & Pants | Baby
    "4325": "baby-toiletries",  # Baby Toiletries Bathing | Baby
    "4403": "baby-toddler",  # Pregnancy Maternity | Baby
    "4442": "strollers-travel",  # Strollers, Prams, Travel Accessories | Baby
    "4476": "baby-toddler",  # Baby Toys Activities | Baby
    "4553": "home-living",  # Dining Furniture | Furniture
    "4562": "home-living",  # Kids Furniture | Furniture
    "4581": "home-living",  # Custom Furniture | Furniture
    "4625": "outdoor-sports",  # Camping & Hiking | Sports & Outdoor
    "4644": "outdoor-sports",  # Garden | root
    "4661": "outdoor-sports",  # Garden Care | Garden
    "4677": "outdoor-sports",  # Mowers & Outdoor Power Tools | Garden
    "4680": "outdoor-sports",  # Barbecue & Outdoor Dining | Garden
    "4686": "outdoor-sports",  # Garden Furniture & Accessories | Garden
    "4692": "outdoor-sports",  # Pools, Hot Tubs & Supplies | Garden
    "4702": "home-living",  # Lighting | root
    "4703": "home-living",  # Indoor Lighting | Lighting
    "4742": "home-living",  # Light Bulbs | Lighting
    "4745": "home-living",  # Outdoor Lighting | Lighting
    "4786": "home-living",  # Cleaning Supplies | Housewares
    "4810": "home-living",  # Clothes Drying & Airers & Ironing | Housewares
    "4830": "home-storage",  # Storage Organisation | Housewares
    "4871": "home-living",  # Bed Textiles | Home Textiles
    "4880": "home-living",  # Bath Textiles | Home Textiles
    "4887": "home-living",  # Living Textiles | Home Textiles
    "4909": "home-living",  # Seasonal & Party | root
    "4910": "home-living",  # Party Supplies | Seasonal & Party
    "4945": "home-living",  # Seasons & Events | Seasonal & Party
    "5049": "other-animals",  # Other Animals | Pet
    "5084": "laptops",  # Laptops | Computing
    "5093": "desktop-pcs",  # Desktop PCs | Computing
    "5100": "computers-accessories",  # Keyboards, Mice & Input Devices | Computing
    "5109": "computers-accessories",  # Components & Replacement Parts | Computing
    "5123": "computers-accessories",  # Data Storage | Computing
    "5175": "computers-accessories",  # Accessories | Computing
    "5202": "mobile-phones",  # Phones | Electronics
    "5205": "tablets",  # Tablets | Electronics
    "5224": "electronics",  # Audio & Hi-Fi | Electronics
    "5287": "pc-gaming",  # PC Gaming | Gaming
    "5313": "games-accessories",  # Components | Gaming
    "5349": "outdoor-sports",  # DIY & Tools | root
    "5363": "outdoor-sports",  # Electrical | DIY & Tools
    "5414": "outdoor-sports",  # Fireplaces, Stoves & Accessories | DIY & Tools
    "5431": "outdoor-sports",  # Hardware | DIY & Tools
    "5464": "outdoor-sports",  # Kitchen & Bath Fixtures | DIY & Tools
    "5519": "outdoor-sports",  # Safety & Security | DIY & Tools
    "5553": "home-living",  # Tobaocco Heater & Sticks | Tobacco, Vapes & Alternatives
    "5825": "home-living",  # Ambient Food | root
    "5826": "home-living",  # Sweet and salted snacks | Ambient Food
    "5887": "home-living",  # Food Cupboard | Ambient Food
    "5968": "home-living",  # Beverages | root
    "5969": "home-living",  # Brew & Ready-to-Drink Beverages | Beverages
    "5987": "home-living",  # Juices | Beverages
    "6007": "home-living",  # Softdrinks | Beverages
    "6032": "water",  # Water | Beverages
    "6037": "home-living",  # Ambient Dairy & Alternatives | Beverages
    "6055": "home-living",  # Beer, Wines & Spirits | Beverages
    "6100": "home-living",  # Wall Art | Home Décor
    "6107": "home-living",  # Mirrors | Home Décor
    "6121": "home-living",  # Artificial Plants & Indoor Planters | Home Décor
    "6136": "electronics",  # Smart Devices | Electronics
    "6158": "baby-toddler",  # Formula | Baby
    "6159": "health-wellness",  # Health & Wellness Accessories | Health Wellness
    "6204": "beauty-personal-care",  # Gifts and Special Editions | Beauty
    "6349": "small-home-appliances",  # TV & Home Cinema | Home Appliances
    "8195": "fragrance",  # Fragrance | Beauty
    "8234": "beauty-personal-care",  # Sun Care | Personal Care
    "8244": "beauty-personal-care",  # Hair Care | Personal Care
    "8270": "beauty-personal-care",  # Shaving and Hair Removal | Personal Care
    "8282": "sexual-wellness",  # Sexual Wellness | Personal Care
    "8300": "eye-vision-care",  # Eye and Visual Care | Personal Care
    "8341": "beauty-personal-care",  # Gifts and Special Editions | Personal Care
    "8346": "beauty-personal-care",  # Travel Sizes and Minis | Personal Care
    "8372": "outdoor-sports",  # Tools | DIY & Tools
    "8425": "beauty-personal-care",  # Male Grooming Appliances | Personal Care Devices
    "8433": "beauty-personal-care",  # Female Hair Removal Appliances | Personal Care Devices
    "8440": "beauty-personal-care",  # Electrical Health & Diagnostics | Personal Care Devices
    "8468": "beauty-personal-care",  # Electrical Wellbeing | Personal Care Devices
    "8476": "small-home-appliances",  # Large Appliance Accessories | Home Appliances
    "8479": "small-home-appliances",  # Cooking Appliances | Home Appliances
    "8488": "small-home-appliances",  # Dishwashing Appliances | Home Appliances
    "8566": "small-home-appliances",  # Refrigeration Appliances | Home Appliances
    "8838": "smart-pet-appliances",  # Smart Pet Appliances | Pet
    "10679": "home-living",  # Home Accessories | Home Décor
    "10773": "home-living",  # Special Celebrations | Seasonal & Party
    "10794": "home-living",  # Gifting | Seasonal & Party
    "10870": "electronics",  # UAV System | Electronics
    "10879": "electronics",  # Home Audio & Video | Electronics
    "10895": "robotics",  # Robotics | Electronics
    "11096": "small-home-appliances",  # Solar & Energy Storage Systems | Home Appliances
    "11608": "pet-supplies",  # Birds | Pet
    "11621": "small-animals",  # Small Animals | Pet
    "11654": "pet-supplies",  # Reptiles & Amphibians | Pet
    "12044": "electronics",  # Security & Protection | Electronics
    "12069": "gaming-headsets",  # Gaming Headsets | Gaming
    "12078": "games-accessories",  # Gaming Streaming Equipment | Gaming
    "12098": "games-accessories",  # PC Peripherals | Gaming
    "12165": "outdoor-sports",  # Garden Hand Tools | Garden
    "12176": "outdoor-sports",  # Watering Equipment | Garden
    "12543": "outdoor-sports",  # Paint, Wallpaper & Sundries | DIY & Tools
    "12819": "home-living",  # Kitchen Furniture | Furniture
    "13101": "clothing-accessories",  # Apparel, Shoes & Accessories | root
    "13202": "clothing-accessories",  # Unisex | Apparel, Shoes & Accessories
    "13221": "clothing-accessories",  # Kids Girls | Apparel, Shoes & Accessories
    "13252": "clothing-accessories",  # Kids Boys | Apparel, Shoes & Accessories
    "13814": "health-wellness",  # Medical Foot Care | Health Wellness
    "13846": "health-wellness",  # Ear Care | Health Wellness
    "14595": "outdoor-sports",  # Decorative Adhesives | DIY & Tools
    "15870": "home-living",  # Hallway & Shoe Storage Furniture | Furniture
    "15881": "home-living",  # Home Entertainment Furniture | Furniture
    "15956": "beauty-personal-care",  # Accessories | Beauty
    "15974": "skincare",  # Face Care | Beauty
    "16045": "nails",  # Nails | Beauty
    "16102": "beauty-personal-care",  # Body Care | Personal Care
    "16307": "home-living",  # Meat & Fish | Fresh & Chilled Food
    "16406": "home-living",  # Cooked Meats, Deli & Dips | Fresh & Chilled Food
    "16469": "pet-supplies",  # Multi Animals | Pet
    "16586": "umbrellas-rain-gear",  # Umbrellas & Rain Gear | Housewares
}

# 只出清单、不写库的 34 条：source_id -> 原因（写进 review_needed.csv）。
REVIEW_NOTES_BY_SOURCE_ID = {
    "806": "词集合包含：建议 sports-nutrition-performance，需人工抽检",  # Nutrition | Health Wellness
    "985": "词集合包含：建议 air-fresheners-home-fragrance，需人工抽检",  # Home Fragrance | Household Laundry
    "1000": "词集合包含：建议 baby-food，需人工抽检",  # Baby Food | Baby
    "1140": "词集合包含：建议 nursery-bedding，需人工抽检",  # Nursery | Baby
    "2700": "跨父级：本地 smart-home 不在源父级 Home Appliances 下",  # Smart Home | Home Appliances
    "3323": "词集合包含：建议 baby-arts-crafts，需人工抽检",  # Arts Crafts | Toy
    "3372": "词集合包含：建议 play-figures，需人工抽检",  # Play Figures | Toy
    "4122": "词集合包含：建议 pocket-money-toys，需人工抽检",  # Pocket Money Collectibles | Toy
    "4133": "词集合包含：建议 vehicles-remote-control，需人工抽检",  # Vehicles | Toy
    "4469": "词集合包含：建议 baby-clothing，需人工抽检",  # Clothing | Baby
    "5128": "词集合包含：建议 office-electronics，需人工抽检",  # Office Electronics | Computing
    "5296": "词集合包含：建议 vr-simulation，需人工抽检",  # Simulation | Gaming
    "5769": "词集合包含：建议 frozen-party-food，需人工抽检",  # Frozen Food | Frozen Food
    "6114": "词集合包含：建议 air-fresheners-home-fragrance，需人工抽检",  # Home Fragrance | Home Décor
    "8314": "词集合包含：建议 stop-smoking，需人工抽检",  # Smoking | Personal Care
    "8596": "无法映射：本地无对应根",  # Automobiles, Parts & Accessories | root
    "8597": "无法映射：本地无对应根",  # Car Lights | Automobiles, Parts & Accessories
    "8608": "无法映射：本地无对应根",  # Auto Parts | Automobiles, Parts & Accessories
    "8621": "无法映射：本地无对应根",  # Auto Accessories | Automobiles, Parts & Accessories
    "8629": "无法映射：本地无对应根",  # Car Electronics | Automobiles, Parts & Accessories
    "8633": "无法映射：本地无对应根",  # Other Vehicle Parts & Accessories | Automobiles, Parts & Accessories
    "8695": "无法映射：本地无对应根",  # Motorcycle Equipments & Parts | root
    "8701": "无法映射：本地无对应根",  # Motorcycle Accessories | Motorcycle Equipments & Parts
    "8726": "无法映射：本地无对应根",  # Car Repair Tool | Automobiles, Parts & Accessories
    "8733": "无法映射：本地无对应根",  # Motorcycle Equipments | Motorcycle Equipments & Parts
    "10558": "无法映射：本地无对应根",  # Motorcycle Parts | Motorcycle Equipments & Parts
    "12093": "词集合包含：建议 vr-simulation，需人工抽检",  # Virtual Reality | Gaming
    "13002": "词集合包含：建议 sports-apparel-shoes，需人工抽检",  # Sports Apparel | Sports & Outdoor
    "13012": "词集合包含：建议 sports-apparel-shoes，需人工抽检",  # Sports Shoes | Sports & Outdoor
    "13027": "词集合包含：建议 sports-apparel-shoes，需人工抽检",  # Sports Accessories | Sports & Outdoor
    "13102": "词集合包含：建议 womens-clothing，需人工抽检",  # Women | Apparel, Shoes & Accessories
    "13159": "词集合包含：建议 mens-clothing，需人工抽检",  # Men | Apparel, Shoes & Accessories
    "15796": "词集合包含：建议 ice-cream，需人工抽检",  # Ice | Frozen Food
    "16377": "词集合包含：建议 frozen-vegetarian-vegan，需人工抽检",  # Vegetarian & Vegan | Fresh & Chilled Food
}

# 34 条待人工确认行的建议目标（没有建议时为 None）；只写进 review_needed.csv。
REVIEW_SUGGESTED_SLUG_BY_SOURCE_ID = {
    "806": "sports-nutrition-performance",
    "985": "air-fresheners-home-fragrance",
    "1000": "baby-food",
    "1140": "nursery-bedding",
    "2700": "smart-home",
    "3323": "baby-arts-crafts",
    "3372": "play-figures",
    "4122": "pocket-money-toys",
    "4133": "vehicles-remote-control",
    "4469": "baby-clothing",
    "5128": "office-electronics",
    "5296": "vr-simulation",
    "5769": "frozen-party-food",
    "6114": "air-fresheners-home-fragrance",
    "8314": "stop-smoking",
    "8596": None,
    "8597": None,
    "8608": None,
    "8621": None,
    "8629": None,
    "8633": None,
    "8695": None,
    "8701": None,
    "8726": None,
    "8733": None,
    "10558": None,
    "12093": "vr-simulation",
    "13002": "sports-apparel-shoes",
    "13012": "sports-apparel-shoes",
    "13027": "sports-apparel-shoes",
    "13102": "womens-clothing",
    "13159": "mens-clothing",
    "15796": "ice-cream",
    "16377": "frozen-vegetarian-vegan",
}
