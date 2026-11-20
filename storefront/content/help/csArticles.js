// 批次 0am（2026-11-20）：真站 customer-service 文章详情页正文（支付 5 篇 + 退货 11 篇）。
// 来源：2026-11-20 真站文章页存档 var/footer_help_20261120/raw_{en_GB,zh_CN}_<slug>.json
// （EN/ZH 均为真站自带文案，非机器翻译），URL 形态 https://www.joybuy.co.uk/help/<slug>
// （真站清单页可跳 /customer-service/<Category>/<slug> 等价页），本地路由 /help/<slug>。
// 块模型与政策页一致（p{segments} / list / image）；segments 内 t=文本、b=粗体、i=斜体、
// u=下划线、href=链接、br=换行。配图 8 张已下载本地托管 storefront/public/images/help/。
// 替换口径（16.5 帮助中心）：support@joybuy.com → Joybuyfumi@gmail.com；
// 16 篇互链 → 本地 /help/<slug>；其余真站网址 → https://www.joyfumi.com；
// EU/欧盟/欧洲 → Asia/亚洲。
export const csArticles = [
  {
    slug: 'payment-methods',
    category: 'payment-and-invoice',
    realUrl: 'https://www.joybuy.co.uk/help/payment-methods',
    title: {
      en: 'Payment Methods',
      zh: '支付方式',
    },
    blocks: {
      en: [
        {
          type: 'p',
          segments: [
            {
              t: 'To make your payment experience as fast and simple as possible, Joybuy supports the following payment options:',
            },
          ],
        },
        {
          type: 'list',
          ordered: false,
          items: [
            [
              {
                t: 'VISA/MasterCard/JCB',
              },
            ],
            [
              {
                t: 'Maestro',
              },
            ],
            [
              {
                t: 'American Express',
              },
            ],
            [
              {
                t: 'WeChat Pay',
              },
            ],
            [
              {
                t: 'PayPal',
              },
            ],
            [
              {
                t: 'Apple Pay',
              },
            ],
            [
              {
                t: 'Klarna',
              },
            ],
            [
              {
                t: 'Google Pay',
              },
            ],
            [
              {
                t: 'NewPay',
              },
            ],
          ],
        },
      ],
      zh: [
        {
          type: 'p',
          segments: [
            {
              t: '为了让您的支付体验尽可能快捷简便，Joybuy支持以下支付方式：',
            },
          ],
        },
        {
          type: 'list',
          ordered: false,
          items: [
            [
              {
                t: 'VISA/MasterCard/JCB',
              },
            ],
            [
              {
                t: 'Maestro',
              },
            ],
            [
              {
                t: 'American Express',
              },
            ],
            [
              {
                t: 'WeChat Pay',
              },
            ],
            [
              {
                t: 'PayPal',
              },
            ],
            [
              {
                t: 'Apple Pay',
              },
            ],
            [
              {
                t: 'Klarna',
              },
            ],
            [
              {
                t: 'Google Pay',
              },
            ],
            [
              {
                t: 'NewPay',
              },
            ],
          ],
        },
      ],
    },
  },
  {
    slug: 'update-payment',
    category: 'payment-and-invoice',
    realUrl: 'https://www.joybuy.co.uk/help/update-payment',
    title: {
      en: 'How do I add or update my payment method?',
      zh: '如何添加或更新我的付款方式？',
    },
    blocks: {
      en: [
        {
          type: 'p',
          segments: [
            {
              t: 'Payment methods cannot be added or saved in advance. Instead, you can select or update your payment method during checkout. ',
            },
            {
              t: 'Simply choose your preferred option on the payment page before confirming your order.',
            },
          ],
        },
      ],
      zh: [
        {
          type: 'p',
          segments: [
            {
              t: '付款方式无法预先添加或保存。您可以在结账时选择或更新付款方式。只需在确认订单前的付款页面选择您偏好的付款方式即可。',
            },
          ],
        },
      ],
    },
  },
  {
    slug: 'download-invoice',
    category: 'payment-and-invoice',
    realUrl: 'https://www.joybuy.co.uk/help/download-invoice',
    title: {
      en: 'Where can I find and download my invoice?',
      zh: '我可以在哪里找到并下载我的发票？',
    },
    blocks: {
      en: [
        {
          type: 'p',
          segments: [
            {
              t: 'Once your order is completed, you can download your invoice directly from your Joybuy account:',
            },
            {
              br: 1,
            },
            {
              t: '1. Go to My Orders.',
            },
            {
              br: 1,
            },
            {
              t: '2. Select the order you need.',
            },
            {
              br: 1,
            },
            {
              t: '3. Tap the Invoice button to download it.',
            },
          ],
        },
        {
          type: 'image',
          src: '/images/help/download-invoice-en-1.png',
        },
        {
          type: 'image',
          src: '/images/help/download-invoice-en-2.png',
        },
        {
          type: 'p',
          segments: [
            {
              t: 'To reduce unnecessary environmental waste, paper invoices are not included in shipments. All invoices are generated and stored digitally in your Joybuy account for easy access at any time.',
            },
          ],
        },
      ],
      zh: [
        {
          type: 'p',
          segments: [
            {
              t: '订单完成后，您可以直接从Joybuy账户下载发票：',
            },
            {
              br: 1,
            },
            {
              t: '1. 前往“我的订单”。',
            },
            {
              br: 1,
            },
            {
              t: '2. 选择您需要的订单。',
            },
            {
              br: 1,
            },
            {
              t: '3. 点击“发票”按钮下载。',
            },
          ],
        },
        {
          type: 'image',
          src: '/images/help/download-invoice-zh-1.png',
        },
        {
          type: 'image',
          src: '/images/help/download-invoice-zh-2.png',
        },
        {
          type: 'p',
          segments: [
            {
              t: '为了减少不必要的环境浪费，纸质发票将不再随包裹寄送。所有发票均以电子方式生成并存储在您的Joybuy账户中，方便您随时查看。',
            },
          ],
        },
      ],
    },
  },
  {
    slug: 'apply-coupon',
    category: 'payment-and-invoice',
    realUrl: 'https://www.joybuy.co.uk/help/apply-coupon',
    title: {
      en: 'How do I apply a coupon or promo code?',
      zh: '如何使用优惠券或促销代码？',
    },
    blocks: {
      en: [
        {
          type: 'p',
          segments: [
            {
              t: 'You can apply a coupon or promo code at checkout:',
            },
            {
              br: 1,
            },
            {
              t: '1. Add your items to the cart and tap Checkout.',
            },
            {
              br: 1,
            },
            {
              t: '2. On the payment page, look for the Coupon Code & Coupons option.',
            },
            {
              br: 1,
            },
            {
              t: '3. Enter your code or select an available coupon from your account.',
            },
            {
              br: 1,
            },
            {
              t: '4. Confirm and proceed with payment.',
            },
            {
              br: 1,
            },
            {
              t: 'If your code isn’t working, check if it has expired, has a minimum spend requirement, or is restricted to specific products.',
            },
          ],
        },
      ],
      zh: [
        {
          type: 'p',
          segments: [
            {
              t: '您可以在结账时使用优惠券或促销代码：',
            },
            {
              br: 1,
            },
            {
              t: '1. 将商品添加到购物车并点击“结账”。',
            },
            {
              br: 1,
            },
            {
              t: '2. 在付款页面，找到“优惠券代码”选项。',
            },
            {
              br: 1,
            },
            {
              t: '3. 输入您的代码或从您的账户中选择可用的优惠券。',
            },
            {
              br: 1,
            },
            {
              t: '4. 确认并完成付款。',
            },
            {
              br: 1,
            },
            {
              t: '如果您的代码无法使用，请检查它是否已过期、是否有最低消费要求或是否仅限用于特定商品。',
            },
          ],
        },
      ],
    },
  },
  {
    slug: 'payment-declined',
    category: 'payment-and-invoice',
    realUrl: 'https://www.joybuy.co.uk/help/payment-declined',
    title: {
      en: 'Why was my payment declined?',
      zh: '我的付款为什么被拒绝了？',
    },
    blocks: {
      en: [
        {
          type: 'p',
          segments: [
            {
              t: 'A payment may be declined for several reasons, including:',
            },
          ],
        },
        {
          type: 'list',
          ordered: false,
          items: [
            [
              {
                t: 'Insufficient funds',
              },
            ],
            [
              {
                t: 'Incorrect card details',
              },
            ],
            [
              {
                t: 'Bank security checks',
              },
            ],
            [
              {
                t: 'Network or connection issues',
              },
            ],
            [
              {
                t: 'Card not supported for international or online transactions',
              },
            ],
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'If this happens, please try a different payment method or contact your bank for clarification.',
            },
          ],
        },
      ],
      zh: [
        {
          type: 'p',
          segments: [
            {
              t: '付款可能因以下几种原因被拒绝：',
            },
          ],
        },
        {
          type: 'list',
          ordered: false,
          items: [
            [
              {
                t: '余额不足',
              },
            ],
            [
              {
                t: '卡片信息错误',
              },
            ],
            [
              {
                t: '银行安全检查',
              },
            ],
            [
              {
                t: '网络或连接问题',
              },
            ],
            [
              {
                t: '卡片不支持国际或在线交易',
              },
            ],
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '如果发生这种情况，请尝试其他付款方式或联系您的银行进行咨询。',
            },
          ],
        },
      ],
    },
  },
  {
    slug: 'statutory-rights',
    category: 'returns-and-refunds',
    realUrl: 'https://www.joybuy.co.uk/help/statutory-rights',
    title: {
      en: 'Your Statutory Rights',
      zh: '法定撤销权',
    },
    blocks: {
      en: [
        {
          type: 'p',
          segments: [
            {
              t: 'Right of Withdrawal',
              b: 1,
            },
            {
              br: 1,
            },
            {
              t: 'You have the right to withdraw from this contract within 14 days without giving any reason. The withdrawal period expires after 14 days from the day on which you (or a third party you nominate) take physical possession of the goods.',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'To exercise your right of withdrawal, you must inform us of your decision by means of a clear statement (e.g., an email, online chat, or telephone call) using the following contact details:',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '24/7 Online Chat:',
            },
            {
              t: ' Available through our website/app.',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'Email:',
            },
            {
              t: ' Joybuyfumi@gmail.com',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'Phone:',
            },
            {
              t: ' You may request a callback via our website/app.',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'You may use the model withdrawal form below, but it is not obligatory. To meet the withdrawal deadline, it is sufficient for you to send your communication before the 14-day period has expired.',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'Model Withdrawal Form',
              b: 1,
            },
            {
              br: 1,
            },
            {
              t: '(To be completed only if you wish to use this form)',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'To:',
              i: 1,
            },
            {
              t: ' Joybuy, Joybuyfumi@gmail.com',
            },
            {
              br: 1,
            },
            {
              t: 'I/We hereby give notice that I/we withdraw from my/our contract of sale of the following goods:',
              i: 1,
            },
            {
              br: 1,
            },
            {
              t: 'Ordered on / Received on: _____',
              i: 1,
            },
            {
              br: 1,
            },
            {
              t: 'Name of consumer(s): _____',
              i: 1,
            },
            {
              br: 1,
            },
            {
              t: 'Address of consumer(s): _____',
              i: 1,
            },
            {
              br: 1,
            },
            {
              t: 'Date: _____',
              i: 1,
            },
            {
              br: 1,
            },
            {
              t: '(Signature – only if this form is notified on paper)',
              i: 1,
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'Effects of Withdrawal',
              b: 1,
            },
            {
              br: 1,
            },
            {
              t: 'If you withdraw from this contract, we will reimburse all payments received from you, including standard delivery costs (except for any supplementary costs arising from your choice of a more expensive delivery option), without undue delay and no later than 14 days from the day we are informed of your decision.',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'We will use the same means of payment you used for the original transaction for the refund, and you will not incur any fees. You must return the goods to our specified address without undue delay and in any event within 14 days of notifying us of withdrawal. The deadline is met if you send back the goods before this 14-day period expires.',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'We will bear the direct cost of returning the goods.',
              b: 1,
            },
            {
              t: ' You are only liable for any diminished value of the goods resulting from handling beyond what is necessary to establish their nature, characteristics, and functioning.',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'Important Exceptions to the Right of Withdrawal',
              b: 1,
            },
            {
              br: 1,
            },
            {
              t: 'The statutory right of withdrawal does not apply to goods made to your specifications, sealed goods unsuitable for return for health/hygiene reasons if unsealed, goods which by their nature are inseparably mixed with others after delivery, sealed audio/video recordings or software if unsealed, and certain other specific cases as defined by law. ',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'For more details please visit the following:',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'Our Return Policy',
              href: '/help/our-return-policy',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'Return Exceptions',
              href: '/help/return-exceptions',
            },
          ],
        },
      ],
      zh: [
        {
          type: 'p',
          segments: [
            {
              t: '退货权（撤销权）',
              b: 1,
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '您有权在14天内无理由撤销您的订购，退货期自您（或您指定的第三方）收到货物之日起14天后结束。',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '要行使您的退货权，您必须通过清晰声明（例如，电子邮件、在线聊天或电话）告知我们您的决定，联系方式如下：',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '7×24小时在线服务：通过我们的网站/app访问',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '电子邮件：Joybuyfumi@gmail.com',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '电话：您可以通过我们的网站/app要求回电',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '同时，您也可以选择使用下面的退货表格范本，但这不是强制性的。为遵守退货期限，您只需在14天期限届满前发送您的通知即可。',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '退货表格范本',
              b: 1,
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '（仅在您希望使用此表格时填写）',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '收件人：Joybuy，Joybuyfumi@gmail.com',
              i: 1,
            },
            {
              br: 1,
            },
            {
              t: '我/我们特此通知，我/我们撤销购买以下商品的合同：',
              i: 1,
            },
            {
              br: 1,
            },
            {
              t: '订购日期/收货日期：_____',
              i: 1,
            },
            {
              br: 1,
            },
            {
              t: '消费者姓名：_____',
              i: 1,
            },
            {
              br: 1,
            },
            {
              t: '消费者地址：_____',
              i: 1,
            },
            {
              br: 1,
            },
            {
              t: '日期：_____',
              i: 1,
            },
            {
              br: 1,
            },
            {
              t: '（签名 – 仅在此表格以纸质形式通知时需要）',
              i: 1,
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '退货流程',
              b: 1,
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '如果您撤销订购，我们将退还从您那里收到的所有款项，包括标准配送费用（不包含其他配送方式的额外费用），我们会立即且最迟在得知您撤销合同决定之日起14天内完成退款。',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '我们将使用您原始交易相同的支付方式进行退款，您不会因此被收取任何费用。需要注意的是，您需要将货物退回至我们指定的地址，或在适用的情况下交还至我们的实体门店，不得无故延误，且必须在您通知我们撤销合同之日起14天内完成。如果您在14天期限届满前寄回货物，即视为遵守该期限。',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '我们会完全承担退货产生的直接费用。只有在您由于不当使用或检查而导致商品价值受损时，才需要承担相应责任。例如：试穿衣物时沾上无法清除的污渍，或在体验电子产品时造成划痕或损坏。',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '退货权的重要例外情况',
              b: 1,
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '法定退货权不适用于根据您的规格定制的商品、出于健康/卫生原因开封后不适合退回的密封商品、因其性质在交付后与其他商品无法分离地混合的商品、开封后的密封音视频记录或软件，以及法律规定的某些其他特定情况。',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '更多详情请访问以下页面：',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '退货政策',
              href: '/help/our-return-policy',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '不符合无理由退货的场景',
              href: '/help/return-exceptions',
            },
          ],
        },
      ],
    },
  },
  {
    slug: 'our-return-policy',
    category: 'returns-and-refunds',
    realUrl: 'https://www.joybuy.co.uk/help/our-return-policy',
    title: {
      en: 'Our Return Policy',
      zh: '退货政策',
    },
    blocks: {
      en: [
        {
          type: 'p',
          segments: [
            {
              t: 'Joybuy provides voluntary free returns within 14 or 30 days',
              b: 1,
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'Joybuy provides a voluntary 30-day free return service for most products. Some designated products may be subject to a different voluntary free return period. The applicable return period is subject to the information displayed on the product page, checkout page, order confirmation, and in this Return Policy. Please carefully check the applicable return period before placing your order.',
            },
            {
              t: ' The available free return methods (such as home collection and/or drop‑off at a return point) may vary depending on your location.',
            },
            {
              t: " Unless you find the product is damaged, faulty and not as described on delivery then you are absolutely entitled for a full refund. We really appreciate you thinking of returning items to us, to make sure the process goes smoothly, it's important to return each item in the same condition you received it.",
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'If you receive a product in sealed packaging, please ensure it is unused, with all original packaging and accessories intact. Certain items (e.g. tablets, mobile phones) are sold in manufacturer‑sealed condition. You may open the outer packaging to inspect the product. However, for items with a one‑time tear‑off seal (where the seal cannot be reapplied once opened), breaking the seal means the product can no longer be sold as new, in such cases, a deduction may apply even if the product has not been activated or used. ',
            },
            {
              br: 1,
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'If a manufacturer‑sealed product is returned without quality issues but has been unsealed or opened beyond what is necessary to inspect, activated, used, or has damaged original packaging that prevents it from being sold as new (including a broken one‑time seal), we may deduct an amount reflecting the loss in value from your refund. ',
            },
            {
              br: 1,
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'If you receive a product without factory sealing, please ensure the returned item shows no signs of use or physical damage.',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'Joybuy has the right to request product photos, information, or videos from customers when processing after-sales requests. This helps prevent unnecessary shipping costs for both parties in cases where the return does not meet the after-sales requirements. Most items sold on Joybuy are subject to our general return policy, but some products have different policies. Go to ',
            },
            {
              t: 'Return Exceptions',
              href: '/help/return-exceptions',
            },
            {
              t: ' to find out more.',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'Please rest assured that Joybuy’s return policy is provided in addition to, and does not affect, any of',
              b: 1,
            },
            {
              t: ' ',
              b: 1,
            },
            {
              t: 'your statutory rights',
              b: 1,
              href: '/help/statutory-rights',
            },
            {
              t: ' as a customer.',
              b: 1,
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'Seasonal Cooling Products',
              b: 1,
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'For designated seasonal cooling products, such as fans, air conditioners and air coolers, Joybuy provides a voluntary 14-day free return service from the date the product is delivered. You must submit your free return request within 14 days after delivery and return the product in accordance with the return instructions.',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'This voluntary 14-day free return period does not affect your statutory right of withdrawal, statutory warranty rights, or any other rights you may have under applicable law in relation to defective, damaged or misdescribed products. Refunds will be handled in accordance with Joybuy’s Return Policy and applicable law.',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'Fresh & Frozen Items',
              b: 1,
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'The majority of fresh items are non-returnable but may be refunded ',
            },
            {
              t: 'if there is a quality problem on delivery.',
              u: 1,
            },
            {
              t: " If you receive a damaged, spilled or otherwise unusable product from Joybuy, we'll issue a refund. This depends on the product's shelf life, for example, if a product's shelf life is 5 days, then we will issue a refund up to 5 days.",
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'As with fresh items, frozen products are non-returnable but may be refunded ',
            },
            {
              t: 'if there is a quality issue on delivery',
              u: 1,
            },
            {
              t: '. If you receive an item that the product package is broken, thawed or with bad smell bought from Joybuy, we will issue a refund.',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'Please note: ',
              b: 1,
            },
            {
              t: 'Refunds for fresh and frozen products are only available in case of quality issues. Please inspect your order within 24 hours of delivery or pickup. If you notice any quality problems (such as spoilage, damage, or thawing), please keep photos or videos of the items and submit an after-sales request which we will handle it promptly. ',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'In accordance with Asia and UK consumer protection regulations, fresh and frozen goods are considered perishable items and are not eligible for change‑of‑mind returns. Therefore, we are unable to offer a refund in cases where, due to personal reasons (such as refusal to accept delivery, failure to receive the order at the agreed time, or missing the scheduled pickup window), the products cannot be delivered or have deteriorated, unless a quality issue is found.',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'Ambient Food & Beverages',
              b: 1,
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'You are eligible for free returns of food and drink products within 30 days of delivery if they are broken, damaged, leaking or unusable due to a quality issue. In such cases, you are fully entitled to a refund. This aligns with your legal rights under Asia and UK consumer laws, which guarantee that products must be of satisfactory quality, fit for purpose and match the description. ',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'Kind reminder: ',
              b: 1,
            },
            {
              t: 'For reasons of public safety and hygiene regulations, we cannot resell returned food and beverage items to other customers. Therefore, if a product is of good quality but you dislike its taste, have ordered the wrong flavour or product, or are requesting a discretionary return, you may contact our service team for further assistance.',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'Fashion Items',
              b: 1,
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'If you are not entirely satisfied with your purchase, we will gladly accept the return of fashion products in new, unused and unaltered condition. This includes any attached tags (product tags and security tags), and, where applicable, hygiene seals and related accessories. Accessories include, but are not limited to, duster bags, garment bags, removable accessories or attachments, and spare parts. ',
            },
            {
              t: 'For example:',
              b: 1,
            },
            {
              br: 1,
            },
            {
              t: 'For shoes,',
              i: 1,
              u: 1,
            },
            {
              t: ' if you are trying on shoes, it is advisable to stand on a carpeted surface in order to protect the soles. The shoebox forms part of the product and, if possible, please ensure that it remains intact by placing it in an outer shipping container when sending it back to us. Otherwise, unfortunately, it will not be accepted.',
            },
            {
              br: 1,
            },
            {
              t: 'For intimate apparel, lingerie and swimsuits,',
              i: 1,
              u: 1,
            },
            {
              t: ' if you are not yet sure whether to keep the purchased briefs, bottoms, swimsuits and bikini bottoms, it may be a good idea to try them on over underwear, and without removing the protective adhesive strip.',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'Beauty and Skincare',
              b: 1,
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'Within our free return period, we are happy to offer a full refund if the item remains brand new, unopened, and with its original packaging and seals completely intact (including plastic wrapping and hygiene seals).',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'Due to the specific nature of beauty and skincare products, and in accordance with hygiene and health safety regulations, we cannot accept returns once the item has been opened, the seal broken, or the product used. As opened items pose a hygiene risk and cannot be resold to other customers, we appreciate your understanding in this matter.',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'Please rest assured that if the product is damaged during transport or has a quality defect, regardless of whether it has been opened, please contact us immediately. Upon verification, we will promptly process a full refund or arrange a free replacement for you.',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'Heavy and Bulky Items',
              b: 1,
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'For heavy and bulky items are eligible for our free returns policy within 30 days when you find the product is faulty. If the item you have received is damaged, defective or incorrect within 30 days of delivery, you may entitled to a full refund. If you find any defectives after 30 days of delivery, you may be entitled to a repair, replacement or a refund. If this is the case, you can submit a return request directly with some photos or videos to check where the faults are and arrange a free collection for you.',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'For reasons other than a product defect, you will be responsible for the cost of the return or the cost will be deducted from your refund if you use a prepaid return label.',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'Gift Cards',
              b: 1,
            },
            {
              t: ' ',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'Gift Cards are non-returnable. However, a refund may be requested through our customer support team within 14 days of receipt if the Gift Card has not been added to an account or used. For full details, see ',
            },
            {
              t: 'Terms & Conditions',
              href: 'https://www.joyfumi.com/help/giftcard-terms-conditions',
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
              t: 'Warranty & Support After 30 Days',
              b: 1,
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'Legal Guarantee',
              b: 1,
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: "The legal guarantee applies to all items that you buy from us. Legal guarantee means that a product is or must do what the consumer can reasonably expect from it. Some products also have a manufacturer's guarantee. This guarantee does not affect the legal guarantee.",
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'If a product becomes defective after 30 days, customer should contact our customer support team for further assistance. Depending on the item and the issue, Joybuy may offer support options, or directing customers to the manufacturer for warranty service. Some products are covered under the manufacturer’s warranty, in such cases, we may refer customers to the manufacturer for repairs or replacement. Customers can also visit the manufacturer’s website or contact them directly for troubleshooting and warranty claims. ',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'Friendly reminder: ',
              b: 1,
            },
            {
              t: 'Joybuy does not accept returns after 30 days for consumable products, including but not limited to paper goods, detergents, drinks, food, vitamins and supplements, and personal hygiene products, unless required by applicable law. ',
            },
          ],
        },
        {
          type: 'p',
          segments: [],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'Returns may also be refused where the issue is caused by accidental damage, deliberate damage, misuse, external factors, or normal wear and tear. This does not affect your rights if the product is faulty, incorrect, or not as described.',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'Return Costs',
              b: 1,
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'Please note that in most cases the return label is created and prepaid by Joybuy, so no extra return fee is charged to you. Free returns are offered in all delivery areas, but the specific return method (home collection and/or drop‑off) may differ by location. However, if your item is not eligible for a free return as listed below, you will need to pay the return costs yourself, or the cost may be deducted directly from your refund if you use a Joybuy prepaid return label.',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'Ineligible or Incorrect Returns',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'Will I receive a full refund after return?',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'Return Methods',
              b: 1,
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'Once your after‑sales request has been processed, you can return items using one or more of the following methods, depending on your location and the options shown in your return request',
            },
            {
              t: ' (go to ',
            },
            {
              t: 'How do I return an item for a refund?',
              href: '/help/return-request',
            },
            {
              t: ' to find out how):',
            },
          ],
        },
        {
          type: 'list',
          ordered: false,
          items: [
            [
              {
                t: 'Home collection',
              },
            ],
            [
              {
                t: 'Drop‑off at a designated return point (where available)',
              },
            ],
          ],
        },
      ],
      zh: [
        {
          type: 'p',
          segments: [
            {
              t: 'Joybuy提供14至30天免费退货服务',
              b: 1,
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'Joybuy为大多',
            },
            {
              t: '数商品提供30天免费退货服务。部分指定商品可能适用不同的免费退货期限，具体期限以商品页面、结算页、订单确认信息及本退货政策中的说明为准。请您在购买前仔细查看相关商品适用的退货期限。',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '可用的免费退货方式（如上门取件和/或到指定网点自助退货）会因您所在的地区而有所不同。',
            },
            {
              t: '需要您注意的是，退回的商品需保持完好状态，没有使用痕迹或人为损坏。当然，如果您遇到商品本身质量问题、配件不完整、运输破损或与描述不符的情况，我们将第一时间为您安排全额退款。为确保顺利办理退货退款，请您保持商品与收货时状态一致。',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '如果您收到的是带有塑封的商品，请确保商品未经使用，且包装、配件保持完好。部分商品（如平板电脑、手机）以原厂密封状态销售。您可以打开外包装检查商品。但对于带有一次性防拆封条的商品（即：开封后无法复原），撕开封条意味着商品无法再次以新品状态销售，在此情况下，即使商品未被激活或使用，我们仍可能扣除相应的价值贬损金额。',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '如果原厂密封包装的产品本身无质量问题，但退回时存在超出必要检查范围的拆封、激活使用，或原包装损坏导致无法作为新品销售（包括一次性封条破损），根据商品价值贬损情况，我们可能从您的退款中扣除对应金额。',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '如果您收到的商品本身无塑封，请在退货时确保商品无使用痕迹或人为损坏。',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '办理退货过程中，我们可能会请您配合提供商品照片、视频或补充说明，这样既能帮助我们快速确认情况，也能避免不必要的运费产生。要特别说明的是，绝大多数商品都适用本政策（不包含定制、易腐等有特殊属性的商品、以及',
            },
            {
              t: '不符合无理由退货的场景',
              href: '/help/return-exceptions',
            },
            {
              t: '），您可以通过此政策页面查看更多细节。',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '请您放心，Joybuy的退货政策是消费者法定权利的补充，并不影响消费者的任何法定权利。',
              b: 1,
              i: 1,
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '季节性制冷产品',
              b: 1,
            },
            {
              t: ' ',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '对于指定的季节性制冷产品，例如风扇、空调和冷风机，Joybuy提供14天免费退货服务。您需要在商品送达后14天内提交免费退货申请，并按照退货说明退回商品。 该14天免费退货期限不影响您依法享有的法定撤回权、法定质保权，以及针对瑕疵、破损或描述不符商品依法享有的其他相关权利。退款将根据Joybuy退货政策及适用法律处理。',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '生鲜和冷冻商品',
              b: 1,
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '针对生鲜食品我们有以下特别服务说明：',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '生鲜食品不支持退换，如果您签收后发现商品存在质量问题（如损坏、渗漏或无法正常食用），我们会立即为您安排退款，您无需将商品退回。具体售后时效以商品保质期为准，例如保质期5天的生鲜商品，我们会提供等于该商品保质期的售后保障。',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '冷冻食品同样适用，如果您签收后发现冷冻商品存在包装破损、化冻或异味等情况，我们会第一时间为您操作退款。',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '温馨提醒：',
              b: 1,
            },
            {
              t: '生鲜冻品仅在出现质量问题时提供退款服务。请您在签收/提取后的24小时内尽快检查，如果发现任何质量问题（如变质、破损、化冻等），请您保留商品图片或视，从您的订单页面提交售后申请，我们将第一时间为您处理。根据亚洲及英国消费者权益法规，生鲜冻品属于易腐商品，不适用无理由退货。因此，在无质量问题的情况下，因您个人原因（如拒绝签收、未在约定时间接收、错过自提时间等）导致商品无法交付或变质的，我们将无法提供退款服务。',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '常温食品和饮料',
              b: 1,
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '若您收到的食品或饮品在送达后存在破损、漏液/漏气或因本身质量问题无法使用的情况，我们会立即为您安排退款。这符合亚洲及英国消费者法律赋予您的合法权利，该法律保证商品必须具备满意的质量、符合其用途并与描述相符。',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '温馨提醒：',
              b: 1,
            },
            {
              t: '出于公共安全和卫生保护条例的考虑，退回的食品和饮品将无法再次销售给其他顾客。因此，如果食品或饮品没有任何质量问题，您只是不喜欢其口味、订购了错误的商品或希望无理由退款，请您联系我们的客户服务团队为您提供支持。',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '服饰箱包类',
              b: 1,
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '如果您对商品存在任何顾虑，我们诚挚接受未经穿着使用、未经改动且保留完整标识的全新商品退货。',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '请您特别注意以下细节：',
              b: 1,
            },
            {
              br: 1,
            },
            {
              t: '所有商品需保留原厂标签（含产品标签和防伪标签），如商品本身带有卫生密封条或相关配件（例如防尘袋、衣物护罩、可拆卸装饰配件、备用部件等）也需保持原样。如果出现个人修改尺寸，长时间穿着、体味及香水污染等，非常抱歉我们无法为您办理退款。',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '为保障您的权益，以下试穿建议供您参考：',
              b: 1,
            },
            {
              br: 1,
            },
            {
              t: '鞋类商品',
              i: 1,
              u: 1,
            },
            {
              t: '：',
              i: 1,
            },
            {
              t: '建议在铺有地毯的地面进行试穿，以避免鞋底磨损或者沾染灰尘。鞋盒属于商品的重要组成部分，退货时请将其放入外包装箱妥善寄回，若鞋盒缺失可能影响退货受理。',
            },
            {
              br: 1,
            },
            {
              t: '贴身服饰',
              i: 1,
              u: 1,
            },
            {
              t: '：',
              i: 1,
            },
            {
              t: '试穿内衣（裤）、泳装及比基尼下装时，建议您隔着内衣试穿，同时请勿撕除防护贴条。',
            },
            {
              br: 1,
            },
            {
              t: '如果您需要办理售后或存在任何疑问，欢迎随时通过 ',
            },
            {
              t: '在线服务',
            },
            {
              t: ' ',
            },
            {
              t: '联系我们。',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '美妆护肤类',
              b: 1,
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '在免费退货期内，如果您的商品保持全新、未开封且原始密封包装完好（包括塑封膜、密封贴未撕毁），我们非常乐意为您提供全额退款服务。',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '鉴于美妆护肤类产品的特殊性，根据相关卫生与健康安全规定，一旦商品被打开、密封条破损或被使用过，我们将无法接受退货申请。因为此类商品在拆封后即存在卫生风险，我们无法将其再次出售给其他顾客，希望您能理解。',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '请您放心，如果是产品在运输中损坏或本身存在质量问题，无论是否开封，请务必第一时间联系我们，我们核实后会立即为您办理全额退款或免费更换。',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '大件商品',
              b: 1,
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '自您签收商品之日起30天内，若发现商品存在质量问题（如运输损坏、功能故障或错发商品），我们将为您安排免费退货并全额退款。如果超过30天后发现质量问题，您仍可享受维修、换新或退款服务，届时请通过订单页面提交售后申请，或直接联系在线客服，并附上相关照片/视频说明问题情况，我们会为您安排免费上门取件。',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '温馨提醒：',
              b: 1,
            },
            {
              t: '非质量问题导致的退货，请您理解相关退回的运费需由您自行承担。若您使用我们提供的预付费退货标签，相应的费用将从退款金额中抵扣。',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '礼品卡',
              b: 1,
            },
            {
              t: ' ',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '礼品卡不可退货。但是，如果礼品卡尚未被添加到账户或使用，您可以在收到礼品卡后14天内通过联系我们的客服团队申请退款。有关完整详情，请查看',
            },
            {
              t: '条款与条件',
              href: 'https://www.joyfumi.com/help/giftcard-terms-conditions',
            },
            {
              t: '。',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '签收30天后的质保政策',
              b: 1,
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '法定保障',
              b: 1,
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '您从我们这里购买的所有商品均适用法规。法定保障意味着商品应该符合消费者对其的合理预期。部分商品还附有制造商质保，但其不影响法律保证的效力。',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '如果商品使用超过30天后出现质量问题，请您及时联系 ',
            },
            {
              t: 'Joybuy客服团队 ',
            },
            {
              t: '获取帮助。我们的客服专员将根据商品类型和具体问题，为您提供最适合的解决方案。这包括：为您提供退货退款或者换新处理，或协助您联系制造商进行维修处理。部分商品享有制造商提供的保修服务，遇到这种情况时，我们的客服会协助您与制造商沟通，进行售后服务。您也可以访问制造商官网获取技术支持，或直接致电制造商的客服热线提交保修申请。',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '温馨提示：',
              b: 1,
            },
            {
              t: '快消及易耗类商品在签收30天后不再支持普通售后申请，包括但不限于纸巾、清洁剂、食品饮料、维生素及保健品、个人护理用品等。因意外损坏（如摔落、碰撞）、人为破坏、不当使用、外部因素或正常使用产生的自然损耗，不属于商品质量问题或平台责任范围，我们会根据具体情况拒绝售后申请。',
            },
          ],
        },
        {
          type: 'p',
          segments: [],
        },
        {
          type: 'p',
          segments: [
            {
              t: '如果涉及质量问题、破损、与商品描述不符或其他根据法规应该处理的情形，我们将根据具体情况、消费者提供的信息及适用的法律法规为您提供售后支持。',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '退货费用',
              b: 1,
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '通常情况下，Joybuy会为您自动生成预付运费标签或者二维码，您无需承担任何额外费用，',
            },
            {
              t: '具体退货方式（上门取件和/或投递至指定网点）可能因地区而异。',
            },
            {
              t: '如果您的商品不符合下方免费退货条件，则需要您自行承担退回的运费，若您使用Joybuy提供的预付费退货标签，相应的费用将从退款金额中抵扣，具体信息可以通过点击下方帮助页面查看：',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '不符合退货条件或退错的商品',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '退货后我能收到全额退款吗？',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '退货方式',
              b: 1,
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '售后申请通过后，根据您所在地区会为您显示可用的退货方式，请您通过以下方式退回您的商品（',
            },
            {
              t: '详情查看：',
            },
            {
              t: '如何申请退货退款？',
              href: '/help/return-request',
            },
            {
              t: '）',
            },
          ],
        },
        {
          type: 'list',
          ordered: false,
          items: [
            [
              {
                t: '上门取件',
              },
            ],
            [
              {
                t: '到承运商的任意退货点退回商品（取决于我们在当地是否提供该服务）',
              },
            ],
          ],
        },
      ],
    },
  },
  {
    slug: 'return-exceptions',
    category: 'returns-and-refunds',
    realUrl: 'https://www.joybuy.co.uk/help/return-exceptions',
    title: {
      en: 'Return Exceptions',
      zh: '不符合无理由退货的场景',
    },
    blocks: {
      en: [
        {
          type: 'p',
          segments: [
            {
              t: 'You cannot return the following items. The same exclusions apply to our ',
            },
            {
              t: 'Return Policy',
              href: '/help/our-return-policy',
            },
            {
              t: ' as to the legal right of withdrawal. The products listed below therefore cannot be returned under our return policy (unless they are defective):',
            },
          ],
        },
        {
          type: 'list',
          ordered: false,
          items: [
            [
              {
                t: 'Products that have been opened or unsealed after delivery for health or hygiene reasons, including beauty and skincare items (such as masks, creams and serums), menstrual and dental care products, baby care and nappy‑changing items, and personal care devices such as hair removal tools, shavers and foot massagers.',
              },
            ],
            [
              {
                t: 'Personalised or custom‑made products.',
              },
            ],
            [
              {
                t: 'Food, beverages, alcohol or tobacco that have been opened or unsealed.',
              },
            ],
            [
              {
                t: 'Perishable goods (for example, flowers or fresh food) which, due to their nature, are liable to deteriorate or expire rapidly.',
              },
            ],
            [
              {
                t: 'Digital content (such as e‑books, music files, software or game activation keys) once it has been accessed, downloaded or activated.',
              },
            ],
            [
              {
                t: 'CDs, DVDs or software where the seal has been broken.',
              },
            ],
            [
              {
                t: 'Services that have been fully performed after you agreed that performance could begin during the withdrawal period.',
              },
            ],
          ],
        },
        {
          type: 'p',
          segments: [],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'These exclusions are in line with our return policy and with applicable right‑of‑withdrawal regulations in the Asia and UK.',
            },
          ],
        },
      ],
      zh: [
        {
          type: 'p',
          segments: [
            {
              t: '为保障您和其他消费者的健康与合法权益，除非商品本身存在质量问题或与描述严重不符，以下场景不支持无理由退货退款：',
            },
          ],
        },
        {
          type: 'list',
          ordered: false,
          items: [
            [
              {
                t: '出于健康或卫生原因，收货后已被拆封或开封的商品，例如美妆及护肤品（如片状面膜、乳霜、精华）、经期用品、口腔护理用品、婴儿尿布及护理用品，以及脱毛仪、剃须刀、足部按摩仪等个人护理设备。',
              },
            ],
            [
              {
                t: '个性化或定制类商品。',
              },
            ],
            [
              {
                t: '已拆封或开封的常温食品、酒水饮料及烟草制品。',
              },
            ],
            [
              {
                t: '易腐或保质期较短的商品（例如鲜花、生鲜冷冻食品等）在发出后，因其自身特性容易迅速变质或过期的。',
              },
            ],
            [
              {
                t: '一经访问、下载或激活使用的数字内容（例如电子书、音乐文件、软件或游戏激活码等）。',
              },
            ],
            [
              {
                t: '外包装封条或塑封膜已被拆封的 CD、DVD 或软件产品。',
              },
            ],
            [
              {
                t: '您同意开始履行，且服务已经完成的服务类商品，如安装、拆卸、回收等。',
              },
            ],
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '上述情形均符合适用地区的相关消费者保护法规。如果商品存在质量问题、损坏或与描述严重不符，您的法定权利不受上述条款影响。',
            },
          ],
        },
      ],
    },
  },
  {
    slug: 'wrong-return',
    category: 'returns-and-refunds',
    realUrl: 'https://www.joybuy.co.uk/help/wrong-return',
    title: {
      en: 'Ineligible or Incorrect Returns',
      zh: '错误或不符合条件的退货',
    },
    blocks: {
      en: [
        {
          type: 'p',
          segments: [
            {
              t: 'Please make sure you return the correct item and that it meets the conditions of our ',
            },
            {
              t: 'Return Policy.',
              href: '/help/our-return-policy',
            },
            {
              t: ' We can only process a refund after we have received an eligible item.',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'If you have accidentally returned the wrong item to Joybuy, please contact Joybuy Customer Service as soon as possible. Joybuy does not store incorrectly returned items and we cannot guarantee that such items can be located or sent back to you. No compensation will be provided for items that were sent to us in error.',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'To cancel and return an order for',
            },
            {
              t: ' no-reasons',
              b: 1,
            },
            {
              t: ' within 30 days of delivery, the item must be returned in new, undamaged condition, exactly as you received it. For more details about returns, please check following links:',
            },
          ],
        },
        {
          type: 'list',
          ordered: false,
          items: [
            [
              {
                t: 'Our return policy',
                href: '/help/our-return-policy',
              },
            ],
            [
              {
                t: 'Return exceptions',
                href: '/help/return-exceptions',
              },
            ],
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'We reserve the right to monitor customer return activity and take appropriate action (including, but not limited to, refusing refunds) if account abuse and/or activity in violation of our return policy mentioned here is detected. In the event of a return of an item other than that purchased, we may delay the refund to allow time for proper inspection or disposal of the item without compensation.',
            },
          ],
        },
      ],
      zh: [
        {
          type: 'p',
          segments: [
            {
              t: '请确保您退回的是正确且完整的商品，在收到正确且符合退货条件的商品后，我们会尽快为您处理退款。',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '如果您不小心向Joybuy退回了错误的商品，请尽快联系我们的客服团队。Joybuy无法为错误退回的商品提供专门存储，且无法保证能够找到或将此类商品寄回给您。对于错误寄送给我们的商品，我们不提供退款或赔偿。',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '如果您需要在订单完成后的30天内进行',
            },
            {
              t: '无理由退货',
              b: 1,
            },
            {
              t: '，请您确保商品保持全新且无损坏，与您收到时的情况一致。其他退货退款信息请参考：',
            },
          ],
        },
        {
          type: 'list',
          ordered: false,
          items: [
            [
              {
                t: '退货政策',
                href: '/help/our-return-policy',
              },
            ],
            [
              {
                t: '不符合无理由退货的场景',
                href: '/help/return-exceptions',
              },
            ],
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '为保障公平交易环境，我们会对退货情况进行必要核验。如果发现账户存在异常操作，可能会暂缓处理相关订单以便仔细核查，但绝对不会影响您的正当权益。',
            },
          ],
        },
      ],
    },
  },
  {
    slug: 'refunds-overview',
    category: 'returns-and-refunds',
    realUrl: 'https://www.joybuy.co.uk/help/refunds-overview',
    title: {
      en: 'Refund Timing and Amount',
      zh: '退款说明',
    },
    blocks: {
      en: [
        {
          type: 'p',
          segments: [
            {
              t: 'Refund timing',
              b: 1,
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'Refunds are always sent back to the same payment method used to place the order. The timing depends on whether your order was cancelled or returned.',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'Order cancellations',
              b: 1,
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'Once your order has been successfully cancelled, we will process your refund. It is usually credited to your original payment method within 3–5 working days, depending on your payment provider’s processing time.',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'Returns',
              b: 1,
            },
            {
              br: 1,
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'For returns, we will refund your purchase as soon as possible and no later than 14 days after we receive your notice of withdrawal. However, we may wait to issue the refund until we have received the products, or until you have provided proof that you have sent them back. ',
            },
            {
              t: 'Once the refund has been processed, please allow ',
            },
            {
              t: '3–5 working days',
            },
            {
              t: ' for it to be fully reflected in your account, depending on your bank or payment provider.',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'Refund amount',
              b: 1,
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'If you return only part of your order, the refund will be adjusted accordingly and will apply only to the items actually returned.',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'If your order included free gifts, vouchers or discounts linked to the returned items, the value of any unreturned free gifts, as well as any delivery fees, vouchers or discounts directly connected to those items, may be deducted from your refund.',
            },
          ],
        },
        {
          type: 'p',
          segments: [],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'In such cases, the final refund amount is calculated based on the actual value of the returned items, after all applicable deductions under our return policy.',
            },
          ],
        },
      ],
      zh: [
        {
          type: 'p',
          segments: [
            {
              t: '退款时间',
              b: 1,
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '退款会原路返回至您下单时使用的支付方式，退款时间',
            },
            {
              t: '取决于您的订单是',
            },
            {
              t: '取消',
            },
            {
              t: '还是退货退款',
            },
            {
              t: '。',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '订单取消',
              b: 1,
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '当您的订单成功取消后，我们会立即发起退款。通常情况下，退款会在3–5个工作日内退回到您的原支付方式，具体时间取决于您的银行或支付服务提供方的到账时间。',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '售后退款',
              b: 1,
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '对于退货退款的处理，我们会在收到您撤销/退货通知之日起14天内完成退款，但我们有权在以下任一情形发生后为您处理：',
            },
          ],
        },
        {
          type: 'list',
          ordered: false,
          items: [
            [
              {
                t: '我们已经收到您退回的商品，',
              },
              {
                t: '或',
                b: 1,
              },
            ],
            [
              {
                t: '您提供了充分的退货凭证',
              },
            ],
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '退款处理完成后，通常会需要3–5个工作日内退回到您的原支付方式，具体时间取决于您的银行或支付服务提供方的到账时间。',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '退款金额',
              b: 1,
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '如果您只退回了订单中的部分商品，我们会根据实际退回的商品金额进行相应退款。',
            },
            {
              t: '如果您的订单中包含与所退商品相关的',
            },
            {
              t: '赠品、优惠券或折扣',
            },
            {
              t: '，则以下金额可能会从退款中扣减：',
            },
          ],
        },
        {
          type: 'list',
          ordered: false,
          items: [
            [
              {
                t: '未退回赠品的价值',
              },
            ],
            [
              {
                t: '与所退商品直接关联的配送费用、优惠券或折扣金额',
              },
            ],
          ],
        },
        {
          type: 'p',
          segments: [],
        },
        {
          type: 'p',
          segments: [
            {
              t: '因此，我们会基于退回商品的实际价值，并按照实际支付金额为您操作退款。',
            },
          ],
        },
      ],
    },
  },
  {
    slug: 'return-request',
    category: 'returns-and-refunds',
    realUrl: 'https://www.joybuy.co.uk/help/return-request',
    title: {
      en: 'How do I return an item for a refund?',
      zh: '如何申请退货退款？',
    },
    blocks: {
      en: [
        {
          type: 'p',
          segments: [
            {
              t: 'Once you’ve received your parcel and the order status shows Delivered or Completed, you can submit a return or refund request by following these steps:',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '1. Go to your order details page and click the button next to a specific product to request service for that item, or click the button on the order to request service for some or all items in the order.',
              b: 1,
            },
          ],
        },
        {
          type: 'image',
          src: '/images/help/return-request-en-1.jpg',
        },
        {
          type: 'p',
          segments: [
            {
              t: 'If your product is faulty, damaged, or not working as expected, please select the affected item and submit a request as soon as possible so we can review your case and advise on the next steps. To help us assess your request more quickly, please upload clear photos or videos showing the issue, the product packaging, or any visible damage, along with the serial number (SN) found on the outer box, if applicable.',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'After submission, we’ll complete the review within 24 hours. ',
            },
            {
              t: 'Once your return is approved and, if applicable, the item is received in eligible condition, the refund will be processed automatically.',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '2. Choose a return method',
              b: 1,
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'Drop off your item at any authorized return carrier location or arrange collection by our logistics partner at your preferred time slot.',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '3. You can check the status of your request in the Joybuy app → Me → Returns',
              b: 1,
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'If you don’t see available drop‑off locations or need to rearrange your collection, please contact the Joybuy customer service team for assistance.',
            },
          ],
        },
      ],
      zh: [
        {
          type: 'p',
          segments: [
            {
              t: '收到包裹且订单状态显示“已完成”后，您可以按照以下步骤提交售后申请：',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '1. 前往订单详情页面，点击特定商品旁边的按钮，或点击订单的按钮申请部分商品或整单售后。',
              b: 1,
            },
          ],
        },
        {
          type: 'image',
          src: '/images/help/return-request-zh-1.jpg',
        },
        {
          type: 'p',
          segments: [
            {
              t: '如果您的商品出现故障、损坏或无法正常工作，请选择受影响的商品并尽快提交申请，以便我们审核您的情况并告知后续步骤。为了帮助我们更快地评估您的申请，请上传清晰的照片或视频，展示问题、商品包装或任何可见的损坏情况，以及外包装盒上的序列号（如有）。',
            },
            {
              t: '提交后，我们将在 24 小时内完成审核。',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '2. 选择退货方式',
              b: 1,
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '您可以将商品送至任何授权的退货点，或安排我们的物流合作伙伴在您方便的时间段上门取件。',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '3. 您可以在 Joybuy App → 我的 → 退货 中查看您的申请状态',
              b: 1,
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '如果您没有看到可用的投递点、或者需要重新安排取货时间，请联系我们的客服团队。',
            },
          ],
        },
      ],
    },
  },
  {
    slug: 'return-window',
    category: 'returns-and-refunds',
    realUrl: 'https://www.joybuy.co.uk/help/return-window',
    title: {
      en: 'What is the return window for my order?',
      zh: '我的订单退货时限是多少？',
    },
    blocks: {
      en: [
        {
          type: 'p',
          segments: [
            {
              t: 'We offer a free 30 day return policy on most products from the date of receipt of your order, you can request a return and refund from the order page (see ',
            },
            {
              t: 'How do I return an item for a refund?',
              href: '/help/return-request',
            },
            {
              t: '). ',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'If a return is required, the item must be sent back within ',
            },
            {
              t: '14 calendar days',
            },
            {
              t: ' after you submit your return request. If the item is not returned within this timeframe, the request may be automatically closed.',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'Refunds are issued to your ',
            },
            {
              t: 'original payment method',
            },
            {
              t: '. In most cases, refunds are completed within ',
            },
            {
              t: '3–5 working days',
            },
            {
              t: ', ',
            },
            {
              t: 'depending on your bank or payment provider',
            },
            {
              t: '. For more information, please see ',
            },
            {
              t: 'Refund Timing and Amount',
              href: '/help/refunds-overview',
            },
          ],
        },
      ],
      zh: [
        {
          type: 'p',
          segments: [
            {
              t: '对于大多数商品，我们在您签收之日起30天内提供免费退货服务。在此期间，您可以在订单页面发起退货退款申请（参考：',
            },
            {
              t: '如何申请退货退款？',
              href: '/help/return-request',
            },
            {
              t: '）。',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '对于需要退货的订单，商品必须在您提交退货申请后的14个自然日内寄出。如果在该期限内您未能将商品寄回，退货申请可能会被系统自动关闭。',
            },
          ],
        },
        {
          type: 'p',
          segments: [],
        },
        {
          type: 'p',
          segments: [
            {
              t: '退款将退回至您的原支付方式，在大多数情况下退款处理完毕后，会需要3–5个工作日内退回至您的账户，具体取决于您使用银行卡、支付方式的到账时间。更多信息请您查看：',
            },
            {
              t: '退款说明',
              href: '/help/refunds-overview',
            },
            {
              t: '。',
            },
          ],
        },
      ],
    },
  },
  {
    slug: 'return-method',
    category: 'returns-and-refunds',
    realUrl: 'https://www.joybuy.co.uk/help/return-method',
    title: {
      en: 'Can I change my return method?',
      zh: '我可以更改退货方式吗？',
    },
    blocks: {
      en: [
        {
          type: 'p',
          segments: [
            {
              t: 'Customers can’t change the return method directly once the request has been created. However, there are two options:',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'Cancel and resubmit the return ',
              b: 1,
            },
          ],
        },
        {
          type: 'list',
          ordered: false,
          items: [
            [
              {
                t: 'As long as you haven’t sent the parcel yet, you can cancel your current return request from the order page and submit a new one.',
              },
            ],
            [
              {
                t: 'If your address and order are eligible for more than one return method (e.g. Pickup and Drop‑off), the available options will be shown again when you create the new request.',
              },
            ],
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'Ask Customer Service to help (where multiple options exist) ',
              b: 1,
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'If your order supports more than one return method, our team can help you switch between Pickup and Drop‑off, provided that:',
            },
          ],
        },
        {
          type: 'p',
          segments: [],
        },
        {
          type: 'list',
          ordered: false,
          items: [
            [
              {
                t: 'The courier is not already on the way to pick up your parcel, and',
              },
            ],
            [
              {
                t: 'For Drop‑off, you have not yet handed over the parcel at the drop‑off point.',
              },
            ],
          ],
        },
        {
          type: 'p',
          segments: [],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'If your order or location only supports one return method, we’re unable to change it, even if you contact customer service team. Once the parcel has been picked up or dropped off, the return method can no longer be changed.',
            },
          ],
        },
        {
          type: 'p',
          segments: [],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'If you’re unsure which option is best or need help cancelling and resubmitting a return, our team is always happy to assist.',
            },
          ],
        },
      ],
      zh: [
        {
          type: 'p',
          segments: [
            {
              t: '售后申请提交后，客户无法直接自行修改退货方式，您可以参考以下两种方式进行操作：',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '取消当前申请并重新提交',
              b: 1,
            },
          ],
        },
        {
          type: 'list',
          ordered: false,
          items: [
            [
              {
                t: '只要您尚未寄出包裹，您可以随时取消当前退货申请，并重新发起新的退货申请。',
              },
            ],
            [
              {
                t: '如果您的地址和订单支持多种退货方式（例如上门取件和服务网点投递），系统会在您重新创建退货申请时为您展示可选的退货方式。',
              },
            ],
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '存在多种方式时联系客服协助修改',
              b: 1,
            },
          ],
        },
        {
          type: 'p',
          segments: [],
        },
        {
          type: 'p',
          segments: [
            {
              t: '如果您的订单支持不止一种退货方式，我们的客服团队可以在以下前提下，协助您取消当前售后单并为您重新提交： ',
            },
          ],
        },
        {
          type: 'list',
          ordered: false,
          items: [
            [
              {
                t: '上门取件：快递员尚未分配或者没有在上门取件途中；',
              },
            ],
            [
              {
                t: '自助投递：您尚未在自助投递点交付包裹。',
              },
            ],
          ],
        },
        {
          type: 'p',
          segments: [],
        },
        {
          type: 'p',
          segments: [],
        },
        {
          type: 'p',
          segments: [
            {
              t: '如果您的订单或所在地区仅支持一种退货方式，我们的客服团队也无法协助您进行修改。',
            },
            {
              t: '一旦包裹已被快递员取走、或者已在投递点成功寄回，退货方式将无法更改。',
            },
          ],
        },
        {
          type: 'p',
          segments: [],
        },
        {
          type: 'p',
          segments: [],
        },
        {
          type: 'p',
          segments: [
            {
              t: '如果您不确定哪种退货方式更适合自己，或需要帮助取消并重新提交退货申请，我们的客服团队随时乐意为您提供协助。',
            },
          ],
        },
      ],
    },
  },
  {
    slug: 'return-pickup-reschedule',
    category: 'returns-and-refunds',
    realUrl: 'https://www.joybuy.co.uk/help/return-pickup-reschedule',
    title: {
      en: 'How can I reschedule my return pickup?',
      zh: '如何重新预约退货取件时间？',
    },
    blocks: {
      en: [
        {
          type: 'p',
          segments: [
            {
              t: 'You can reschedule your pick-up time only for return orders that are handled directly by Joybuy’s own courier team - JoyExpress. If your return is managed by an external logistics partner, the reschedule option will not be available.',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'How to reschedule your pick-up time:',
              b: 1,
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '1. Log in to your Joybuy account.',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '2. Go to ',
            },
            {
              t: 'Me',
            },
            {
              t: ' > ',
            },
            {
              t: 'Returns',
            },
            {
              t: ' and select your return order.',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '3. Tap ',
            },
            {
              t: 'Reschedule.',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '4. Select a new available time slot.',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '5. Confirm your new pick-up time.',
            },
          ],
        },
        {
          type: 'image',
          src: '/images/help/return-pickup-reschedule-en-1.png',
        },
        {
          type: 'p',
          segments: [
            {
              t: 'Please note:',
              b: 1,
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'You can only reschedule one time.',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'You can modify the pick-up time only (changing return method is not supported).',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'Rescheduling is available only before the courier is on the way.',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'You’ll receive an email once your new pickup time has been successfully updated.',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'If you can’t see the Reschedule button:',
              b: 1,
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'You may have already rescheduled once.',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'The courier might already be on the way to pick up your return.',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'Your return is handled by a partnered logistics.',
            },
          ],
        },
      ],
      zh: [
        {
          type: 'p',
          segments: [
            {
              t: '只有由Joybuy自有快递团队 - JoyExpress处理的退货订单，可以支持重新预约取件时间。如果您的退货由其他合作物流伙伴处理，则无法重新预约。',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '如何重新安排取件时间：',
              b: 1,
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '1. 登录您的Joybuy账户。',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '2. 前往 “我的” > “售后” 并选择您的退货订单。',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '3. 点击 “取件改约”。',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '4. 选择新的可用时间段。',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '5. 确认新的取件时间。',
            },
          ],
        },
        {
          type: 'image',
          src: '/images/help/return-pickup-reschedule-zh-1.png',
        },
        {
          type: 'p',
          segments: [
            {
              t: '温馨提示：',
              b: 1,
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '取件时间只能重新安排一次。',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '您只能修改取件时间（不支持更改退货方式）。',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '仅在快递员未出发前支持重新预约。',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '新的取件时间更新成功后，您将收到一封电子邮件。',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '如果看不到“重新预约”按钮：',
              b: 1,
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '您可能已经重新预约过一次。',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '快递员可能已经在前往取件的途中。',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '您的退货由合作物流伙伴处理。',
            },
          ],
        },
      ],
    },
  },
  {
    slug: 'return-refund',
    category: 'returns-and-refunds',
    realUrl: 'https://www.joybuy.co.uk/help/return-refund',
    title: {
      en: 'Will I receive a full refund after return?',
      zh: '退货后我能收到全额退款吗？',
    },
    blocks: {
      en: [
        {
          type: 'p',
          segments: [
            {
              t: 'In most cases, yes, provided that the returned product is in its original condition – complete, undamaged and with no signs of use.',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'You are always fully entitled to a full refund if the item is faulty, damaged or not as described on delivery, in line with Asia and UK consumer law.',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'In a few situations, your refund may be adjusted:',
            },
          ],
        },
        {
          type: 'list',
          ordered: false,
          items: [
            [
              {
                t: 'The return does not meet the conditions set out in our ',
              },
              {
                t: 'Return Policy',
                href: '/help/our-return-policy',
              },
            ],
            [
              {
                t: 'The return is for a non‑fault reason (for example, you changed your mind or ordered the wrong item) and, under our policy, certain costs (such as specific delivery or service fees) are not refundable.',
              },
            ],
            [
              {
                t: 'You purchased extra services (for example, installation) that have already been provided.',
              },
            ],
            [
              {
                t: 'Perishable goods cannot be delivered or deteriorate because of an incorrect address or repeated unsuccessful delivery attempts.',
              },
            ],
            [
              {
                t: 'Only part of an order is returned, or a free gift linked to the returned item is not sent back.',
              },
            ],
          ],
        },
        {
          type: 'p',
          segments: [],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'In these cases, we will calculate your refund based on the actual value of the items returned, after any applicable deductions in line with our ',
            },
            {
              t: 'Return Policy',
              href: '/help/our-return-policy',
            },
            {
              t: '. We will always show you the final refund amount on your refund confirmation.',
            },
          ],
        },
      ],
      zh: [
        {
          type: 'p',
          segments: [
            {
              t: '在大多数情况下，是的。当您退回的商品处于原始完好的状态（配件齐全、无损坏且无明显使用痕迹），您通常会获得全额退款。',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '如果商品在送达时存在质量问题、破损或与描述明显不符，根据亚洲及英国消费者法规，您始终有权利获得全额退款。',
            },
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: '在少数情况下，退款金额可能会有所调整：',
            },
          ],
        },
        {
          type: 'list',
          ordered: false,
          items: [
            [
              {
                t: '退货不符合我们的',
              },
              {
                t: '退货政策',
                href: '/help/our-return-policy',
              },
              {
                t: '；',
              },
            ],
            [
              {
                t: '退货原因为非商品故障（例如：无理由退货、买错商品等），根据政策比如配送费用或服务费（如有）则不予退还；',
              },
            ],
            [
              {
                t: '您购买的额外服务（例如：安装服务）已经实际提供；',
              },
            ],
            [
              {
                t: '因地址填写错误、或多次投递未成功导致生鲜或易腐商品无法送达或变质；',
              },
            ],
            [
              {
                t: '仅退回订单中的部分商品，或者没有完整退回与退货商品绑定的赠品。',
              },
            ],
          ],
        },
        {
          type: 'p',
          segments: [],
        },
        {
          type: 'p',
          segments: [
            {
              t: '在上述情形下，我们会根据实际收到的退回商品的价值，以及您的实际支付金额（即不包含优惠券、积分、折扣等），为您计算退款金额，退款金额会清晰为您进行。',
            },
          ],
        },
      ],
    },
  },
  {
    slug: 'submit-complaint',
    category: 'returns-and-refunds',
    realUrl: 'https://m.joybuy.co.uk/help/submit-complaint',
    title: {
      en: 'Submit a Complaint',
      zh: '提交投诉',
    },
    blocks: {
      en: [
        {
          type: 'p',
          segments: [
            {
              t: 'We are here to help and will work to resolve your complaint as quickly as possible. Please follow below steps:',
            },
          ],
        },
        {
          type: 'list',
          ordered: true,
          items: [
            [
              {
                t: 'Start a live chat directly with our support team (available 24/7, recommended).',
              },
            ],
            [
              {
                t: 'Email us at Joybuyfumi@gmail.com.',
              },
            ],
            [
              {
                t: 'Request a callback via the app or website.',
              },
            ],
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: 'We aim to start processing your complaint within 1 working day and respond within 2 working days, following up until a full resolution is reached.',
            },
          ],
        },
      ],
      zh: [
        {
          type: 'p',
          segments: [],
        },
        {
          type: 'p',
          segments: [
            {
              t: '我们竭诚为您提供帮助，并将尽快解决您的问题，请您查看以下方式： ',
            },
          ],
        },
        {
          type: 'list',
          ordered: false,
          items: [
            [
              {
                t: '直接与我们的支持团队进行在线聊天（全天候 24/7 服务，推荐使用）',
              },
            ],
            [
              {
                t: '发送电子邮件至 Joybuyfumi@gmail.com',
              },
            ],
            [
              {
                t: '通过Joybuy App或通过我们的网站要求回电',
              },
            ],
          ],
        },
        {
          type: 'p',
          segments: [
            {
              t: ' 我们会在1个工作日内开始处理您的投诉，并在2个工作日内回复您的投诉，并且持续跟进至问题解决。',
            },
          ],
        },
      ],
    },
  },
]

export const csArticleBySlug = Object.fromEntries(
  csArticles.map((article) => [article.slug, article]),
)
