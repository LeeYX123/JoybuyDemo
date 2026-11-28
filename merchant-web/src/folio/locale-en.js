// ---------------------------------------------------------------------------
// folio/locale-en.js — 商家端手机版「渲染后 DOM 本地化」字典。
//
// 键 = 静态稿渲染出的中文原文（文本节点或 placeholder/title/aria-label/alt 的
// 完整值），值 = 英文。带变量的文案不放进本表，统一由文件末尾的 PATTERNS
// 正则处理（例如「共 8353 件」→「8353 items」）。
//
// 分组：壳头 / 首页 / 店铺与商品 / 订单与详情 / 钱包 / 保证金 / 售后 /
// 活动与推荐 / 消息 / 通知 / 登录与店铺资料 / 表单与通用 / toast 与错误 /
// 状态与类型。
// ---------------------------------------------------------------------------

// 平台品类名（单独维护：既用于精确匹配，也用于「品类 · SKU 00001」等组合文案）
export const CATEGORIES = {
  全部品类: 'All categories',
  活动商品: 'Featured items',
  电子产品: 'Electronics',
  数码电子: 'Electronics',
  美妆个人护理: 'Beauty & Personal Care',
  健康与保健: 'Health & Wellness',
  计算机与配件: 'Computers & Accessories',
  服装与配饰: 'Clothing & Accessories',
  服饰箱包: 'Bags & Clothing',
  户外运动: 'Outdoor & Sports',
  运动户外: 'Sports & Outdoors',
  宠物用品: 'Pet Supplies',
  婴幼儿用品: 'Baby & Kids',
  游戏及配件: 'Gaming & Accessories',
  家居生活: 'Home & Living',
  小家电: 'Small Appliances',
  家用电器: 'Home Appliances',
  其他: 'Other',
  食品饮料: 'Food & Beverage',
  美妆: 'Beauty',
  女装: 'Women’s Clothing',
  男装: 'Men’s Clothing',
  箱包: 'Bags',
  鞋靴: 'Shoes',
  奢侈品: 'Luxury',
  户外用品: 'Outdoor Gear',
  节日商品: 'Holiday',
  电子数码: 'Electronics',
}

