// 批次 Q（需求 15.1 / 15.2）：真站 help 中心「Cookie Policy」页正文。
// 来源：2026-11-20 Playwright 实测真站对应 help 页（批次 Q 抓取，原始数据见 var/policy_help_20261120/）。
// 批次 S 追加（用户 2026-11-20 口径）：正文中所有真站网址 → www.joyfumi.com（保留路径结构）；
// 公司名 / 地址 / 注册号 / 监管表述与邮箱不变。
//（原始抓取 var/policy_help_20261120/content_{en_GB,zh_CN}_cookie-policy.json；
//  zh 为真站自带中文版，非机器翻译）。
// 口径：除邮箱 → Joybuyfumi@gmail.com 外，全文照抄真站（公司名 / 地址 / 注册号 /
// 监管表述 / 章节 / 表格 / 生效日期均保持原文）。块结构：p{segments} + table{rows}；
// segments 内 t=文本、b=粗体、i=斜体、href=链接、br=换行（真站正文用 <br> 分行）。
const en = [
  {
    type: 'p',
    segments: [
      {
        t: 'Jingdong Retail (UK) Limited, Jingdong Retail (Netherlands) B.V., Jingdong Retail (France) SAS, and Jingdong Retail Germany GmbH ("Joybuy", "we", "us" or "our") attaches great importance to the protection of its users\' and customers\' privacy and personal information. We use cookies and other similar technologies when you visit our website (',
      },
      {
        t: 'www.joyfumi.com',
        href: 'https://www.joyfumi.com/',
      },
      {
        t: ') or use the Joybuy app ("Services").',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'This Joybuy Cookie Policy ("Policy") explains how we and other members of our group use cookies and similar technologies when you, or business users acting on your behalf (your “Personnel”), use(s) our Services.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Please read the Joybuy Cookie Policy carefully. If you have any questions, please feel free to contact us.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'For more detailed information about how we process your Personal Data, please see our ',
      },
      {
        t: 'Privacy Policy',
        href: '/pages/privacy-policy',
      },
      {
        t: '. For information on using the Services, please see our ',
      },
      {
        t: 'Term of Use',
        href: '/pages/terms-conditions',
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
        t: 'This Policy covers:',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '1. Scope',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '2. What are cookies?',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '3. What types of cookies do we use?',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '4. How can you delete cookies or change your cookie settings?',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '5. Contact details',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '6. Changes to this Policy',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '1 Scope',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '1.1 We will only use cookies and similar technologies in accordance with this Policy.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '2 What are cookies?',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '2.1 Cookies and other similar technologies are small text files that can be placed on your computer, tablet, smartphone or other electronic device with which you can use to surf the internet via a web browser (“Device”). Websites or apps can place cookies on your Device via your web browser if you visit such website or use an app – this typically involves storing pieces of information or code transferred to or accessed from your Device to store and, sometimes, record information about your interaction with online services from your Device. Examples of web browsers are: Internet Explorer, Firefox, Safari, Google Chrome and Opera.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '2.2 After a cookie is placed on your Device, your Device can be recognised as you surf through the website via the same web browser or use an app. This will for instance enable the website or app to ‘remember’ your language settings, which pages you visited and the items in your shopping chart. If such cookies are placed by a third-party, such third-party can (also) recognise your device (third-party cookies). It is also possible that cookie information is shared with third-parties. For more information on cookies, please be referred to the website ',
      },
      {
        t: 'www.allaboutcookies.org',
        href: 'https://allaboutcookies.org/',
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
        t: '2.3 Lifecycle cookies: after a cookie is placed on a device, it is only valid for a certain period.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'a. After the validity period of a cookie lapses, the cookie is automatically removed by the web browser. The validity period varies per cookie. For example, some cookies are only valid during the browser session. Other cookies can also recognise your Device if you visit the website or app during a new browser session, e.g. for a year after being placed on your Device.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'b. Early deletion/refusal of cookies: you can choose to delete a cookie manually before its validity period has lapsed. You can also decide to refuse cookies which may only be placed with your consent, in the first place. For more information on this, please see the section “How can you delete cookies or change your cookie setting?” below.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '2.4 Similar technologies: in addition to cookies, other techniques are also used for similar purposes:',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'a. HTML5 Local Storage and Flash cookie: HTML5 Local Storage and local shared objects (LSOs, also called “Flash cookies”) can be used for the same purposes as cookies.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'b. Web beacons: Web beacons (also called “tags”) are bits of programming code that can be included in web pages, emails, and ads. Web beacons can notify the user when those web pages, emails, or ads have been viewed or clicked on by you.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'c. Embedded scripts: Embedded scripts (also called “JavaScript”), are sections of programming code that can be included in web pages to measure how those web pages are used by you, e.g. by registering which links you click on.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'd. Device fingerprints: information collected about software or hardware of a device for identification and security purposes. This information is collected for two main purposes, namely (i) ensuring the security of your account by detecting hacking activities, security threats and related abnormal statuses of your account, and (ii) ensuring fair dealing and protecting your and our interests by detecting and blocking cybercrime or online deceptive activities.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'e. Event tracking: an event is your interaction or activity with a page, which will be tracked through the tracker. This information is collected for the following main purpose, namely identifying which ads or pages have led to purchases and calculating the conversion rate in order to optimize performance levels.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'f. SDKs (software development kits) provided by our suppliers and embedded in our app, These SDKs help us with analytics (including understanding how are users our interacting with our Services), with online advertising (including analysing how effective advertising on the apps has been and recording which ads you have seen and interacted with) and with stability monitoring which helps us ensure the app is performing as it should.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '2.5 We use cookies, either alone or in combination with each other, to create a unique ID which corresponds to you.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '2.6 When you first interact with our Services, you will be notified that we use cookies and we will ask for your consent to use non-essential cookies. This banner will also allow you to decide which non-essential cookies you want to accept. We also give you information about how to disable cookies below. Where you change your browser settings to generally disable all cookies, you may not be able to take full advantage of our Services; some aspects may not work without some cookies being used.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'We use these cookies on the basis that they are necessary for the performance of a contract with you, or because using them is in our legitimate interests (where we have considered that these are not overridden by your rights) or where you have consented to their use.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '3 What types of cookies do we use?',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '3.1 We use four types of cookies on this Site: (i) essential cookies (ii) functional cookies, (iii) analytical and performance cookies, (iv) targeting and advertising cookies. More information on this is provided below.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '3.2 Essential cookies:',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'a. These are cookies that are essential for the operation of our Services and under our terms with you. They include, for example, cookies that enable you to log into secure areas of our Services, use a shopping cart, take steps to deliver our Services to you and preserve the proper layout and navigation of a Services. If you disable these cookies, certain features of the Services may not work.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'b. Essential cookies may be placed without your consent.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '3.3 Functional cookies:',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'a. These are used to recognise you when you return to our Services. This enables us, subject to your choices and preferences, to personalise our content, greet you by name and remember your preferences (for example, your choice of language or region).',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '3.4 Analytical and performance cookies:',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'a. Analytical and performance cookies are used to analyse and map the use of our Services, so that the quality and/or effectiveness can be improved. These types of cookies will, for example, capture the number of users and see how they engage with our Services, including specific content and features. This helps us for our legitimate interests of improving the way our website works (for example, by ensuring that users are finding what they are looking for easily).',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'b. We will not place analytical and performance cookies without your consent.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '3.5 Targeting / advertising cookies:',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'a. Tracking cookies are used to follow the behaviour of website visitors across multiple websites. If such cookies are placed by another party, these are called third party tracking cookies.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'b. We will not place tracking cookies without your consent.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '4 How can you delete cookies or change your cookie settings?',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '4.1 You can you change your cookie settings in general – for all websites you visit – via your browser settings. You can also change your cookie setting just for our Site.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '5 Contact Details',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '5.1 Jingdong Retail (UK) Limited (Company number: 15830555), Jingdong Retail (Netherlands) B.V. (Company number 80456774), Jingdong Retail (France) SAS (Company number 947844197 ), and Jingdong Retail Germany GmbH (Company number HRB 277115 B) are joint controllers which administer and host the Services and from which global and strategic decisions are made. The four data controllers operate the website of Joybuy in different UK and EU states. For any questions, comments or requests, you may contact us via Joybuyfumi@gmail.com. Please let us know by e-mail if you prefer to have further contact over the phone.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '5.2 Our address is: Jingdong Retail (UK) Limited, Floor 3, 20 King Street, London SW1Y 6QY, for other controllers, Floor 12, Boompjes 40, 3011 XB Rotterdam, the Netherlands.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '5.3 Our data protection officer can be contacted at Joybuyfumi@gmail.com.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '6 Changes to this Policy',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Joybuy reserves the right to change this Policy on a regular basis. Where required, Joybuy will inform you of updates made to this Policy. The current version is always available on our website and in our app. This Policy was last amended and revised in April 2026.',
      },
    ],
  },
]

