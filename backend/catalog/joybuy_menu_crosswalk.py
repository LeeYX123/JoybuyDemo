"""Joybuy 频道菜单（14 频道 / 163 二级）→ 本地 11 个一级类目的交叉映射。

用户口径（2026-11-11，**推翻 2026-11-09 的多对一合并桶口径**）：

* **一对一**：每个 Joybuy 菜单二级 → 恰好一个本地二级；本地二级集合与
  Joybuy 二级集合一一对应，彻底取消多对一合并桶（食品杂货/手机与平板/
  笔记本与台式机/电脑配件/音响&家庭影院/宠物食品/宠物玩具/玩具早教/
  游戏机/显示器等桶全部拆开）。
* **名称**：一对一子类目名称用 Joybuy 原名（zh 沿用中文菜单翻译、en 用
  Joybuy 英文原文）；同一父类目下跨频道 union 出现的重名二级按
  ``NAME_OVERRIDES`` 消歧（如游戏频道的「显示器」→「游戏显示器」）。
* **按二级拆分**：计算机硬件从「电子产品」拆到「计算机与配件」；个护家清
  里个人护理归「美妆个人护理」、清洁归「家居生活」；汽车类不映射；大家电
  仍归「小家电」。
* **食品不进商城（2026-11-25，推翻 2026-11-11「食品归 home-living」口径）**：
  Joymart（超市）/ World-Foods（世界美食）两个频道整体不映射，家居生活频道
  自己的食品/酒水/烟草/冷冻节点也进 ``NODE_UNMAPPED``——食品一律不建/不激活
  本地二级（历史已建的食品类目移入隐藏的「世界食品」一级、商品下架，由
  2026-11-25 数据脚本处理）。
* **只建两级**：Joybuy 菜单里偶发的 ``l3:*`` 节点在这里一律拍平成本地二级。
* **退役**：被拆开的旧桶 slug 与 6 个不在 Joybuy 菜单里的基座二级
  （``RETIRED_LOCAL_SLUGS``）由同步命令在**无商品/无子类目/无商品类目/
  无搜索文档引用**时清理，绝不级联删数据。

本模块只做纯数据解析，不访问数据库；写入由
``catalog.management.commands.sync_local_categories_from_joybuy`` 负责。
"""

import re

#: 频道 → 本地一级；None = 该类目暂不进入我们的 11 个一级。
#: 2026-11-25：食品从家居生活撤出（用户口径：前期划分把食品混进了家居生活）。
#: Joymart（超市）与 World-Foods（世界美食）两个频道整体不再映射——它们的
#: 节点全是食品，改挂到任何 11 个一级都不对；future sync 不再创建/激活它们，
#: 已隐藏的食品类目也不会被重新置回 ACTIVE。
CHANNEL_PARENT = {
    "minihome:UK-Mini-HP-Home-Appliances": "small-home-appliances",
    "minihome:UK-Mini-HP-Electronics": "electronics",
    "minihome:UK-Mini-HP-Pets": "pet-supplies",
    "minihome:UK-Mini-HP-TV": "electronics",
    "minihome:UK-Mini-HP-Beauty": "beauty-personal-care",
    "minihome:UK-Mini-HP-Gaming": "games-accessories",
    "minihome:UK-Mini-HP-Joymart": None,
    "minihome:UK-Mini-HP-Home-Living": "home-living",
    "minihome:uk-mini-hp-everyday-essentials": "beauty-personal-care",
    "minihome:UK-Mini-HP-Toys-Baby-and-Kids": "baby-toddler",
    "minihome:uk-minihp-clothing-footwear-acc-": "clothing-accessories",
    "minihome:UK-Mini-HP-Health-and-Wellness": "health-wellness",
    "minihome:UK-Mini-HP-Automotive": None,
    "minihome:UK-Mini-HP-World-Foods": None,
}

