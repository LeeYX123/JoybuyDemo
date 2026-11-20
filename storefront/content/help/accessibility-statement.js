// 批次 Q（需求 15.1 / 15.2）：真站 help 中心「Accessibility Statement」页正文。
// 来源：2026-11-20 Playwright 实测真站对应 help 页（批次 Q 抓取，原始数据见 var/policy_help_20261120/）。
// 批次 S 追加（用户 2026-11-20 口径）：正文中所有真站网址 → www.joyfumi.com（保留路径结构）；
// 公司名 / 地址 / 注册号 / 监管表述与邮箱不变。
//（原始抓取 var/policy_help_20261120/content_{en_GB,zh_CN}_AccessibilityStatement.json；
//  zh 为真站自带中文版，非机器翻译）。
// 口径：除邮箱 → Joybuyfumi@gmail.com 外，全文照抄真站（公司名 / 地址 / 注册号 /
// 监管表述 / 章节 / 表格 / 生效日期均保持原文）。块结构：p{segments} + table{rows}；
// segments 内 t=文本、b=粗体、i=斜体、href=链接、br=换行（真站正文用 <br> 分行）。
const en = [
  {
    type: 'list',
    ordered: true,
    items: [
      [
        {
          t: 'Accessibility Statement',
          b: 1,
        },
      ],
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'We are fully aware of the importance of website accessibility and are committed to ensuring that all users, regardless of their abilities, can access and utilize the information and services provided on our website equally.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'This accessibility statement applies to the online marketplace operated by JD, accessible via Joybuy website and mobile application. Through our platform, users can browse, search for, register and purchase, as well as manage their orders, track deliveries, and access customer support. Our services are designed to be accessible across desktop and mobile websites, as well as native applications, supporting a broad range of user needs.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '2. Our Commitments',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Our commitments are guided by the four core principles of web accessibility enshrined in the EU Accessibility Act: Perceivable (information and user interface components must be presentable to users in ways they can perceive), Operable (user interface components and navigation must be operable), Understandable (information and the operation of the user interface must be understandable), and Robust (content must be robust enough to be interpreted reliably by a wide variety of user agents, including assistive technologies). We are dedicated to following the ',
      },
      {
        t: 'POUR',
        b: 1,
      },
      {
        t: ' accessibility design principles.',
      },
    ],
  },
  {
    type: 'list',
    ordered: false,
    items: [
      [
        {
          t: 'To ensure it is ',
        },
        {
          t: 'Perceivable',
          b: 1,
        },
        {
          t: ', our content can be effectively identified and processed by various assistive technologies, such as screen readers, screen magnifiers, and voice recognition software, thereby offering better support for users who rely on these tools. We maintain a sufficient contrast between foreground content (such as text) and background colors. This ensures that users with visual impairments, such as poor eyesight or color blindness, can read and distinguish content clearly, avoiding difficulties caused by insufficient color contrast. Text transcripts, and other alternative content are provided for multimedia content such as videos and audio. This ensures that hearing-impaired users can access the key information in multimedia, allowing them to stay informed without missing out on important updates.',
        },
      ],
      [
        {
          t: 'To ensure it is ',
        },
        {
          t: 'Operable',
          b: 1,
        },
        {
          t: ', all functions on our website can be operated using a keyboard, without the need for a mouse or other pointing devices. This makes it easier for users with motor disabilities to navigate and use the website’s features efficiently through keyboard shortcuts and other keyboard operations.',
        },
      ],
      [
        {
          t: 'To ensure it is ',
        },
        {
          t: 'Understandable',
          b: 1,
        },
        {
          t: ',we provide text alternatives for non-text content such as images and charts, ensuring that visually impaired users can understand the information being conveyed. This guarantees that no information is missed by those who depend on text-based information.',
        },
      ],
      [
        {
          t: 'To ensure they are ',
        },
        {
          t: 'Robust',
          b: 1,
        },
        {
          t: ', our web pages are constructed using semantic HTML tags,compatible with major screen readers.This results in a clear page structure and logical organization, which is not only beneficial for assistive technologies and search engines to parse but also advantageous for the long-term maintenance and optimization of the website. It improves the overall accessibility and maintainability of the site.',
        },
      ],
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '3. Current Status',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Our website currently:',
      },
    ],
  },
  {
    type: 'list',
    ordered: false,
    items: [
      [
        {
          t: 'We have endeavored to follow the WCAG 2.2 AA level and adhere to the provisions of EN 301 549 regarding web accessibility standards. This involves optimizing page structure, content presentation, and interactive operations to meet the basic accessible needs of most users.',
        },
      ],
      [
        {
          t: 'We had undergone a comprehensive accessibility evaluation through both internal testing and external reviews. Our testing methodology combined automated scans with manual checks using Accessibility Insights, screen readers (VoiceOver, NVDA), keyboard navigation, and contrast analyzers. Additionally, dynamic content, forms, and user flows were thoroughly verified manually against applicable standards. Through this process, we identified and resolved multiple accessibility issues, significantly enhancing the website’s overall accessibility and usability.',
        },
      ],
      [
        {
          t: 'Employs responsive design to adapt to different devices and screen sizes, including desktop computers, laptops, tablets, and smartphones. This provides mobile users with an excellent browsing experience and ensures the consistency and coherence of accessible services across various terminals.',
        },
      ],
      [
        {
          t: 'It is in the process of integrating certain accessibility features. For instance, font resizing functions (PC ≥ 16px,mobile:≥ 14px) and high-contrast mode (4.5:1) switching are being implemented. These features offer users more convenient personalized options, enabling them to adjust their browsing environment according to their individual needs.',
        },
      ],
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '4. Limitations and Areas for Improvement',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'While we strive to ensure comprehensive accessibility across our platform, we acknowledge that some areas may not yet fully comply with WCAG 2.2 AA or EN 301 549. We are actively working to address the following known limitations:',
      },
    ],
  },
  {
    type: 'list',
    ordered: false,
    items: [
      [
        {
          t: 'Content Accessibility',
          b: 1,
        },
        {
          t: ': The quality of alternative text for product images is currently inconsistent, and synchronized captions and descriptive transcripts are not available for some videos. A limited number of navigation icons lack alt attributes maybe incomplete supported by screen readers .',
        },
      ],
      [
        {
          t: 'Third-Party Integrations:',
          b: 1,
        },
        {
          t: ' A limited number of embedded modules gateways such as feedback entrance and online service are not yet fully compatible with keyboard-only navigation.',
        },
      ],
      [
        {
          t: 'Non-Transactional Pages',
          b: 1,
        },
        {
          t: ': Certain low-frequency, non-transactional pages (e.g., network error prompts, loyalty points, browsing history, favorites, auctions, and temporary marketing campaigns) may have incomplete support for screen reader announcements, keyboard focus management, or color contrast.',
        },
      ],
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'This list will be updated regularly as progress is made. If users encounter any of the above issues, they can obtain assistance via email Joybuyfumi@gmail.com or online customer service.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'We are committed to addressing these limitations and have included them in our accessibility improvement roadmap. We aim to resolve identified issues on a prioritized basis and will update this statement as improvements are made.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '5. E-Commerce Accessibility',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'As an online marketplace, we recognize the importance of ensuring that all critical transactional user flows are accessible. We are committed to the following:',
      },
    ],
  },
  {
    type: 'list',
    ordered: false,
    items: [
      [
        {
          t: 'Checkout, login/authentication, and payment flows are designed to be perceivable, operable, understandable, and robust. Identification methods, electronic signatures, and payment services are implemented in a manner that supports assistive technologies, ensures clear error messaging, and provides sufficient time for users to complete transactions.',
        },
      ],
      [
        {
          t: 'Where sellers or vendors on our marketplace provide accessibility information about their products or services, we surface this information to users in an accessible manner, in accordance with applicable requirements.',
        },
      ],
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '6. Feedback Mechanism',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'We recognize that accessibility improvement is an ongoing process. If you encounter any accessibility issues or have suggestions for improvement while using our website, please feel free to contact us through the following channels:',
      },
    ],
  },
  {
    type: 'list',
    ordered: false,
    items: [
      [
        {
          t: 'Email: Joybuyfumi@gmail.com',
        },
      ],
      [
        {
          t: 'Online Customer Service: Available 24/7 for instant assistance. You can start a chat instantly by clicking the "Customer Service" floating icon on our website. Callback Service: To get help faster, you can request a callback, please go to Me → Customer Service → Request a Callback in the Joybuy App.',
        },
      ],
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Upon receiving your feedback, we will:',
      },
    ],
  },
  {
    type: 'list',
    ordered: false,
    items: [
      [
        {
          t: 'Immediately investigate and analyze the issue you have encountered. We will strive to provide you with an initial response within 15 working days, informing you of the progress of the issue and the estimated time for resolution.',
        },
      ],
      [
        {
          t: 'If the issue is complex and requires a longer time to resolve, we will regularly update you on the progress. During this period, we will also offer temporary solutions or alternative options to minimize the impact on you.',
        },
      ],
      [
        {
          t: 'After resolving the issue, we will conduct comprehensive testing and verification of the website to ensure that similar issues do not recur. We will also document the solutions and improvement measures for future reference in website updates and maintenance, to continually enhance the accessibility performance of our site.',
        },
      ],
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '7. Continuous Improvement',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'We are well aware that building an accessible website is a long-term and challenging task that requires continuous learning, improvement, and innovation. Therefore, we will:',
      },
    ],
  },
  {
    type: 'list',
    ordered: false,
    items: [
      [
        {
          t: 'Regularly organize internal training sessions to enhance team members’ understanding and skills in accessible design. This ensures that accessibility is always considered a key factor during website development and maintenance, guaranteeing the quality and sustainability of our accessible services from the outset.',
        },
      ],
      [
        {
          t: 'Closely follow the development of accessibility technologies and industry best practices. We will actively explore and adopt new technologies and methods to further improve the accessibility performance and user experience of our website, enabling it to better adapt to evolving user needs and technological environments.',
        },
      ],
      [
        {
          t: 'Conduct a comprehensive accessibility review and evaluation of our website on an annual] basis. Based on the findings, we will develop detailed improvement plans and integrate accessibility enhancement work into the daily development and maintenance processes of our website. This ensures the continuous optimization and improvement of our accessibility services, allowing all users to enjoy a higher quality, more convenient, and fully accessible digital experience.',
        },
      ],
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Thank you for your attention to and support of our website. We will continue to strive for the construction of a more inclusive and accessible digital world!',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '8. Reference in Terms and Conditions',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'This accessibility statement is referenced in, and forms part of, JD’s general terms and conditions of service. Users are encouraged to review the terms and conditions for further information on how accessibility is integrated into our service delivery.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '9. Joybuy Accessibility Conformance VPAT Report',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'iOS Version: ',
      },
      {
        t: 'https://www.joyfumi.com/help/AccessibilityConformanceReport-IOS',
        href: 'https://www.joyfumi.com/help/AccessibilityConformanceReport-IOS',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Android Version: ',
      },
      {
        t: 'https://www.joyfumi.com/help/AccessibilityConformanceReport-Android',
        href: 'https://www.joyfumi.com/help/AccessibilityConformanceReport-Android',
      },
    ],
  },
]

