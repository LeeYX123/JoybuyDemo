// 批次 Q（需求 15.1 / 15.2）：真站 help 中心「Privacy Policy」页正文。
// 来源：2026-11-20 Playwright 实测真站对应 help 页（批次 Q 抓取，原始数据见 var/policy_help_20261120/）。
// 批次 S 追加（用户 2026-11-20 口径）：正文中所有真站网址 → www.joyfumi.com（保留路径结构）；
// 公司名 / 地址 / 注册号 / 监管表述与邮箱不变。
//（原始抓取 var/policy_help_20261120/content_{en_GB,zh_CN}_privacy-policy.json；
//  zh 为真站自带中文版，非机器翻译）。
// 口径：除邮箱 → Joybuyfumi@gmail.com 外，全文照抄真站（公司名 / 地址 / 注册号 /
// 监管表述 / 章节 / 表格 / 生效日期均保持原文）。块结构：p{segments} + table{rows}；
// segments 内 t=文本、b=粗体、i=斜体、href=链接、br=换行（真站正文用 <br> 分行）。
const en = [
  {
    type: 'p',
    segments: [
      {
        t: 'JOYBUY PRIVACY POLICY',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        br: 1,
      },
      {
        t: ' Jingdong Retail (UK) Limited, Jingdong Retail (Netherlands) B.V., Jingdong Retail (France) SAS, and Jingdong Retail Germany GmbH (each as a data controller, collectively referred to as “',
      },
      {
        t: 'Joybuy',
        b: 1,
      },
      {
        t: '”, "',
      },
      {
        t: 'we',
        b: 1,
      },
      {
        t: '", "',
      },
      {
        t: 'us',
        b: 1,
      },
      {
        t: '" or "',
      },
      {
        t: 'our',
        b: 1,
      },
      {
        t: "\") attaches great importance to the protection of its users' and customers' privacy and personal information. We collect and use Personal Data (defined below) when you visit our website (",
      },
      {
        t: 'www.joyfumi.com',
        href: 'https://www.joyfumi.com',
      },
      {
        t: '), use the Joybuy app ("',
      },
      {
        t: 'App',
        b: 1,
      },
      {
        t: '") and buy our products and / or services, contact us or otherwise engage with us (together the "',
      },
      {
        t: 'Services',
        b: 1,
      },
      {
        t: '").',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: ' This Privacy Policy ("',
      },
      {
        t: 'Policy',
        b: 1,
      },
      {
        t: '") explains how we collect, use, retain, share, transfer or otherwise process your Personal Data (defined below) when you access and use our Services.',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: ' Please note, our processing activities may differ if you have registered for an account with us or if you have signed-up for one of our memberships. Where there is a distinction between the way in which we use the Personal Data of members and non-members, we will make this clear below (see section 4 (Details of processing) for more information).',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: ' Please read this Policy carefully. If you have any questions, please feel free to contact us via ',
      },
      {
        t: 'Joybuyfumi@gmail.com',
        href: 'mailto:Joybuyfumi@gmail.com',
      },
      {
        t: '.',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: ' You should also review our ',
      },
      {
        t: 'Terms of Use',
        href: '/pages/terms-of-use',
      },
      {
        t: ' and ',
      },
      {
        t: 'Cookies Policy',
        href: '/pages/cookie-policy',
      },
      {
        t: '. to understand other aspects of our relationship with you.',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: ' This Policy covers:',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: ' 1. Scope',
      },
      {
        br: 1,
      },
      {
        t: ' 2. How we obtain your Personal Data',
      },
      {
        br: 1,
      },
      {
        t: ' 3. Lawful Basis of processing Personal Data',
      },
      {
        br: 1,
      },
      {
        t: ' 4. Details of processing',
      },
      {
        br: 1,
      },
      {
        t: ' 5. Sharing with third parties',
      },
      {
        br: 1,
      },
      {
        t: ' 6. Transfer to countries outside the EEA and UK',
      },
      {
        br: 1,
      },
      {
        t: ' 7. Retention',
      },
      {
        br: 1,
      },
      {
        t: ' 8. Your rights',
      },
      {
        br: 1,
      },
      {
        t: ' 9. Protection of minors',
      },
      {
        br: 1,
      },
      {
        t: ' 10. Contact details',
      },
      {
        br: 1,
      },
      {
        t: ' 11. Changes to this Policy',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: ' 1 Scope',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: ' 1.1 We will only process Personal Data in accordance with this Policy. Personal Data means information from which you may be identified both directly (from that information alone) and indirectly (when different pieces of information are combined) ("',
      },
      {
        t: 'Personal Data',
        b: 1,
      },
      {
        t: '").',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: ' 1.2 The Services include links to third party websites and integrated third party services (such as our customer service agent). This Policy does not apply to such third-party services and we are not responsible for the content of these websites, services provided by these third parties or their compliance with the applicable privacy and data protection legislation. Please review third-party privacy policies and, where applicable, your privacy settings of such third parties.',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: ' 2 How we obtain your Personal Data',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: ' 2.1 We obtain your Personal Data in various ways:',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: ' a. We obtain your Personal Data when you provide it to us. For example, if you contact us, if you sign up for our newsletter or if you provide information to us in the course of receiving our Services.',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: ' b. We may collect your data with your consent or, in extremely exceptional circumstances, such as when necessary cookies are required to access webpages, we may collect information directly from you.For more information on this, please see our ',
      },
      {
        t: 'Cookie Policy',
        href: '/pages/cookie-policy',
      },
      {
        t: '.',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: ' c. We obtain your Personal Data from other sources. For example, from social media platforms such as Facebook, Instagram, TikTok, Pinterest, Twitter if you view or interact with our content on those platforms. We will only be able to see the content you post to your social media account if your profile is set to "public" or if we are "following" you. For more information on the specific categories of Personal Data we collect and process about you, please see section 4 (Detail of processing) below.',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: ' 3 Lawful Basis of processing Personal Data',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: ' 3.1 We process your Personal Data where we have a lawful basis under UK and European data protection law for doing so. Lawful bases for processing include consent, contractual necessity and our “legitimate interests” or the legitimate interests of others. "Legitimate interests" is a legal term used in UK and European data protection law. When we rely on legitimate interests, we mean in pursuing our own interests we have considered your rights and interests at the same time, and concluded that these are not overridden by your rights.',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: ' 3.2 It may be that providing certain Personal Data to us is a statutory or contractual requirement, a requirement necessary to enter into a contract, or that you are otherwise obliged to provide the data to us. If that is the case, we will inform you thereof separately, and will also explain the possible consequences if you fail to provide such Personal Data to us.',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: ' 3.3 If we rely on your consent to process your Personal Data, we will ask for this before processing.',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: ' 4 Details of processing',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: ' 4.1 The table below sets out what Personal Data we process about you, for which purposes and on which legal basis.',
      },
    ],
  },
  {
    type: 'table',
    rows: [
      [
        'Activity / Category of Personal Data',
        'Personal Data processed',
        'Lawful basis and purposes for processing',
      ],
      [
        'Visiting our website or app (“cookie information”)',
        "• IP address • Your device's unique identifier, such as its IMEI (International Mobile Equipment Identity) or MEID (Mobile Equipment Identifier) • Browsing history • Cookie preferences • Movements on our websites or websites of third parties gathered through tracking cookies • Information gathered through “event tracking” activities. • Information gathered through “device fingerprinting”, where we combine information about the browser, hardware device and their settings to infer it is the same user using our Services. For detailed information about our use of cookies, we refer to our Cookie Policy.",
        'We collect these Personal Data on the basis of your consent or, in case we are not legally required to obtain consent, on the basis of our legitimate interests, namely improving our online services. This is the case with regard to technical cookies necessary for the functioning of the website and several analytic cookies that are not used to treat you differently from other users. We process your Personal Data for purposes of (i) improving our website and/or app, (ii) being able to show you the products and services that fit your preferences, (iii) being able to provide you with consistent service across all your devices, (iv) enhancing our security and protecting your information and (v) identifying you and enhancing your shopping experiences.',
      ],
      [
        'Registering a user account (“user account information”)',
        '• Your gathered cookie information • Telephone number • Email address • Gender • Date of birth • Login details, such as your login name, password, answers to passphrase protection questions, and your Google, Facebook and/or AppleID login information (if you choose to login through one of these third parties). • User avatar',
        'We collect these Personal Data on the basis of your consent or, in case we are not legally required to obtain consent, on the basis of our legitimate interests, namely verifying your identity for security reasons. We process your Personal Data for the purposes of (i) registering you as a user to our Services, (ii) verifying your identity to make sure you are who you say you are, and (iii) enhancing our security and protecting your information. We collect and process your Personal Data for security and risk management purposes, including to detect and prevent fraud, unauthorized activities, and access, and to ensure the security of our Services.',
      ],
      [
        'Additional memberships (“membership information”)',
        '• Your gathered cookie information • Your provided user account information • Your provided shopping information with regard to purchases made through the membership card •Type of membership • Duration of the membership • Credit and coupon amounts • Information with regard to cancellation of the membership',
        'We collect these Personal Data on the basis of your consent or, in case we are not legally required to obtain consent, as this is necessary for the performance of a contract or on the basis of our legitimate interests, namely verifying your identity for security reasons. We process your Personal Data for the purposes of (i) registering you as a member, (ii) carrying out our obligations with regard to your membership, (iii) verifying your identity to make sure you are who you say you are, and (iv) enhancing our security and protecting your information.',
      ],
      [
        'Online shopping (“shopping information”)',
        '• Your gathered cookie information • Your provided user account information • Contents of your shopping basket • Order information, such as verification information, the consignee`s name, order number, the goods and/or services purchased, serial numbers, price and terms of payment • Payment details, such as you bank card number, billing address, payment method, amount paid, date of payment and outstanding payments • Delivery information, such as your address or chosen delivery depot, track and trace code and third party delivery company • Order history, such as received and/or cancelled orders, pictures of damaged products, receipts of your orders and information regarding refunds • Location information.',
        'We collect these Personal Data on the basis of your consent or, in case we are not legally required to obtain consent, as this is necessary for the performance of a contract or on the basis of our legitimate interests, namely improving our online services, verifying your identity for reasons of security and for carrying out debtor management activities. We process your Personal Data for the purposes of (i) enhancing your shopping experiences, (ii) carrying out your orders (including identifying your closest delivery location), payments and deliveries as per the contract, (iii) gathering and collecting your order history, (iv) verifying your identity to make sure you are who you say you are, and (v) enhancing our security and protecting your information. We collect and process your Personal Data for security and risk management purposes, including to detect and prevent fraud, unauthorized activities, and access, and to ensure the security of our Services.',
      ],
      [
        'Customer service or otherwise corresponding with you',
        "• If registered, your provided user account information • Your shopping information (including order number, order status, payment status, refund status, refund amounts, refund processing times, delivery information, and transaction history) to the extent necessary to respond to your queries • Content of your message and review, including your queries to our AI customer service system and the AI's responses, voice recording of your conversation with our customer services personnel, for instance a complaint or pictures of a damaged product",
        'We collect these Personal Data on the basis of your consent or, in case we are not legally required to obtain consent, as this is necessary for the performance of a contract or on the basis of our legitimate interests, namely verifying your identity for reasons of security, improving our services and providing customer service and developing and improving our AI systems.\n\nWe use artificial intelligence (AI) technology to provide automated customer service responses to your queries about products, orders, refunds, payments, and delivery. Our AI customer service system accesses your personal data (mentioned in the column to the left) to provide you with personalised responses to your questions. When you interact with our AI customer service system, we rely on our legitimate interest of providing you with customer support and improving the performance, accuracy, and functionality of our AI systems to provide our customers with an improved customer experience.\n\nWe process your Personal Data for the purposes of (i) following up on your questions, complaints and claims, (ii) to provide after-sales services, (iii) providing information with regard to products or services that are relevant to you, (iv) verifying your identity to make sure you are who you say you are, and (v) enhancing our security and protecting your information.',
      ],
      [
        'Newsletter',
        '• If registered, your provided user account information • If not registered, your name and e-mail address • Preferences for receiving information, such as frequency and categories of information',
        'We collect these Personal Data on the basis of your consent. We process your Personal Data for the purposes of (i) providing information with regard to products or services that you might like, and (ii) providing offers.',
      ],
      [
        'Other general purposes ("general information")',
        '• If registered, your provided user account information • If not registered, any other information we possibly have of you that is necessary for the relevant purpose of processing.',
        'We collect these Personal Data as this might be necessary for compliance with a legal obligation that is applicable to us as a data controller or for purposes of our legitimate interests, namely carrying out our regular business activities and protecting our interests in case of conflicts. We process your Personal Data for purposes of (i) following requests of public authorities, (ii) conducting criminal investigations, prosecutions, trails and the execution of judgments, (iii) protecting rights of third parties, (iv) conducting statistical or academic researches, or (v) other circumstances as stipulated by relevant laws and regulations.',
      ],
      [
        'Social media information',
        "• Your interactions with our social media accounts (for example if you 'like' our content or send us a direct message); the content of your direct messages, comments, likes, and any information visible on your profile to us as a result of your interaction; and any other information which is visible to us in relation to those interactions and your social media account.",
        'We collect these Personal Data on the basis of our legitimate interests, namely promoting our services and monitoring our social media presence.',
      ],
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '4.2 If your Personal Data is processed on the basis of legitimate interests, information can be obtained by you as to the specific legitimate interest we are relying on and how we have considered your rights and interests at the same time. For more information, please contact us at ',
      },
      {
        t: 'Joybuyfumi@gmail.com',
        href: 'mailto:Joybuyfumi@gmail.com',
      },
      {
        t: '. ',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: '4.3 We use automated systems to analyse your personal data to create a profile of your preferences and provide you with personalised product recommendations and advertisements. This is known as "profiling" under data protection law. We analyse your browsing behaviour, purchase history, products you\'ve viewed or added to your basket, account preferences, membership information, cookie/device data, size details and other personal characteristics you share with us or we derive from your purchase history. We use profiling to: (a) provide personalised product and purchase recommendations; (b) customise website content; (c) personalise marketing communications (where you\'ve consented to receive these); and (d) improve our services. We rely on your consent for cookie-based profiling (which you can withdraw via Cookie Settings) and our legitimate interests for profiling based on your account activity and purchase history. You have the right to object to profiling based on our legitimate interests by contacting ',
      },
      {
        t: 'Joybuyfumi@gmail.com',
        href: 'mailto:Joybuyfumi@gmail.com',
      },
      {
        t: '. You can opt out of Personalized recommendations at any time by navigating to Me > Setting & Privacy > Personalised settings > Personalised recommendations. You can opt out of cookie-based profiling through Cookie Settings.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        br: 1,
      },
      {
        t: '4.4 It may be that we intend to further process your Personal Data for a purpose other than those for which the Personal Data have been collected. In such case, we will provide you with information about the(se) other purpose(s), the lawful basis we are relying on, and all relevant further information prior to that further processing.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        br: 1,
      },
      {
        t: "4.5 We use artificial intelligence (AI) technology to provide automated customer service and improve our services. Our AI customer service system can answer your questions about products, orders, payments, deliveries, and refunds by accessing your Personal Data. When you contact customer service, you may interact with our AI system. The AI accesses your account information, order history, payment details, and refund information to provide accurate, personalised responses to your specific queries. Your conversations with the AI are logged for quality assurance and to improve the system's performance and accuracy. You can request to speak to a human customer service agent at any time by typing in “request for human support” or by clicking the button of “dislike”. Complex queries beyond the scope of AI's capabilities are automatically escalated and converted to human agents. The AI operates under human supervision. We also provide AI summaries from other users’ reviews in order to enhance user experience. You have the right to object to AI processing of your data for customer service purposes by contacting ",
      },
      {
        t: 'Joybuyfumi@gmail.com',
        href: 'mailto:Joybuyfumi@gmail.com',
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
        br: 1,
      },
      {
        t: '5 Sharing with third parties',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: '5.1 To ensure the smooth delivery of our Services, we may share your Personal Data with some third parties. This, however, only takes place strictly on a need-to-know-basis with:',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: 'a. Group companies of Joybuy, who may also process your Personal Data for the purposes set out in this Policy.',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: 'b. subcontractors and service providers involved in delivery of the Services, such as:',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: '• shipping and trucking companies and depots for purposes of providing our Services;',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: '• auditing companies, consulting and law firms for professional advisory services;',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: '• third party merchants in order for you to carry out purchases of goods and services of third parties that provide offers through our website and App;',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: '• hosting and payment providers for technical and financial infrastructure services;',
      },
      {
        br: 1,
      },
      {
        t: '• marketing partners including online platforms and publishers for providing you with offers through our mailing list, for gathering information about your preferences for provision of customer services, and for collecting and analysing your other behavior preferences on our website or App to retarget and run customized advertisements',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: '• third party customer services company to provide customer services to all employed or engaged by a data processor of Joybuy or affiliated companies of Joybuy, on a need-to-know basis;',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: 'c. If required to do so by law, we will also disclose your Personal Data to third parties, on a need-to-know basis to competent authorities, such as the authorities of the country of transit or destination for customs clearance where such disclosure is required in order to comply with legal requests, where required or legally permitted to establish, exercise or defend legal rights; in order to enforce or apply our terms of supply and other agreements with you; or to protect the rights, property, or safety of Joybuy, our customers, or others, in as far as required by the laws of the respective country; and',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: 'd. We will disclose your Personal Data to third parties, on a need-to-know basis, incidentally, for instance in case of a merger, acquisition, asset transfer or similar transaction of where this is needed to comply with the law or to protect our own rights, properties and safety – in which case we will disclose your Personal Data to the prospective buyer of such business or assets subject to the terms of this Policy.',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: '6 Transfer to countries outside the EEA and UK',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: '6.1 Some of our recipients as referenced above are located in countries outside the United Kingdom ("',
      },
      {
        t: 'UK',
        b: 1,
      },
      {
        t: '") and the European Economic Area ("',
      },
      {
        t: 'EEA',
        b: 1,
      },
      {
        t: '") that may not – by law – provide the same level of data protection as you are used to in the European Union or UK. In those cases, we will ensure that there are appropriate safeguards in place to protect your Personal Data. ',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: '6.3 If and insofar as we transfer Personal Data with parties in countries outside the EEA and UK to which no adequacy decision applies, we will enter into approved standard contractual clauses. A copy of the agreed standard contractual clauses can be requested by you. If needed, we will in addition make use of supplementary measures in order to protect your Personal Data.',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: '6.4 Please also contact us at ',
      },
      {
        t: 'Joybuyfumi@gmail.com',
        href: 'mailto:Joybuyfumi@gmail.com',
      },
      {
        t: ' if you would like to obtain additional information on the transfer of your personal data out of the EEA and UK.',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: '6.5 The Personal Data processed by us are primarily stored on a server located in the Netherlands.',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: '7 Retention periods',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: '7.1 We keep your Personal Data for as long as it is required in order to fulfil the relevant purposes for which we process your Personal Data (as mentioned in Section 4, above), as may be required to satisfy any legal, tax, regulatory or accounting requirements, as required to solve disputes, for information security purposes, to enforce our legal rights, terms and policies, or as otherwise communicated to you. ',
      },
      {
        br: 1,
      },
      {
        t: 'To determine the appropriate retention period for Personal Data, we consider the amount, nature and sensitivity of the Personal Data, the potential risk of harm from unauthorised use or disclosure of your Personal Data, the purposes for which we process your Personal Data and whether we can achieve those purposes through other means, and the applicable legal, regulatory, tax, accounting or other requirements.',
      },
      {
        br: 1,
      },
      {
        t: 'For example, we have to keep basic information about our customers (including order and transaction records) for six years after they cease being customers for tax purposes.',
      },
      {
        br: 1,
      },
      {
        t: 'For more information on our retention periods please contact us at ',
      },
      {
        t: 'Joybuyfumi@gmail.com',
        href: 'mailto:Joybuyfumi@gmail.com',
      },
      {
        t: '.',
      },
      {
        br: 1,
      },
      {
        t: 'Our retention policy does not affect the exercise of your legal rights (mentioned below).',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '7.2 Please contact us at ',
      },
      {
        t: 'Joybuyfumi@gmail.com',
        href: 'mailto:Joybuyfumi@gmail.com',
      },
      {
        t: ', should you wish to be further informed on how long we process your Personal Data.',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: '8 Your rights (incl. the right to object)',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: '8.1 In relation to our processing of your Personal Data, you have the below privacy rights under certain circumstances. To exercise these rights, please email ',
      },
      {
        t: 'Joybuyfumi@gmail.com',
        href: 'mailto:Joybuyfumi@gmail.com',
      },
      {
        t: ' and state Privacy Query in the subject line.',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: 'a. Right to withdraw consent: In so far as our processing of your Personal Data is based on your consent (see above), you have the right to withdraw consent without detriment at any time. ',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: 'You can change your preferences and object to receiving further marketing at any time selecting the "unsubscribe" link at the end of all our marketing and promotional update communications to you, or by sending us an email to ',
      },
      {
        t: 'Joybuyfumi@gmail.com',
        href: 'mailto:Joybuyfumi@gmail.com',
      },
      {
        t: ' and state Privacy Query in the subject line.',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: 'b. Right of access: You have the right to find out what Personal Data we hold about you and request access to your Personal Data. This enables you to receive a copy of the Personal Data we hold about you (but not necessarily the documents themselves). We will then also provide you with further details of our processing of your Personal Data in accordance with applicable law. ',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: 'c. Right to rectification: You have the right to request rectification of the Personal Data that we hold about you. This enables you to have any incomplete or inaccurate data we hold about you corrected. ',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: 'd. Right to erasure: You have the right to request erasure of your Personal Data. This enables you to ask us to delete or remove Personal Data where: (i) the Personal Data are no longer necessary, (ii) you have withdrawn your consent, (iii) you have objected to the processing activities, (iv) the Personal Data have been unlawfully processed, (v) the Personal Data have to be erased on the basis of a legal requirement, or (vi) where the Personal Data have been collected in relation to the offer of information society services. We do not have to honour your request to the extent that the processing is necessary: (i) for exercising the right of freedom of expression and information, (ii) for compliance with a legal obligation which requires processing, (iii) for reasons of public interest in the area of public health, (iv) for archiving purposes, or (v) for the establishment, exercise or defence of legal claims. ',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: 'e. Right to object: You have the right to object to processing of your Personal Data where we are relying on legitimate interests as processing ground (see above). Insofar as the processing of your Personal Data takes place for direct marketing purposes, we will always honour your request. For processing for other purposes, we will also cease and desist processing, unless we have compelling legitimate grounds for the processing which override your interests, rights and freedoms or that are related to the institution, exercise or substantiation of a legal claim. ',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: 'f. Right to restriction: You have the right to request restriction of processing of your Personal Data in case: (i) the accuracy of the Personal Data is contested by you, during the period we verify your request, (ii) the processing is unlawful and restriction is requested by you instead of erasure, (iii) we no longer need the Personal Data but they are required by you for the establishment, exercise or defence of legal claims, or (iv) in case you have objected to processing, during the period we verify your request. If we have restricted the processing of your Personal Data, this means that we will only store them and no longer process them in any other way, unless: (i) with your consent, (ii) for the establishment, exercise or defence of legal claims, (iii) for the protection of the rights of another natural or legal person, (iv) or for reasons of important public interest. ',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: 'g. Right to data portability: You have the right to request to transfer of your Personal Data to you or to a third party of your choice. We will provide to you, or such third, your Personal Data in a structured, commonly used, machine-readable format. Please note that this right only applies if it concerns processing that is carried out by us by automated means, and only if the our processing ground for such processing is your consent or the performance of a contract to which you are a party (see above). ',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: 'h. Automated decision-making: You have the right not to be subject to a decision based solely on automated processing, which significantly impacts you (“which produces legal effects concerning you or similarly significantly affects you”). We use profiling for personalised recommendations (see Section 4.3), but this does not constitute automated decision-making under Article 22A UK GDPR and Article 22 GDPR as recommendations do not produce legal effects or similarly significantly affect you. You have the right to object to this profiling (see Section 4.3 and 8.1(e)).',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: '8.2 The exercise of the above mentioned rights is free of charge and can be carried out by e-mail at ',
      },
      {
        t: 'Joybuyfumi@gmail.com',
        href: 'mailto:Joybuyfumi@gmail.com',
      },
      {
        t: '. If requests are manifestly unfounded or excessive, in particular because of the repetitive character, we will where lawfully permitted, either charge you a reasonable fee or refuse to comply with the request.',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: '8.3 We may request specific information from you to help us confirm your identity before we comply with a request from you concerning one of your rights.',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: '8.4 If you want to de-register from Joybuy, you can do so through your account. You can also contact us at ',
      },
      {
        t: 'Joybuyfumi@gmail.com',
        href: 'mailto:Joybuyfumi@gmail.com',
      },
      {
        t: ' to delete your account. ',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: '8.5 If you have subscribed to our newsletter, you can always revoke your consent through the unsubscribe-link at the bottom of the newsletter.',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: '9 Protection of minors',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: '9.1 Joybuy attaches great importance to the protection of Personal Data of minors. The Services are intended for use by those who are at least 18 years of age. If you are a minor under the age of 18 or such other age of majority as set out in applicable law, you must obtain prior written consent from your parent or legal guardian before using our Services. Joybuy protects Personal Data of minors in accordance with applicable laws and regulations. For Personal Data of minors collected with the consent of parents or legal guardians, we will only use or disclose it when permitted by law, explicitly consented to by the parent or guardian or required for protecting the child. If we find ourselves collecting personal information of a minor without the prior consent of a verifiable parent or legal guardian, we will delete promptly upon becoming aware.',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: '10 Contact details',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: '10.1 Jingdong Retail (UK) Limited (Company number: 15830555), Jingdong Retail (Netherlands) B.V. (Company number 80456774), Jingdong Retail (France) SAS (Company number 947844197 ), and Jingdong Retail Germany GmbH (Company number HRB 277115 B) are joint controllers which administer and host the Services and from which global and strategic decisions are made. The four data controllers operate the website of Joybuy in different UK and EU states. For any questions, comments or requests, you may contact us via ',
      },
      {
        t: 'Joybuyfumi@gmail.com',
        href: 'mailto:Joybuyfumi@gmail.com',
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
        t: '10.2 Our address is: Jingdong Retail (UK) Limited, Floor 3, 20 King Street, London SW1Y 6QY; for other controllers, Floor 12, Boompjes 40, 3011 XB Rotterdam, the Netherlands.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '10.3 Further, the data protection officer can be contacted at ',
      },
      {
        t: 'Joybuyfumi@gmail.com',
        href: 'mailto:Joybuyfumi@gmail.com',
      },
      {
        t: '.',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: '11 Changes to this Policy',
      },
      {
        br: 1,
      },
      {
        br: 1,
      },
      {
        t: '11.1 Joybuy reserves the right to change this Policy on a regular basis. Where required, Joybuy will inform you of updates made to this Policy. The current version is always available on our website and in our App. This Policy became effective in April 2026.',
      },
    ],
  },
]