#: 跨频道归属覆盖（按二级拆分）。
NODE_PARENT = {
    # 电子产品频道里的计算机硬件 → 计算机与配件
    "l2:1434": "computers-accessories",  # 键盘、鼠标及输入设备
    "l2:2656": "computers-accessories",  # 台式电脑
    "l2:1438": "computers-accessories",  # 笔记本电脑
    "l2:2623": "computers-accessories",  # 零件与替换配件
    "l2:1436": "computers-accessories",  # 显示器
    # 游戏频道里的 PC 硬件 → 计算机与配件
    "l3:1437": "computers-accessories",  # 显示器
    "l3:5116": "computers-accessories",  # 游戏键盘
    "l3:5117": "computers-accessories",  # 游戏鼠标
    "l2:5380": "computers-accessories",  # 游戏内存与存储
    # 家居生活里的运动/户外 → 户外运动
    "l2:1587": "outdoor-sports",  # 体育与休闲
    "l2:1585": "outdoor-sports",  # 户外
    # 电视与影音里的游戏机 → 游戏及配件
    "l3:1430": "games-accessories",
    # 个护家清：个人护理留在美妆个人护理，按摩归健康与保健，清洁归家居生活
    "l2:2735": "health-wellness",  # 按摩与舒缓
    "l2:1532": "home-living",  # 清洁用品
    "l2:1534": "home-living",  # 洗衣用品
    "l2:1528": "home-living",  # 餐具清洁
    "l3:3144": "home-living",  # 卷纸 / 厕纸
    "l3:1531": "home-living",  # 厨房用纸
    "l3:1523": "home-living",  # 虫害防治
    "l2:1526": "home-living",  # 锡纸、保鲜膜和食品储存
    "l2:1524": "home-living",  # 空气清新剂 & 家居香氛
    # 2026-11-11 全频道对齐：区块归属与其所在频道的默认一级不同
    "l2:1522": "home-living",  # 家居必需品（个护家清频道）
    "l2:1530": "home-living",  # 厨房用纸、厕纸与面巾纸（个护家清频道）
    "l2:4268": "computers-accessories",  # 打印机与扫描仪（电子产品频道）
    "l2:4270": "computers-accessories",  # 打印机配件（电子产品频道）
    "l2:1432": "computers-accessories",  # 网络设备（电子产品频道）
    "l2:1583": "outdoor-sports",  # 花园（家居生活频道）
    "l2:5332": "outdoor-sports",  # 运动服饰与鞋（家居生活频道）
    "l2:1584": "outdoor-sports",  # DIY（户外、运动与DIY 分组）
    "l2:2621": "computers-accessories",  # 办公电子产品（计算机与配件分组）
}