export const PHRASES = {
  // ---- 壳头 / 导航 ----
  寰: 'J',
  寰球优选: 'Joybuy Global',
  商家工作空间: 'Merchant Workspace',
  商家端: 'Merchant',
  商家中心: 'Merchant Center',
  商家服务中心: 'Merchant Service Center',
  '全球站 · 中国商家': 'Global · China Merchants',  '© 2026 寰球优选': '© 2026 Joybuy Global',
  经营看板: 'Business Overview',
  店铺管理: 'Shop Management',
  商品上架中心: 'Listing Center',
  订单管理: 'Orders',
  订单详情: 'Order details',
  钱包管理: 'Wallet',
  保证金管理: 'Deposit',
  售后中心: 'After-sales',
  平台活动中心: 'Campaigns',
  消息中心: 'Messages',
  平台通知中心: 'Notifications',
  '♧ 平台通知': '♧ Notifications',
  '♧ 联系客服': '♧ Support',
  切换去商城: 'Go to Store',
  切换店铺: 'Switch shop',
  编辑: 'Edit',
  返回: 'Back',
  关闭: 'Close',
  取消: 'Cancel',
  确定: 'OK',
  保存: 'Save',
  操作: 'Actions',
  全部: 'All',
  全部类型: 'All types',
  全部订单: 'All orders',
  全部通知: 'All',
  全部标记已读: 'Mark all read',
  已读: 'Read',
  未读: 'Unread',
  首页: 'Home',
  订单: 'Orders',
  商品: 'Products',
  钱包: 'Wallet',
  更多: 'More',
  '当前离线，可查看本地记录': 'Offline. Showing locally cached records.',  商家工作台: 'Merchant Workspace',
  商家工作台主导航: 'Merchant workspace navigation',
  选择语言: 'Language',
  简体中文: 'Simplified Chinese',
  English: 'English',

  // ---- 首页 / 经营面板 ----
  经营面板: 'Operations',
  店铺状态: 'Shop status',
  接单中: 'Accepting orders',
  今日订单: 'Orders today',
  今日曝光: 'Exposure today',
  总关注: 'Followers',
  完整经营面板: 'Full overview',
  今日订单数量: 'Orders today',
  待发货订单: 'Orders to ship',
  今日曝光度: 'Exposure today',
  店铺信誉分: 'Shop rating',
  业务模块: 'Modules',
  商品与经营: 'Products & Ops',
  店铺商品: 'Shop products',
  平台活动: 'Campaigns',
  资金管理: 'Funds',
  售后与沟通: 'After-sales & Support',
  平台通知: 'Notifications',
  联系平台客服: 'Contact support',
  订单品类占比: 'Category share',
  按店铺订单量统计: 'By order volume',
  近一周: 'Last 7 days',
  近一月: 'Last 30 days',
  总订单量: 'Total orders',
  笔: 'orders',
  次: 'views',
  订单数量: 'Orders',
  '单位：笔': 'Unit: orders',
  '单位：次': 'Unit: views',
  店铺曝光度: 'Shop exposure',
  店铺曝光量: 'Impressions',
  较昨日: 'vs yesterday',
  店铺经营状态正常: 'Shop is operating normally',
  资金安全保障中: 'Funds are protected',
  待处理订单: 'Pending orders',
  待发货订单请尽快履约: 'Please ship pending orders promptly',
  今日新增关注: 'New followers today',
  今日新增收益: 'Revenue today',
  今日回款: 'Payouts today',
  今日发货扣款: 'Shipping deductions today',
  今日扣款: 'Deductions today',
  当日新增展示: 'Impressions today',
  店铺与资产: 'Shop & assets',
  履约工作台: 'Fulfillment desk',
  经营总览: 'Business overview',
  统计: 'Statistics',
  店铺受限: 'Shop restricted',
  已封店: 'Suspended',
  正常: 'Normal',
  优秀: 'Excellent',
  首页看板: 'Dashboard',

  // ---- 店铺与商品 / 上架中心 ----
  搜索: 'Search',
  查询: 'Search',
  重置: 'Reset',
  分类: 'Category',
  商品分类: 'Category',
  本店商品: 'Shop products',
  平台商品: 'Platform products',
  成本价: 'Cost',
  零售价: 'Retail',
  已上架: 'Listed',
  可上架: 'Listable',
  上架商品: 'List',
  上架至我的店铺: 'List in my shop',
  上架至店铺: 'List in shop',
  点击上架: 'List now',
  上一页: 'Previous',
  下一页: 'Next',
  搜索商品: 'Search products',
  搜索商品名称: 'Search by product name',
  输入商品名称搜索: 'Search by product name',
  商品详情: 'Product details',
  商品ID: 'Product ID',
  商品品类: 'Category',
  商品描述: 'Description',
  商品名称: 'Product name',
  商品管理: 'Products',
  商品上架: 'List product',
  商品示意图: 'Product illustration',
  商品数量: 'Quantity',
  商品零售价: 'Retail price',
  商品成本价: 'Cost price',
  确认上架商品: 'Confirm listing',
  '确认将该商品上架至您的店铺？上架后可在「店铺管理」中查看。':
    'List this item in your shop? You can manage it in Shop Management.',
  确认上架: 'Confirm listing',
  该商品已上架: 'This product is already listed',
  商品已上架至您的店铺: 'Product listed in your shop',
  '店铺状态已变更，暂不支持上架': 'Shop status changed. Listing is unavailable.',  当前店铺状态暂不支持上架: 'Listing is unavailable for the current shop status',
  前往选品上架: 'Browse products to list',
  前往处理: 'Handle now',

  // ---- 订单 / 订单详情 ----
  待处理: 'Pending',
  待发货: 'To ship',
  已发货: 'Shipped',
  已完成: 'Completed',
  已收货成功: 'Received',
  已完成结算: 'Settled',
  发货: 'Ship',
  订单金额: 'Order amount',
  发货成本: 'Shipping cost',
  预估盈利: 'Est. profit',
  盈利: 'Profit',
  查看详情: 'View details',
  订单号: 'Order No.',
  数量: 'Qty',
  至: 'to',
  开始日期: 'Start date',
  结束日期: 'End date',
  '订单号 / 商品名称': 'Order No. / Product',
  暂无匹配订单: 'No matching orders',
  '暂无符合条件的订单，请尝试调整筛选条件。': 'No matching orders. Try adjusting the filters.',  订单履约进度: 'Fulfillment progress',
  待出库: 'To dispatch',
  查看全部进度: 'View full progress',
  全部进度: 'All progress',
  当前: 'Current',
  已出库: 'Dispatched',
  已揽收: 'Collected',
  运输中: 'In transit',
  到达网点: 'At local hub',
  到达目的地网点: 'At destination hub',
  派送中: 'Out for delivery',
  已签收: 'Delivered',
  用户确认收货: 'Buyer confirmed',
  收起进度: 'Collapse',
  等待上一节点完成: 'Waiting for the previous step',
  '商家已提交发货，等待仓库出库': 'Shipment submitted. Awaiting warehouse dispatch.',  仓库完成拣货与出库: 'Warehouse picked and dispatched',
  承运商已揽收包裹: 'Carrier collected the parcel',
  包裹正在跨境运输: 'Parcel is in cross-border transit',
  包裹已到达目的地网点: 'Parcel arrived at the destination hub',
  快递员正在派送: 'Courier is delivering',
  物流显示已签收: 'Tracking shows delivered',
  用户已确认收货成功: 'Buyer confirmed receipt',
  订单交易已完成: 'Order completed',
  货款进入回款流程: 'Payment is being settled',
  货款已入账商家钱包: 'Payment credited to your wallet',
  物流进度持续更新: 'Tracking updates continuously',
  '发货成本（合计）': 'Shipping cost (total)',  订单与商品信息: 'Order & product',
  标准款: 'Standard',
  订单编号: 'Order No.',
  下单时间: 'Order time',
  支付方式: 'Payment method',
  收件地区: 'Destination',
  成本合计: 'Total cost',
  回款后预估盈利: 'Est. profit after payout',
  确认发货: 'Confirm shipment',
  该订单已发货: 'Order already shipped',
  '该订单已发货，请勿重复提交': 'Order already shipped. Do not submit again.',  已完成发货: 'Shipped',
  '店铺已封店，请联系客服': 'Shop is suspended. Contact support.',  钱包余额不足: 'Insufficient balance',
  '请联系客服充值，平台确认入账后继续发货。':
    'Contact support to top up. Shipping resumes after the top-up is confirmed.',
  确认扣款并发货: 'Deduct and ship',
  物流与资金全链路: 'Tracking & payment timeline',
  等待商家发货: 'Awaiting shipment',
  订单尚未发货: 'Order not shipped yet',
  '确认发货后将显示物流与回款进度。':
    'Tracking and payout progress appear after shipment.',
  当前订单状态: 'Current order status',
  返回订单列表: 'Back to orders',
  返回评论: 'Back to review',
  订单查询记录: 'Order query history',
  当前用户无权确认此订单: 'This user cannot confirm the order',
  订单不存在: 'Order not found',

  // ---- 钱包 ----
  钱包余额: 'Balance',
  充值: 'Top up',
  提现: 'Withdraw',
  钱包安全: 'Wallet security',
  钱包密码未设置: 'Wallet PIN not set',
  钱包密码已设置: 'Wallet PIN set',
  设置钱包密码: 'Set wallet PIN',
  修改钱包密码: 'Change wallet PIN',
  重置钱包密码: 'Reset wallet PIN',
  钱包密码: 'Wallet PIN',
  当前钱包密码: 'Current PIN',
  新钱包密码: 'New PIN',
  确认密码: 'Confirm PIN',
  保存密码: 'Save PIN',
  资金明细: 'Transactions',
  资金类型: 'Fund type',
  订单回款: 'Order payout',
  订单发货: 'Order shipping',
  提现申请: 'Withdrawal',
  充值入账: 'Top-up',
  推荐返佣: 'Referral commission',
  申请提现: 'Request withdrawal',
  银行卡: 'Bank card',
  '银行卡（Visa / Mastercard）': 'Bank card (Visa / Mastercard)',
  数字货币链上转账: 'Crypto transfer',
  U地址: 'U address (USDT)',
  'U地址（USDT 收款地址）': 'U address (USDT)',
  银行名称: 'Bank name',
  银行卡号: 'Card number',
  姓名: 'Name',
  银行支行名称: 'Branch',
  支行编号: 'Branch code',
  '提现金额（CNY）': 'Amount (CNY)',
  提现金额: 'Amount',
  收款网络: 'Network',
  收款方式: 'Receiving method',
  收款信息: 'Receiving info',
  收款地址: 'Receiving address',
  请输入银行名称: 'Enter bank name',
  请输入银行卡号: 'Enter card number',
  请输入收款人姓名: 'Enter account holder',
  请输入银行支行名称: 'Enter branch name',
  请输入支行编号: 'Enter branch code',
  请输入提现金额: 'Enter amount',
  请输入完整收款地址: 'Enter the full receiving address',
  请输入开户人姓名: 'Enter account holder name',
  请输入6位数字密码: 'Enter a 6-digit PIN',
  请输入钱包密码: 'Enter wallet PIN',
  请再次输入密码: 'Re-enter PIN',
  验证钱包密码: 'Verify wallet PIN',
  确认提现: 'Confirm withdrawal',
  提现申请成功: 'Withdrawal submitted',
  提现申请已提交后台审核: 'Withdrawal submitted for review',
  提现申请记录: 'Withdrawal requests',
  提现处理明细: 'Withdrawal details',
  处理明细: 'Details',
  银行收款信息: 'Bank details',
  '申请单号 / 时间': 'Request / Time',
  '关联订单 / 单号': 'Order / Ref',
  金额变动: 'Amount',
  账户: 'Account',
  来源说明: 'Notes',
  当前钱包余额: 'Current balance',
  可用余额: 'Available balance',
  可提现余额: 'Available balance',
  冻结金额: 'Frozen amount',
  待审核: 'Under review',
  已打回: 'Rejected',
  审核通过: 'Approved',
  转账中: 'Transferring',
  转账成功: 'Transfer succeeded',
  已到账: 'Credited',
  转账失败: 'Transfer failed',
  申请金额: 'Requested amount',
  申请金额已冻结: 'Amount frozen',
  '申请金额已冻结，等待后台审核': 'Amount frozen, awaiting review',  '申请已打回，冻结资金已退回': 'Rejected. Frozen funds returned.',  '审核通过，转账完成': 'Approved. Transfer completed.',  发货扣款: 'Shipping deduction',
  提现记录: 'Withdrawal',
  平台处罚扣款: 'Platform penalty',
  调整: 'Adjustment',
  发货成本扣除: 'Shipping cost deducted',
  订单发货成本: 'Order shipping cost',
  订单发货成本扣除: 'Order shipping cost deducted',
  钱包校验: 'Wallet check',
  余额充足: 'Sufficient balance',
  余额不足: 'Insufficient balance',
  请输入大于0且不超过可用余额的金额: 'Enter an amount greater than 0 and within your available balance',
  请输入12至22位银行卡号: 'Enter a 12–22 digit card number',
  请填写开户人姓名: 'Enter the account holder name',
  请核实收款地址格式: 'Check the receiving address format',
  '请输入不超过可用余额的有效金额，最多两位小数':
    'Enter a valid amount within your balance, up to 2 decimals',
  '请完整填写银行名称、姓名、支行名称及支行编号':
    'Complete bank name, holder, branch and branch code',
  钱包密码必须为6位数字: 'Wallet PIN must be 6 digits',
  两次输入的密码不一致: 'PINs do not match',
  当前钱包密码不正确: 'Current PIN is incorrect',
  '钱包密码不正确，请重新输入': 'Incorrect PIN. Try again.',  '可用余额已变更，请重新申请': 'Available balance changed. Submit a new request.',  '验证失败，请重试': 'Verification failed. Try again.',  '密码保存失败，请使用新版 Chrome 或 Edge 重试':
    'Failed to save PIN. Use a recent Chrome or Edge.',
  '您尚未设置钱包密码，请先设置后再申请提现。':
    'Set a wallet PIN before requesting a withdrawal.',
  '提现前需验证钱包密码，保护资金操作。':
    'Withdrawal requires PIN verification to protect your funds.',
  '此密码用于提现验证，请妥善保管；忘记密码可联系平台客服重置。':
    'This PIN is used for withdrawals. Keep it safe; contact support to reset it.',
  本次申请提现: 'Withdrawal request',
  '连续输错5次，已锁定15分钟': 'Too many attempts. Locked for 15 minutes.',  '钱包密码已锁定，请15分钟后重试或找回密码':
    'PIN locked. Try again in 15 minutes or reset it.',
  钱包密码校验通过: 'PIN verified',
  '钱包密码验证通过，提交申请': 'PIN verified. Request submitted.',  提现金额不足: 'Withdrawal amount too low',
  '提现金额超出钱包余额，当前可提现余额为':
    'Amount exceeds the current available balance: ',
  暂无匹配记录: 'No matching records',
  '可用余额 · 待审冻结': 'Available · frozen pending review',
  交易时间: 'Transaction time',
  交易类型: 'Type',
  时间: 'Time',
  金额: 'Amount',
  扣款账户: 'Debit account',
  操作人: 'Operator',

  // ---- 保证金 ----
  保证金: 'Deposit',
  保证金余额: 'Deposit balance',
  保证金明细: 'Deposit records',
  保证金规则: 'Deposit rules',
  保证金账户: 'Deposit account',
  保证金状态: 'Deposit status',
  保证金未启用: 'Deposit not enabled',
  本店无需缴纳保证金: 'No deposit required for this shop',
  '不参与保证金缴纳、扣罚与补缴流程。平台关闭该规则后不可再次开启。':
    'This shop does not participate in deposit payment, penalties or top-ups. This cannot be re-enabled once disabled.',
  应缴保证金: 'Required deposit',
  待缴保证金: 'Deposit due',
  待缴金额: 'Amount due',
  已缴纳: 'Paid',
  '未启用保证金，不执行保证金扣罚与补缴。':
    'Deposit is disabled; no deposit penalties or top-ups apply.',
  '按平台为店铺配置的规则展示保证金信息。':
    'Deposit information follows the rules configured for your shop.',
  '查看平台为您的店铺配置的履约保障规则。':
    'View the fulfillment guarantee rules configured for your shop.',
  由平台按商家单独配置: 'Configured by the platform per merchant',
  由平台按商家配置: 'Configured by the platform per merchant',
  预览保证金状态: 'Preview deposit status',
  暂无保证金明细: 'No deposit records',
  当前状态: 'Current status',
  是否启用保证金: 'Deposit enabled',
  启用示例: 'Enable example',
  关闭示例: 'Disable example',
  封店示例: 'Suspend example',
  接单示例: 'Accept orders example',
  已启用: 'Enabled',
  未设置: 'Not set',
  已设置: 'Set',
  '保证金余额为0或负数，请联系客服补缴保证金，并由客服手动解封。':
    'Deposit balance is zero or negative. Contact support to top up and unblock manually.',
  处罚扣款优先使用保证金: 'Penalties are deducted from the deposit first',

  // ---- 售后 ----
  全部售后: 'All after-sales',
  用户投诉: 'Complaint',
  退货订单: 'Return',
  处理中: 'Processing',
  等待商家响应: 'Awaiting merchant response',
  售后单号: 'After-sales No.',
  关联订单: 'Related order',
  关联单号: 'Related ref',
  关联订单号: 'Related order No.',
  处理售后: 'Handle',
  售后处理: 'After-sales handling',
  售后处理详情: 'After-sales details',
  售后处理规则: 'After-sales rules',
  售后状态: 'Status',
  售后类型: 'Type',
  当前处理进度: 'Current progress',
  状态: 'Status',
  当前进度: 'Current progress',
  凭证: 'Evidence',
  暂无凭证: 'No evidence',
  上传凭证: 'Upload evidence',
  处理说明: 'Notes',
  处理记录: 'History',
  更新进度: 'Update progress',
  申请平台介入: 'Escalate to platform',
  完成处理: 'Complete',
  填写处理依据或最终结果: 'Enter findings or final result',
  填写处理进度或反馈: 'Enter progress or feedback',
  暂无该类型的售后记录: 'No after-sales records of this type',
  '类型 / 问题': 'Type / Issue',
  问题: 'Issue',
  类型: 'Type',
  原因: 'Reason',
  说明: 'Notes',
  商家受理: 'Merchant accepted',
  商家完成处理: 'Merchant completed',
  商家更新进度: 'Merchant updated progress',
  '客户确认解决，售后关闭': 'Buyer confirmed resolution; case closed',  客户问题: 'Buyer issue',
  物流信息咨询: 'Shipping inquiry',
  物流咨询: 'Shipping inquiry',
  '催促发货，咨询预计发货时间': 'Shipping reminder: asking for the estimated ship date',  商品外包装损坏: 'Outer packaging damaged',
  反馈外包装破损: 'Reported outer packaging damage',
  售前收货异常: 'Pre-delivery receipt issue',
  请填写处理说明: 'Enter handling notes',
  请填写打回原因: 'Enter the rejection reason',
  请填写申请介入的原因: 'Enter the reason for escalation',
  请选择后续进度节点: 'Select the next progress step',
  已更新售后进度: 'After-sales progress updated',
  平台介入: 'Platform intervention',
  平台介入中: 'Platform intervention in progress',
  等待平台核实: 'Awaiting platform verification',
  平台核实通过: 'Platform verified',
  核实通过: 'Verified',
  核实物流破损责任: 'Verify shipping damage responsibility',
  要求补充包装照片: 'More packaging photos required',
  处理订单: 'Handle order',
  '凭证保存失败，请缩小图片': 'Failed to save evidence. Try a smaller image.',  '请选择2MB以内的 JPG、PNG 或 WebP 图片':
    'Choose a JPG, PNG or WebP image under 2 MB.',
  请选择1MB以内图片: 'Choose an image under 1 MB.',

  // ---- 活动 / 推荐 ----
  常驻活动: 'Ongoing',
  限时活动: 'Limited-time',
  推荐新商家入驻: 'Refer a merchant',
  '推荐新人开店，按月发货成功金额享阶梯返佣':
    'Refer new merchants and earn tiered commission on monthly shipped GMV',
  查看推荐码与返佣: 'View referral code & commission',
  查看活动: 'View campaign',
  参与活动: 'Join campaign',
  已参与: 'Joined',
  开放参与: 'Open to join',
  即将开始: 'Starting soon',
  尚未开始: 'Not started',
  长期有效: 'Always active',
  我的推荐码: 'My referral code',
  复制推荐码: 'Copy code',
  推荐码: 'Referral code',
  推荐码已复制: 'Referral code copied',
  返佣规则: 'Commission rules',
  新人当月发货成功金额: 'New merchant monthly shipped GMV',
  返佣比例: 'Commission rate',
  我推荐的新商家: 'Referred merchants',
  店铺名称: 'Shop name',
  店铺ID: 'Shop ID',
  审核通过时间: 'Approved at',
  暂无通过审核的新商家: 'No approved referrals yet',
  推荐与返佣明细: 'Referral & commission details',
  月份: 'Month',
  新人商家: 'Referred merchant',
  发货成功金额: 'Shipped GMV',
  比例: 'Rate',
  返佣金额: 'Commission',
  核算日期: 'Calculated on',
  到账时间: 'Credited at',
  参与时间: 'Joined at',
  参与记录: 'Participation',
  活动名称: 'Campaign',
  活动类型: 'Type',
  活动时间: 'Period',
  活动中心: 'Campaigns',
  已记录参与意向: 'Interest recorded',
  已记录活动参与意向: 'Campaign interest recorded',
  暂无该类型的活动: 'No campaigns of this type',
  推荐码已复制到剪贴板: 'Referral code copied',
  '按每位新人月发货成功金额匹配档位，整月金额 × 对应比例。返佣期 12 个月，每月1日核算上月返佣，7个工作日内由客服确认发放至钱包。':
    'Tiers are based on each new merchant’s monthly shipped GMV; the full month’s GMV is multiplied by the matching rate. The referral period is 12 months, commissions are calculated on the 1st of each month and credited to your wallet by support within 7 business days.',
  '参与年度购物盛典，获取活动专区与精选资源位曝光。':
    'Join the annual shopping festival for campaign-zone and featured placement exposure.',
  '参与活动，获得平台活动资源位与额外曝光。':
    'Join campaigns for platform placement and extra exposure.',
  '限时活动，结束时间到期后自动转为已结束。':
    'Limited-time campaign; ends automatically when the end date passes.',
  '常驻活动，参与后在商城活动页获得额外曝光。':
    'Ongoing campaign; join for extra exposure on the storefront campaign page.',
  '面向家居生活品类，精选冬日好物，连接品质生活。':
    'Selected winter home & living picks for a better everyday life.',
  全球品质好物计划: 'Global Quality Picks Program',
  双十一全球好物节: 'Global Shopping Festival',
  冬日家居焕新季: 'Winter Home Refresh',
  数码好物精选计划: 'Digital Picks Program',
  '把握平台运营机会，让店铺获得更多曝光。':
    'Take part in platform campaigns to gain more exposure.',
  '参与平台活动，让全球好物被更多人看见。':
    'Join platform campaigns so more shoppers discover your products.',

  // ---- 消息 / 客服 ----
  会话列表: 'Conversations',
  客服中心: 'Support Center',
  '平台专属客服 · 单独联系': 'Dedicated platform support',
  平台客服专属会话: 'Platform support chat',
  '服务时间：09:00–21:00': 'Hours: 09:00–21:00',
  平台客服专属沟通记录: 'Platform support history',
  用户会话记录: 'Conversation history',
  商品咨询会话: 'Product inquiry',
  用户通过此商品联系商家: 'Buyer contacted you about this product',
  发送消息: 'Send',
  发送: 'Send',
  发送回复: 'Send reply',
  输入消息: 'Enter a message',
  '输入回复内容…（Ctrl+Enter 发送）': 'Reply… (Ctrl+Enter to send)',  请输入消息内容: 'Enter a message',
  请输入回复内容: 'Enter a reply',
  '全球商家服务 · 请使用清晰、友好的沟通方式':
    'Global merchant service · Please communicate clearly and politely',
  仅与平台客服联系: 'Platform support only',
  '请使用清晰、友好的沟通方式': 'Please communicate clearly and politely',  '与全球用户保持沟通，及时响应每一次咨询。':
    'Stay in touch with global shoppers and respond to every inquiry.',
  '用户咨询与平台客服，集中沟通处理。':
    'Buyer inquiries and platform support in one place.',
  商: 'M',
  客: 'C',
  消息: 'Messages',

  // ---- 通知 ----
  '关注系统经营提醒、评价与平台规则通知。':
    'System alerts, reviews and platform policy notices.',
  暂无通知: 'No notifications',
  重要: 'Important',
  催发货: 'Shipping reminder',
  订单提醒: 'Order alert',
  活动通知: 'Campaign notice',
  处罚通知: 'Penalty notice',
  解封结果: 'Unblock result',
  其他通知: 'Other',
  '重要经营事项，及时掌握。': 'Stay on top of important business matters.',  查看通知: 'View notice',
  '全部通知 →': 'All notifications →',  未读通知: 'Unread notification',

  // ---- 登录 / 店铺资料 ----
  '寰球优选 · 商家端手机版，请使用商家账号登录':
    'Joybuy Global · Merchant mobile. Sign in with your merchant account.',
  邮箱: 'Email',
  密码: 'Password',
  请输入商家账号邮箱: 'Enter merchant email',
  请输入密码: 'Enter password',
  登录: 'Sign in',
  退出登录: 'Sign out',
  '登录失败，请稍后再试。': 'Sign-in failed. Please try again later.',  该账号还没有绑定店铺: 'No shop is linked to this account',
  '请联系平台客服完成店铺入驻与绑定后再登录。':
    'Contact platform support to complete onboarding and linking, then sign in again.',
  编辑店铺资料: 'Edit shop profile',
  店铺资料: 'Shop profile',
  店铺头像: 'Shop avatar',
  上传头像: 'Upload avatar',
  恢复默认: 'Reset',
  新头像预览: 'New avatar preview',
  请输入1至30字的店铺名称: 'Enter a shop name of 1–30 characters',
  '头像存储失败，请使用更小的图片后重试':
    'Failed to store avatar. Try a smaller image.',
  店铺资料已更新: 'Shop profile updated',
  '店铺 ID 由平台分配，不可修改。': 'Shop ID is assigned by the platform and cannot be changed.',
  复制店铺ID: 'Copy shop ID',
  '复制店铺 ID': 'Copy shop ID',  店铺ID已复制: 'Shop ID copied',
  '复制失败，请手动复制店铺ID': 'Copy failed. Please copy the shop ID manually.',  已切换店铺: 'Shop switched',

  // ---- 联系客服弹层 ----
  '寰球优选 · 商家专属服务': 'Joybuy Global · Merchant support',
  '服务时间：每日 09:00–21:00（北京时间）':
    'Hours: 09:00–21:00 daily (Beijing time)',
  '可咨询：钱包充值、保证金补缴、商品下架、解封申请。':
    'Topics: wallet top-up, deposit top-up, delisting, unblocking requests.',
  '当前为 UI 演示，未连接真实客服系统。':
    'UI demo only; not connected to a live support system.',
  联系客服: 'Contact support',
  联系客服充值: 'Contact support to top up',
  联系客服缴纳: 'Contact support to pay',
  联系客服补缴: 'Contact support to top up',
  '充值请联系客服。提现申请提交后台审核，审核打回时将展示原因并退回冻结金额。':
    'Contact support to top up. Withdrawals are reviewed; if rejected, the reason is shown and frozen funds are returned.',

  // ---- 通用按钮 / 表单 ----
  提交: 'Submit',
  提交回复: 'Submit reply',
  提交审核: 'Submit for review',
  提交找回申请: 'Submit reset request',
  删除: 'Delete',
  查看: 'View',
  处理: 'Handle',
  标记处理中: 'Mark processing',
  完成: 'Complete',
  打回: 'Reject',
  确认打回: 'Confirm rejection',
  确认到账: 'Confirm receipt',
  开始转账: 'Start transfer',
  演示处理: 'Demo handling',
  演示审核通过: 'Demo approval',
  演示审核打回: 'Demo rejection',
  演示后台审核打回: 'Demo backend rejection',
  忘记密码: 'Forgot PIN',
  找回密码: 'Reset PIN',
  找回钱包密码: 'Reset wallet PIN',
  方式: 'Method',
  总数: 'Total',
  合计: 'Total',
  小计: 'Subtotal',
  零售合计: 'Retail total',
  预计毛利: 'Est. gross profit',
  变动金额: 'Amount change',
  调整后总数: 'Adjusted total',
  新增: 'Add',
  手动新增: 'Add manually',
  输入新增数量: 'Enter quantity to add',
  可重置: 'Resettable',
  未记录: 'Not recorded',
  未知: 'Unknown',
  '—': '—',
  暂无: 'None',
  收起: 'Collapse',
  展开: 'Expand',
  全部已读: 'All read',
  查看结果: 'View result',
  查看订单: 'View order',
  查看钱包: 'Wallet',
  查看待处理订单: 'View pending orders',
  '查看客户问题，跟进售后处理进度。':
    'View buyer issues and track after-sales progress.',
  '集中处理用户投诉与退货订单，持续跟进处理进度。':
    'Handle complaints and returns, and track progress in one place.',
  '每一笔资金流转，清晰可查。': 'Every fund movement, clearly traceable.',  '资金变动透明可查，安全管理每笔收支。':
    'Transparent fund movements with secure management of every transaction.',
  '从下单到结算，全流程掌握每笔订单。':
    'Manage every order from checkout to settlement.',
  '及时处理订单，保障履约效率与经营体验。':
    'Process orders promptly to protect fulfillment and service quality.',
  '从平台商品池精选好物，快速上架至您的店铺。':
    'Pick products from the platform catalog and list them in your shop.',
  '从平台商品池自主选品，拓展您的全球商品矩阵。':
    'Source products from the platform catalog to expand your global range.',
  '管理本店已上架商品，查看商品信息与销售价格。':
    'Manage listed products, details and prices.',
  '优质商品常态曝光，持续为店铺引入全球客流。':
    'Quality products get steady exposure and global traffic.',
  '连接全球生意，从掌握每一个经营信号开始。':
    'Grow globally by staying on top of every business signal.',

  // ---- toast / 错误 ----
  商城地址未配置: 'Store URL is not configured',
  '切换失败，请稍后重试': 'Switch failed. Please try again.',  '发货成功，订单进入待出库阶段':
    'Shipped. Order is now awaiting dispatch.',
  发货成功: 'Shipped',
  '发货成功，成本已从钱包扣除': 'Shipped. Cost deducted from wallet.',  提现申请已提交后台审核: 'Withdrawal submitted for review',
  '回复已提交，可在评价详情中查看':
    'Reply submitted. You can view it in the review details.',
  回复已发送: 'Reply sent',
  回复不能超过500字: 'Reply cannot exceed 500 characters',
  请输入1至1000字回复: 'Enter a reply of 1–1000 characters',
  开始日期不能晚于结束日期: 'Start date cannot be after end date',
  '已有节点时间晚于当前时间，请先调整':
    'An existing step is later than the current time. Adjust it first.',
  '订单超时未处理，请联系客服解封。':
    'Order overdue. Contact support to unblock the shop.',
  '订单超时未处理 · 历史封店处罚':
    'Order overdue · historical suspension penalty',
  '封店处罚为500元，启用保证金时按规则扣除。':
    'Suspension penalty is ¥500, deducted from the deposit when enabled.',
  '历史封店处罚 · 保证金扣除': 'Historical suspension penalty · deposit deduction',
  '历史履约处罚通知 · 保证金扣除500元':
    'Historical fulfillment penalty · ¥500 deposit deduction',
  '处罚金额：500元 · 扣款来源：保证金。余额不足时须先补缴。':
    'Penalty: ¥500 · Source: deposit. Top up first if the balance is insufficient.',
  订单超时未处理: 'Order overdue',
  平台履约规则与保证金扣罚说明:
    'Platform fulfillment rules and deposit penalties',
  '您的店铺已恢复接单，请及时处理订单。':
    'Your shop can accept orders again. Please process orders promptly.',
  保证金余额不足: 'Insufficient deposit balance',
  '当前店铺状态暂不支持发货，请联系客服':
    'Shipping is unavailable for the current shop status. Contact support.',
  店铺尚未满足经营条件: 'Shop does not yet meet operating requirements',
  '店铺核验资料不完整，请联系客服补充':
    'Shop verification is incomplete. Contact support.',
  申请解封: 'Request unblock',
  解封审核中: 'Unblock under review',
  '解封申请已提交，等待平台审核':
    'Unblock request submitted, awaiting platform review',
  等待平台核实店铺资料: 'Awaiting platform verification of shop details',
  '请尽快核实订单并处理发货。超时未处理订单将进入平台履约监管流程。':
    'Verify and ship orders promptly. Overdue orders enter platform fulfillment review.',

  // ---- 状态 / 类型 ----
  全部消息: 'All messages',
  已记录: 'Recorded',
  已通过: 'Approved',
  通过: 'Approved',
  待发放: 'To be paid',
  待核算: 'To be calculated',
  计日: 'Today',
  计入今日: 'Counted today',
  非今日: 'Not today',
  当天: 'Today',
  结算: 'Settlement',
  封: 'Suspended',
  待: 'Pending',
  待缴: 'Due',
  已关闭: 'Closed',
  审核中: 'Under review',
  尚未申请: 'Not applied',
  已解冻退回: 'Unfrozen and returned',
  未扣款: 'Not deducted',
  未创建物流单: 'No shipment created',
  '校验未通过，未扣款、未创建物流单':
    'Verification failed. No deduction and no shipment created.',
  '确认前余额变化，未扣款': 'Balance changed before confirmation. Nothing deducted.',  '请求失败，未扣款，可重新发货':
    'Request failed. Nothing deducted; you can ship again.',
  '校验未通过，未扣款': 'Verification failed. Nothing deducted.',  '钱包校验失败，未扣款': 'Wallet check failed. Nothing deducted.',  '收款渠道返回失败，请核对收款账户':
    'Payment channel failed. Check the receiving account.',
  收款账户状态异常: 'Receiving account status is abnormal.',
  '收款资料不完整，请补充后重新申请':
    'Receiving details are incomplete. Complete them and resubmit.',
  '收款地址与所选网络不匹配，请核实后重新提交。':
    'Receiving address does not match the selected network. Check and resubmit.',
  '请输入正确的 ERC-20 钱包地址': 'Enter a valid ERC-20 address',  '请输入正确的 TRC-20 钱包地址': 'Enter a valid TRC-20 address',  请选择币种: 'Select a currency',
  请选择链类型: 'Select a network',
  币种: 'Currency',
  链类型: 'Network',
  'ETH 请选择 ERC-20 链': 'ETH — select the ERC-20 network',
  '（示例结算快照）': '(example settlement snapshot)',
  示例结算快照: 'Example settlement snapshot',
}