const zh = [
  {
    type: 'p',
    segments: [
      {
        t: 'Jingdong Retail (UK) Limited、Jingdong Retail (Netherlands) B.V.、Jingdong Retail (France) SAS 以及 Jingdong Retail Germany GmbH（以下统称“Joybuy”、“我们”或“我们的”）非常重视保护用户和客户的隐私及个人信息。当您访问我们的网站 (',
      },
      {
        t: 'www.joyfumi.com',
        href: 'w.www.joyfumi.com',
      },
      {
        t: ') 或使用 Joybuy 应用程序（以下简称“服务”）时，我们会使用 Cookie 及其他类似技术。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '本《Joybuy Cookie 政策》（以下简称“本政策”）旨在说明当您或代表您的业务用户（您的“人员”）使用我们的服务时，我们及我们集团的其他成员如何使用 Cookie 及类似技术。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '请仔细阅读本《Joybuy Cookie 政策》。如有任何疑问，请随时与我们联系。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '有关我们如何处理您的个人数据的详细信息，请参阅我们的《隐私政策》。有关使用服务的信息，请参阅我们的《使用条款》。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '本政策涵盖以下内容：',
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
          t: '什么是 Cookie？',
        },
      ],
      [
        {
          t: '我们使用哪些类型的 Cookie？',
        },
      ],
      [
        {
          t: '您如何删除 Cookie 或更改 Cookie 设置？',
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
        t: '1. 范围',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '我们仅会按照本政策的规定使用 Cookie 及类似技术。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '2. 什么是 Cookie？',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '2.1 Cookie 及其他类似技术是小型文本文件，可以放置在您用于通过网络浏览器浏览互联网的计算机、平板电脑、智能手机或其他电子设备（以下简称“设备”）上。当您访问网站或使用应用程序时，网站或应用程序可以通过您的网络浏览器在您的设备上放置 Cookie——这通常涉及存储传输至您的设备或从您的设备访问的信息或代码，以存储并有时记录有关您与设备在线服务交互的信息。网络浏览器的示例包括：Internet Explorer、Firefox、Safari、Google Chrome 和 Opera。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '2.2 在设备上放置 Cookie 后，当您通过同一网络浏览器浏览网站或使用应用程序时，您的设备可以被识别。例如，这将使网站或应用程序能够“记住”您的语言设置、您访问过的页面以及购物车中的物品。如果此类 Cookie 由第三方放置，则该第三方也可以识别您的设备（第三方 Cookie）。Cookie 信息也有可能与第三方共享。有关 Cookie 的更多信息，请参阅网站 www.allaboutcookies.org。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '2.3 Cookie 生命周期：Cookie 放置在设备上后，仅在特定时期内有效。 a. Cookie 的有效期届满后，它会被网络浏览器自动删除。有效期因 Cookie 而异。例如，某些 Cookie 仅在浏览器会话期间有效。其他 Cookie 也可以在您于新的浏览器会话期间访问网站或应用程序时识别您的设备，例如在放置于您的设备后一年内。 b. 提前删除/拒绝 Cookie：您可以选择在有效期届满前手动删除 Cookie。您也可以决定拒绝最初可能仅在征得您同意后才能放置的 Cookie。有关此方面的更多信息，请参阅下文“您如何删除 Cookie 或更改 Cookie 设置？”部分。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '2.4 类似技术：除 Cookie 外，还使用其他技术实现类似目的： a. HTML5 本地存储和 Flash Cookie：HTML5 本地存储和本地共享对象（LSO，也称为“Flash Cookie”）可用于与 Cookie 相同的目的。 b. 网络信标 (Web beacons)：网络信标（也称为“标签”）是可包含在网页、电子邮件和广告中的编程代码片段。当您查看或点击这些网页、电子邮件或广告时，网络信标可以通知用户。 c. 嵌入式脚本：嵌入式脚本（也称为“JavaScript”）是可包含在网页中的编程代码部分，用于衡量您如何使用这些网页，例如通过记录您点击的链接。 d. 设备指纹：为识别和安全目的收集的有关设备软件或硬件的信息。收集这些信息主要有两个目的：(i) 通过检测黑客活动、安全威胁及您账户的相关异常状态来确保您的账户安全，以及 (ii) 通过检测和阻止网络犯罪或在线欺诈活动，确保公平交易并保护您和我们的利益。 e. 事件追踪：事件是您与页面之间的交互或活动，将通过追踪器进行追踪。收集这些信息的主要目的是识别哪些广告或页面促成了购买，并计算转化率，以优化性能水平。 f. 软件开发工具包 (SDK)：由我们的供应商提供并嵌入在我们的应用程序中。这些 SDK 帮助我们进行分析（包括了解用户如何与我们的服务进行交互）、进行在线广告宣传（包括分析应用程序上的广告效果，并记录您查看和与之交互的广告）以及进行稳定性监控，从而帮助我们确保应用程序正常运行。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '2.5 我们单独或结合使用 Cookie，以创建一个与您对应的唯一 ID。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '2.6 当您首次与我们的服务进行交互时，我们将通知您我们正在使用 Cookie，并将征求您对使用非必要 Cookie 的同意。此横幅还将允许您决定要接受哪些非必要 Cookie。我们还在下文中提供了有关如何禁用 Cookie 的信息。如果您更改浏览器设置以全面禁用所有 Cookie，您可能无法充分利用我们的服务；某些功能在没有使用 Cookie 的情况下可能无法正常工作。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '我们使用这些 Cookie 是基于它们对于履行与您的合同是必要的，或者因为使用它们符合我们的合法利益（前提是我们已考虑到这些利益并未被您的权利所覆盖），或者是在您已同意使用它们的情况下。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '3. 我们使用哪些 Cookie 和类似技术？',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '3.1 我们在本网站上使用四种类型的 Cookie：',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '(i) 必要 Cookie，(ii) 功能性 Cookie，(iii) 分析和性能 Cookie，(iv) 目标定位和广告 Cookie。更多信息如下。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '3.2 必要 Cookie：',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '这些是对于我们服务的运行以及根据我们与您的条款所必需的 Cookie。例如，它们包括使您能够登录我们服务的安全区域、使用购物车、采取步骤向您提供服务以及保持服务布局和导航正常的 Cookie。如果您禁用这些 Cookie，服务的某些功能可能无法工作。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '必要 Cookie 无需征得您的同意即可放置。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '3.3 功能性 Cookie：',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '这些用于在您返回我们的服务时识别您。这使我们能够根据您的选择和偏好，个性化我们的内容、以您的姓名问候您并记住您的偏好（例如，您对语言或地区的选择）。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '3.4 分析和性能 Cookie：',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '分析和性能 Cookie 用于分析和绘制我们服务的使用情况，以便改进质量和/或有效性。这些类型的 Cookie 例如将捕获用户数量并查看他们如何与我们的服务进行交互，包括特定内容和功能。这有助于我们实现改善网站运作方式的合法利益（例如，确保用户能轻松找到他们正在寻找的内容）。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '未经您的同意，我们不会放置分析和性能 Cookie。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '3.5 目标定位 / 广告 Cookie：',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '追踪 Cookie 用于追踪网站访问者跨多个网站的行为。如果此类 Cookie 由另一方放置，则称为第三方追踪 Cookie。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '未经您的同意，我们不会放置追踪 Cookie。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '4. 您如何删除 Cookie 或更改 Cookie 设置？',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '4.1 您可以通过浏览器设置更改通用的 Cookie 设置（适用于您访问的所有网站）。您也可以仅针对我们的网站更改 Cookie 设置。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '5. 联系方式',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '5.1 Jingdong Retail (UK) Limited（公司编号：15830555）、Jingdong Retail (Netherlands) B.V.（公司编号：80456774）、Jingdong Retail (France) SAS（公司编号：947844197）以及 Jingdong Retail Germany GmbH（公司编号：HRB 277115 B）是共同控制者，负责管理和托管服务，并由此做出全球和战略决策。这四个数据控制者在英国和欧盟不同国家运营 Joybuy 网站。如有任何问题、意见或请求，您可以通过 Joybuyfumi@gmail.com 与我们联系。如果您希望通过电话进行进一步沟通，请通过电子邮件告知我们。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '5.2 我们的地址是：Jingdong Retail (UK) Limited, Floor 3, 20 King Street, London SW1Y 6QY；其他控制者的地址为：Floor 12, Boompjes 40, 3011 XB Rotterdam, the Netherlands。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '5.3 我们的数据保护官联系方式为：Joybuyfumi@gmail.com。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '6. 本政策的变更',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '6.1 Joybuy 保留定期更改本政策的权利。在必要时，Joybuy 将告知您本政策的更新。当前版本始终可在我们的网站和应用程序上获取。本政策最后一次修订于 2026 年 4 月。',
      },
    ],
  },
]

import { jaTitle as jaPageTitle, jaBlocks as jaPageBlocks } from './cookie-policy.ja.js'
export const cookiePolicyPage = {
  slug: 'cookie-policy',
  title: { en: 'Cookie Policy', zh: 'Cookie 政策' },
  hasArchive: false,
  blocks: { en, zh },
  jaTitle: jaPageTitle,
  jaBlocks: jaPageBlocks,
}