#: 2026-11-25 食品撤出家（家居）生活：48 个食品/酒水/烟草/冷冻源节点。
#: 语义：
#: ① 本地不再映射（并入上面的 ``NODE_UNMAPPED``）：future sync 不会把它们
#:    重新建类目/置回 ACTIVE/挂回家居生活——历史食品二级已移入隐藏的
#:    「世界食品」一级（slug world-foods，status HIDDEN），商品已下架；
#: ② 管理后台爬虫任务的品类树选择器（AdminCrawlerSourceTreeView）同样按
#:    本集合过滤：食品节点不再可勾选，子节点被清空的食品频道
#:    （Joymart / World-Foods）整棵隐藏。
FOOD_SOURCE_IDS = frozenset({
    # ① Joymart（超市）16 节点（巧克力糖果/零食坚果/酒水饮料/罐头调料/米面等）
    "l2:1277",  # 巧克力与糖果
    "l2:1285",  # 薯片、零食与坚果
    "l2:1329",  # 葡萄酒
    "l2:1302",  # 碳酸饮料
    "l2:1300",  # 能量、运动与健康饮品
    "l2:1312",  # 瓶装水
    "l2:1338",  # 茶、咖啡与热饮
    "l2:1315",  # 啤酒
    "l2:1325",  # 烈酒
    "l2:1317",  # 果酒
    "l2:1297",  # 罐头食品
    "l2:1295",  # 酱料、调味品与沙拉酱
    "l2:1275",  # 早餐麦片
    "l2:1278",  # 烹饪调料
    "l2:1276",  # 饼干
    "l2:1293",  # 米面杂粮
    # ② World-Foods（世界美食）8 节点（韩/日/泰东南亚/印南亚/非加勒比/国际/
    #    世界烈酒/中国食品）
    "l2:1549",  # 韩国食品
    "l2:1547",  # 日本食品
    "l2:1557",  # 泰国及东南亚食品
    "l2:1551",  # 印度及南亚食品
    "l2:1555",  # 非洲 & 加勒比地区食品
    "l2:2758",  # 国际风味
    "l2:3983",  # 世界烈酒
    "l2:1545",  # 中国食品
    # ③ 家居生活频道的食品饮料烟草 15 节点（饼干脆面包/烘焙糖类/果酱/快手菜/
    #    儿童午餐/浓缩果汁/预调鸡尾酒/低醇/汤力水/烟草/电子烟/烟草替代品/
    #    冰鲜世界美食/高端烈酒/冷冻派对食品）
    "l2:1280",  # 饼干与脆面包
    "l2:1287",  # 家庭烘焙与糖
    "l2:1289",  # 果酱与涂抹酱
    "l2:1291",  # 快手菜套装
    "l2:1306",  # 儿童与午餐盒
    "l2:1310",  # 浓缩果汁
    "l2:1319",  # 鸡尾酒与预调酒
    "l2:1321",  # 低醇与无酒精
    "l2:1327",  # 汤力水与调酒饮料
    "l2:1538",  # 烟草
    "l2:1539",  # 电子烟
    "l2:1540",  # 烟草替代品
    "l2:1559",  # 冷冻世界美食
    "l2:3669",  # 高端烈酒
    "l2:4376",  # 冷冻派对食品
    # ④ 冷冻食品 9 节点（冷冻即食餐/甜品/披萨蒜香面包/冰淇淋/薯条/素食/
    #    蔬果/海鲜/肉类禽类）
    "l2:1505",  # 冷冻即食餐
    "l2:1506",  # 冷冻甜点
    "l2:1507",  # 冷冻披萨与蒜香面包
    "l2:1508",  # 冰淇淋与冰块
    "l2:1510",  # 冷冻薯条与薯类
    "l2:1511",  # 冷冻素食
    "l2:1512",  # 冷冻蔬果与香草
    "l2:1513",  # 冷冻鱼类与海鲜
    "l2:1514",  # 冷冻肉类与禽类
})

#: 不映射的节点：
#: ①汽车相关——我们的 11 个一级里没有对应类目；
#: ②2026-11-11 全频道对齐时发现的「Joybuy 深层节点」：它们在源树里仍存在
#:   （旧抓取把它们当二级抓了下来），但**现网分类下拉里不出现**。我们只做
#:   两级，用户能看到的二级集合以「下拉面板」为准，因此这些不再作为本地
#:   二级（对应旧本地二级在 ``RETIRED_LOCAL_SLUGS`` 里一并退役）。
NODE_UNMAPPED = {
    "l2:3902",  # 洗车及保养工具
    "l2:3904",  # 汽车配件
    "l2:3896",  # 车载电器
    "l2:3898",  # 汽车灯具
    "l2:3900",  # 汽车维修工具
    "l3:3129",  # 手动工具与电动工具
    # 下拉里不出现的深层节点（2026-11-11）
    # 注意：l2:2621 / l2:2735 / l2:1584 / l2:5380 虽然不在「自己频道」的区块里，
    # 但它们在别的区块（计算机/美妆/户外/游戏）的下拉里出现，属于现网可见二级，
    # 因此**不能**放进这个集合。
    "l3:1437",  # 游戏显示器（显示器下的深层节点）
    "l3:5116",  # 游戏键盘
    "l3:5117",  # 游戏鼠标
    "l3:1500",  # 影音电子配件
    "l3:1430",  # 影音游戏机
    "l3:3014",  # 私密护理（深层）
    "l3:2746",  # 防晒（深层）
    "l3:3144",  # 卷纸 / 厕纸（现网并入「厨房用纸、厕纸与面巾纸」）
    "l3:1531",  # 厨房用纸（现网并入同上）
    "l3:1523",  # 虫害防治
    "l3:3121",  # 浇水和园艺工具（现网有「花园」区块）
} | FOOD_SOURCE_IDS

