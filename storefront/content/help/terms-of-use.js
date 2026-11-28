// 批次 Q（需求 15.1 / 15.2）：真站 help 中心「Terms of Use」页正文。
// 来源：2026-11-20 Playwright 实测真站对应 help 页（批次 Q 抓取，原始数据见 var/policy_help_20261120/）。
// 批次 S 追加（用户 2026-11-20 口径）：正文中所有真站网址 → www.joyfumi.com（保留路径结构）；
// 公司名 / 地址 / 注册号 / 监管表述与邮箱不变。
//（原始抓取 var/policy_help_20261120/content_{en_GB,zh_CN}_TermsofUse.json；
//  zh 为真站自带中文版，非机器翻译）。
// 口径：除邮箱 → Joybuyfumi@gmail.com 外，全文照抄真站（公司名 / 地址 / 注册号 /
// 监管表述 / 章节 / 表格 / 生效日期均保持原文）。块结构：p{segments} + table{rows}；
// segments 内 t=文本、b=粗体、i=斜体、href=链接、br=换行（真站正文用 <br> 分行）。
const en = [
  {
    type: 'p',
    segments: [
      {
        t: 'Joybuy Terms of Use',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'These terms (‘Terms of Use’) set out the terms on which you may make use of ',
      },
      {
        t: 'www.joyfumi.com',
        href: 'https://www.joyfumi.com',
      },
      {
        t: ' and our mobile applications (together the ‘Joybuy Site’). This includes whether you are accessing the Joybuy Site as a guest or logged in to your registered Joybuy account.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Please read these Terms of Use carefully before you access the Joybuy Site. By accessing the Joybuy Site you indicate that you accept these Terms of Use. Please do not continue to access our Joybuy Site if you do not agree to these Terms of Use.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'We reserve the right to change these Terms of Use from time to time.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'These Terms of Use were last updated on 20 February 2026.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'About us',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'We are Jingdong Retail (UK) Limited trading as ‘Joybuy’ a company registered in England and Wales under company number 15830555. Our registered office address is at Floor 3, 20 King Street, London SW1Y 6QY. Our VAT number is 481236788.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'If you need to contact us in relation to these Terms of Use you can contact us by:',
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
        t: 'Access to the Joybuy site',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'We reserve the right to withdraw or amend access to the Joybuy Site without notice. We will not be liable if, for any reason, the Joybuy Site is unavailable at any time.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'You must be over 18 years old to access the Joybuy Site.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'You are responsible for obtaining and maintaining any equipment needed to access or connect to the Joybuy Site. This includes hardware, software and internet connections and our mobile applications may require minimum operating system requirements.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'You may only use the Joybuy Site for lawful purposes and in a lawful manner. You agree to comply with all applicable laws and regulations when accessing and using the Joybuy Site.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Your personal information',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Any personal information or data that is submitted to us via your use of the Joybuy Site is governed by our ',
      },
      {
        t: 'Privacy Policy',
        href: '/pages/privacy-policy',
      },
      {
        t: ' and ',
      },
      {
        t: 'Cookie Policy',
        href: '/pages/cookie-policy',
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
        t: 'Intellectual property rights',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'The content on the Joybuy Site is protected by copyright, trademarks, database, and other intellectual property rights. We are the owner or licensee of all intellectual property rights on the Joybuy Site. You must not infringe our intellectual property rights or those of any third party when using the Joybuy Site.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'You may not copy, reproduce, modify, distribute, or use any content on the Joybuy Site except for your personal non-commercial use.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'No licence is granted to you to use any trademark of Jingdong Retail (UK) Limited, or any of our affiliated companies including but not limited to the trademarks Joybuy, JoyExpress or JD.com.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Automated access and data scaping',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'You may not use any automated system, software, robot, spider, crawler, scraper, or other automated means to access, extract, copy, monitor, or collect any part of the Joybuy Site or its contents without our prior written consent.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'You must not harvest or collect information about users, products, pricing, or other data for commercial purposes.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'This clause does not prevent the lawful use of publicly available information where permitted by applicable law, nor does it restrict any statutory rights you may have under consumer law.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Links from the Joybuy site',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'The Joybuy Site may contain links to third party websites. We have no control and are not responsible in any way for any content outside of the Joybuy Site. They are provided for information purposes only.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Content you may upload to the Joybuy site',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'You may upload content to our Joybuy Site to provide reviews on products you have purchased or in relation to our services. However, we retain the right to remove content from the Joybuy Site for any reasonable reason.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'You agree any content you upload will not:',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '· breach any applicable laws and regulations;',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '· infringe any intellectual property rights such as copyright or database rights of any other person;',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '· be defamatory, hateful, inflammatory, discriminatory, contain violent or sexual material or content, cause upset, alarm, or harassment to any other person;',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '· breach any duty of confidentiality;',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '· impersonate any brands or other users; or',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '· contain any unverified or false claims about products.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'If you post reviews in relation to products or make comments on the Joybuy Site, you grant us a royalty-free worldwide licence to use, reproduce, publish, make available, and modify such content. If you delete the content from the Joybuy Site, you withdraw your licence for us to publish and make use of the content publicly.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Suspension and termination',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Should you fail to comply with these Terms of Use we may:',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '· remove any content you have uploaded to the Joybuy Site;',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '· withdraw or terminate your customer account, or your access the Joybuy Site;',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '· take legal action against you for any costs or losses we suffer resulting from the breach; or',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '· disclose information about your actions to any legal or regulatory authorities.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Our liability',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'We make reasonable efforts to update information and content on our Joybuy Site. However, we make no representations, warranties or guarantees, whether express or implied that the content on the Joybuy Site is accurate or up to date.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'We make no warranties of any kind, whether express or implied in relation to Joybuy Site, or any transaction that may be conducted on the Joybuy Site including but not limited to implied warranties of security, accuracy, compatibility, non-infringement, and completeness.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'If we are informed of any inaccuracies on the Joybuy Site we will correct this as soon as we reasonably can.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'To the fullest extent permitted by law, we exclude all liability (whether arising in contract, negligence or otherwise) for any loss or damage which you or any third-party may incur in connection with our Joybuy Site, or our services.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'This does affect our liability for any liability which cannot be excluded or limited by law.',
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
        t: 'These Terms of Use shall be governed by and construed in accordance with English law, and any disputes will be decided by the English Courts.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'If a court decides that some of these terms in the Terms of Sale are unlawful, then the rest will continue to apply.',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'If you breach these Terms of Use and we do not take action in relation to your breach, we will still be entitled to enforce our rights at a later date, or for any other breach by you of these Terms of Use.',
      },
    ],
  },
]