const zh = [
  {
    type: 'p',
    segments: [
      {
        t: '1.无障碍声明',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '我方充分认识到网站无障碍的重要性，并致力于确保所有用户，无论其能力如何，都能平等地获取和利用我方网站所提供的信息与服务。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '本无障碍声明适用于京东运营的、可通过 Joybuy 网站及移动应用程序访问的在线市场。通过我方平台，用户可以浏览、搜索、注册与购买，以及管理其订单、追踪配送状态并获取客户支持。我方服务旨在通过桌面及移动网站以及原生应用程序实现无障碍访问，以满足广泛的用户需求。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '2.我方承诺',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '我方承诺遵循《欧盟无障碍法案》所确立的网络无障碍四大核心原则：',
      },
      {
        t: '可感知性',
        b: 1,
      },
      {
        t: '（信息和用户界面组件必须以用户能够感知的方式呈现）、',
      },
      {
        t: '可操作性',
        b: 1,
      },
      {
        t: '（用户界面组件和导航必须可操作）、',
      },
      {
        t: '可理解性',
        b: 1,
      },
      {
        t: '（信息及用户界面的操作必须易于理解）以及',
      },
      {
        t: '稳健性',
        b: 1,
      },
      {
        t: '（内容必须足够稳健，以便能够被包括辅助技术在内的各种用户代理可靠地解释）。我方致力于遵循 POUR 无障碍设计原则。',
      },
    ],
  },
  {
    type: 'list',
    ordered: false,
    items: [
      [
        {
          t: '为确保其',
        },
        {
          t: '可感知性',
          b: 1,
        },
        {
          t: '，我方内容可被各类辅助技术（如屏幕阅读器、屏幕放大器、语音识别软件）有效识别和处理，从而为依赖这些工具的用户提供更好的支持。我方在前景内容（如文本）与背景颜色之间保持足够的对比度。这确保了有视觉障碍（如视力不佳或色盲）的用户能够清晰地阅读和区分内容，避免因颜色对比度不足造成的困难。对于视频和音频等多媒体内容，我方提供文字记录及其他替代内容。这确保了听力受损的用户能够获取多媒体中的关键信息，使其在不错过重要更新的情况下保持信息畅通。',
        },
      ],
      [
        {
          t: '为确保其',
        },
        {
          t: '可操作性',
          b: 1,
        },
        {
          t: '，我方网站的所有功能均可使用键盘操作，无需鼠标或其他指点设备。这使得有运动障碍的用户能够通过键盘快捷键及其他键盘操作，更便捷地导航和高效使用网站功能。',
        },
      ],
      [
        {
          t: '为确保其',
        },
        {
          t: '可理解性',
          b: 1,
        },
        {
          t: '，我方为图像和图表等非文本内容提供文本替代方案，确保视障用户能够理解所传达的信息。这保证了依赖基于文本信息的用户不会遗漏任何信息。',
        },
      ],
      [
        {
          t: '为确保其',
        },
        {
          t: '稳健性',
          b: 1,
        },
        {
          t: '，我方网页采用语义化 HTML 标签构建，兼容主流屏幕阅读器。这形成了清晰的页面结构和逻辑组织，不仅有利于辅助技术和搜索引擎解析，也有利于网站的长期维护与优化。它提升了网站的整体无障碍性和可维护性。',
        },
      ],
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '3.当前状态',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '我方网站目前：',
      },
    ],
  },
  {
    type: 'list',
    ordered: false,
    items: [
      [
        {
          t: '我们已努力遵循 WCAG 2.2 AA 级别标准，并遵守 EN 301 549 关于网络无障碍标准的规定。这涉及优化页面结构、内容呈现和交互操作，以满足大多数用户的基本无障碍需求。',
        },
      ],
      [
        {
          t: '我们已通过内部测试和外部评审进行了全面的无障碍评估。我们的测试方法结合了自动化扫描与使用 Accessibility Insights、屏幕阅读器（VoiceOver、NVDA）、键盘导航和对比度分析器进行的人工检查。此外，动态内容、表单和用户流程均已根据适用标准进行了彻底的人工验证。通过此过程，我们识别并解决了多个无障碍问题，显著提升了网站的整体无障碍性和可用性。',
        },
      ],
      [
        {
          t: '采用响应式设计以适应不同设备和屏幕尺寸，包括台式电脑、笔记本电脑、平板电脑和智能手机。这为移动用户提供了卓越的浏览体验，并确保了无障碍服务在不同终端的一致性与连贯性。',
        },
      ],
      [
        {
          t: '正在整合某些无障碍功能。例如，字体大小调整功能（PC ≥ 16px，移动端：≥ 14px）和高对比度模式（4.5:1）切换正在实施中。这些功能为用户提供了更便捷的个性化选项，使其能够根据个人需求调整浏览环境。',
        },
      ],
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '4.局限性与改进领域',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '尽管我们努力确保平台全面的无障碍性，但我们承认某些领域可能尚未完全符合 WCAG 2.2 AA 或 EN 301 549 标准。我们正在积极处理以下已知局限性：',
      },
    ],
  },
  {
    type: 'list',
    ordered: false,
    items: [
      [
        {
          t: '内容无障碍性',
          b: 1,
        },
        {
          t: '：产品图像的替代文本质量目前尚不一致，部分视频缺少同步字幕和描述性文字记录。少量导航图标缺少 alt 属性，可能无法被屏幕阅读器完全支持。',
        },
      ],
      [
        {
          t: '第三方集成',
          b: 1,
        },
        {
          t: '：少量嵌入式模块入口（如反馈入口和在线客服）尚未完全兼容纯键盘导航。',
        },
      ],
      [
        {
          t: '非交易页面',
          b: 1,
        },
        {
          t: '：某些低频非交易页面（例如，网络错误提示、忠诚度积分、浏览历史、收藏夹、拍卖和临时营销活动）可能对屏幕阅读器播报、键盘焦点管理或颜色对比度的支持不完整。',
        },
      ],
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '此列表将随着进展定期更新。若用户遇到上述任何问题，可通过电子邮件 ',
      },
      {
        t: 'Joybuyfumi@gmail.com',
        href: 'mailto:Joybuyfumi@gmail.com',
      },
      {
        t: ' 或在线客服获取协助。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '我们承诺解决这些局限性，并已将其纳入我们的无障碍改进路线图。我们旨在按优先级解决已识别的问题，并将在改进后更新本声明。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '5.电子商务无障碍性',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '作为在线市场，我们认识到确保所有关键交易用户流程无障碍的重要性。我们承诺如下：',
      },
    ],
  },
  {
    type: 'list',
    ordered: false,
    items: [
      [
        {
          t: '结账、登录/认证和支付流程均设计为可感知、可操作、可理解且稳健的。身份验证方法、电子签名和支付服务的实施方式支持辅助技术、确保清晰的错误信息提示，并为用户提供充足的时间来完成交易。',
        },
      ],
      [
        {
          t: '若我方市场上的卖家或供应商提供了关于其产品或服务的无障碍信息，我们将根据适用要求，以无障碍方式向用户展示该信息。',
        },
      ],
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '6.反馈机制',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '我们认识到无障碍改进是一个持续的过程。如果您在使用我方网站时遇到任何无障碍问题或有改进建议，请随时通过以下渠道联系我们：',
      },
    ],
  },
  {
    type: 'list',
    ordered: false,
    items: [
      [
        {
          t: '电子邮件',
          b: 1,
        },
        {
          t: '：',
        },
        {
          t: 'Joybuyfumi@gmail.com',
          href: 'mailto:Joybuyfumi@gmail.com',
        },
      ],
      [
        {
          t: '在线客服',
          b: 1,
        },
        {
          t: '：提供 7x24 小时即时协助。您可通过点击我方网站上的“客服”浮动图标立即开始聊天。',
        },
      ],
      [
        {
          t: '回拨服务',
          b: 1,
        },
        {
          t: '：为更快获得帮助，您可以请求回拨，请在 Joybuy App 中前往“我的” → “客户服务” → “请求回拨”。',
        },
      ],
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '收到您的反馈后，我们将：',
      },
    ],
  },
  {
    type: 'list',
    ordered: false,
    items: [
      [
        {
          t: '立即调查分析您遇到的问题。我们将努力在 ',
        },
        {
          t: '15 个工作日',
          b: 1,
        },
        {
          t: '内向您提供初步回复，告知您问题的进展情况及预计解决时间。',
        },
      ],
      [
        {
          t: '若问题复杂，需要更长时间解决，我们将定期向您更新进展。在此期间，我们也将提供临时解决方案或替代选项，以尽量减少对您的影响。',
        },
      ],
      [
        {
          t: '问题解决后，我们将对网站进行全面测试和验证，确保类似问题不再发生。我们还将记录解决方案和改进措施，以供未来网站更新和维护时参考，持续提升我方网站的无障碍性能。',
        },
      ],
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '7.持续改进',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '我们深知，构建无障碍网站是一项长期且具有挑战性的任务，需要持续学习、改进和创新。因此，我们将：',
      },
    ],
  },
  {
    type: 'list',
    ordered: false,
    items: [
      [
        {
          t: '定期组织内部培训，提升团队成员对无障碍设计的理解和技能。这确保在网站开发和维护过程中，无障碍性始终被视为关键因素，从一开始就保障我方无障碍服务的质量和可持续性。',
        },
      ],
      [
        {
          t: '密切关注无障碍技术的发展和行业最佳实践。我们将积极探索并采用新技术和新方法，以进一步提升我方网站的无障碍性能和用户体验，使其更好地适应不断变化的用户需求和技术环境。',
        },
      ],
      [
        {
          t: '每年对我方网站进行一次全面的无障碍审查与评估。基于评估结果，我们将制定详细的改进计划，并将无障碍增强工作融入网站的日常开发和维护流程。这确保了我方无障碍服务的持续优化与改进，让所有用户都能享受更高质量、更便捷、更充分无障碍的数字体验。',
        },
      ],
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '感谢您对我方网站的关注与支持。我们将继续为建设一个更具包容性和无障碍性的数字世界而努力！',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '8.服务条款中的引用',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '本无障碍声明在京东的一般服务条款中被引用，并构成其一部分。建议用户查阅服务条款，以进一步了解无障碍性如何融入我方服务交付。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '9. Joybuy 无障碍VPAT合规报告',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'iOS 版本请参考:',
      },
      {
        t: 'https://www.joyfumi.com/help/AccessibilityConformanceReport-IOS',
        href: 'https://www.joyfumi.com/help/AccessibilityConformanceReport-IOS',
      },
      {
        br: 1,
      },
      {
        t: 'Android 版本请参考:',
      },
      {
        t: 'https://www.joyfumi.com/help/AccessibilityConformanceReport-Android',
        href: 'https://www.joyfumi.com/help/AccessibilityConformanceReport-Android',
      },
    ],
  },
]

export const accessibilityStatementPage = {
  slug: 'accessibility-statement',
  title: { en: 'Accessibility Statement', zh: '无障碍声明' },
  hasArchive: false,
  blocks: { en, zh },
}