#: 「活动商品」不是类目，是 Spu.is_activity 标记（见 catalog.models.Spu 注释）。
#: 节庆装饰品不建本地二级；抓取/导入时直接标成活动商品。
ACTIVITY_SOURCE_IDS = {"l2:1580"}  # 节庆装饰品
ACTIVITY_LOCAL_SLUGS = {"seasonal-decor"}  # 历史同步曾创建的本地二级，命令负责清理

#: Joybuy 二级 → 已有本地二级 slug（历史基座节点改名复用，slug 不断链；
#: 一对一：每个 slug 只接收一个 Joybuy 节点）。
MERGE_INTO_EXISTING = {
    # 家居生活
    "l2:1572": "kitchen-essentials",  # 厨房与餐厅用品
    "l2:1574": "home-storage",  # 整理收纳
    "l2:1568": "bedding-textiles",  # 床上用品
    "l2:1532": "cleaning-supplies",  # 清洁用品
    # 电子产品
    "l2:1416": "cameras-photo",  # 摄影摄像
    "l2:1536": "smart-home",  # 智能家居
    # 计算机与配件
    "l2:1434": "peripherals",  # 键盘、鼠标及输入设备
    # 小家电
    "l2:2702": "kitchen-appliances",  # 厨房电器
    "l2:1403": "cleaning-appliances",  # 地板清洁电器
    # 美妆个人护理
    "l2:2747": "skincare",  # 面部护肤
    "l2:2753": "makeup",  # 彩妆
    "l2:2710": "body-hair-care",  # 身体护理
    "l2:2751": "fragrance",  # 香水
    # 健康与保健
    "l2:1462": "nutrition-supplements",  # 维生素 & 补充剂
    "l2:2567": "health-monitors",  # 电子健康检测
    "l2:2735": "massage-relaxation",  # 按摩与舒缓
    # 服装与配饰
    "l2:1877": "womens-clothing",
    "l2:1879": "mens-clothing",
    "l2:1881": "watches",
    "l2:1883": "shoes-boots",
    "l2:1885": "bags-luggage",
    "l2:1889": "jewellery",
    # 户外运动
    "l2:1587": "fitness-training",  # 体育与休闲
    "l2:1585": "outdoor-gear",  # 户外
    # 宠物用品
    "l2:3538": "pet-grooming",  # 宠物美容护理
    # 婴幼儿用品
    "l2:1494": "diapers-wipes",  # 婴幼儿纸尿裤
    "l2:1484": "baby-feeding",  # 婴儿哺育喂养
    # 游戏及配件（游戏频道自己的「游戏机」节点沿用基座 slug）
    "l2:1429": "consoles",  # 游戏机
}