// 由字典自动生成「英文 → 中文」反向表（只用于少数需要在 JS 侧把英文还原为
// 中文的场景；DOM 还原主要依赖节点上保存的中文原文）。
export const EN_TO_ZH = (() => {
  const reverse = new Map()
  for (const [zh, en] of Object.entries(PHRASES)) {
    if (!reverse.has(en)) reverse.set(en, zh)
  }
  for (const [zh, en] of Object.entries(CATEGORIES)) {
    if (!reverse.has(en)) reverse.set(en, zh)
  }
  return reverse
})()

function cat(value) {
  return CATEGORIES[value] || PHRASES[value] || value
}

function plural(n, singular, pluralForm) {
  const num = String(n).replace(/,/g, '')
  return `${n} ${Number(num) === 1 ? singular : pluralForm}`
}

function shortCat(text) {
  // 「家居生活77%，小家电23%」这类图表 aria-label：逐段翻译品类前缀。
  return text
    .split(/，/)
    .map((part) => {
      const m = part.match(/^(.*?)([\d.]+%)$/)
      return m ? `${cat(m[1].trim())}${m[2]}` : part
    })
    .join(', ')
}

// 带变量的文案：先匹配完整字符串，再输出英文。回调返回 null 表示不匹配，
// 引擎会继续尝试下一条。
export const PATTERNS = [
  // 分页 / 计数
  [/^共 ([\d,]+) 件$/, (m) => `${m[1]} items`],
  [/^共 ([\d,]+) 条记录$/, (m) => `${m[1]} records`],
  [/^已上架 ([\d,]+) 件商品$/, (m) => `${m[1]} products listed`],
  [/^第 (\d+) \/ (\d+) 页$/, (m) => `Page ${m[1]} / ${m[2]}`],
  [/^(\d+) 个会话$/, (m) => plural(m[1], 'conversation', 'conversations')],
  [/^(\d+) 条未读$/, (m) => plural(m[1], 'unread', 'unread')],
  [/^共 ([\d,]+) 条$/, (m) => `${m[1]} records`],
  [/^第(\d+)周$/, (m) => `Week ${m[1]}`],

  // 首页指标 / 图表
  [/^近7天累计 ([\d,]+) 笔$/, (m) => `Last 7 days: ${plural(m[1], 'order', 'orders')}`],
  [/^近7天累计 ([\d,]+) 次$/, (m) => `Last 7 days: ${plural(m[1], 'view', 'views')}`],
  [/^([\d,]+) 笔$/, (m) => plural(m[1], 'order', 'orders')],
  [/^([\d,]+) 次$/, (m) => plural(m[1], 'view', 'views')],
  [/^(\d{1,2}\/\d{1,2})，([\d,]+) 笔$/, (m) => `${m[1]}, ${plural(m[2], 'order', 'orders')}`],
  [/^(\d{1,2}\/\d{1,2})，([\d,]+) 次$/, (m) => `${m[1]}, ${plural(m[2], 'view', 'views')}`],
  [/^(?:[^，]+?\d+%[，])+[^，]+?\d+%$/, (m) => shortCat(m[0])],
  [/^(\d+) 笔待发货$/, (m) => `${plural(m[1], 'order', 'orders')} to ship`],

  // 组合文案：品类 · SKU / 数量 / 标准款
  [/^(.+?) · SKU (\d+)$/, (m) => `${cat(m[1])} · SKU ${m[2]}`],
  [/^(.+?) · 数量 × (\d+)$/, (m) => `${cat(m[1])} · Qty × ${m[2]}`],
  [/^(.+?) · 标准款$/, (m) => `${cat(m[1])} · Standard`],
  [/^(.+?) · (\d+) 个会话$/, (m) => `${m[1]} · ${plural(m[2], 'conversation', 'conversations')}`],
  [/^(.+?)，平台精选(.+?)商品，标准款。$/, (m) => `${m[1]}, a platform-selected ${cat(m[2].trim())} item, standard edition.`],

  // 订单 / 金额
  [/^订单 (.+)$/, (m) => `Order ${m[1]}`],
  [/^订单编号[:：]?\s*(.+)$/, (m) => `Order No. ${m[1]}`],
  [/^下单时间[:：]?\s*(.+)$/, (m) => `Order time ${m[1]}`],
  [/^商家编号[:：]?\s*(.*)$/, (m) => `Merchant ID ${m[1]}`.trim()],
  [/^商品ID[:：]\s*(.+)$/, (m) => `Product ID: ${m[1]}`],
  [/^商品数量[:：]\s*(\d+)$/, (m) => `Quantity: ${m[1]}`],
  [/^数量 × (\d+)$/, (m) => `Qty × ${m[1]}`],
  [/^本次发货扣款[:：]\s*(.*)$/, (m) => `Shipping deduction: ${m[1]}`.trim()],
  [/^扣款后钱包余额[:：]\s*(.*)$/, (m) => `Balance after deduction: ${m[1]}`.trim()],
  [/^关联订单[:：]?\s*(.*)$/, (m) => `Related order ${m[1]}`.trim()],
  [/^关联订单号[:：]?\s*(.*)$/, (m) => `Related order No. ${m[1]}`.trim()],
  [/^可提现余额\s*(.*)$/, (m) => `Available balance ${m[1]}`.trim()],
  [/^可用余额 · 待审冻结 (.*)$/, (m) => `Available · frozen pending review ${m[1]}`],
  [/^扣款流水 (.+?) · 物流单 (.+)$/, (m) => `Deduction ${m[1]} · Tracking ${m[2]}`],

  // 活动 / 返佣
  [/^活动时间[:：]\s*(.+)$/, (m) => `Period: ${m[1] === '长期有效' ? 'Always active' : m[1]}`],
  [/^¥\s*([\d,]+) 起，低于 ¥\s*([\d,]+)$/, (m) => `From ¥${m[1]}, below ¥${m[2]}`],
  [/^¥\s*([\d,]+) 起$/, (m) => `From ¥${m[1]}`],
  [/^(\d+) 件商品$/, (m) => `${m[1]} products`],
  [/^(\d+) 件$/, (m) => `${m[1]} items`],
  [/^(\d+) 星评价$/, (m) => `${m[1]}-star review`],
  [/^(\d+)\/500$/, (m) => `${m[1]}/500`],

  // 通知 / 会话 aria
  [/^未读通知[:：]\s*(.+)$/, (m) => `Unread notification: ${m[1]}`],
  [/^查看(.+)详情$/, (m) => `View ${m[1]} details`],
  [/^选择语言，当前为(.+)$/, (m) => `Language: ${cat(m[1])}`],
  [/^商品分类，当前为(.+)$/, (m) => `Category: ${cat(m[1])}`],
  [/^资金类型，当前为(.+)$/, (m) => `Fund type: ${cat(m[1])}`],
  [/^(.+)，当前为(.+)$/, (m) => `${cat(m[1])}: ${cat(m[2])}`],
  [/^订单管理，(.+)$/, (m) => `Orders, ${m[1]}`],
  [/^消息中心，(.+)$/, (m) => `Messages, ${m[1]}`],
  [/^平台通知，(.+)$/, (m) => `Notifications, ${m[1]}`],
  [/^暂无(?:已读|未读)?通知$/, () => 'No notifications'],
  [/^暂无(.*)$/, (m) => `No ${m[1] || 'records'}`],

  // 日期（保留数字，去掉中文年月日/星期）
  [
    /^(\d{4})年(\d{1,2})月(\d{1,2})日(?: · (.*))?$/,
    (m) => `${m[1]}-${String(m[2]).padStart(2, '0')}-${String(m[3]).padStart(2, '0')}${m[4] ? ` · ${m[4]}` : ''}`,
  ],
  [
    /^(\d{4})年(\d{1,2})月(\d{1,2})日\s*(星期[日一二三四五六])$/,
    (m) => `${m[1]}-${String(m[2]).padStart(2, '0')}-${String(m[3]).padStart(2, '0')} ${({ 星期日: 'Sunday', 星期一: 'Monday', 星期二: 'Tuesday', 星期三: 'Wednesday', 星期四: 'Thursday', 星期五: 'Friday', 星期六: 'Saturday' })[m[4]] || m[4]}`,
  ],
  [/^昨天 (.*)$/, (m) => `Yesterday ${m[1]}`],
  [/^刚刚$/, () => 'Just now'],
]

// 精准翻译（精确字典 → 品类 → 正则）。返回 null 表示没有命中。
export function translateZh(text) {
  if (Object.prototype.hasOwnProperty.call(PHRASES, text)) return PHRASES[text]
  if (Object.prototype.hasOwnProperty.call(CATEGORIES, text)) return CATEGORIES[text]
  for (const [re, replacer] of PATTERNS) {
    const m = text.match(re)
    if (m) {
      const out = replacer(m)
      if (out != null) return out
    }
  }
  return null
}

// 反向翻译（英文 → 中文），仅用于 JS 主动构造文案时的兜底。
export function translateEn(text) {
  return EN_TO_ZH.get(text) || null
}