const zh = [
  {
    type: 'p',
    segments: [
      {
        t: 'Joybuy 使用条款',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '这些条款（“使用条款”）规定了您使用',
      },
      {
        t: 'www.joyfumi.com',
        href: 'https://www.joyfumi.com',
      },
      {
        t: '和我们的移动应用程序（统称“Joybuy 网站”）的条款。这包括您是以访客身份访问 Joybuy 网站，还是登录到您注册的 Joybuy 帐户。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '请在访问 Joybuy 网站前仔细阅读这些使用条款。访问 Joybuy 网站即表示您接受这些使用条款。如果您不同意这些使用条款，请勿继续访问 Joybuy 网站。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '我们保留随时更改这些使用条款的权利。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '这些使用条款最后更新于 2026 年 2 月 20 日。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '关于我们',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '我们是京东零售（英国）有限公司，以“Joybuy”品牌进行交易，是一家在英格兰和威尔士注册的公司，公司编号为15830555。我们的注册办公地址是：伦敦SW1Y 6QY国王街20号3楼。我们的增值税号是481236788。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '如果您需要就这些条款与我们联系， 您可以通过以下方式联系我们：',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '· 电子邮件 - ',
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
        t: '· 在线聊天 - 使用Joybuy 网站上提供的客户服务聊天功能。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '访问 Joybuy 网站',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '我们保留随时撤销或修改Joybuy网站访问权限的权利，恕不另行通知。如果Joybuy网站因任何原因在任何时间无法访问，我们概不负责。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '您必须年满 18 岁才能访问 Joybuy 网站。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '您需自行负责获取并维护访问或连接 Joybuy 网站所需的任何设备，包括硬件、软件和互联网连接。我们的移动应用程序可能对操作系统有最低要求。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '您仅可出于合法目的并以合法方式使用 Joybuy 网站。您同意在访问和使用 Joybuy 网站时遵守所有适用的法律法规。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '您的个人信息',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '您通过使用 Joybuy 网站向我们提交的任何个人信息或数据均受我们的',
      },
      {
        t: '隐私政策',
        href: '/pages/privacy-policy',
      },
      {
        t: '和',
      },
      {
        t: 'Cookie 政策的约束',
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
        t: '知识产权',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Joybuy网站上的内容受版权、商标、数据库和其他知识产权保护。我们是Joybuy网站所有知识产权的所有者或被许可人。您在使用Joybuy网站时，不得侵犯我们的知识产权或任何第三方的知识产权。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '除个人非商业用途外，您不得复制、转载、修改、分发或使用 Joybuy 网站上的任何内容。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '您无权使用京东零售（英国）有限公司或我们任何关联公司的任何商标，包括但不限于 Joybuy、 JoyExpress或 JD.com 商标。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '自动化访问和数据景观',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '您不得使用任何自动化系统、软件、机器人、蜘蛛、爬虫、抓取器或其他自动化手段访问、提取、复制、监控或收集 Joybuy 网站或其内容的任何部分。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '您不得出于商业目的收集或获取有关用户、产品、定价或其他数据的信息。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '情况下合法使用公开信息，也不限制您根据消费者法可能享有的任何法定权利。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Joybuy 网站上的链接',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: 'Joybuy网站可能包含指向第三方网站的链接。我们对Joybuy网站以外的任何内容均不拥有控制权，也不承担任何责任。这些链接仅供参考。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '您可以上传到 Joybuy 网站的内容',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '您可以将内容上传至 Joybuy 网站，对您购买的产品或我们的服务进行评价。但是，我们保留因任何合理原因从 Joybuy 网站删除内容的权利。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '您同意您上传的任何内容不会：',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '· 违反任何适用的法律法规；',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '· 侵犯任何其他人的知识产权，例如版权或数据库权利；',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '· 不得包含诽谤、仇恨、煽动性、歧视性内容，不得包含暴力或色情材料或内容，不得引起他人不安、惊恐或骚扰；',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '· 违反任何保密义务；',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '· 冒充任何品牌或其他用户；或',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '· 不得包含任何未经证实或虚假的产品声明。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '如果您在 Joybuy 网站上发布产品评论或发表评论，即表示您授予我们一项免版税的全球许可，允许我们使用、复制、发布、提供和修改此类内容。如果您从 Joybuy 网站删除该内容，则表示您撤销了授予我们公开发布和使用该内容的许可。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '暂停和终止',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '如果您未能遵守这些使用条款，我们可能会：',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '· 删除您上传到 Joybuy网站的所有内容；',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '· 撤销或终止您的客户帐户，或您对 Joybuy网站的访问权限；',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '· 我们将就因您违约而给我们造成的任何损失或费用向您提起法律诉讼；或者',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '· 向任何法律或监管机构披露您的行为信息。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '我们的责任',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '我们会尽合理努力更新 Joybuy 网站上的信息和内容。但是，我们不作任何明示或暗示的陈述、保证或担保，保证 Joybuy 网站上的内容准确或最新。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '我们对 Joybuy 网站或在 Joybuy 网站上进行的任何交易，不作任何明示或暗示的保证，包括但不限于安全性、准确性、兼容性、不侵权和完整性的暗示保证。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '如果我们发现 Joybuy网站上有任何不准确之处，我们将尽快予以纠正。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '在法律允许的最大范围内，我们对您或任何第三方因使用我们的 Joybuy 网站或我们的服务而遭受的任何损失或损害（无论是因合同、疏忽或其他原因引起的）不承担任何责任。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '这确实会影响我们对任何依法不得排除或限制的责任所承担的责任。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '其他信息',
        b: 1,
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '本使用条款应受英国法律管辖并按其解释，任何争议均应由英国法院裁决。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '如果法院裁定销售条款中的某些条款违法，则其余条款将继续有效。',
      },
    ],
  },
  {
    type: 'p',
    segments: [
      {
        t: '如果您违反本使用条款，而我们没有就您的违约行为采取行动，我们仍有权在日后或针对您违反本使用条款的任何其他行为行使我们的权利。',
      },
    ],
  },
]

import { jaTitle as jaPageTitle, jaBlocks as jaPageBlocks } from './terms-of-use.ja.js'
export const termsOfUsePage = {
  slug: 'terms-of-use',
  title: { en: 'Terms of Use', zh: 'Joybuy 使用条款' },
  hasArchive: false,
  blocks: { en, zh },
  jaTitle: jaPageTitle,
  jaBlocks: jaPageBlocks,
}