#: 新建本地二级的 slug 固定值；不写则用英文名自动生成。
#: 一对一：每个 slug 恰好对应一个 Joybuy 节点（同名节点跨频道的各自独立，
#: 见 ``NAME_OVERRIDES`` 的消歧名）。
NODE_SLUG = {
    # 家用电器 / 小家电
    "l2:1407": "coffee-machines",
    "l2:1401": "heating-cooling-purifier",
    "l2:1405": "kettles-toasters",
    "l2:2696": "fridges-freezers",
    "l2:1397": "blenders-food-processors",
    "l2:2700": "washing-machines",
    "l2:2547": "tabletop-cooking",
    "l2:2551": "hair-styling-tools",
    "l2:2543": "air-fryers",
    "l2:2553": "toothbrushes-flossers",
    "l2:2555": "male-grooming",
    "l2:1399": "ironing",
    "l2:2557": "female-hair-removal",
    "l2:2544": "microwaves-ovens",
    "l2:2704": "cooker-hoods",
    # 电子产品（手机/平板拆开；电视影音频道的配件独立）
    "l2:1420": "mobile-phones",  # 手机 Phones
    "l2:1418": "tablets",  # 平板电脑 Tablets
    "l2:1412": "soundbars-home-cinema",  # 音响 & 家庭影院 Soundbars & Home Cinema
    "l3:1500": "tv-audio-accessories",  # 电视与影音频道的电子配件（消歧名）
    "l2:1414": "headphones",
    "l2:2846": "speakers",
    "l2:1410": "wearables",
    "l2:2621": "office-electronics",
    "l2:1499": "electronics-accessories",
    "l2:3567": "batteries",
    "l2:2693": "tvs",
    # 家居生活
    "l2:1570": "bath",
    "l2:1566": "home-decor",
    "l2:4663": "party-decorations",
    "l2:1443": "home-arts-craft-supplies",
    "l2:1578": "gift-wrap-cards",
    "l2:1564": "furniture",
    "l3:3121": "watering-garden-tools",
    "l2:1584": "diy-tools",
    "l2:1449": "notebooks-pads-paper",
    "l2:1445": "pens-pencils",
    "l2:1447": "school-office-accessories",
    "l2:1441": "mailing-supplies",
    # 个护家清 → 家居生活（清洁/纸品）
    "l3:3144": "toilet-roll",
    "l3:1531": "kitchen-roll",
    "l2:1534": "laundry",
    "l2:1528": "dishwashing",
    "l3:1523": "pest-control",
    "l2:1526": "food-storage-wraps",
    "l2:1524": "air-fresheners-home-fragrance",
    # 个护家清 → 美妆个人护理
    "l2:2711": "dental-care",
    "l3:3014": "intimate-care",
    "l2:2739": "sexual-wellness",
    "l3:2746": "sunscreens",
    "l2:2737": "mens-essentials",
    "l2:2731": "shaving-hair-removal",
    "l2:2741": "stop-smoking",
    "l2:2743": "eye-vision-care",
    # 美妆
    "l2:5316": "premium-beauty",
    "l2:2729": "hair-styling",
    "l2:2745": "sun-cream-lotion",
    "l2:2755": "nails",
    # 健康与保健
    "l2:1454": "weight-management",
    "l2:1456": "sexual-wellbeing-family-planning",
    "l2:1458": "period-products-intimate-care",
    "l2:1460": "sports-nutrition-performance",
    "l2:1464": "pharmacy-health",
    "l2:2569": "electronic-therapy",
    # 计算机与配件（笔记本/台式机、零件/游戏内存、两处显示器拆开）
    "l2:1438": "laptops",  # 笔记本电脑 Laptops
    "l2:2656": "desktop-pcs",  # 台式电脑 Desktop PCs
    "l2:2623": "gaming-pc-components",  # 零件与替换配件 Gaming PC components
    "l2:5380": "gaming-memory-storage",  # 游戏内存与存储 Gaming Memory & Storage
    "l2:1436": "monitors",  # 显示器 Monitors（电子产品频道）
    "l3:1437": "gaming-monitors",  # 游戏频道的显示器（消歧名）
    "l3:5116": "gaming-keyboards",
    "l3:5117": "gaming-mice",
    # 游戏及配件（电视与影音频道的游戏机节点，消歧名）
    "l3:1430": "consoles-tv-audio",  # 影音游戏机 Consoles (TV & Audio)
    "l2:1425": "controllers",
    "l2:1427": "console-games",
    "l2:3505": "steering-wheels",
    # 宠物用品（狗粮/猫粮/猫零食/猫玩具拆开；2026-11-11 现网新增 5 个节点补齐到 13 个）
    "l2:1364": "dog-food",  # 狗粮 Dog Food
    "l2:1363": "cat-food",  # 猫粮 Cat Food
    "l2:3532": "cat-treats",  # 猫零食 Cat Treats
    "l2:3540": "cat-toys",  # 猫玩具 Cat Toys
    "l2:3536": "pet-health",
    "l2:3534": "other-animals",
    "l2:3542": "pet-accessories",
    # 2026-11-11 现网菜单新增（8 → 13）
    "l2:4707": "cat-litter",  # 猫砂 Cat Litter
    "l2:5441": "dog-treats",  # 狗零食 Dog Treats
    "l2:4711": "smart-pet-appliances",  # 智能宠物电器 Smart Pet Appliances
    "l2:4713": "dog-toys",  # 狗玩具 Dog Toys
    "l2:1365": "small-animals",  # 小宠用品 Small Animals
    # 婴幼儿用品（两个学前玩具节点拆开）
    "l2:1372": "infant-pre-school-toys",  # 婴幼儿学前玩具 Infant & Pre-school Toys
    "l2:1476": "infant-pre-school-toys-activities",  # 婴幼儿玩具与活动用品
    "l2:1382": "dress-up-imaginative-play",
    "l2:1374": "construction-toys",
    "l2:1394": "games-puzzles",
    "l2:1388": "play-figures",
    "l2:1386": "dolls",
    "l2:1370": "pocket-money-toys",
    "l2:1392": "outdoor-toys",
    "l2:1390": "baby-arts-crafts",
    "l2:1384": "learning-discovery-science",
    "l2:1376": "vehicles-remote-control",
    "l2:1380": "electronic-toys-music",
    "l2:1378": "soft-toys",
    "l2:1492": "baby-milk",
    "l2:1490": "baby-food",
    "l2:1488": "baby-toiletries",
    "l2:1486": "baby-health",
    "l2:1482": "strollers-travel",
    "l2:1480": "nursery-bedding",
    "l2:1474": "baby-clothing",
    "l2:1478": "safety-equipment",
    # 家居生活 / 超市 + 世界美食：食品 24 节点一对一拆开（原 groceries-food 桶）
    "l2:1277": "chocolate-sweets",  # 巧克力与糖果 Chocolate & Sweets
    "l2:1285": "crisps-snacks-nuts",  # 薯片、零食与坚果 Crisps, Snacks & Nuts
    "l2:1329": "wine",  # 葡萄酒 Wine
    "l2:1302": "fizzy-drinks",  # 碳酸饮料 Fizzy Drinks
    "l2:1300": "energy-sports-health-drinks",  # 能量、运动与健康饮品
    "l2:1312": "water",  # 瓶装水 Water
    "l2:1338": "tea-coffee-hot-drinks",  # 茶、咖啡与热饮 Tea, Coffee & Hot Drinks
    "l2:1315": "beer",  # 啤酒 Beer
    "l2:1325": "spirits",  # 烈酒 Spirits
    "l2:1317": "cider",  # 果酒 Cider
    "l2:1297": "tins-cans",  # 罐头食品 Tins & Cans
    "l2:1295": "table-sauces-condiments-dressings",  # 酱料、调味品与沙拉酱
    "l2:1275": "cereals",  # 早餐麦片 Cereals
    "l2:1278": "cooking-ingredients",  # 烹饪调料 Cooking Ingredients
    "l2:1276": "biscuits",  # 饼干 Biscuits
    "l2:1293": "rice-pasta-pulses",  # 米面杂粮 Rice, Pasta & Pulses
    "l2:1549": "korean",  # 韩国食品 Korean
    "l2:1547": "japanese",  # 日本食品 Japanese
    "l2:1557": "thai-south-east-asian",  # 泰国及东南亚食品 Thai & South East Asian
    "l2:1551": "indian-south-asian",  # 印度及南亚食品 Indian & South Asian
    "l2:1555": "african-caribbean",  # 非洲 & 加勒比地区食品 African & Caribbean
    "l2:2758": "international-flavours",  # 国际风味 International Flavours
    "l2:3983": "world-spirits",  # 世界烈酒 World Spirits
    "l2:1545": "chinese",  # 中国食品 Chinese
    # 2026-11-11 全频道对齐：现网菜单比 11-04 快照新增的二级
    # （宠物 5 个已在上面的「宠物用品」段）
    # 电子产品
    "l2:4468": "robotics",  # Robotics（现网暂无中文名）
    "l2:4469": "drones",  # Drones（现网暂无中文名）
    # 计算机与配件
    "l2:4268": "printers-scanners",  # 打印机与扫描仪 Printers & Scanners
    "l2:4270": "printer-accessories",  # 打印机配件 Printer Accessories
    "l2:1432": "networking-devices",  # Networking Devices（现网暂无中文名）
    # 游戏及配件
    "l2:1423": "gaming-gear",  # 游戏配件 Gaming Accessories
    "l2:3499": "gaming-headsets",  # 游戏耳机 Gaming Headsets
    "l2:3501": "pc-gaming",  # PC 游戏 PC Gaming
    "l2:3503": "vr-simulation",  # Virtual Reality & Simulation（现网暂无中文名）
    # 小家电
    "l2:2705": "dishwashers",  # 洗碗机 Dishwashers
    "l2:2549": "drink-makers",  # 饮品制作机 Drink Makers
    # 美妆个人护理
    "l2:2733": "intimate-hygiene",  # 私密护理 Intimate & Hygiene
    # 服装与配饰
    "l2:1887": "fashion-accessories",  # 配饰 Accessories
    # 婴幼儿
    "l2:5403": "lego-sets",  # 乐高 LEGO Sets
    # 户外运动
    "l2:1583": "garden",  # 花园 Garden
    "l2:5332": "sports-apparel-shoes",  # 运动服饰与鞋 Sports apparel, Shoes & Accessories
    # 家居生活（食品/饮料/清洁/纸品）
    "l2:1280": "crackers-crispbread",  # 饼干与脆面包 Crackers & Crispbread
    "l2:1287": "home-baking-sugar",  # 家庭烘焙与糖 Home Baking & Sugar
    "l2:1289": "jam-spreads",  # 果酱与涂抹酱 Jam & Spreads
    "l2:1291": "meal-kits",  # 快手菜套装 Meal Kits
    "l2:1306": "kids-lunchbox",  # 儿童与午餐盒 Kids' & Lunchbox
    "l2:1310": "squash-cordial",  # 浓缩果汁 Squash & Cordial
    "l2:1319": "cocktails-pre-mixed",  # 鸡尾酒与预调酒 Cocktails & Pre-Mixed Drinks
    "l2:1321": "low-alcohol",  # 低醇与无酒精 Low Alcohol & Alcohol Free
    "l2:1327": "tonic-water-mixers",  # 汤力水与调酒饮料 Tonic Water & Mixers
    "l2:1538": "tobacco",  # 烟草 Tobacco
    "l2:1539": "vapes",  # 电子烟 Vapes
    "l2:1540": "tobacco-alternatives",  # 烟草替代品 Tobacco Alternatives
    "l2:1559": "frozen-world-food",  # 冷冻世界美食 Frozen World Food
    "l2:3669": "premium-spirits",  # 高端烈酒 Premium Spirits
    "l2:4376": "frozen-party-food",  # 冷冻派对食品 Frozen Party Food
    "l2:5395": "umbrellas-rain-gear",  # 雨伞与雨具 Umbrellas & Rain Gear
    "l2:1522": "household-essentials",  # 家居必需品 Household Essentials
    "l2:1530": "kitchen-toilet-roll",  # 厨房用纸、厕纸与面巾纸
    "l2:1505": "frozen-ready-meals",  # 冷冻即食餐 Frozen Ready Meals
    "l2:1506": "frozen-desserts",  # 冷冻甜点 Frozen Desserts
    "l2:1507": "frozen-pizza-garlic-bread",  # 冷冻披萨与蒜香面包
    "l2:1508": "ice-cream",  # 冰淇淋与冰块 Ice & Ice Cream
    "l2:1510": "frozen-chips-potatoes",  # 冷冻薯条与薯类 Frozen Chips & Potatoes
    "l2:1511": "frozen-vegetarian-vegan",  # 冷冻素食 Frozen Vegetarian & Vegan
    "l2:1512": "frozen-fruit-vegetables",  # 冷冻蔬果与香草
    "l2:1513": "frozen-fish-seafood",  # 冷冻鱼类与海鲜 Frozen Fish & Seafood
    "l2:1514": "frozen-meat-poultry",  # 冷冻肉类与禽类 Frozen Meat & Poultry
}