const zh = [
  {
    type: 'p',
    segments: [
      {
        t: 'JOYBUY 隐私政策',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Jingdong Retail (UK) Limited、Jingdong Retail (Netherlands) B.V.、Jingdong Retail (France) SAS 及 Jingdong Retail Germany GmbH（各自作为数据控制方，合称为"',
      },
      {
        t: 'Joybuy',
        b: 1,
      },
      {
        t: '"、"',
      },
      {
        t: '我们',
        b: 1,
      },
      {
        t: '"或"',
      },
      {
        t: '我们的',
        b: 1,
      },
      {
        t: '")高度重视保护其用户和客户的隐私及个人信息。当您访问我们的网站(',
      },
      {
        t: 'www.joyfumi.com',
        href: 'https://www.joyfumi.com',
      },
      {
        t: ')、使用Joybuy应用程序（"',
      },
      {
        t: 'App',
        b: 1,
      },
      {
        t: '"）、购买我们的产品和/或服务、联系我们或以其他方式与我们互动（合称为"',
      },
      {
        t: '服务',
        b: 1,
      },
      {
        t: '"）时，我们会收集和使用个人数据（定义见下文）。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '本隐私政策（"',
      },
      {
        t: '本政策',
        b: 1,
      },
      {
        t: '"）解释了当您访问和使用我们的服务时，我们如何收集、使用、保留、分享、转让或以其他方式处理您的个人数据（定义见下文）。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '请注意，如果您已向我们注册帐户或已注册我们的某项会员服务，我们的处理活动可能会有所不同。如果我们在使用会员和非会员个人数据的方式上存在区别，我们将在下文（更多信息请参阅第 4 节（处理详情））明确说明。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '请仔细阅读本政策。如有任何疑问，请随时通过',
      },
      {
        t: 'Joybuyfumi@gmail.com',
        href: 'mailto:Joybuyfumi@gmail.com',
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
        t: '您还应查看我们的',
      },
      {
        t: '使用条款',
        href: '/pages/terms-of-use',
      },
      {
        t: '和',
      },
      {
        t: 'Cookie 政策',
        href: '/pages/cookie-policy',
      },
      {
        t: '，以了解与我们关系的其他方面。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '本政策涵盖：',
      },
    ],
  },
  {
    type: 'list',
    ordered: true,
    items: [
      [
        {
          t: '范围',
        },
      ],
      [
        {
          t: '我们如何获取您的个人数据',
        },
      ],
      [
        {
          t: '处理个人数据的合法性基础',
        },
      ],
      [
        {
          t: '处理详情',
        },
      ],
      [
        {
          t: '与第三方共享',
        },
      ],
      [
        {
          t: '向欧洲经济区和英国以外的国家传输',
        },
      ],
      [
        {
          t: '保留',
        },
      ],
      [
        {
          t: '您的权利',
        },
      ],
      [
        {
          t: '未成年人保护',
        },
      ],
      [
        {
          t: '联系方式',
        },
      ],
      [
        {
          t: '本政策的变更',
        },
      ],
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '1 范围',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '1.1 我们将仅根据本政策处理个人数据。个人数据是指可以直接（仅从该信息本身）和间接（当不同信息组合在一起时）识别您身份的信息（"',
      },
      {
        t: '个人数据',
        b: 1,
      },
      {
        t: '"）。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '1.2 服务包括指向第三方网站的链接和集成的第三方服务（例如我们的客服代理）。本政策不适用于此类第三方服务，我们不对这些网站的内容、这些第三方提供的服务或其遵守适用的隐私和数据保护法规的情况负责。请查看第三方的隐私政策以及您在适用情况下关于该第三方的隐私设置。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '2 我们如何获取您的个人数据',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '2.1 我们通过多种方式获取您的个人数据：',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'a. 当您向我们提供个人数据时，我们会获取这些数据。例如，如果您联系我们、注册我们的新闻通讯或在接收我们服务的过程中向我们提供信息。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'b. 我们可能会在征得您同意的情况下收集您的数据，或者在极其特殊的情况下，例如当访问网页需要必要的 Cookie 时，我们可能会直接从您那里收集信息。有关此方面的更多信息，请参阅我们的',
      },
      {
        t: 'Cookie 政策',
        href: '/pages/cookie-policy',
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
        t: 'c. 我们从其他来源获取您的个人数据。例如，来自社交媒体平台，如 Facebook、Instagram、TikTok、Pinterest、Twitter，如果您在这些平台上查看或与我们的内容进行互动。只有当您的个人资料设置为"公开"或我们"关注"您时，我们才能看到您发布到社交媒体帐户的内容。关于我们收集和处理您个人数据的具体类别，请参阅下文第 4 节（处理详情）。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '3 处理个人数据的合法性基础',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '3.1 我们仅在拥有英国和欧洲数据保护法规定的合法性基础时，才会处理您的个人数据。处理的合法性基础包括同意、合同必要性以及我们的"合法利益"或他人的合法利益。"合法利益"是英国和欧洲数据保护法中使用的法律术语。当我们依赖合法利益进行处理时，意味着在我们追求自身利益的同时，已兼顾考虑了您的权利和利益，并认定您的权益并未超越我们的合法利益。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '3.2 向我们提供某些个人数据可能是法定或合同要求、签订合同所必需的要求，或者您有义务向我们提供该数据。如果是这种情况，我们将另行通知您，并解释如果您未能向我们提供此类个人数据可能产生的后果。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '3.3 如果我们依赖您的同意来处理您的个人数据，我们将在处理前征求您的同意。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '4 处理详情',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '4.1 下表列出了我们处理您哪些个人数据、处理目的以及合法性基础。',
      },
    ],
  },
  {
    type: 'table',
    rows: [
      ['活动/个人数据类别', '处理的个人数据', '处理的合法性基础和目的'],
      [
        '访问我们的网站或应用程序（"Cookie 信息"）',
        '• IP 地址 • 您设备的唯一标识符，例如 IMEI（国际移动设备识别码）或 MEID（移动设备识别符）• 浏览历史记录 • Cookie 偏好设置 • 通过跟踪 Cookie 收集的在我们网站或第三方网站上的移动轨迹 • 通过"事件跟踪"活动收集的信息 • 通过"设备指纹识别"收集的信息，即我们结合浏览器、硬件设备及其设置的信息，推断是同一用户在使用我们的服务。关于我们使用 Cookie 的详细信息，请参阅我们的Cookie 政策。',
        '我们在征得您同意的基础上收集这些个人数据，或者，如果法律未要求我们必须征得同意，则基于我们的合法利益（即改进我们的在线服务）收集。后一种情况适用于网站运行所必需的技术 Cookie 以及若干不会用于区分您与其他用户的统计分析 Cookie。我们处理您的个人数据是为了 (i) 改进我们的网站和/或应用程序，(ii) 能够向您展示符合您偏好的产品和服务，(iii) 能够在您的所有设备上为您提供一致的服务，(iv) 加强我们的安全性并保护您的信息，以及 (v) 识别您的身份并提升您的购物体验。',
      ],
      [
        '注册用户帐户（"用户帐户信息"）',
        '• 收集到的您的 Cookie 信息 • 电话号码 • 电子邮件地址 • 性别 • 出生日期 • 登录详细信息，例如您的登录名、密码、密码保护答案，以及您的 Google、Facebook 和/或 AppleID 登录信息（如果您选择通过这些第三方之一登录）• 用户头像',
        '我们在征得您同意的基础上收集这些个人数据，或者，如果法律未要求我们必须征得同意，则基于我们的合法利益（即出于安全原因验证您的身份）收集。我们处理您的个人数据是为了 (i) 将您注册为我们的服务用户，(ii) 验证您的身份以确保您是本人声称的身份，以及 (iii) 加强我们的安全性并保护您的信息。我们出于安全和风险管理目的收集和处理您的个人数据，包括检测和预防欺诈、未经授权的活动和访问，并确保我们服务的安全性。',
      ],
      [
        '附加会员服务（"会员信息"）',
        '• 收集到的您的Cookie信息 • 您提供的用户帐户信息 • 您提供的与通过会员卡进行的购买相关的购物信息 • 会员类型 • 会员期限 • 积分和优惠券金额 • 与会员取消相关的信息',
        '我们在征得您同意的基础上收集这些个人数据，或者，如果法律未要求我们必须征得同意，则基于履行合同的必要或我们的合法利益（即出于安全原因验证您的身份）收集。我们处理您的个人数据是为了 (i) 将您注册为会员，(ii) 履行与您的会员资格相关的义务，(iii) 验证您的身份以确保您是本人声称的身份，以及 (iv) 加强我们的安全性并保护您的信息。',
      ],
      [
        '在线购物（"购物信息"）',
        '• 收集到的您的Cookie信息 • 您提供的用户帐户信息 • 您购物车的内容 • 订单信息，例如验证信息、收货人姓名、订单号、购买的商品和/或服务、序列号、价格和付款条款 • 付款详情，例如您的银行卡号、账单地址、付款方式、支付金额、支付日期和未付金额 • 配送信息，例如您的地址或选定的配送站、跟踪码和第三方快递公司 • 订单历史记录，例如已接收和/或已取消的订单、损坏产品图片、订单收据和退款信息 • 位置信息。',
        '我们在征得您同意的基础上收集这些个人数据，或者，如果法律未要求我们必须征得同意，则基于履行合同的必要或我们的合法利益（即改进我们的在线服务、出于安全原因验证您的身份以及进行债务人管理活动）收集。我们处理您的个人数据是为了 (i) 提升您的购物体验，(ii) 根据合同执行您的订单（包括确定您最近的配送位置）、付款和配送，(iii) 收集和整理您的订单历史记录，(iv) 验证您的身份以确保您是本人声称的身份，以及 (v) 加强我们的安全性并保护您的信息。我们出于安全和风险管理目的收集和处理您的个人数据，包括检测和预防欺诈、未经授权的活动和访问，并确保我们服务的安全性。',
      ],
      [
        '客户服务或以其他方式与您通信',
        '• 如果已注册，您提供的用户帐户信息 • 在响应您的查询所必需的范围内，您的购物信息（包括订单号、订单状态、付款状态、退款状态、退款金额、退款处理时间、配送信息和交易历史记录）• 您消息和评论的内容，包括您向我们的 AI 客服系统提出的问题以及 AI 的回复、您与客服人员通话的录音（例如投诉或损坏产品图片）',
        '我们在征得您同意的基础上收集这些个人数据，或者，如果法律未要求我们必须征得同意，则基于履行合同的必要或我们的合法利益（即出于安全原因验证您的身份、改进我们的服务、提供客户服务以及开发和改进我们的 AI 系统）收集。\n我们使用人工智能 (AI) 技术为您提供自动化的客户服务回复，解答您关于产品、订单、退款、付款和配送的疑问。我们的 AI 客服系统会访问您的个人数据（如左侧栏所述），以便为您的问题提供个性化的回复。当您与我们的 AI 客服系统互动时，我们依赖的是我们为您提供客户支持以及改进我们 AI 系统的性能、准确性和功能以提升客户体验的合法利益。\n我们处理您的个人数据是为了 (i) 跟进您的问题、投诉和索赔，(ii) 提供售后服务，(iii) 提供与您可能相关的产品或服务信息，(iv) 验证您的身份以确保您是本人声称的身份，以及 (v) 加强我们的安全性并保护您的信息。',
      ],
      [
        '新闻通讯',
        '• 如果已注册，则为您提供的用户帐户信息 • 如果未注册，则为您的姓名和电子邮件地址 • 接收信息的偏好，例如频率和信息类别',
        '我们在征得您同意的基础上收集这些个人数据。我们处理您的个人数据是为了 (i) 提供您可能喜欢的产品或服务信息，以及 (ii) 提供商品优惠。',
      ],
      [
        '其他一般目的（"一般信息"）',
        '• 如果已注册，您提供的用户帐户信息 • 如果未注册，我们在相关处理目的下可能拥有的您的任何其他必要信息。',
        '我们收集这些个人数据可能是因为这可能是遵守适用于我们作为数据控制方的法律义务所必需的，或者是为了我们的合法利益，即开展我们的常规业务活动并在发生冲突时保护我们的利益。我们处理您的个人数据是为了 (i) 遵循公共当局的要求，(ii) 进行刑事调查、起诉、审判和执行判决，(iii) 保护第三方的权利，(iv) 进行统计或学术研究，或 (v) 相关法律法规规定的其他情况。',
      ],
      [
        '社交媒体信息',
        '• 您与我们社交媒体帐户的互动（例如，如果您"点赞"我们的内容或向我们发送直接消息）；您的直接消息、评论、点赞以及因您的互动而在您个人资料上对我们可见的任何信息；以及与这些互动和您的社交媒体帐户相关的、对我们可见的任何其他信息。',
        '我们基于我们的合法利益（即推广我们的服务和跟踪我们在社交媒体的表现）收集这些个人数据。',
      ],
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '4.2 如果您的个人数据是基于合法利益处理的，您可以获取我们所依赖的具体合法利益以及我们如何同时考虑您的权利和利益的信息。如需了解更多信息，请通过',
      },
      {
        t: 'Joybuyfumi@gmail.com',
        href: 'mailto:Joybuyfumi@gmail.com',
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
        t: '4.3 我们使用自动化系统分析您的个人数据，以创建您的偏好档案，并向您提供个性化的产品推荐和广告。这在数据保护法中称为"画像"。我们会分析您的浏览行为、购买历史、您查看或添加到购物车的产品、帐户偏好、会员信息、Cookie/设备数据、尺码详情以及您与我们分享或我们从您的购买历史中推导出的其他个人特征。我们使用画像来：(a) 提供个性化的产品和购买推荐；(b) 定制网站内容；(c) 个性化营销传播（在您已同意接收的情况下）；以及 (d) 改进我们的服务。对于基于Cookie的画像，我们依赖您的同意（您可以通过Cookie设置撤回）；对于基于您帐户活动和购买历史的画像，我们依赖我们的合法利益。您有权通过联系',
      },
      {
        t: 'Joybuyfumi@gmail.com',
        href: 'mailto:Joybuyfumi@gmail.com',
      },
      {
        t: '反对基于我们合法利益的画像。您可以随时通过“我 > 设置与隐私 > 个性化设置 > 个性化推荐”路径，选择退出个性化推荐。您可以通过Cookie设置选择退出基于Cookie的画像。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '4.4 我们可能打算将您的个人数据用于收集目的之外的其他目的。在此情况下，我们将在进一步处理之前，向您提供有关该等其他目的、我们依赖的合法性基础以及所有相关的进一步信息。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '4.5 我们使用人工智能(AI)技术提供自动化客户服务，并不断优化我们的服务质量。我们的AI客服系统可以通过访问您的个人数据，回答您关于产品、订单、付款、配送和退款的问题。当您联系客服时，您可能会与我们的AI系统互动。AI会访问您的帐户信息、订单历史、付款详情和退款信息，以便为您具体的问题提供准确、个性化的回复。您与AI的对话会被记录下来，用于质量保证和改进系统的性能和准确性。您可以随时输入"请求人工支持"或点击"踩"按钮，请求转接人工客服。超出 AI 能力范围的复杂咨询会自动升级并转交给人工客服。AI在人工监督下运行。同时，为了提升用户体验，我们还提供基于其他用户评价生成的AI摘要。您有权通过联系',
      },
      {
        t: 'Joybuyfumi@gmail.com',
        href: 'mailto:Joybuyfumi@gmail.com',
      },
      {
        t: '反对出于客服目的对您的数据进行AI处理。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '5 与第三方共享',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '5.1 为确保我们服务的顺利提供，我们可能会与某些第三方共享您的个人数据。但这仅在严格需要知晓的基础上进行，共享对象包括：',
      },
      {
        br: 1,
      },
      {
        t: 'a. Joybuy的集团公司，它们也可能为本政策所述目的处理您的个人数据。',
      },
      {
        br: 1,
      },
      {
        t: 'b. 参与提供服务的分包商和服务提供商，例如：',
      },
      {
        br: 1,
      },
      {
        t: '• 用于提供我们服务的航运公司和卡车运输公司以及仓库；',
      },
      {
        br: 1,
      },
      {
        t: '• 提供专业咨询服务的审计公司、咨询公司和律师事务所；',
      },
      {
        br: 1,
      },
      {
        t: '• 第三方商家，以便您购买通过我们的网站和App提供的第三方商品和服务；',
      },
      {
        br: 1,
      },
      {
        t: '• 提供技术和金融基础设施服务的托管和支付提供商；',
      },
      {
        br: 1,
      },
      {
        t: '• 营销合作伙伴，包括在线平台和发布商，用于通过我们的邮件列表向您提供优惠、收集您的偏好信息以提供客户服务，以及收集和分析您在我们网站或App上的其他行为偏好，以便进行重新定向和投放定制广告；',
      },
      {
        br: 1,
      },
      {
        t: '• 第三方客服公司中，在需要知晓的基础上，为Joybuy或其关联公司提供客户服务所雇佣或聘用的人员；',
      },
      {
        br: 1,
      },
      {
        t: 'c. 如果法律要求，我们还将根据需要知晓的原则，向主管当局等第三方披露您的个人数据，例如为了遵守法律要求而需要向过境国或目的国海关披露以进行清关；在法律要求或允许的情况下，用于建立、行使或捍卫合法权利；为了执行或适用我们的供应条款和与您的其他协议；或在各个国家法律要求的范围内，为了保护Joybuy、我们的客户或其他人的权利、财产或安全；以及',
      },
      {
        br: 1,
      },
      {
        t: 'd. 我们可能会在特殊情况下，根据需要知晓的原则向第三方披露您的个人数据，例如在合并、收购、资产转让或类似交易中，或者当需要遵守法律或保护我们自身的权利、财产和安全时——在这种情况下，我们将根据本政策的条款向该业务或资产的潜在买方披露您的个人数据。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '6 向欧洲经济区和英国以外的国家传输',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '6.1 我们上文提到的一些接收方位于英国和欧洲经济区以外的国家，这些国家的法律可能无法提供您在欧盟或英国所习惯的同等级别的数据保护。在这种情况下，我们将确保采取适当的保障措施来保护您的个人数据。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '6.3 如果我们将个人数据传输给位于欧洲经济区和英国以外且无充分性决定适用的国家的当事方，我们将签订经批准的标准合同条款。您可以请求一份达成一致的标准合同条款副本。如有需要，我们将额外使用补充措施以保护您的个人数据。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '6.4 如果您想获取更多关于将您的个人数据传出欧洲经济区和英国的信息，也请联系我们 ',
      },
      {
        t: 'Joybuyfumi@gmail.com',
        href: 'mailto:Joybuyfumi@gmail.com',
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
        t: '6.5 我们处理的个人数据主要存储位于荷兰的服务器上。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '7 保留期限',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '7.1 我们保留您的个人数据的时间，以达到我们处理您个人数据的相关目的（如上文第 4 节所述）所需的时间为准，也可能是为了满足任何法律、税务、监管或会计要求、解决争议、保障信息安全、执行我们的合法权利、条款和政策所需的时间，或按照我们另行通知您的情况所需的时间。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '为确定个人数据的适当保留期限，我们会考虑个人数据的数量、性质和敏感性，未经授权使用或披露您的个人数据可能造成的损害风险，我们处理您个人数据的目的以及我们是否可以通过其他方式实现这些目的，以及适用的法律、监管、税务、会计或其他要求。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '例如，出于税务目的，我们必须在客户停止成为客户后保留其基本信息（包括订单和交易记录）六年。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '有关我们保留期限的更多信息，请联系',
      },
      {
        t: 'Joybuyfumi@gmail.com',
        href: 'mailto:Joybuyfumi@gmail.com',
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
        t: '我们的保留政策不影响您行使您的合法权利（如下文提及）。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '7.2 如您希望进一步了解我们对您个人数据的处理时长，请通过 ',
      },
      {
        t: 'Joybuyfumi@gmail.com',
        href: 'mailto:Joybuyfumi@gmail.com',
      },
      {
        t: ' 联系我们。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '8 您的权利（包括反对权）',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '8.1 关于我们对您个人数据的处理，您在特定情况下享有以下隐私权利。要行使这些权利，请发送电子邮件至 ',
      },
      {
        t: 'Joybuyfumi@gmail.com',
        href: 'mailto:Joybuyfumi@gmail.com',
      },
      {
        t: '，并在主题行注明"隐私查询"。',
      },
      {
        br: 1,
      },
      {
        t: 'a. 撤回同意的权利： 对于我们基于您同意处理您的个人数据（见上文）的情况，您有权在任何时候撤回同意而不会受到不利影响。',
      },
      {
        br: 1,
      },
      {
        t: '您可以通过点击我们所有营销和促销更新通讯末尾的"退订"链接，或发送电子邮件至 ',
      },
      {
        t: 'Joybuyfumi@gmail.com',
        href: 'mailto:Joybuyfumi@gmail.com',
      },
      {
        t: '并在主题行注明"隐私查询"，随时更改您的偏好并反对接收进一步的营销信息。',
      },
      {
        br: 1,
      },
      {
        t: 'b. 访问权： 您有权了解我们持有您的哪些个人数据，并请求访问您的个人数据。这使您能够获得我们持有的关于您的个人数据的副本（但不一定是文件本身）。我们届时将根据适用法律向您提供我们处理您个人数据的更多详细信息。',
      },
      {
        br: 1,
      },
      {
        t: 'c. 更正权： 您有权要求更正我们持有的关于您的个人数据。这使您能够纠正我们持有的关于您的任何不完整或不准确的数据。',
      },
      {
        br: 1,
      },
      {
        t: 'd. 删除权（被遗忘权）： 您有权要求删除您的个人数据。这使您能够在以下情形下要求我们删除或移除个人数据：(i) 个人数据不再必要，(ii) 您已撤回同意，(iii) 您反对处理活动，(iv) 个人数据被非法处理，(v) 基于法律要求必须删除个人数据，或 (vi) 个人数据是与提供信息社会服务相关的收集。如果处理是出于以下必要，我们无需满足您的请求：(i) 行使言论和信息自由权，(ii) 为遵守法律义务而需要处理，(iii) 出于公共卫生领域的公共利益原因，(iv) 出于存档目的，或 (v) 用于法律索赔的提起、行使或抗辩。',
      },
      {
        br: 1,
      },
      {
        t: 'e. 反对权： 在我们依赖合法利益作为处理依据（见上文）的情况下，您有权反对处理您的个人数据。如果您的个人数据是为了直接营销目的而处理，我们将始终尊重您的请求。对于其他目的的处理，我们也将停止处理，除非我们有令人信服的合法理由继续进行该处理，并且该理由超越您的利益、权利和自由，或者与提起、行使或抗辩法律索赔有关。',
      },
      {
        br: 1,
      },
      {
        t: 'f. 限制处理权： 您有权在以下情形下要求限制对您个人数据的处理：(i) 您对个人数据的准确性提出异议，在我们验证您请求的期间内；(ii) 处理是非法的，并且您要求限制使用而非删除；(iii) 我们不再需要这些个人数据，但您需要它们来提起、行使或抗辩法律索赔；或 (iv) 在您反对处理的情况下，在我们验证您请求的期间内。如果我们限制了您个人数据的处理，这意味着我们将仅存储它们，不再以任何其他方式处理，除非：(i) 征得您的同意，(ii) 用于提起、行使或抗辩法律索赔，(iii) 为了保护另一个自然人或法人的权利，(iv) 或出于重要的公共利益原因。',
      },
      {
        br: 1,
      },
      {
        t: 'g. 数据可携权： 您有权要求将您的个人数据转移给您或您选择的第三方。我们将以结构化、常用且机器可读的格式向您或该第三方提供您的个人数据。请注意，此权利仅适用于我们通过自动化方式进行处理的个人数据，并且仅当我们处理此类数据的依据是您的同意或履行您作为一方的合同（见上文）时才适用。',
      },
      {
        br: 1,
      },
      {
        t: 'h. 自动化决策： 您有权不受仅基于自动化处理做出的、对您产生重大影响（"产生法律效力或类似地严重影响您"）的决定的约束。我们使用画像进行个性化推荐（见第 4.3 节），但这不构成英国通用数据保护条例第 22A 条以及通用数据保护条例第22条所指的自动化决策，因为推荐不会产生法律效力或类似地严重影响您。您有权反对这种画像（见第 4.3 节和第 8.1(e) 节）。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '8.2 行使上述权利是免费的，可以通过向 ',
      },
      {
        t: 'Joybuyfumi@gmail.com',
        href: 'mailto:Joybuyfumi@gmail.com',
      },
      {
        t: '发送电子邮件进行。如果请求明显毫无根据或过度，特别是因其重复性，我们将在法律允许的情况下，要么向您收取合理的费用，要么拒绝处理该请求。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '8.3 在处理您关于某项权利的请求之前，我们可能会要求您提供特定信息以帮助我们确认您的身份。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '8.4 如果您想注销在Joybuy的注册，您可以通过您的帐户进行操作。您也可以通过',
      },
      {
        t: 'Joybuyfumi@gmail.com',
        href: 'mailto:Joybuyfumi@gmail.com',
      },
      {
        t: '联系我们删除您的帐户。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '8.5 如果您已订阅我们的新闻通讯，您可以随时通过新闻通讯底部的退订链接撤销您的同意。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '9 未成年人保护',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '9.1 Joybuy高度重视对未成年人个人数据的保护。本服务面向至少年满 18 周岁的用户。如果您是未满 18 周岁或适用法律规定的其他成年年龄的未成年人，您在使用我们的服务前必须获得您的父母或法定监护人的事先书面同意。Joybuy根据适用法律法规保护未成年人的个人数据。对于经父母或法定监护人同意收集的未成年人个人数据，我们仅在法律允许、父母或监护人明确同意或为保护儿童所必需时使用或披露。如果我们发现自己在未经可核实的父母或法定监护人事先同意的情况下收集了未成年人的个人信息，我们将在发现后立即删除。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '10 联系方式',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '10.1 Jingdong Retail (UK) Limited（公司编号：15830555）、Jingdong Retail (Netherlands) B.V.（公司编号：80456774）、Jingdong Retail (France) SAS（公司编号：947844197）和 Jingdong Retail Germany GmbH（公司编号：HRB 277115 B）是联合控制方，负责管理和托管服务，并做出全球和战略决策。这四个数据控制方在不同的英国和欧盟国家运营Joybuy的网站。如有任何问题、意见或请求，您可以通过',
      },
      {
        t: 'Joybuyfumi@gmail.com',
        href: 'mailto:Joybuyfumi@gmail.com',
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
        t: '10.2 我们的地址是：Jingdong Retail (UK) Limited, Floor 3, 20 King Street, London SW1Y 6QY；对于其他控制方：Floor 12, Boompjes 40, 3011 XB Rotterdam, the Netherlands。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '10.3 此外，可通过',
      },
      {
        t: 'Joybuyfumi@gmail.com',
        href: 'mailto:Joybuyfumi@gmail.com',
      },
      {
        t: '联系数据保护官。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '11 本政策的变更',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '11.1 Joybuy保留定期更改本政策的权利。如有需要，Joybuy将通知您本政策的更新内容。当前版本始终可在我们的网站和 App 上获取。本政策自2026 年 4月起生效。',
      },
    ],
  },
]

import { jaTitle as jaPageTitle, jaBlocks as jaPageBlocks } from './privacy-policy.ja.js'
export const privacyPolicyPage = {
  slug: 'privacy-policy',
  title: { en: 'Privacy Policy', zh: '隐私政策' },
  hasArchive: true,
  blocks: { en, zh },
  jaTitle: jaPageTitle,
  jaBlocks: jaPageBlocks,
}
