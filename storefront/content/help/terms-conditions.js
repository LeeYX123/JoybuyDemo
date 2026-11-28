// 批次 Q（需求 15.1 / 15.2）：真站 help 中心「Terms of Sale」页正文。
// 来源：2026-11-20 Playwright 实测真站对应 help 页（批次 Q 抓取，原始数据见 var/policy_help_20261120/）。
// 批次 S 追加（用户 2026-11-20 口径）：正文中所有真站网址 → www.joyfumi.com（保留路径结构）；
// 公司名 / 地址 / 注册号 / 监管表述与邮箱不变。
//（原始抓取 var/policy_help_20261120/content_{en_GB,zh_CN}_terms-conditions.json；
//  zh 为真站自带中文版，非机器翻译）。
// 口径：除邮箱 → Joybuyfumi@gmail.com 外，全文照抄真站（公司名 / 地址 / 注册号 /
// 监管表述 / 章节 / 表格 / 生效日期均保持原文）。块结构：p{segments} + table{rows}；
// segments 内 t=文本、b=粗体、i=斜体、href=链接、br=换行（真站正文用 <br> 分行）。
const en = [
  {
    type: 'p',
    segments: [
      {
        t: 'Updated 13 March 2026',
        i: 1,
        u: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Terms of Sale',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'We greatly appreciate your choice to become a customer of Joybuy and enjoy our products and services!',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Please see details on order and payments, account settings, shipping and delivery, and after-sales services and policies from Joybuy customer service portal by ',
      },
      {
        t: '',
        href: 'https://www.joyfumi.com/hc/en-us',
      },
      {
        t: 'clicking here',
        href: 'https://www.joyfumi.com/customer-service-centre',
      },
      {
        t: '.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'These terms of sale (‘Terms of Sale’) explain the terms which apply when you create an account or order any products from our website ',
      },
      {
        t: 'www.joyfumi.com',
        href: 'https://www.joyfumi.com',
      },
      {
        t: ' or on our mobile application (together the ‘Joybuy Site’).',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'We reserve the right to make changes to these Terms of Sale. The Terms of Sale applicable to the purchase of your product(s) will be the Terms of Sale available on the Joybuy Site at the time you order the product from us.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'You should read these Terms of Sale carefully before creating an account with us.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'These Terms of Sale were last updated on 13th March 2026.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Who we are and how to contact us',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'We are Jingdong Retail (UK) Limited trading as ‘Joybuy’. We are a company registered in England and Wales under company number 15830555. Our registered office is at Floor 3, 20 King Street, London, and our VAT number is 481236788.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'If you need to contact us for any reason, including if you have a complaint, if your order has not arrived, or if the products are damaged or faulty, then you can contact us by:',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '· Email - ',
      },
      {
        t: 'Joybuyfumi@gmail.com',
        href: 'mailto:Joybuyfumi@gmail.com',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '· LiveChat - using our customer service chat feature available on the Joybuy Site.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Your account',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'You must be over the age of 18 years old to create a Joybuy account and place an order.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'You confirm that all information and details provided by you are true, accurate, and up to date.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'When you create an account with us, you will need to create a password and may have to provide your credit card details. It is your responsibility to maintain the security and confidentiality of your login details and prevent others from accessing your email account or mobile device. We will not be liable to you or any other person for any loss or damage which may arise a result of any failure by you to protect your login information.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'If you become aware of any unauthorised use of your account or your password being compromised, please contact us immediately.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'We reserve the right to terminate or suspend your account at any time at our discretion, including but not limited to if we suspect fraud, unauthorised activity, unusual returns activity, or any breach of these Terms of Sale or our Terms of Use.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Acceptance of your order',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'You will receive confirmation of your order via the email address you provided to us. If you order via our mobile application, you may also receive push notifications in relation to your order. This order confirmation does not mean that your order has been accepted. Prior to dispatch we are not under any obligation to provide the product to you, even if we have sent you an order confirmation.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'We only conclude the contract of sale and accept your order when we dispatch the product to you and send you an email confirmation that the product have been dispatched.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Pricing and product availability',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Sometimes we may reject orders for example because a product is unexpectedly out of stock, because the product was mispriced by us, or a promotion has been described wrongly. When this happens, we will let you know as soon as possible and either give you the option of reconfirming your order at the correct price (if the item is available) or cancelling it and refunding any sums you have paid.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'We reserve the right to limit the quantities of any item that can be bought by you at any time.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Our prices are inclusive of VAT.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Age-restricted products',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'If you are placing an order for an item that is by law age-restricted, then by clicking the order button you confirm that you are over 18 years old.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Please make sure you are able to receive delivery of the items, and have a valid form of identification available, regardless of your age. If we ask for identification and you are unable to provide this, we reserve the right to withhold the delivery.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Some age-restricted items may not be available for delivery to all the locations that we currently operate in. If you live in an area where age-restricted items cannot be delivered, this will be made clear to you before you place an order for an age-restricted item.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Vouchers',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'If you are using a voucher, the voucher will be subject to its own terms and conditions. Please refer to these terms and conditions communicated to you with the relevant voucher, for any restrictions which may apply.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Delivery',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'The cost of delivery will be shown before you place your order. The delivery charge will be set at our sole discretion and may vary for each order dependent on the value of the order, the date and time of your delivery, and the delivery address. We may deliver the products in instalments and will invoice each partial delivery separately. Should we deliver in instalments, you will only be charged one delivery fee.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Delivery dates and times are estimates only and not guaranteed delivery times. Sometimes there may also be delivery delays for example because of logistics or bad weather. We will keep you updated on your delivery.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'The address you provide to us must be accurate and up to date. We will not be responsible for not delivering the products if you give us incorrect or incomplete information.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'We cannot be held liable for any parcels that are lost or stolen because of specific delivery instructions you provide.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'We reserve the right to restrict deliveries in certain areas and may not deliver to certain remote areas. You will be notified of this before placing your order and at the time of entering your address.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Products',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'We are not the manufacturer of the products sold on Joybuy. We are not liable for inaccuracies or mis-statements about products by manufacturers or other third parties.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'We take reasonable care to ensure all details and descriptions of products on the Joybuy Site are correct, and aim to keep the Joybuy Site as up to date as possible. However, all information is provided for information purposes only.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'The product descriptions may not be up to date at the point in time that you place an order. The product you receive and its packaging and materials may contain different and additional information. Product ingredients may change.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Please always ensure you read the labels, warnings and directions that are provided to you with the product you purchase before you use it.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Payment',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Payments for orders can be made by one of the approved payment methods listed on the checkout page.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Some payment services we offer are not always available to select. We may not offer specific payment services based on conditions of use or suspected misuse.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Online payment transactions are subject to checks by your card issuer and we are not responsible if your card issuer declines to authorise the payment for any reason. Your card issuer may charge an online handling fee or processing fee which we are not responsible for.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Returns or issues with your order',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'If you wish to return an item please refer to our ',
      },
      {
        t: '',
        href: 'https://www.joyfumi.com/hc/en-us/articles/43253173737497-Joybuy-After-sales-Policy',
      },
      {
        t: 'After Sales Policy.',
        href: 'https://www.joyfumi.com/customer-service/Returns%20&%20Refunds',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Our liability to you',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Nothing in these Terms of Sale will restrict or limit our liability for death or personal injury or for any other matter which we may not exclude as a matter of law.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'If you are a consumer, you have certain rights derived from laws such as the Consumer Rights Act 2015, and nothing in these Terms of Sale restricts any of these rights.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'We are not responsible for losses that you suffer that is a foreseeable result of us breaking these Terms of Sale or us failing to use reasonable case and skill in relation to your use of our Joybuy Site. We are not responsible for any loss or damage that is not foreseeable.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'We are not responsible for any loss or damage for:',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '· any unexpected losses;',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '· anything that is caused by an event outside of our control;',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '· something that could have been avoided by you taking reasonable action; or',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '· any business loss.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Our total liability to you is limited to the purchase price of the products and the cost of delivery.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Personal data',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'We use your personal data as set out in our ',
      },
      {
        t: 'Privacy Policy',
        href: 'https://www.joyfumi.com/help/privacy-policy',
      },
      {
        t: '.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Other information',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'If a court decides that some of the terms in these Terms of Sale are unlawful, then the rest will continue to apply.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'We can transfer or subcontract any of our responsibilities or obligations under these Terms of Sale with you, so that a different organisation may be responsible for supplying or delivering your products.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'If we have a right to enforce your failure to comply with these Terms of Sale, that right will not be lost even if we delay enforcing that right, or waive our right to enforce it in any instance.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Nobody else has any rights under these Terms of Sale. The contract made under these Terms of Sale each time you purchase a product on the Joybuy Site is between you and us. No other person shall have any rights to enforce any of these Terms of Sale.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Our Terms of Sale are governed by English law and you can bring legal proceedings in respect of products purchased on the Joybuy Site in the English courts.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'ATTACHMENT - Gift Card Terms & Conditions',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Updated 20 April 2026',
        i: 1,
        u: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '1. Redemption',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Joybuy Gift Cards may only be redeemed toward the purchase of eligible products on the designated Joybuy country site specified at the time of issuance. Purchases are deducted from the Gift Card balance. If a purchase exceeds the available Gift Card balance, the remaining amount must be paid using another available payment method.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '2. Country / Site Restriction',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'A Joybuy Gift Card is redeemable only on the specific Joybuy country site for which it is issued. It may not be used on other Joybuy country sites or for orders designated for other consumer markets, except where expressly stated by Joybuy.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '3. Expiry',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Joybuy Gift Cards expires 5 Years from the date of issuance, unless a longer period is required by applicable law.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '4. No Reload, No Cash Redemption, No Transfer',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Gift Cards cannot be reloaded, resold, transferred for value, redeemed for cash, or used for any unauthorized commercial purpose. Unused Gift Card balances may not be transferred to another account.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '5. Restricted Products',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Gift Cards may not be used to purchase:',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '• other gift cards, vouchers, or stored value products;',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '• account top-ups, balance top-ups, or similar value-stored products;',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '• restricted digital products, codes, or services as designated by Joybuy from time to time.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '6. Refunds',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'When refunding an order is paid in whole or in part using a Gift Card, any refund relating to the Gift Card-funded portion will, unless otherwise required by applicable law or technically impossible, be credited back to the original Gift Card used for the purchase. Where such credit back is not possible, Joybuy may issue a replacement Gift Card for the refunded amount.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'You will not be able to refund after your Joybuy Gift Card is added to your Account or used on Joybuy.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '7. Risk of Loss',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'The risk of loss and title for the Gift Card pass to the purchaser or designated recipient upon electronic transmission or delivery. Joybuy is not responsible for lost, stolen, destroyed, or unauthorized use of a Gift Card, except as required by applicable law.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '8. Fraud / Abuse',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Joybuy reserves the right to refuse, suspend, cancel, or restrict Gift Cards, Gift Card balances, orders, or associated accounts where fraud, abuse, unauthorized commercial use, or prohibited activity is suspected.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '9. Limitation of Use',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Gift Cards may only be used within Joybuy’s designated retail ecosystem and in accordance with these Terms. Gift Cards do not constitute a bank account, payment account, electronic money account, or cash equivalent.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '10. General',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'These Gift Card Terms form part of, and should be read together with, Joybuy’s general Terms & Conditions, Privacy Notice, and other policies as applicable. Mandatory consumer protection laws of the consumer’s country of habitual residence shall remain unaffected where applicable.',
      },
    ],
  },
]