#: 跨频道 union 后同一父类目下的重名二级消歧（zh/en 都改，报告里可追溯）。
#: 2026-11-11 全频道对齐后**已无生效条目**：三处同名冲突都来自 ``l3:`` 深层节点
#: （影音电子配件 / 游戏显示器 / 影音游戏机），现网下拉里不出现、已进
#: ``NODE_UNMAPPED``。机制保留，将来若再现同名二级再补条目。
NAME_OVERRIDES: dict[str, dict[str, str]] = {}

#: 2026-11-11 一对一拆分后退役的本地二级 slug。
#: 前 8 个是被拆开的多对一桶（pet-toys 拆为 cat-toys；其余按节点拆开）；
#: 后 6 个是不在 Joybuy 菜单里的历史基座二级（0 商品时清理）。
#: 同步命令仅在**无商品/无子类目/无商品类目/无搜索文档引用**时删除，
#: 否则保留并在报告里警告，绝不级联删数据。
RETIRED_LOCAL_SLUGS = {
    # 被拆开的多对一桶
    "groceries-food",  # → 24 个食品一对一子类目
    "phones-tablets",  # → mobile-phones / tablets
    "laptops-desktops",  # → laptops / desktop-pcs
    "pc-components",  # → gaming-pc-components / gaming-memory-storage
    "tv-audio",  # → soundbars-home-cinema / tv-audio-accessories
    "pet-food",  # → dog-food / cat-food / cat-treats
    "pet-toys",  # → cat-toys（改名复用行不可行时按新 slug 新建，旧行退役）
    "toys-early-learning",  # → infant-pre-school-toys(-activities)
    # 不在 Joybuy 菜单里的历史基座二级（「集合与 Joybuy 一模一样」要求移除）
    "networking",
    "cycling",
    "water-sports",
    "personal-care-appliances",
    "gaming-accessories",
    "board-card-games",
    # 2026-11-11 全频道对齐：这些「二级」其实是 Joybuy 的深层节点，现网下拉
    # 里不出现（对应源节点进了 NODE_UNMAPPED）。0 商品时可安全清理。
    "tv-audio-accessories",  # ← l3:1500
    "consoles-tv-audio",  # ← l3:1430
    "gaming-keyboards",  # ← l3:5116
    "gaming-mice",  # ← l3:5117
    "gaming-monitors",  # ← l3:1437
    "intimate-care",  # ← l3:3014（现网有「私密护理」l2:2733）
    "sunscreens",  # ← l3:2746
    "toilet-roll",  # ← l3:3144（并入 kitchen-toilet-roll）
    "kitchen-roll",  # ← l3:1531（并入 kitchen-toilet-roll）
    "pest-control",  # ← l3:1523
    "watering-garden-tools",  # ← l3:3121（现网有「花园」l2:1583）
}

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify_name(value: str) -> str:
    """英文名 → slug；中文名无法生成时由调用方回退到 source_id。"""

    slug = _SLUG_RE.sub("-", (value or "").lower()).strip("-")
    return slug[:110]