const zh = [
  {
    type: 'p',
    segments: [
      {
        br: 1,
      },
      {
        t: '2025年2月28日更新',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: '通用条款和条件',
      },
      {
        br: 1,
      },
      {
        t: '感谢您选择成为Joybuy的客户！我们将竭诚为您提供优质的产品与服务！',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: '客户在本网站购买任何待售产品，均需遵守本通用条款和条件（以下简称“本条款”）。客户下单购买任何产品，即表示同意受本条款约束。建议您留存本条款副本，以备查阅。您通过本网站提交的个人信息，将根据Joybuy',
      },
      {
        t: '《隐私政策》',
        href: 'https://www.joyfumi.com/help/privacy-policy',
      },
      {
        t: '及',
      },
      {
        t: '《Cookies政策》',
        href: 'https://www.joyfumi.com/help/cookie-policy',
      },
      {
        t: '进行处理。',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: 'Joybuy有权随时在本网站上修订、变更本条款，但此类变更不会影响您已通过网站向Joybuy下达的任何订单。本条款于2025年2月28日进行最后一次更新。',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: '请点击此处，在Joybuy客服门户页面查看订单与付款、账户设置、运输与交付，以及售后服务与政策等详细信息。',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: '• 第1条 定义',
        b: 1,
      },
      {
        br: 1,
      },
      {
        t: '在本条款中，下列术语应具有如下含义：',
      },
    ],
  },
  {
    type: 'table',
    // 真站实测（2026-11-20）：仅销售条款「第1条 定义」表格首列每个单元格内为 <b>（700）；
    // 隐私政策表格首列不加粗。故用块级标志控制，避免全局 td:first-child 污染其他政策表格。
    firstColBold: true,
    rows: [
      ['售后服务政策', '售后说明中规定的产品退货、退款相关政策；'],
      ['账户', 'Joybuy向客户提供、可通过这里访问的虚拟账户；'],
      ['消费者', '以非商业目的（即完全或主要非出于其行业、业务、工艺或专业需求）行事的自然人；'],
      [
        '合同',
        'Joybuy与客户之间就产品销售及交付达成的任何协议、前述协议的修正版或修订版，以及为订立或履行本协议所产生的所有法律行为；',
      ],
      [
        '客户',
        '符合以下任一条件的个人或法人实体：向Joybuy提交订单、与Joybuy签订合同、正在与Joybuy讨论或协商合同，或接受Joybuy要约。客户亦包括消费者和商家；',
      ],
      ['天', '日历日；'],
      ['Joybuy', '本条款第1.2条明确指定的法人实体和（或）其关联公司及业务实体；'],
      ['订单确认通知', '具有本条款第4.2条赋予其之含义；'],
      ['产品', 'Joybuy通过网站向客户提供的任何产品、商品和（或）其他物品；'],
      [
        '专用条款和条件',
        'Joybuy不时另行通知客户且适用于合同或客户账户的任何专用条款和条件（包括代金券或优惠券相关条款）；',
      ],
      ['条款', '不时进行修订和更新的通用条款和条件；'],
      [
        '商家',
        '出于商业目的（与其行业、业务、工艺或专业相关）行事的个人，无论是以其本人名义或通过授权代表以商家名义行事；',
      ],
      ['网站', '网站www.joyfumi.com，或Joybuy供客户购物的其他网站，包括在线网站和移动应用程序。'],
    ],
  },
  {
    type: 'p',
    segments: [
      {
        br: 1,
      },
      {
        t: '1.1 Joybuy可通过电子邮件、短信或网站公告等电子方式与客户进行通信。出于履行合同之目的，客户同意，所有以电子形式发送的协议、通知、披露文件及其他通信均满足书面形式的法律要求，适用的强制性法律明确规定需采用其他通信形式的除外。',
      },
      {
        br: 1,
      },
      {
        t: '1.2 Joybuy信息：',
      },
      {
        br: 1,
      },
      {
        t: 'Joybuy：JINGDONG RETAIL (UK) Limited',
      },
      {
        br: 1,
      },
      {
        t: '营业地址：Floor 3, 20 King Street, London, SW1Y 6QY',
      },
      {
        br: 1,
      },
      {
        t: '电话号码：+44 20 33073410',
      },
      {
        br: 1,
      },
      {
        t: '电子邮箱地址：Joybuyfumi@gmail.com.',
      },
      {
        br: 1,
      },
      {
        t: '公司注册号：15830555',
      },
      {
        br: 1,
      },
      {
        t: '增值税识别号：481236788',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: '• 第2条 客户账户',
        b: 1,
      },
      {
        br: 1,
      },
      {
        t: '2.1 客户应妥善保管其账户及密码，并确保其保密性与安全性。在法律允许的最大范围内，客户应对其账户内的一切活动承担全部责任。如客户发现或怀疑其密码泄露或账户存在未经授权的使用行为，应立即通知Joybuy。',
      },
      {
        br: 1,
      },
      {
        t: '2.2 客户应确保其向Joybuy提供的信息准确、完整。如信息发生变更，客户应及时通知Joybuy。',
      },
      {
        br: 1,
      },
      {
        t: '2.3 客户不得以下列方式使用网站：（i）对网站的正常运行或访问造成干扰、破坏或损害；（ii）用于欺诈、刑事犯罪或其他非法用途；（iii）造成骚扰或不便。',
      },
      {
        br: 1,
      },
      {
        t: '2.4 若客户违反（或Joybuy合理怀疑客户可能违反）适用法律或本条款规定，Joybuy有权终止客户账户或限制客户访问和使用网站。基于技术或安全原因，Joybuy可临时或永久暂停账户访问权限。',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: '• 第3条 适用性',
        b: 1,
      },
      {
        br: 1,
      },
      {
        t: '3.1 本条款适用于Joybuy向客户销售的所有产品，并构成Joybuy与客户间签订的各项合同不可分割的一部分，对Joybuy的产品销售及交付具有法律约束力。',
      },
      {
        br: 1,
      },
      {
        t: '3.2 客户必须持有有效的Joybuy注册账户方可在网站上购物。若无有效账户，客户将无法使用网站功能和（或）与Joybuy签订合同。',
      },
      {
        br: 1,
      },
      {
        t: '3.3 客户与Joybuy签订合同前，必须仔细阅读本条款。',
      },
      {
        br: 1,
      },
      {
        t: '3.4 客户通过Joybuy购买产品和（或）使用网站，即视为接受本条款。',
      },
      {
        br: 1,
      },
      {
        t: '3.5 Joybuy明确拒绝接受客户提出的任何购物条件或其他（一般）条件，除非Joybuy针对特定交易或购买行为，以书面形式确认接受该等条件。',
      },
      {
        br: 1,
      },
      {
        t: '3.6 Joybuy有权将合同项下的全部或部分义务分包给第三方履行。除客户指定第三方外，Joybuy对分包商的履约行为承担与自身履约同等的责任。',
      },
      {
        br: 1,
      },
      {
        t: '3.7 Joybuy仅向年满18周岁的成年人销售产品。若Joybuy合理怀疑客户未满18周岁或未达到其他法定年龄，Joybuy有权（i）拒绝任何购买行为；（ii）发出书面通知，终止合同；（iii）要求客户证明其已年满18周岁或达到购买特定产品的法定年龄；（iv）拒绝交付产品；和（或）（v）终止客户账户。未满18周岁的客户，仅可在其父母或法定监护人（年满18周岁）的参与和监督下使用网站。',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: '• 第4条 订立合同',
        b: 1,
      },
      {
        br: 1,
      },
      {
        t: '消费者',
        b: 1,
        i: 1,
      },
      {
        br: 1,
      },
      {
        t: '4.1 消费者可点击其拟购买的产品，按照页面提示完成购买操作。在点击结账页面上的“立即购买”、“立即支付”或“确认购买并支付”按钮，并向Joybuy提交订单前，消费者可核对并修改已输入的信息。',
      },
      {
        br: 1,
      },
      {
        t: '4.2 消费者下单后，Joybuy将向消费者发送订单接收通知，但该通知不代表Joybuy已接受订单。订单构成消费者向Joybuy发出的相关产品的购买要约。Joybuy有权自行决定是否接受订单。然而，客户确认，点击“立即购买”、“立即支付”或“确认购买并支付”按钮，即视为客户应履行相关付款义务。若接受订单，Joybuy将发送订单已发出的确认函，确认其接受该订单（以下简称“订单确认通知”）。在Joybuy发送订单确认通知时，双方间关于所购产品的合同正式成立。合同成立后，Joybuy有义务按照约定向客户提供合格产品。',
      },
      {
        br: 1,
      },
      {
        t: '4.3 合同标的仅涉及订单确认通知中列明的产品。在相关订单确认通知中进行确认前，Joybuy无义务提供订单中可能包含的任何其他产品。',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: '商家',
        b: 1,
        i: 1,
      },
      {
        br: 1,
      },
      {
        t: '4.4 除非Joybuy另行作出书面说明，否则Joybuy发布的所有要约或报价均不构成具有法律约束力的承诺。',
      },
      {
        br: 1,
      },
      {
        t: '4.5 若客户有合理理由认为要约、报价或其任何部分存在错误或笔误，则该要约或报价对Joybuy不具有约束力。',
      },
      {
        br: 1,
      },
      {
        t: '4.6 在客户接受要约前，Joybuy有权向客户发出通知，撤回任何要约或报价。',
      },
      {
        br: 1,
      },
      {
        t: '4.7 合同及其修订和补充条款，在Joybuy书面接受或确认时，或在Joybuy开始履行合同后成立。',
      },
      {
        br: 1,
      },
      {
        t: '4.8 若客户对要约的回复与Joybuy原要约存在差异，或包含补充、限制或其他修订信息（无论是否涉及次要事项），Joybuy不受该等差异、补充、限制或其他修订信息的约束。',
      },
      {
        br: 1,
      },
      {
        t: '4.9 若Joybuy提供的要约或报价涉及特定数量或品类的产品，则仅在客户完全接受报价并接收所有品类和数量的产品时适用该报价。若客户仅需部分产品，或不接受全部数量或品类的产品，除非Joybuy在要约或报价中另有明确书面说明，否则单件产品的价格将按比例上浮。',
      },
      {
        br: 1,
      },
      {
        t: '4.10 除非另有书面规定，任何要约或报价中包含或附带的文件和（或）材料仅供参考，对Joybuy不具有约束力。Joybuy将审慎提供产品价格、数量、尺寸、重量、颜色、图片和（或）其他（技术）规格相关声明。展示或提供的文件、样品、图纸或模型仅作示意用途，不构成客户的任何权利。Joybuy不保证实际产品与展示材料完全一致。',
      },
      {
        br: 1,
      },
      {
        t: '4.11 Joybuy发出的要约和报价以及任何约定偏差或补充，并不自动适用于后续合同。任何要约、报价和（或）任何约定偏差或补充，不构成客户在其他和（或）后续合同中的任何权利。',
      },
      {
        br: 1,
      },
      {
        t: '4.12 根据适用法定权利和限制，Joybuy有权核查客户履行其付款义务的能力，并了解所有与负责任地签订合同相关的事实和因素，包括进行必要的信用调查。若基于此调查，Joybuy有充分理由拒绝签订合同，则Joybuy可拒绝订单或请求。但是，所述拒绝必须有充分理由，或可确保专用条款和条件可适用于合同。',
      },
      {
        br: 1,
      },
      {
        t: '4.13 若在客户下单或合同订立后，无法提供一种或多种产品，Joybuy将尽快通知客户。在此情况下，Joybuy将重新核算订单金额，并按调整后的金额向客户收取费用，其中不可供货产品的价格将从订单总金额中扣除。若客户已付款，Joybuy将立即退还相应金额。',
      },
      {
        br: 1,
      },
      {
        t: '4.14 客户应及时向Joybuy提供履行合同所必须的信息，并确保该等信息的准确性和完整性，包括但不限于客户地址、付款详情及合同信息等。若因客户提供错误或不准确信息导致的无法按约定供货，Joybuy概不承担任何责任。',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: '• 第5条 交货条款',
        b: 1,
      },
      {
        br: 1,
      },
      {
        t: '5.1 交货期自双方签订合同之日起开始计算。若Joybuy为履行合同需要客户提供数据或其他信息，交货期将自客户向Joybuy提供所有所需数据或信息之日起开始计算（若该日期晚于合同签订日期）。',
      },
      {
        br: 1,
      },
      {
        t: '5.2 无论何时，Joybuy均有权分批交付产品。若分批交货，Joybuy有权就每批货物分别开具发票。',
      },
      {
        br: 1,
      },
      {
        t: '5.3 若由Joybuy将产品送至客户地址，则交货地点为客户订单中指定的地址。Joybuy仅向英国本土客户提供送货服务。对于非英国本土地址的订单，Joybuy有权暂停或取消订单。',
      },
      {
        br: 1,
      },
      {
        t: '5.4 若客户交货地址偏远（如位于偏远岛屿或其他孤立地区），Joybuy可能无法提供送货服务。在此情况下，Joybuy将在接受订单前通知客户。Joybuy有权不向任何受适用出口法律或其他制裁禁止的地区或国家提供送货服务。订单无法送至邮政信箱或其他类似地址。',
      },
      {
        br: 1,
      },
      {
        t: '5.5 对于商家：',
      },
      {
        br: 1,
      },
      {
        t: '5.5.1 除非Joybuy和客户另有约定，产品交货方式为工厂交货，交货地点为Joybuy英国仓库，并按合同订立时国际商会现行最新国际贸易术语解释通则执行；',
      },
      {
        br: 1,
      },
      {
        t: '5.5.2 客户可提取产品时即视为已交货；和',
      },
      {
        br: 1,
      },
      {
        t: '5.5.3 除非双方另有书面约定，所有产品的运输费用和风险均由客户承担，即使Joybuy已安排运输和（或）以运费已付的方式发货，本款仍然适用。',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: '• 第6条 价格',
        b: 1,
      },
      {
        br: 1,
      },
      {
        t: '6.1 网站展示或以其他方式列示的产品价格均以英镑标价，并已包含增值税。但是，该价格不包括运输及交货费用，该等费用将在客户选择交货方式后，作为产品价格额外费用单独开具发票。',
      },
      {
        br: 1,
      },
      {
        t: '6.2 Joybuy有权在签订合同前随时调整产品标价。若Joybuy调整产品标价，将发送电子邮件通知客户。',
      },
      {
        br: 1,
      },
      {
        t: '6.3 除非Joybuy另有书面说明，Joybuy发出的所有成本估算仅供参考。',
      },
      {
        br: 1,
      },
      {
        t: '6.4 鉴于网站内产品数量庞大，尽管Joybuy已尽最大努力，但仍有可能标错网站内部分产品的价格。Joybuy通常会在发货过程中核实价格；因此，若产品价格高于或低于网站标价，Joybuy通常会在发货前联系客户获取指示，或联系客户取消订单。',
      },
      {
        br: 1,
      },
      {
        t: '6.5签订合同后，若因法规原因导致产品价格影响因素发生变动，即使双方已约定固定价格，客户也需支付相应费用。若不同意产品价格调整，客户可在价格上涨生效之日终止合同，Joybuy将向客户退还已付产品价格及适用交货费用。',
      },
      {
        br: 1,
      },
      {
        t: '6.6 签订合同后，若产品价格影响因素或Joybuy额外成本发生变动，包括但不限于采购价格、汇率、交货费用、仓储费用、进出口关税以及进出口产生的其他税费、保险费率、运费和其他税费或税款，即使双方已约定固定价格，Joybuy亦可向商家收取上述费用。',
      },
      {
        br: 1,
      },
      {
        t: '6.7 若客户是商家，商家应赔偿Joybuy因其未正确登记增值税或其他类似税务、提供错误信息或未在任何约定期限内向Joybuy提供必要信息而导致Joybuy遭受的所有损害、损失和（或）费用。',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: '• 第7条 付款',
        b: 1,
      },
      {
        br: 1,
      },
      {
        t: '消费者',
        b: 1,
        i: 1,
      },
      {
        br: 1,
      },
      {
        t: '7.1 必须通过第7.3条所载任一方式或结账页面上另行指定的付款方式，支付所有订单款项。',
      },
      {
        br: 1,
      },
      {
        t: '7.2 客户应知悉，在线支付需经客户发卡银行验证授权。若客户发卡银行因任何原因拒绝授权，导致支付失败，Joybuy不承担任何责任。请注意，发卡银行可能收取在线支付手续费，Joybuy概不承担该等费用。',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: '商家',
        b: 1,
        i: 1,
      },
      {
        br: 1,
      },
      {
        t: '7.3 若客户是商家，Joybuy可能要求客户支付预付款。若双方约定支付预付款，客户在支付约定预付款前，不得主张任何订单相关权利。',
      },
      {
        br: 1,
      },
      {
        t: '7.4 Joybuy接受以下付款方式：PayPal、信用卡/借记卡、Google Pay、先买后付、Apple Pay和微信支付，以及订购产品时支付页面显示的其他付款方式。付款方式受客户银行卡或支付服务提供商任何附加条款和条件的约束。Joybuy可自行决定随时增加或移除网站所示付款方式。',
      },
      {
        br: 1,
      },
      {
        t: '7.5 若客户迟延支付或破产，所有未付款项将立即到期应付。',
      },
      {
        br: 1,
      },
      {
        t: '7.6 若客户未能履行其付款义务或按时付款，Joybuy可将相关债权转让给第三方。',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: '• 第8条 所有权保留',
        b: 1,
        i: 1,
      },
      {
        br: 1,
      },
      {
        t: '8.1 对于消费者客户，自交付起，应由客户承担所订产品相关风险。在交付时，所订产品的所有权将转移至客户，但前提是Joybuy已收到所订产品全额款项（包括任何交货费用）。',
      },
      {
        br: 1,
      },
      {
        t: '8.2 对于商家客户，尽管已实际交付，但Joybuy仍保留其已交付商家客户产品的所有权，直至客户已全额支付已交付或待交付产品相关的所有款项，包括可能根据本条款和合同应付的任何附加费用、利息、税费、手续费、征收款、关税及其他费用。',
      },
      {
        br: 1,
      },
      {
        t: '8.3 只要产品所有权尚未转移至商家客户，则客户无权出租、抵押或以其他方式向第三方设定负担或转让产品。',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: '• 第9条 投诉',
        b: 1,
        i: 1,
      },
      {
        br: 1,
      },
      {
        t: '9.1 在不影响消费者法定权利的前提下，客户应在产品交付或可供客户使用时，立即自行检查产品。此外，客户须检查所交付产品的质量和（或）数量是否符合合同及双方约定要求。',
      },
      {
        br: 1,
      },
      {
        t: '9.2 客户必须立即向Joybuy发送书面通知或发送电子邮件至Joybuyfumi@gmail.com，详细说明任何产品投诉内容。关于客户提出的产品不足/缺陷/投诉的通知，应包含订单确认号或单号、交货日期、适用发票副本、产品序列号，以及详尽的不足/缺陷/投诉性质说明，以便Joybuy做出适当回应（以下简称“',
      },
      {
        t: '通知',
        b: 1,
      },
      {
        t: '”）。',
      },
      {
        br: 1,
      },
      {
        t: '9.3 所有通知将按照Joybuy《售后服务政策》处理。更多《售后服务政策》相关信息，请点击客服门户页面查阅。',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: '• 第10条 遵守合同和额外保证',
        b: 1,
      },
      {
        br: 1,
      },
      {
        t: '10.1 除客户依法享有的法定权利外，Joybuy应保证其提供的产品符合以下要求：合同约定条款、要约所载规格、合理的可靠性和（或）可用性要求，以及合同订立时现行有效的所有适用法律法规。',
      },
      {
        br: 1,
      },
      {
        t: '10.2 Joybuy提供的额外保证不影响客户在Joybuy违约时依据合同享有的法定权利和主张。',
      },
      {
        br: 1,
      },
      {
        t: '10.3 额外保证是指Joybuy向客户承诺的、超出法律法规授予范围（Joybuy未履行合同义务时）的特定权利或主张。Joybuy应承担所述额外保证相关义务。',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: '• 第11条 知识产权',
        b: 1,
      },
      {
        br: 1,
      },
      {
        t: '11.1 网站及其全部内容，包括但不限于品牌、图纸、模型、照片、文本、插图、标志、图标、图形、产品及衍生商品，均为Joybuy及其关联公司、许可方或内容提供方的专有财产。除访问网站授权外，Joybuy未授予客户及第三方任何其他许可或权利。客户使用或复制全部或部分上述内容，只能用于参考或个人及私人用途，不得出于任何其他目的复制及使用任何副本。',
      },
      {
        br: 1,
      },
      {
        t: '11.2 客户承诺不得通过使用或其他方式直接或间接侵犯或损害Joybuy知识产权或其他专有权利，并承认Joybuy是该等权利的唯一受益人。',
      },
      {
        br: 1,
      },
      {
        t: '11.3 对于Joybuy披露的、已知或理应知悉的所有机密信息，客户应采取保密措施，且不得向任何第三方披露。客户仅可将该等保密信息用于Joybuy提供该等信息的原始目的。若Joybuy指定该信息为保密信息，则在任何情况下均应将其视为保密信息。',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: '• 第12条 责任与赔偿',
        b: 1,
      },
      {
        br: 1,
      },
      {
        t: '12.1 在不损害消费者可能享有的法定权利或补救措施的情况下，在消费者居住国法律相关责任限制及法律允许的最大范围内，Joybuy的责任限制如本条款第12条所述。',
      },
      {
        br: 1,
      },
      {
        t: '12.2 下列情况下，Joybuy免于承担任何责任：',
      },
      {
        br: 1,
      },
      {
        t: '12.2.1 网站服务中断；',
      },
      {
        br: 1,
      },
      {
        t: '12.2.2 因第三方欺诈性入侵导致网站上的信息被篡改造成的任何损失或损害；',
      },
      {
        br: 1,
      },
      {
        t: '12.2.3 因库存不足导致订单取消（无论是否订立合同）；',
      },
      {
        br: 1,
      },
      {
        t: '12.2.4 未通过网站购买产品；',
      },
      {
        br: 1,
      },
      {
        t: '12.2.5 产品的正常磨损；或',
      },
      {
        br: 1,
      },
      {
        t: '12.2.6 产品已超出合理使用寿命。',
      },
      {
        br: 1,
      },
      {
        t: '12.3 在不影响第12.1条和第12.2条所载前提下，并且在法律允许的最大范围内，Joybuy对于因其未能履行任何合同和（或）本条款项下义务（明确包括未能履行任何保证义务）而产生的责任（无论是基于侵权行为还是任何其他原因或依据），均应仅限于客户根据相关合同向Joybuy支付的金额。',
      },
      {
        br: 1,
      },
      {
        t: '12.4 在任何情况下，Joybuy均不对客户承担任何特殊损失、后果性损失、间接性损失、刑事损失或附带损失相关责任，包括但不限于延期引起的损失、利润损失、储蓄损失、运营成本增加、消费者客户索赔导致的损害或损失、客户流失、商誉贬损、因使用客户指示Joybuy获取的第三方物品、材料或服务引起的任何损害或损失，以及因按客户指示同意第三方参与引起的任何损害或损失，无论该等责任依据为何，且无论是否曾在合同中或以其他方式提前告知该等损害发生的可能性。Joybuy亦不对任何数据灭失或丢失承担责任。',
      },
      {
        br: 1,
      },
      {
        t: '12.6 若且仅当相关损失完全由Joybuy故意行为或重大过失引起时，上述第12.2条至第12.4条所载限制和除外条款不再适用。本条款任何内容均不限制或排除Joybuy对其欺诈性陈述应承担的责任，或因Joybuy疏忽或故意不当行为导致的死亡或人身伤害相关责任。',
      },
      {
        br: 1,
      },
      {
        t: '12.7 客户主张损害赔偿，需以客户在知悉违约行为后立即书面通知Joybuy为前提。若Joybuy在客户知悉违约事件后十二（12）个月才收到的索赔请求，Joybuy概不承担任何责任。',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: '• 第13条 不可抗力',
        b: 1,
      },
      {
        br: 1,
      },
      {
        t: '13.1 若临时性或永久性不可抗力导致合同无法履行，Joybuy有权全部或部分终止合同，且无需承担任何赔偿责任，或暂停执行合同。在暂停期间，Joybuy可宣布合同全部或部分终止。若发生不可抗力，受影响方应立即通知另一方，并持续向其通报不可抗力的发展情况。',
      },
      {
        br: 1,
      },
      {
        t: '13.2本条中，“不可抗力”是指超出Joybuy控制、使其无法合理履行其义务的任何情形，以及（若尚未包含在内）政府措施、配额限制、（工业罢工、（内战）战争、战争危险、流行病、传染病、暴动、占领、疾病、骚扰、火灾、水损、洪水）、公司被占领、能源供应中断、存储和运输困难、供应商未能提供Joybuy交付产品所需货物，以及无合理理由期望Joybuy能够履行其义务的所有其他情形。',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: '• 第14条 合同终止',
        b: 1,
      },
      {
        br: 1,
      },
      {
        t: '14.1 若客户发生下列情形：',
      },
      {
        br: 1,
      },
      {
        t: '14.1.1 未能履行其合同项下的一项或多项义务；',
      },
      {
        br: 1,
      },
      {
        t: '14.1.2 宣告破产；或',
      },
      {
        br: 1,
      },
      {
        t: '14.1.3 客户以其他方式丧失对其资产的自由处置权，',
      },
      {
        br: 1,
      },
      {
        t: '在不影响其所有其他法定及合同权利的前提下，Joybuy可立即暂停或终止合同，无需发出违约通知和（或）申请司法介入。若根据第14.1条暂停或终止合同，客户欠付Joybuy的任何及所有款项应立即全额到期应付。对于Joybuy已交付但客户尚未付款的货物，客户应立即退还货物。Joybuy根据第14.1条执行权利，不影响其要求赔偿损失、费用和利息的相关权利。',
      },
      {
        br: 1,
      },
      {
        t: '14.2 若Joybuy根据第14.1条终止合同，客户可在三十（30）天内下载其用户账户信息。更多客户个人信息处理相关信息，包括Joybuy的数据保留政策，请参阅',
      },
      {
        t: '《隐私政策》',
        href: 'https://www.joyfumi.com/help/privacy-policy',
      },
      {
        t: '和',
      },
      {
        t: '《Cookies政策》',
        href: '/pages/cookie-policy',
      },
      {
        t: '。',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: '• 第15条 其他',
        b: 1,
      },
      {
        br: 1,
      },
      {
        t: '15.1 未经Joybuy事先书面同意，客户无权将其在本条款或合同项下的权利和（或）义务转让给任何第三方。',
      },
      {
        br: 1,
      },
      {
        t: '15.2 Joybuy有权向客户发出书面通知，对本条款及特别条款和条件进行修订或补充。除非：（i）客户在通知日期后十四（14）天内向Joybuy发出书面通知，说明其不接受该等修订和（或）补充；或（ii）客户继续使用网站，否则客户应被视为已接受本条款修订版。',
      },
      {
        br: 1,
      },
      {
        t: '15.3 若在任何时候，本条款任一或多项条款全部或部分失效或可撤销，则其余条款仍应保有完全效力。在此情况下，Joybuy可根据第15.2条修订相关条款。',
      },
      {
        br: 1,
      },
      {
        t: '15.4 本条款及其明确提及的任何文件，构成客户与Joybuy之间关于任何合同主题事项的全部协议。Joybuy须依法告知客户，合同仅以英语订立，且不适用任何公开备案要求。',
      },
      {
        br: 1,
      },
      {
        t: '15.5 本条款及所有合同均受英格兰和威尔士法律管辖。本条款项下Joybuy与客户之间的所有争议，均应受英格兰伦敦法院管辖。',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: '• 第16条 关于产品交付的消费者撤回权',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '附件 - 礼品卡条款与条件',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '更新于2026年4月20日',
        i: 1,
        u: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '1. 使用说明',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Joybuy 礼品卡仅可用于在发行时指定的 Joybuy 国家站点购买符合条件的商品。订单金额将从礼品卡余额中扣除；如订单金额超过礼品卡余额，差额需使用其他支付方式补足。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '2. 国家/站点限制',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Joybuy 礼品卡仅限在其发行对应的 Joybuy 国家站点使用，不可在其他国家站点或面向其他市场的订单中使用，除非 Joybuy 另有明确说明。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '3. 有效期',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Joybuy 礼品卡自发行之日起有效期为 5 年，若适用法律规定更长期限，则以法律规定为准。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '4. 不可充值、不可兑现、不可转让',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '礼品卡不可充值、转售、转让获取价值、兑换现金，亦不得用于任何未经授权的商业用途。未使用的礼品卡余额不可转移至其他账户。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '5. 限制商品',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '礼品卡不可用于购买：',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '• 其他礼品卡、代金券或储值类产品；',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '• 账户充值、余额充值或类似储值产品；',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '• Joybuy 不时指定的受限数字商品、兑换码或服务。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '6. 退款说明',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '若订单全部或部分使用礼品卡支付，退款中对应礼品卡支付的部分（除法律另有规定或技术上无法实现的情况外）将退回至原礼品卡；如无法退回，Joybuy 可能会发放等额的新礼品卡。 礼品卡一旦被添加到账户或使用后，将无法申请退款。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '7. 风险承担',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '请仔细查验实体礼品卡和电子礼品卡的交付详情。 礼品卡在通过电子方式发送或交付后，其风险与所有权即转移至购买方或指定接收人。除法律另有规定外，Joybuy 不对礼品卡的遗失、被盗、损毁或未经授权使用承担责任。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '8. 欺诈/滥用',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '如发现存在欺诈、滥用、未经授权的商业使用或其他违规行为，Joybuy 有权拒绝、暂停、取消或限制礼品卡、礼品卡余额、相关订单或账户。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '9. 使用限制',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '礼品卡仅可在 Joybuy 指定的零售生态体系内使用，并须遵守本条款。礼品卡不构成银行账户、支付账户、电子货币账户或现金等价物。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '10. 一般条款',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '本礼品卡条款为 Joybuy《条款与条件》《隐私政策》及其他相关政策的组成部分，应一并阅读。在适用情况下，消费者常住国的强制性消费者保护法律不受影响。',
      },
    ],
  },
]

import { jaTitle as jaPageTitle, jaBlocks as jaPageBlocks } from './terms-conditions.ja.js'
export const termsConditionsPage = {
  slug: 'terms-conditions',
  title: { en: 'Terms of Sale', zh: '销售条款' },
  hasArchive: false,
  blocks: { en, zh },
  jaTitle: jaPageTitle,
  jaBlocks: jaPageBlocks,
}