def resolve_node(
    *,
    source_id: str,
    channel_id: str,
    name_zh: str,
    name_en: str,
    sort_order: int,
) -> dict | None:
    """返回一个 Joybuy 二级节点应落到哪个本地一级/二级；None = 不映射。"""

    clean_zh = (name_zh or "").strip()
    clean_en = (name_en or "").strip()
    if source_id in ACTIVITY_SOURCE_IDS:
        # 活动商品不是类目：不建本地二级，导入时标 Spu.is_activity。
        return {
            "source_id": source_id,
            "channel_id": channel_id,
            "parent_slug": "",
            "child_slug": "",
            "action": "activity",
            "name_zh": clean_zh or clean_en,
            "name_en": clean_en or clean_zh,
            "sort_order": int(sort_order or 0),
        }
    if source_id in NODE_UNMAPPED:
        return None
    parent_slug = NODE_PARENT.get(source_id) or CHANNEL_PARENT.get(channel_id)
    if not parent_slug:
        return None

    merge_slug = MERGE_INTO_EXISTING.get(source_id)
    if merge_slug:
        child_slug = merge_slug
        action = "merge"
    elif source_id in NODE_SLUG:
        child_slug = NODE_SLUG[source_id]
        action = "create"
    else:
        child_slug = slugify_name(name_en) or slugify_name(name_zh)
        if not child_slug:
            child_slug = source_id.replace(":", "-")
        action = "create"

    override = NAME_OVERRIDES.get(source_id)
    if override:
        clean_zh = override.get("zh") or clean_zh
        clean_en = override.get("en") or clean_en

    return {
        "source_id": source_id,
        "channel_id": channel_id,
        "parent_slug": parent_slug,
        "child_slug": child_slug,
        "action": action,
        "name_zh": clean_zh or clean_en,
        "name_en": clean_en or clean_zh,
        "sort_order": int(sort_order or 0),
    }
